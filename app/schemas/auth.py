# -*- coding: utf-8 -*-
"""
Pydantic Schemas - Auth (Kimlik Doğrulama)
"""

from typing import Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Login isteği şeması"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response şeması"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Refresh token isteği şeması"""
    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Şifre sıfırlama isteği şeması"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Şifre sıfırlama onay şeması"""
    token: str
    new_password: str



