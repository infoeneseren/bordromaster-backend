# -*- coding: utf-8 -*-
"""
Audit Logging Servisi
- Kritik işlemlerin loglanması
- Güvenlik olaylarının takibi
- KVKK/GDPR uyumu için kayıt tutma
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class AuditAction(str, Enum):
    """Audit edilecek işlem tipleri"""
    # Auth
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    
    # User
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    
    # Employee
    EMPLOYEE_CREATED = "EMPLOYEE_CREATED"
    EMPLOYEE_UPDATED = "EMPLOYEE_UPDATED"
    EMPLOYEE_DELETED = "EMPLOYEE_DELETED"
    EMPLOYEE_BULK_DELETED = "EMPLOYEE_BULK_DELETED"
    EMPLOYEE_IMPORTED = "EMPLOYEE_IMPORTED"
    
    # Payslip
    PAYSLIP_UPLOADED = "PAYSLIP_UPLOADED"
    PAYSLIP_SENT = "PAYSLIP_SENT"
    PAYSLIP_DELETED = "PAYSLIP_DELETED"
    PAYSLIP_BULK_DELETED = "PAYSLIP_BULK_DELETED"
    PAYSLIP_DOWNLOADED = "PAYSLIP_DOWNLOADED"
    
    # Settings
    SMTP_UPDATED = "SMTP_UPDATED"
    COMPANY_UPDATED = "COMPANY_UPDATED"
    LOGO_UPLOADED = "LOGO_UPLOADED"
    LOGO_DELETED = "LOGO_DELETED"
    
    # Security
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_TOKEN = "INVALID_TOKEN"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"


class AuditLogger:
    """
    Audit log servisi
    
    Tüm kritik işlemleri loglar:
    - Kim (user_id, email)
    - Ne (action)
    - Ne zaman (timestamp)
    - Nerede (IP, user_agent)
    - Ne üzerinde (resource_type, resource_id)
    - Detay (details)
    """
    
    def __init__(self):
        # Audit logger'ı yapılandır
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)
        
        # Console handler (production'da file handler eklenebilir)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - AUDIT - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def log(
        self,
        action: AuditAction,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        company_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True
    ):
        """
        Audit log kaydı oluştur
        
        Args:
            action: İşlem tipi
            user_id: Kullanıcı ID
            user_email: Kullanıcı email (maskelenebilir)
            company_id: Şirket ID
            resource_type: Kaynak tipi (employee, payslip, user vb.)
            resource_id: Kaynak ID
            ip_address: İstemci IP
            user_agent: Tarayıcı/Client bilgisi
            details: Ek detaylar
            success: İşlem başarılı mı
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action.value,
            "success": success,
            "user_id": user_id,
            "user_email": self._mask_email(user_email) if user_email else None,
            "company_id": company_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "user_agent": user_agent[:100] if user_agent else None,
            "details": details
        }
        
        # None değerleri kaldır
        log_entry = {k: v for k, v in log_entry.items() if v is not None}
        
        # Log seviyesi belirle
        if action in [
            AuditAction.LOGIN_FAILED,
            AuditAction.RATE_LIMIT_EXCEEDED,
            AuditAction.INVALID_TOKEN,
            AuditAction.UNAUTHORIZED_ACCESS,
            AuditAction.SUSPICIOUS_ACTIVITY
        ]:
            self.logger.warning(json.dumps(log_entry))
        else:
            self.logger.info(json.dumps(log_entry))
    
    def _mask_email(self, email: str) -> str:
        """Email adresini maskele (KVKK uyumu)"""
        if not email or '@' not in email:
            return email
        
        local, domain = email.split('@')
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        
        return f"{masked_local}@{domain}"
    
    # Yardımcı metodlar
    def log_login_success(
        self,
        user_id: int,
        user_email: str,
        ip_address: str,
        user_agent: str = None
    ):
        """Başarılı giriş logla"""
        self.log(
            action=AuditAction.LOGIN_SUCCESS,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    def log_login_failed(
        self,
        user_email: str,
        ip_address: str,
        reason: str = None,
        user_agent: str = None
    ):
        """Başarısız giriş logla"""
        self.log(
            action=AuditAction.LOGIN_FAILED,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": reason} if reason else None,
            success=False
        )
    
    def log_payslip_sent(
        self,
        user_id: int,
        company_id: int,
        payslip_count: int,
        success_count: int,
        ip_address: str = None
    ):
        """Bordro gönderim logla"""
        self.log(
            action=AuditAction.PAYSLIP_SENT,
            user_id=user_id,
            company_id=company_id,
            ip_address=ip_address,
            details={
                "total": payslip_count,
                "success": success_count,
                "failed": payslip_count - success_count
            }
        )
    
    def log_data_deletion(
        self,
        user_id: int,
        company_id: int,
        resource_type: str,
        deleted_count: int,
        ip_address: str = None
    ):
        """Veri silme logla"""
        action = {
            "employee": AuditAction.EMPLOYEE_BULK_DELETED,
            "payslip": AuditAction.PAYSLIP_BULK_DELETED
        }.get(resource_type, AuditAction.PAYSLIP_DELETED)
        
        self.log(
            action=action,
            user_id=user_id,
            company_id=company_id,
            resource_type=resource_type,
            ip_address=ip_address,
            details={"deleted_count": deleted_count}
        )
    
    def log_security_event(
        self,
        action: AuditAction,
        ip_address: str,
        details: Dict[str, Any] = None,
        user_id: int = None
    ):
        """Güvenlik olayı logla"""
        self.log(
            action=action,
            user_id=user_id,
            ip_address=ip_address,
            details=details,
            success=False
        )


# Singleton instance
audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Audit logger instance al"""
    return audit_logger

