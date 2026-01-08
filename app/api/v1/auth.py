# -*- coding: utf-8 -*-
"""
Auth API Endpoints
- Login (Brute Force koruması ile)
- Refresh Token
- Logout (Token blacklist ile)
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    verify_password, 
    create_tokens, 
    verify_token,
    get_password_hash,
    decode_token
)
from app.core.redis_service import brute_force_protection, token_blacklist
from app.models import User, Company, UserRole
from app.schemas import (
    LoginRequest, 
    TokenResponse, 
    RefreshTokenRequest,
    UserMeResponse
)
from app.api.deps import get_current_user, get_client_ip

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Kullanıcı girişi
    
    Güvenlik Özellikleri:
    - Brute force koruması (IP ve email bazlı)
    - Hesap kilitleme (5 başarısız deneme sonrası 15 dakika)
    - Güvenlik loglama
    """
    client_ip = get_client_ip(request)
    email = login_request.email
    
    # 1. Brute force kontrolü - IP ve email engellenmiş mi? (Redis)
    is_blocked, block_message = await brute_force_protection.is_blocked(client_ip, email)
    if is_blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=block_message
        )
    
    # 2. Kullanıcıyı bul
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        # Başarısız denemeyi kaydet (kullanıcı yok)
        await brute_force_protection.record_attempt(client_ip, email, success=False)
        remaining = await brute_force_protection.get_remaining_attempts(client_ip, email)
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"E-posta veya şifre hatalı. Kalan deneme: {remaining}"
        )
    
    # 3. Şifreyi kontrol et
    if not verify_password(login_request.password, user.password_hash):
        # Başarısız denemeyi kaydet
        await brute_force_protection.record_attempt(client_ip, email, success=False)
        remaining = await brute_force_protection.get_remaining_attempts(client_ip, email)
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"E-posta veya şifre hatalı. Kalan deneme: {remaining}"
        )
    
    # 4. Aktiflik kontrolü
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kullanıcı hesabı devre dışı"
        )
    
    # 5. Başarılı giriş - sayaçları sıfırla (Redis)
    await brute_force_protection.record_attempt(client_ip, email, success=True)
    
    # 6. Token oluştur
    tokens = create_tokens(user.id, user.email, user.role.value)
    
    # 7. Refresh token'ı kaydet
    user.refresh_token = tokens.refresh_token
    user.last_login = datetime.utcnow()
    await db.commit()
    
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Access token yenile
    
    Güvenlik Özellikleri:
    - Token blacklist kontrolü (Redis)
    - Refresh token rotation
    """
    # Blacklist kontrolü (Redis)
    if await token_blacklist.is_blacklisted(request.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token geçersiz kılınmış"
        )
    
    # Refresh token'ı doğrula
    token_data = verify_token(request.refresh_token, "refresh")
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz refresh token"
        )
    
    # Kullanıcıyı bul
    result = await db.execute(
        select(User).where(User.id == token_data.user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı bulunamadı"
        )
    
    # Kayıtlı refresh token ile karşılaştır
    if user.refresh_token != request.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token geçersiz"
        )
    
    # Eski token'ı blacklist'e ekle (Redis)
    decoded = decode_token(request.refresh_token)
    if decoded and "exp" in decoded:
        await token_blacklist.add(
            request.refresh_token, 
            datetime.fromtimestamp(decoded["exp"])
        )
    
    # Yeni token oluştur (Token Rotation)
    tokens = create_tokens(user.id, user.email, user.role.value)
    
    # Yeni refresh token'ı kaydet
    user.refresh_token = tokens.refresh_token
    await db.commit()
    
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Çıkış yap
    
    Güvenlik Özellikleri:
    - Refresh token'ı geçersiz kılar
    - Token'ı blacklist'e ekler (Redis)
    """
    # Authorization header'dan token'ı al
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
        # Access token'ı blacklist'e ekle (Redis)
        decoded = decode_token(access_token)
        if decoded and "exp" in decoded:
            await token_blacklist.add(
                access_token,
                datetime.fromtimestamp(decoded["exp"])
            )
    
    # Refresh token'ı da blacklist'e ekle (Redis)
    if current_user.refresh_token:
        decoded = decode_token(current_user.refresh_token)
        if decoded and "exp" in decoded:
            await token_blacklist.add(
                current_user.refresh_token,
                datetime.fromtimestamp(decoded["exp"])
            )
    
    # Refresh token'ı veritabanından sil
    current_user.refresh_token = None
    await db.commit()
    
    return {"message": "Başarıyla çıkış yapıldı"}


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mevcut kullanıcı bilgilerini al"""
    # Şirket adını al
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    return UserMeResponse(
        id=current_user.id,
        company_id=current_user.company_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        last_login=current_user.last_login,
        created_at=current_user.created_at,
        company_name=company.name if company else None
    )



