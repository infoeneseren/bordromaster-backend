# -*- coding: utf-8 -*-
"""
User Session Model
- Aktif oturumların takibi
- Çoklu cihaz desteği
- Oturum sonlandırma
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserSession(Base):
    """Kullanıcı oturumları tablosu"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Hangi kullanıcı
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Oturum bilgileri
    session_token = Column(String(500), unique=True, nullable=False, index=True)  # Refresh token hash
    
    # Cihaz bilgileri
    device_name = Column(String(255), nullable=True)  # "Chrome on Windows", "Safari on iPhone"
    device_type = Column(String(50), nullable=True)  # desktop, mobile, tablet
    browser = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    
    # Konum bilgileri
    ip_address = Column(String(45), nullable=True)
    location = Column(String(255), nullable=True)  # "İstanbul, Türkiye"
    
    # Durum
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_current = Column(Boolean, default=False, nullable=False)  # Mevcut oturum mu
    
    # Zaman bilgileri
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    terminated_at = Column(DateTime, nullable=True)  # Sonlandırıldıysa
    
    # İlişkiler
    user = relationship("User", back_populates="sessions")
    company = relationship("Company")
    
    # Indexler
    __table_args__ = (
        Index('ix_sessions_user_active', 'user_id', 'is_active'),
        Index('ix_sessions_company_active', 'company_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<UserSession {self.id}: user={self.user_id} device={self.device_name}>"
    
    @property
    def is_expired(self) -> bool:
        """Oturum süresi dolmuş mu"""
        return datetime.utcnow() > self.expires_at


