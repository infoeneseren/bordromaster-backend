# -*- coding: utf-8 -*-
"""
Audit Log Service
- Kritik işlemlerin loglanması
- Log sorgulama
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from app.models.audit import AuditLog, AuditAction

security_logger = logging.getLogger("security")


class AuditService:
    """Audit log servisi"""
    
    @staticmethod
    async def log(
        db: AsyncSession,
        action: AuditAction,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        company_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Audit log kaydı oluştur
        
        Args:
            db: Database session
            action: Yapılan işlem
            user_id: İşlemi yapan kullanıcı ID
            user_email: Kullanıcı email'i
            company_id: Şirket ID
            resource_type: Kaynak tipi (user, employee, payslip vb.)
            resource_id: Kaynak ID
            resource_name: Kaynak adı (okunabilirlik için)
            details: Ek detaylar (JSON)
            old_value: Değişiklik öncesi değer
            new_value: Değişiklik sonrası değer
            ip_address: İstemci IP adresi
            user_agent: Tarayıcı bilgisi
        
        Returns:
            Oluşturulan AuditLog kaydı
        """
        audit_log = AuditLog(
            user_id=user_id,
            user_email=user_email,
            company_id=company_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            old_value=json.dumps(old_value, ensure_ascii=False, default=str) if old_value else None,
            new_value=json.dumps(new_value, ensure_ascii=False, default=str) if new_value else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        db.add(audit_log)
        
        # Güvenlik logger'ına da yaz
        security_logger.info(
            f"AUDIT | Action: {action.value} | User: {user_email or user_id} | "
            f"Resource: {resource_type}:{resource_id} | IP: {ip_address}"
        )
        
        return audit_log
    
    @staticmethod
    async def get_logs(
        db: AsyncSession,
        company_id: int,
        user_id: Optional[int] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Audit logları getir
        
        Args:
            db: Database session
            company_id: Şirket ID
            user_id: Filtrelenecek kullanıcı ID
            action: Filtrelenecek aksiyon
            resource_type: Filtrelenecek kaynak tipi
            start_date: Başlangıç tarihi
            end_date: Bitiş tarihi
            page: Sayfa numarası
            page_size: Sayfa boyutu
        
        Returns:
            {items, total, page, page_size, pages}
        """
        # Base query
        query = select(AuditLog).where(AuditLog.company_id == company_id)
        count_query = select(func.count(AuditLog.id)).where(AuditLog.company_id == company_id)
        
        # Filtreler
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
            count_query = count_query.where(AuditLog.user_id == user_id)
        
        if action:
            query = query.where(AuditLog.action == action)
            count_query = count_query.where(AuditLog.action == action)
        
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
            count_query = count_query.where(AuditLog.resource_type == resource_type)
        
        if start_date:
            query = query.where(AuditLog.created_at >= start_date)
            count_query = count_query.where(AuditLog.created_at >= start_date)
        
        if end_date:
            query = query.where(AuditLog.created_at <= end_date)
            count_query = count_query.where(AuditLog.created_at <= end_date)
        
        # Toplam sayı
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Sayfalama ve sıralama
        offset = (page - 1) * page_size
        query = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # Response hazırla
        items = []
        for log in logs:
            items.append({
                "id": log.id,
                "user_id": log.user_id,
                "user_email": log.user_email,
                "action": log.action.value,
                "action_label": get_action_label(log.action),
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "resource_name": log.resource_name,
                "details": json.loads(log.details) if log.details else None,
                "ip_address": log.ip_address,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            })
        
        import math
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": math.ceil(total / page_size) if total > 0 else 1
        }
    
    @staticmethod
    async def get_user_activity(
        db: AsyncSession,
        user_id: int,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Son N gündeki kullanıcı aktivitelerini getir"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        result = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.user_id == user_id,
                AuditLog.created_at >= start_date
            )
            .order_by(desc(AuditLog.created_at))
            .limit(100)
        )
        logs = result.scalars().all()
        
        return [
            {
                "action": log.action.value,
                "action_label": get_action_label(log.action),
                "resource_type": log.resource_type,
                "resource_name": log.resource_name,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    
    @staticmethod
    async def get_security_events(
        db: AsyncSession,
        company_id: int,
        hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """Son N saatteki güvenlik olaylarını getir"""
        start_date = datetime.utcnow() - timedelta(hours=hours)
        
        security_actions = [
            AuditAction.LOGIN_FAILED,
            AuditAction.SESSION_TERMINATE,
            AuditAction.SUSPICIOUS_ACTIVITY,
            AuditAction.PASSWORD_CHANGE,
        ]
        
        result = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.company_id == company_id,
                AuditLog.action.in_(security_actions),
                AuditLog.created_at >= start_date
            )
            .order_by(desc(AuditLog.created_at))
        )
        logs = result.scalars().all()
        
        events = []
        for log in logs:
            # Kullanıcı dostu mesaj oluştur
            if log.action == AuditAction.LOGIN_FAILED:
                message = f"Başarısız giriş denemesi - {log.user_email or 'Bilinmeyen kullanıcı'}"
            elif log.action == AuditAction.SESSION_TERMINATE:
                message = f"Oturum sonlandırıldı - {log.user_email or 'Kullanıcı'}"
            elif log.action == AuditAction.SUSPICIOUS_ACTIVITY:
                message = f"Şüpheli aktivite tespit edildi - {log.user_email or 'Bilinmiyor'}"
            elif log.action == AuditAction.PASSWORD_CHANGE:
                message = f"Şifre değiştirildi - {log.user_email or 'Kullanıcı'}"
            else:
                message = get_action_label(log.action)
            
            events.append({
                "action": log.action.value,
                "action_label": get_action_label(log.action),
                "message": message,
                "user_email": log.user_email,
                "ip_address": log.ip_address,
                "details": json.loads(log.details) if log.details else None,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            })
        
        return events


def get_action_label(action: AuditAction) -> str:
    """Aksiyon etiketini Türkçe olarak döndür"""
    labels = {
        AuditAction.LOGIN: "Giriş yapıldı",
        AuditAction.LOGOUT: "Çıkış yapıldı",
        AuditAction.LOGIN_FAILED: "Başarısız giriş denemesi",
        AuditAction.PASSWORD_CHANGE: "Şifre değiştirildi",
        AuditAction.USER_CREATE: "Kullanıcı oluşturuldu",
        AuditAction.USER_UPDATE: "Kullanıcı güncellendi",
        AuditAction.USER_DELETE: "Kullanıcı silindi",
        AuditAction.USER_DEACTIVATE: "Kullanıcı devre dışı bırakıldı",
        AuditAction.EMPLOYEE_CREATE: "Çalışan oluşturuldu",
        AuditAction.EMPLOYEE_UPDATE: "Çalışan güncellendi",
        AuditAction.EMPLOYEE_DELETE: "Çalışan silindi",
        AuditAction.EMPLOYEE_BULK_DELETE: "Toplu çalışan silme",
        AuditAction.EMPLOYEE_IMPORT: "Çalışan içe aktarıldı",
        AuditAction.PAYSLIP_UPLOAD: "Bordro yüklendi",
        AuditAction.PAYSLIP_DELETE: "Bordro silindi",
        AuditAction.PAYSLIP_BULK_DELETE: "Toplu bordro silme",
        AuditAction.PAYSLIP_SEND: "Bordro gönderildi",
        AuditAction.SETTINGS_UPDATE: "Ayarlar güncellendi",
        AuditAction.SMTP_UPDATE: "SMTP ayarları güncellendi",
        AuditAction.LOGO_UPLOAD: "Logo yüklendi",
        AuditAction.LOGO_DELETE: "Logo silindi",
        AuditAction.DATA_EXPORT: "Veri dışa aktarıldı",
        AuditAction.REPORT_DOWNLOAD: "Rapor indirildi",
        AuditAction.SESSION_TERMINATE: "Oturum sonlandırıldı",
        AuditAction.SUSPICIOUS_ACTIVITY: "Şüpheli aktivite",
    }
    return labels.get(action, action.value)


# Singleton instance
audit_service = AuditService()

