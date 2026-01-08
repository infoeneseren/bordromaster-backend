# -*- coding: utf-8 -*-
"""
Güvenlik Modülü
- JWT Token oluşturma/doğrulama
- Password hashing
- Token yönetimi
- İmzalı Download URL
"""

import hmac
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .config import settings


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData(BaseModel):
    """Token içeriği"""
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    token_type: Optional[str] = None  # "access" veya "refresh"


class Token(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Şifreyi doğrula"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Şifreyi hashle"""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Access token oluştur"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Refresh token oluştur"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_tokens(user_id: int, email: str, role: str) -> Token:
    """Access ve Refresh token oluştur"""
    token_data = {
        "sub": str(user_id),
        "email": email,
        "role": role
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )


def verify_token(token: str, token_type: str = "access") -> Optional[TokenData]:
    """Token'ı doğrula ve decode et"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # Token tipini kontrol et
        if payload.get("type") != token_type:
            return None
        
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        
        if user_id is None:
            return None
        
        return TokenData(
            user_id=int(user_id),
            email=email,
            role=role,
            token_type=token_type
        )
    except JWTError:
        return None


def decode_token(token: str) -> Optional[dict]:
    """Token'ı decode et (doğrulama olmadan)"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False}
        )
        return payload
    except JWTError:
        return None


# ==================== İMZALI DOWNLOAD URL ====================

def generate_secure_tracking_id() -> str:
    """
    Güvenli tracking ID oluştur
    - 64 karakter uzunluğunda
    - Kriptografik olarak güvenli rastgele
    """
    return secrets.token_urlsafe(48)  # 64 karakter


def create_download_signature(tracking_id: str, timestamp: int) -> str:
    """
    Download URL için HMAC imza oluştur
    
    Args:
        tracking_id: Bordro tracking ID
        timestamp: Unix timestamp (saniye)
    
    Returns:
        HMAC-SHA256 imza (hex)
    """
    message = f"{tracking_id}:{timestamp}".encode('utf-8')
    signature = hmac.new(
        settings.DOWNLOAD_LINK_SECRET.encode('utf-8'),
        message,
        hashlib.sha256
    ).hexdigest()
    return signature


def verify_download_signature(tracking_id: str, timestamp: int, signature: str) -> bool:
    """
    Download URL imzasını doğrula
    
    Args:
        tracking_id: Bordro tracking ID
        timestamp: Unix timestamp
        signature: Doğrulanacak imza
    
    Returns:
        İmza geçerli mi
    """
    expected_signature = create_download_signature(tracking_id, timestamp)
    return hmac.compare_digest(signature, expected_signature)


def is_download_link_expired(timestamp: int) -> bool:
    """
    Download linkinin süresinin dolup dolmadığını kontrol et
    
    Args:
        timestamp: Link oluşturulma zamanı (Unix timestamp)
    
    Returns:
        Süre dolmuş mu
    """
    current_time = int(datetime.utcnow().timestamp())
    expire_seconds = settings.DOWNLOAD_LINK_EXPIRE_DAYS * 24 * 60 * 60
    return (current_time - timestamp) > expire_seconds


def generate_signed_download_url(base_url: str, tracking_id: str) -> str:
    """
    İmzalı download URL oluştur
    
    Args:
        base_url: Tracking base URL
        tracking_id: Bordro tracking ID
    
    Returns:
        İmzalı tam URL
    """
    timestamp = int(datetime.utcnow().timestamp())
    signature = create_download_signature(tracking_id, timestamp)
    return f"{base_url}/api/v1/tracking/download/{tracking_id}?t={timestamp}&s={signature}"



