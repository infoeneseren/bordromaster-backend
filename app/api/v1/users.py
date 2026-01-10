# -*- coding: utf-8 -*-
"""
User API Endpoints
- User CRUD (admin only)
- Password change
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_password_hash, verify_password
from app.core.password_policy import password_policy
from app.models import User, UserRole, AuditAction
from app.schemas import (
    UserCreate,
    UserUpdate,
    UserPasswordUpdate,
    UserResponse
)
from app.api.deps import get_current_user, get_current_admin_user, get_client_ip, get_user_agent
from app.services.audit_service import audit_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Kullanıcıları listele (admin only)"""
    result = await db.execute(
        select(User)
        .where(User.company_id == current_user.company_id)
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    
    return [UserResponse.model_validate(user) for user in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Yeni kullanıcı oluştur (admin only)"""
    # Email kontrolü
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kullanımda"
        )
    
    # Kullanıcı oluştur
    new_user = User(
        company_id=current_user.company_id,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True,
        is_verified=True  # Admin tarafından oluşturulduğu için doğrulanmış
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return UserResponse.model_validate(new_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Kullanıcı detayı (admin only)"""
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı"
        )
    
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Kullanıcı güncelle (admin only)"""
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı"
        )
    
    # Kendini devre dışı bırakmasını engelle
    if user.id == current_user.id and user_data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kendinizi devre dışı bırakamazsınız"
        )
    
    # Email değişikliği kontrolü
    if user_data.email and user_data.email != user.email:
        result = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu e-posta adresi zaten kullanımda"
            )
    
    # Güncelle
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Kullanıcı sil (admin only)"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kendinizi silemezsiniz"
        )
    
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı"
        )
    
    await db.delete(user)
    await db.commit()
    
    return {"message": "Kullanıcı silindi"}


@router.post("/change-password")
async def change_password(
    password_data: UserPasswordUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Şifre değiştir
    
    Güvenlik Özellikleri:
    - Mevcut şifre doğrulama
    - Güçlü şifre politikası kontrolü
    - Şifre değişikliği sonrası TÜM oturumlar sonlandırılır (mevcut hariç)
    - Audit log kaydı
    """
    from app.services.session_service import session_service
    from app.core.redis_service import token_blacklist
    from app.core.security import decode_token
    
    # Mevcut şifreyi kontrol et
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mevcut şifre hatalı"
        )
    
    # Ad ve soyadı full_name'den ayıkla
    first_name = None
    last_name = None
    
    if current_user.full_name:
        name_parts = current_user.full_name.strip().split()
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = name_parts[-1]
        elif len(name_parts) == 1:
            first_name = name_parts[0]
    
    # Şifreyi kullanıcı bilgileriyle birlikte doğrula
    is_valid, errors = password_policy.validate(
        password_data.new_password,
        email=current_user.email,
        first_name=first_name,
        last_name=last_name,
        full_name=current_user.full_name
    )
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(errors)
        )
    
    # Yeni şifreyi kaydet
    current_user.password_hash = get_password_hash(password_data.new_password)
    
    # Mevcut token'ı al (bu oturumu korumak için)
    auth_header = request.headers.get("Authorization", "")
    current_token = None
    if auth_header.startswith("Bearer "):
        current_token = auth_header[7:]
    
    # ========== GÜVENLİK: TÜM DİĞER OTURUMLARI SONLANDIR ==========
    # Şifre değişikliği sonrası güvenlik için tüm oturumlar sonlandırılır
    terminated_count = await session_service.terminate_all_sessions(
        db=db,
        user_id=current_user.id,
        except_current=True,
        current_token=current_user.refresh_token  # Mevcut oturumu koru
    )
    
    # Audit log
    await audit_service.log(
        db=db,
        action=AuditAction.PASSWORD_CHANGE,
        user_id=current_user.id,
        user_email=current_user.email,
        company_id=current_user.company_id,
        resource_type="user",
        resource_id=current_user.id,
        details={
            "terminated_sessions": terminated_count,
            "reason": "password_change"
        },
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    
    await db.commit()
    
    return {
        "message": "Şifre başarıyla değiştirildi",
        "terminated_sessions": terminated_count,
        "security_note": f"Güvenliğiniz için {terminated_count} diğer oturum sonlandırıldı."
    }



