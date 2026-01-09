# -*- coding: utf-8 -*-
"""
Pydantic Schemas - User (Kullanıcı)
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from app.models.user import UserRole
from app.core.password_policy import validate_password, password_policy


class UserBase(BaseModel):
    """Kullanıcı temel şeması"""
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)


class UserCreate(UserBase):
    """Kullanıcı oluşturma şeması"""
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.USER
    
    @model_validator(mode='after')
    def validate_password_with_user_info(self):
        """Şifreyi kullanıcı bilgileriyle birlikte doğrula"""
        # Ad ve soyadı full_name'den ayıkla
        first_name = None
        last_name = None
        
        if self.full_name:
            name_parts = self.full_name.strip().split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = name_parts[-1]
            elif len(name_parts) == 1:
                first_name = name_parts[0]
        
        # Şifreyi doğrula
        is_valid, errors = password_policy.validate(
            self.password,
            email=self.email,
            first_name=first_name,
            last_name=last_name,
            full_name=self.full_name
        )
        
        if not is_valid:
            raise ValueError("; ".join(errors))
        
        return self


class UserUpdate(BaseModel):
    """Kullanıcı güncelleme şeması"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


class UserPasswordUpdate(BaseModel):
    """Şifre güncelleme şeması"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
    # Not: Şifre değiştirme sırasında ad/soyad kontrolü API endpoint'inde yapılacak
    # Çünkü bu schema mevcut kullanıcı bilgilerine erişemiyor
    
    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v):
        # Temel kontroller (ad/soyad kontrolü endpoint'te yapılacak)
        return validate_password(v)


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



