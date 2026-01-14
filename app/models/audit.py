# -*- coding: utf-8 -*-
"""
Audit Log Model
- Kritik işlemlerin loglanması
- Kim, ne zaman, ne yaptı takibi
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class AuditAction(enum.Enum):
    """Audit log aksiyonları"""
    # Auth işlemleri
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    
    # Kullanıcı işlemleri
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_DEACTIVATE = "user_deactivate"
    
    # Çalışan işlemleri
    EMPLOYEE_CREATE = "employee_create"
    EMPLOYEE_UPDATE = "employee_update"
    EMPLOYEE_DELETE = "employee_delete"
    EMPLOYEE_BULK_DELETE = "employee_bulk_delete"
    EMPLOYEE_IMPORT = "employee_import"
    
    # Bordro işlemleri
    PAYSLIP_UPLOAD = "payslip_upload"
    PAYSLIP_DELETE = "payslip_delete"
    PAYSLIP_BULK_DELETE = "payslip_bulk_delete"
    PAYSLIP_SEND = "payslip_send"
    
    # Ayar işlemleri
    SETTINGS_UPDATE = "settings_update"
    SMTP_UPDATE = "smtp_update"
    LOGO_UPLOAD = "logo_upload"
    LOGO_DELETE = "logo_delete"
    
    # Veri erişimi
    DATA_EXPORT = "data_export"
    REPORT_DOWNLOAD = "report_download"
    
    # Güvenlik olayları
    SESSION_TERMINATE = "session_terminate"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


class AuditLog(Base):
    """Audit log tablosu"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Kim yaptı
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255), nullable=True)  # User silinse bile email kalır
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    
    # Ne yaptı
    action = Column(Enum(AuditAction), nullable=False, index=True)
    
    # Hangi kaynak üzerinde
    resource_type = Column(String(50), nullable=True)  # user, employee, payslip, settings
    resource_id = Column(Integer, nullable=True)
    resource_name = Column(String(255), nullable=True)  # Kaynak adı (okunabilirlik için)
    
    # Detaylar
    details = Column(Text, nullable=True)  # JSON formatında ek bilgiler
    old_value = Column(Text, nullable=True)  # Değişiklik öncesi değer (JSON)
    new_value = Column(Text, nullable=True)  # Değişiklik sonrası değer (JSON)
    
    # Nereden yaptı
    ip_address = Column(String(45), nullable=True)  # IPv6 desteği için 45 karakter
    user_agent = Column(String(500), nullable=True)
    
    # Ne zaman
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # İlişkiler
    user = relationship("User", foreign_keys=[user_id])
    company = relationship("Company")
    
    # Indexler
    __table_args__ = (
        Index('ix_audit_logs_company_created', 'company_id', 'created_at'),
        Index('ix_audit_logs_user_action', 'user_id', 'action'),
        Index('ix_audit_logs_resource', 'resource_type', 'resource_id'),
    )
    
    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action.value} by {self.user_email}>"


