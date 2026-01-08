# -*- coding: utf-8 -*-
"""
Pydantic Schemas - Company (Şirket)
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class CompanyBase(BaseModel):
    """Şirket temel şeması"""
    name: str = Field(..., min_length=1, max_length=255)


class CompanyCreate(CompanyBase):
    """Şirket oluşturma şeması"""
    pass


class CompanyUpdate(BaseModel):
    """Şirket güncelleme şeması"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    logo_path: Optional[str] = None


class CompanySMTPUpdate(BaseModel):
    """SMTP ayarları güncelleme şeması"""
    smtp_server: Optional[str] = Field(None, max_length=255)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_username: Optional[str] = Field(None, max_length=255)
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_sender_name: Optional[str] = Field(None, max_length=255)
    tracking_base_url: Optional[str] = Field(None, max_length=500)


class CompanyMailTemplateUpdate(BaseModel):
    """Mail şablonu güncelleme şeması"""
    mail_subject: Optional[str] = Field(None, max_length=500)
    mail_body: Optional[str] = None
    mail_delay_seconds: Optional[int] = Field(None, ge=0, le=60)
    mail_batch_size: Optional[int] = Field(None, ge=1, le=100)
    mail_batch_delay: Optional[int] = Field(None, ge=0, le=300)
    # Renk ayarları
    mail_primary_color: Optional[str] = Field(None, max_length=20)
    mail_secondary_color: Optional[str] = Field(None, max_length=20)
    mail_background_color: Optional[str] = Field(None, max_length=20)
    mail_text_color: Optional[str] = Field(None, max_length=20)
    mail_header_text_color: Optional[str] = Field(None, max_length=20)
    mail_footer_text: Optional[str] = None
    mail_disclaimer_text: Optional[str] = None  # Buton altı uyarı metni
    mail_show_logo: Optional[bool] = None
    mail_logo_width: Optional[int] = Field(None, ge=50, le=400)


class CompanyResponse(CompanyBase):
    """Şirket response şeması"""
    id: int
    logo_path: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CompanyDetailResponse(CompanyResponse):
    """Şirket detaylı response şeması (admin için)"""
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_sender_name: Optional[str] = None
    mail_subject: str
    mail_body: str
    mail_delay_seconds: int
    mail_batch_size: int
    mail_batch_delay: int
    tracking_base_url: Optional[str] = None
    # Renk ayarları
    mail_primary_color: str = "#3b82f6"
    mail_secondary_color: str = "#1e40af"
    mail_background_color: str = "#f8fafc"
    mail_text_color: str = "#1e293b"
    mail_header_text_color: str = "#ffffff"
    mail_footer_text: str = "Bu mail otomatik olarak gönderilmiştir.\nLütfen yanıtlamayınız."
    mail_disclaimer_text: str = "Bu butona tıklayarak, bordronuzu görüntülediğinizi ve onaylayarak teslim aldığınızı beyan etmiş olursunuz."
    mail_show_logo: bool = True
    mail_logo_width: int = 150


class CompanySMTPTest(BaseModel):
    """SMTP test şeması"""
    test_email: EmailStr


class MailPreviewRequest(BaseModel):
    """Mail önizleme isteği"""
    employee_name: str = "Örnek Çalışan"
    period: str = "Ocak 2024"


class MailPreviewResponse(BaseModel):
    """Mail önizleme yanıtı"""
    subject: str
    html_content: str



