# -*- coding: utf-8 -*-
"""
Pydantic Schemas - User (Kullanıcı)
"""

import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, field_validator
from app.models.user import UserRole


def validate_password_strength(password: str) -> str:
    """
    Güçlü şifre kontrolü
    
    Kurallar:
    - Minimum 8 karakter
    - En az 1 büyük harf
    - En az 1 küçük harf
    - En az 1 rakam
    - En az 1 özel karakter
    """
    errors = []
    
    if len(password) < 8:
        errors.append("En az 8 karakter olmalı")
    
    if not re.search(r'[A-Z]', password):
        errors.append("En az 1 büyük harf içermeli")
    
    if not re.search(r'[a-z]', password):
        errors.append("En az 1 küçük harf içermeli")
    
    if not re.search(r'\d', password):
        errors.append("En az 1 rakam içermeli")
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/]', password):
        errors.append("En az 1 özel karakter içermeli (!@#$%^&*...)")
    
    if errors:
        raise ValueError("; ".join(errors))
    
    return password


class UserBase(BaseModel):
    """Kullanıcı temel şeması"""
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)


class UserCreate(UserBase):
    """Kullanıcı oluşturma şeması"""
    password: str = Field(..., min_length=8, max_length=100)
    role: UserRole = UserRole.USER
    
    @field_validator('password')
    @classmethod
    def password_strength(cls, v):
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    """Kullanıcı güncelleme şeması"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


class UserPasswordUpdate(BaseModel):
    """Şifre güncelleme şeması"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v):
        return validate_password_strength(v)


class UserResponse(UserBase):
    """Kullanıcı response şeması"""
    id: int
    company_id: int
    role: UserRole
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserMeResponse(UserResponse):
    """Mevcut kullanıcı response şeması"""
    company_name: Optional[str] = None



