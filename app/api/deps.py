# -*- coding: utf-8 -*-
"""
API Dependencies
- Auth dependencies (Token blacklist kontrolü dahil)
- Database session
- Rate limiting
- IDOR koruması
"""

from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import verify_token, TokenData
from app.core.redis_service import token_blacklist
from app.models import User, UserRole

# JWT Bearer token
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Mevcut kullanıcıyı al
    
    Güvenlik:
    - Token doğrulama
    - Token blacklist kontrolü (Redis)
    - Kullanıcı aktiflik kontrolü
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulanamadı",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    
    # 1. Token blacklist kontrolü (Redis)
    if await token_blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum sonlandırılmış. Lütfen tekrar giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Token doğrulama
    token_data = verify_token(token, "access")
    
    if token_data is None:
        raise credentials_exception
    
    # 3. Kullanıcıyı veritabanından al
    result = await db.execute(
        select(User).where(User.id == token_data.user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    # 4. Aktiflik kontrolü
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kullanıcı hesabı devre dışı"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Aktif kullanıcıyı al"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kullanıcı hesabı devre dışı"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Admin kullanıcıyı al"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için admin yetkisi gerekli"
        )
    return current_user


def get_client_ip(request: Request) -> str:
    """İstemci IP adresini al (Proxy-aware)"""
    # Proxy arkasındaysa X-Forwarded-For header'ını kontrol et
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # İlk IP gerçek istemci IP'si
        return forwarded.split(",")[0].strip()
    
    # X-Real-IP de kontrol et (bazı proxy'ler bunu kullanır)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Doğrudan bağlantı
    if request.client:
        return request.client.host
    
    return "unknown"


def get_user_agent(request: Request) -> str:
    """User agent bilgisini al"""
    return request.headers.get("User-Agent", "unknown")


# ==================== IDOR KORUMASI ====================

async def verify_resource_ownership(
    db: AsyncSession,
    model,
    resource_id: int,
    company_id: int,
    resource_name: str = "Kaynak"
):
    """
    Kaynak sahipliğini doğrula (IDOR koruması)
    
    Bu fonksiyon, bir kaynağın (bordro, çalışan vb.) istenen şirkete
    ait olduğunu doğrular.
    
    Args:
        db: Database session
        model: SQLAlchemy model (Payslip, Employee vb.)
        resource_id: Kaynağın ID'si
        company_id: Kullanıcının company_id'si
        resource_name: Hata mesajında kullanılacak kaynak adı
    
    Returns:
        Kaynak objesi
    
    Raises:
        HTTPException 404: Kaynak bulunamadı veya erişim yok
    """
    result = await db.execute(
        select(model).where(
            model.id == resource_id,
            model.company_id == company_id
        )
    )
    resource = result.scalar_one_or_none()
    
    if resource is None:
        # Güvenlik: Kaynak var mı yok mu bilgisi verme
        # Her iki durumda da aynı hata mesajı
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_name} bulunamadı"
        )
    
    return resource


async def verify_bulk_resource_ownership(
    db: AsyncSession,
    model,
    resource_ids: list,
    company_id: int,
    resource_name: str = "Kaynak"
) -> list:
    """
    Toplu kaynak sahipliğini doğrula (IDOR koruması)
    
    Args:
        db: Database session
        model: SQLAlchemy model
        resource_ids: Kaynak ID listesi
        company_id: Kullanıcının company_id'si
        resource_name: Hata mesajında kullanılacak kaynak adı
    
    Returns:
        Kaynak objesi listesi (sadece erişim yetkisi olanlar)
    """
    if not resource_ids:
        return []
    
    result = await db.execute(
        select(model).where(
            model.id.in_(resource_ids),
            model.company_id == company_id
        )
    )
    resources = result.scalars().all()
    
    # İstenen ID sayısı ile dönen kaynak sayısı farklıysa
    # bazı kaynaklara erişim yok demektir
    if len(resources) != len(resource_ids):
        import logging
        security_logger = logging.getLogger("security")
        security_logger.warning(
            f"IDOR_ATTEMPT | Requested: {len(resource_ids)} | "
            f"Accessible: {len(resources)} | Company: {company_id}"
        )
    
    return list(resources)



