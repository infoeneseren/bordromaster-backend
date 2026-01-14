# -*- coding: utf-8 -*-
"""
Audit Log API Endpoints
- Log listesi (admin only)
- Kullanıcı aktiviteleri
- Güvenlik olayları
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User, AuditAction
from app.services.audit_service import audit_service, get_action_label
from app.api.deps import get_current_user, get_current_admin_user

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Audit logları listele (admin only)
    
    Filtreler:
    - user_id: Belirli kullanıcının logları
    - action: Belirli aksiyon tipi (login, user_create vb.)
    - resource_type: Kaynak tipi (user, employee, payslip vb.)
    - start_date: Başlangıç tarihi
    - end_date: Bitiş tarihi
    """
    # Action string'i enum'a çevir
    action_enum = None
    if action:
        try:
            action_enum = AuditAction(action)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Geçersiz aksiyon: {action}"
            )
    
    result = await audit_service.get_logs(
        db=db,
        company_id=current_user.company_id,
        user_id=user_id,
        action=action_enum,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    
    return result


@router.get("/actions")
async def get_available_actions(
    current_user: User = Depends(get_current_admin_user),
):
    """Mevcut aksiyon tiplerini listele"""
    return {
        "actions": [
            {
                "value": action.value,
                "label": get_action_label(action)
            }
            for action in AuditAction
        ]
    }


@router.get("/my-activity")
async def get_my_activity(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Kendi aktivite geçmişim"""
    activities = await audit_service.get_user_activity(
        db=db,
        user_id=current_user.id,
        days=days,
    )
    return {"activities": activities}


@router.get("/security-events")
async def get_security_events(
    hours: int = Query(24, ge=1, le=168),  # Max 7 gün
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Güvenlik olaylarını listele (admin only)
    
    Başarısız girişler, şüpheli aktiviteler vb.
    """
    events = await audit_service.get_security_events(
        db=db,
        company_id=current_user.company_id,
        hours=hours,
    )
    return {"events": events, "hours": hours}


@router.get("/user/{user_id}")
async def get_user_activity(
    user_id: int,
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Belirli kullanıcının aktivite geçmişi (admin only)"""
    activities = await audit_service.get_user_activity(
        db=db,
        user_id=user_id,
        days=days,
    )
    return {"user_id": user_id, "activities": activities}


@router.get("/summary")
async def get_audit_summary(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Audit özeti (admin only)
    
    Son N günlük aktivite özeti
    """
    from sqlalchemy import select, func, desc
    from app.models import AuditLog
    from app.models.audit import AuditAction
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Aksiyon bazlı sayımlar
    result = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id))
        .where(
            AuditLog.company_id == current_user.company_id,
            AuditLog.created_at >= start_date
        )
        .group_by(AuditLog.action)
    )
    action_counts = {row[0].value: row[1] for row in result.fetchall()}
    
    # Günlük aktivite sayısı
    result = await db.execute(
        select(
            func.date(AuditLog.created_at),
            func.count(AuditLog.id)
        )
        .where(
            AuditLog.company_id == current_user.company_id,
            AuditLog.created_at >= start_date
        )
        .group_by(func.date(AuditLog.created_at))
        .order_by(func.date(AuditLog.created_at))
    )
    daily_counts = [
        {"date": str(row[0]), "count": row[1]}
        for row in result.fetchall()
    ]
    
    # Toplam sayı
    result = await db.execute(
        select(func.count(AuditLog.id))
        .where(
            AuditLog.company_id == current_user.company_id,
            AuditLog.created_at >= start_date
        )
    )
    total = result.scalar() or 0
    
    # Benzersiz kullanıcı sayısı
    result = await db.execute(
        select(func.count(func.distinct(AuditLog.user_id)))
        .where(
            AuditLog.company_id == current_user.company_id,
            AuditLog.created_at >= start_date
        )
    )
    active_users = result.scalar() or 0
    
    # Son 24 saatteki başarısız giriş denemeleri
    last_24h = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.company_id == current_user.company_id,
            AuditLog.action == AuditAction.LOGIN_FAILED,
            AuditLog.created_at >= last_24h
        )
        .order_by(desc(AuditLog.created_at))
        .limit(10)
    )
    failed_logins = result.scalars().all()
    recent_failed_logins = [
        {
            "user_email": log.user_email,
            "ip_address": log.ip_address,
            "timestamp": log.created_at.isoformat() if log.created_at else None,
        }
        for log in failed_logins
    ]
    
    # Frontend için uyumlu response (action.value = "login", "login_failed" vs.)
    return {
        "days": days,
        "total_actions": total,
        "login_success": action_counts.get("login", 0),
        "login_failed": action_counts.get("login_failed", 0),
        "active_users": active_users,
        "action_counts": action_counts,
        "daily_counts": daily_counts,
        "recent_failed_logins": recent_failed_logins,
    }

