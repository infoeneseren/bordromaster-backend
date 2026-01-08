# -*- coding: utf-8 -*-
"""
SQLAlchemy Models - TrackingEvent (Takip Olayları)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


class EventType(str, enum.Enum):
    """Olay türleri"""
    EMAIL_SENT = "email_sent"        # Mail gönderildi
    EMAIL_OPENED = "email_opened"    # Mail açıldı (tracking pixel)
    LINK_CLICKED = "link_clicked"    # İndirme linkine tıklandı
    PDF_DOWNLOADED = "pdf_downloaded"  # PDF indirildi


class TrackingEvent(Base):
    """Takip olayları modeli"""
    __tablename__ = "tracking_events"
    
    id = Column(Integer, primary_key=True, index=True)
    payslip_id = Column(Integer, ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False)
    
    # Olay bilgileri
    event_type = Column(Enum(EventType), nullable=False)
    
    # İstemci bilgileri
    ip_address = Column(String(45), nullable=True)  # IPv4 veya IPv6
    user_agent = Column(Text, nullable=True)
    
    # Ek bilgiler
    extra_data = Column(Text, nullable=True)  # JSON formatında ek veri
    
    # Zaman
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # İlişkiler
    payslip = relationship("Payslip", back_populates="tracking_events")
    
    def __repr__(self):
        return f"<TrackingEvent(id={self.id}, type={self.event_type}, payslip_id={self.payslip_id})>"



