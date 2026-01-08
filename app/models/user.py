# -*- coding: utf-8 -*-
"""
SQLAlchemy Models - User (Kullanıcı)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


class UserRole(str, enum.Enum):
    """Kullanıcı rolleri"""
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """Kullanıcı modeli"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Kimlik bilgileri
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Profil
    full_name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER)
    
    # Durum
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Token yönetimi
    refresh_token = Column(String(500), nullable=True)
    
    # Zaman damgaları
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # İlişkiler
    company = relationship("Company", back_populates="users")
    sent_payslips = relationship("Payslip", back_populates="sent_by_user", foreign_keys="Payslip.sent_by")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"



