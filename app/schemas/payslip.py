# -*- coding: utf-8 -*-
"""
Pydantic Schemas - Payslip (Bordro)
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.payslip import PayslipStatus


class PayslipBase(BaseModel):
    """Bordro temel şeması"""
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$")  # YYYY-MM
    period_label: Optional[str] = None


class PayslipCreate(PayslipBase):
    """Bordro oluşturma şeması"""
    employee_id: Optional[int] = None  # Çalışan bulunamayabilir
    pdf_path: str


class PayslipResponse(BaseModel):
    """Bordro response şeması"""
    id: int
    employee_id: Optional[int] = None  # Çalışan bulunamadıysa None
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    period: str
    period_label: Optional[str] = None
    status: PayslipStatus
    tracking_id: str
    download_url: Optional[str] = None  # İmzalı indirme URL'i
    sent_at: Optional[datetime] = None
    send_error: Optional[str] = None
    created_at: datetime
    
    # PDF'den çıkarılan bilgiler
    tc_no: Optional[str] = None
    extracted_name: Optional[str] = None  # Çalışan yoksa PDF'den çıkarılan isim
    
    # Tracking özeti
    is_opened: bool = False
    is_downloaded: bool = False
    opened_at: Optional[datetime] = None
    downloaded_at: Optional[datetime] = None
    download_count: int = 0
    
    # Çalışan eşleşme durumu
    has_employee: bool = False  # Çalışan bulundu mu?
    
    class Config:
        from_attributes = True


class PayslipListResponse(BaseModel):
    """Bordro listesi response şeması"""
    items: List[PayslipResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PayslipUploadResponse(BaseModel):
    """PDF yükleme sonucu şeması"""
    total_pages: int
    success_count: int
    error_count: int
    payslips: List[PayslipResponse]
    errors: List[str]


class PayslipSendRequest(BaseModel):
    """Toplu gönderim isteği şeması"""
    payslip_ids: List[int]
    force_resend: bool = False  # Daha önce gönderilmişleri tekrar gönder


class PayslipSendResult(BaseModel):
    """Gönderim sonucu şeması"""
    payslip_id: int
    employee_email: str
    success: bool
    error: Optional[str] = None


class PayslipBulkSendResponse(BaseModel):
    """Toplu gönderim sonucu şeması"""
    total: int
    success_count: int
    error_count: int
    results: List[PayslipSendResult]



