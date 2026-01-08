# -*- coding: utf-8 -*-
"""
Pydantic Schemas - Employee (Çalışan)
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator


def validate_tc_no(tc_no: str) -> str:
    """
    TC Kimlik Numarası doğrulama
    
    Kurallar:
    - 11 haneli olmalı
    - Sadece rakam içermeli
    - 0 ile başlamamalı
    - TC algoritmasına uymalı
    """
    if not tc_no:
        raise ValueError("TC kimlik numarası gerekli")
    
    # Sadece rakam kontrolü
    if not tc_no.isdigit():
        raise ValueError("TC kimlik numarası sadece rakam içermelidir")
    
    # 11 haneli kontrolü
    if len(tc_no) != 11:
        raise ValueError("TC kimlik numarası 11 haneli olmalıdır")
    
    # 0 ile başlamamalı
    if tc_no[0] == '0':
        raise ValueError("TC kimlik numarası 0 ile başlayamaz")
    
    # TC algoritma kontrolü
    try:
        digits = [int(d) for d in tc_no]
        
        # 10. hane kontrolü
        odd_sum = sum(digits[0:9:2])  # 1, 3, 5, 7, 9. haneler
        even_sum = sum(digits[1:8:2])  # 2, 4, 6, 8. haneler
        digit_10 = (odd_sum * 7 - even_sum) % 10
        
        if digit_10 != digits[9]:
            raise ValueError("Geçersiz TC kimlik numarası")
        
        # 11. hane kontrolü
        digit_11 = sum(digits[0:10]) % 10
        
        if digit_11 != digits[10]:
            raise ValueError("Geçersiz TC kimlik numarası")
        
    except (ValueError, IndexError) as e:
        if "Geçersiz" in str(e):
            raise
        raise ValueError("TC kimlik numarası doğrulanamadı")
    
    return tc_no


class EmployeeBase(BaseModel):
    """Çalışan temel şeması"""
    tc_no: str = Field(..., min_length=11, max_length=11, pattern=r"^\d{11}$")
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=255)
    
    @field_validator('tc_no')
    @classmethod
    def validate_tc(cls, v):
        return validate_tc_no(v)
    
    @field_validator('first_name', 'last_name')
    @classmethod
    def sanitize_name(cls, v):
        """İsim alanlarını temizle"""
        if v is None:
            return v
        # Sadece harf, boşluk ve Türkçe karakterler
        import re
        cleaned = re.sub(r'[^a-zA-ZğüşıöçĞÜŞİÖÇ\s]', '', v)
        return cleaned.strip()


class EmployeeCreate(EmployeeBase):
    """Çalışan oluşturma şeması"""
    pass


class EmployeeBulkCreate(BaseModel):
    """Toplu çalışan oluşturma şeması (Excel'den)"""
    employees: List[EmployeeCreate]


class EmployeeUpdate(BaseModel):
    """Çalışan güncelleme şeması"""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    
    @field_validator('first_name', 'last_name')
    @classmethod
    def sanitize_name(cls, v):
        """İsim alanlarını temizle"""
        if v is None:
            return v
        import re
        cleaned = re.sub(r'[^a-zA-ZğüşıöçĞÜŞİÖÇ\s]', '', v)
        return cleaned.strip()


class EmployeeResponse(BaseModel):
    """Çalışan response şeması"""
    id: int
    tc_no: str  # Maskeli gösterilecek
    tc_masked: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    department: Optional[str] = None
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class EmployeeListResponse(BaseModel):
    """Çalışan listesi response şeması"""
    items: List[EmployeeResponse]
    total: int
    page: int
    page_size: int
    pages: int


class EmployeeImportResult(BaseModel):
    """Excel import sonucu şeması"""
    success_count: int
    error_count: int
    errors: List[str]



