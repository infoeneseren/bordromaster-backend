# -*- coding: utf-8 -*-
"""
SQLAlchemy Models - Company (Şirket)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, LargeBinary
from sqlalchemy.orm import relationship
from app.core.database import Base


class Company(Base):
    """Şirket modeli"""
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Temel bilgiler
    name = Column(String(255), nullable=False)
    logo_path = Column(String(500), nullable=True)
    
    # SMTP Ayarları
    smtp_server = Column(String(255), nullable=True)
    smtp_port = Column(Integer, default=587)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(Text, nullable=True)  # Encrypted
    smtp_use_tls = Column(Boolean, default=True)
    smtp_sender_name = Column(String(255), nullable=True)
    
    # Mail Şablonu
    mail_subject = Column(String(500), default="Bordronuz Hakkında")
    mail_body = Column(Text, default="Sayın {name},\n\nEkte {period} dönemine ait bordronuz bulunmaktadır.\n\nSaygılarımızla")
    
    # Mail Şablonu Renk Ayarları
    mail_primary_color = Column(String(20), default="#3b82f6")  # Ana renk (butonlar, vurgu)
    mail_secondary_color = Column(String(20), default="#1e40af")  # İkincil renk (hover, gradyan)
    mail_background_color = Column(String(20), default="#f8fafc")  # Arka plan rengi
    mail_text_color = Column(String(20), default="#1e293b")  # Metin rengi
    mail_header_text_color = Column(String(20), default="#ffffff")  # Header metin rengi
    mail_footer_text = Column(Text, default="Bu mail otomatik olarak gönderilmiştir.\nLütfen yanıtlamayınız.")
    mail_disclaimer_text = Column(Text, default="Bu butona tıklayarak, bordronuzu görüntülediğinizi ve onaylayarak teslim aldığınızı beyan etmiş olursunuz.")  # Buton altı uyarı metni
    mail_show_logo = Column(Boolean, default=True)  # Logonun gösterilip gösterilmeyeceği
    mail_logo_width = Column(Integer, default=150)  # Logo genişliği (px)
    
    # Tracking URL (dışarıdan erişilebilir URL)
    tracking_base_url = Column(String(500), nullable=True)
    
    # Gönderim Ayarları
    mail_delay_seconds = Column(Integer, default=2)
    mail_batch_size = Column(Integer, default=10)
    mail_batch_delay = Column(Integer, default=5)
    
    # Durum
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # İlişkiler
    users = relationship("User", back_populates="company", lazy="selectin")
    employees = relationship("Employee", back_populates="company", lazy="selectin")
    payslips = relationship("Payslip", back_populates="company", lazy="selectin")
    
    def __repr__(self):
        return f"<Company(id={self.id}, name={self.name})>"



