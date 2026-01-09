# -*- coding: utf-8 -*-
"""
SQLAlchemy Models - Payslip (Bordro)
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum, func
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


class PayslipStatus(str, enum.Enum):
    """Bordro durumları"""
    PENDING = "PENDING"          # Bekliyor (henüz gönderilmedi)
    SENT = "SENT"                # Gönderildi
    OPENED = "OPENED"            # Açıldı (mail okundu)
    DOWNLOADED = "DOWNLOADED"    # İndirildi
    FAILED = "FAILED"            # Gönderim başarısız
    NO_EMPLOYEE = "NO_EMPLOYEE"  # Çalışan bulunamadı


class Payslip(Base):
    """Bordro modeli"""
    __tablename__ = "payslips"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)  # nullable olabilir
    
    # PDF'den okunan bilgiler (çalışan bulunamasa bile saklanır)
    tc_no = Column(String(11), nullable=True, index=True)  # TC Kimlik No
    extracted_full_name = Column(String(200), nullable=True)  # PDF'den çıkarılan ad soyad
    
    # Dönem bilgisi
    period = Column(String(7), nullable=False)  # Format: YYYY-MM (örn: 2024-01)
    period_label = Column(String(100), nullable=True)  # Görüntü adı: "Ocak 2024"
    
    # PDF bilgileri
    pdf_path = Column(String(500), nullable=False)
    pdf_original_name = Column(String(255), nullable=True)
    pdf_password = Column(String(50), nullable=True)  # TC'nin son 6 hanesi
    
    # Tracking
    tracking_id = Column(String(64), unique=True, index=True, nullable=False)
    
    # Durum - PostgreSQL native enum ile uyumlu
    status = Column(
        Enum(
            PayslipStatus,
            name='payslipstatus',
            create_constraint=False,
            native_enum=True
        ),
        default=PayslipStatus.PENDING
    )
    
    # Gönderim bilgileri
    sent_at = Column(DateTime, nullable=True)
    sent_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    send_error = Column(Text, nullable=True)
    
    # Zaman damgaları
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # İlişkiler
    company = relationship("Company", back_populates="payslips")
    employee = relationship("Employee", back_populates="payslips")
    sent_by_user = relationship("User", back_populates="sent_payslips", foreign_keys=[sent_by])
    tracking_events = relationship("TrackingEvent", back_populates="payslip", lazy="selectin")
    
    @property
    def display_name(self):
        """Görüntülenecek isim - çalışan varsa onun adı, yoksa PDF'den çıkarılan"""
        if self.employee:
            return self.employee.full_name
        elif self.extracted_full_name:
            return self.extracted_full_name
        return "Bilinmeyen"
    
    def __repr__(self):
        return f"<Payslip(id={self.id}, period={self.period}, status={self.status})>"
    
    def __repr__(self):
        return f"<Payslip(id={self.id}, period={self.period}, status={self.status})>"



