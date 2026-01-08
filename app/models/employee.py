# -*- coding: utf-8 -*-
"""
SQLAlchemy Models - Employee (Çalışan)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Employee(Base):
    """Çalışan modeli"""
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Kimlik bilgileri
    tc_no = Column(String(11), index=True, nullable=False)  # TC Kimlik No
    
    # Kişisel bilgiler
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=False)
    
    # Departman bilgisi (opsiyonel)
    department = Column(String(255), nullable=True)
    
    # Durum
    is_active = Column(Boolean, default=True)
    
    # Zaman damgaları
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # İlişkiler
    company = relationship("Company", back_populates="employees")
    payslips = relationship("Payslip", back_populates="employee", lazy="selectin")
    
    @property
    def full_name(self) -> str:
        """Ad soyad birleştir"""
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else "İsimsiz"
    
    @property
    def tc_masked(self) -> str:
        """TC'yi maskele (son 4 hane görünür)"""
        if self.tc_no and len(self.tc_no) >= 4:
            return f"*******{self.tc_no[-4:]}"
        return "***********"
    
    def __repr__(self):
        return f"<Employee(id={self.id}, tc={self.tc_masked}, name={self.full_name})>"



