# -*- coding: utf-8 -*-
"""
Session Management API Endpoints
- Aktif oturumları listele
- Oturum sonlandır
- Tüm oturumları sonlandır
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User, AuditAction
from app.services.session_service import session_service
from app.services.audit_service import audit_service
from app.api.deps import get_current_user, get_client_ip, get_user_agent
from app.core.redis_service import token_blacklist

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("")
async def get_my_sessions(
    include_expired: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktif oturumlarımı listele
    
    Her oturum için:
    - Cihaz bilgisi (browser, OS)
    - IP adresi
    - Son aktivite zamanı
    - Mevcut oturum mu
    """
    sessions = await session_service.get_user_sessions(
        db=db,
        user_id=current_user.id,
        include_expired=include_expired,
    )
    
    # Aktif oturum sayısı
    active_count = sum(1 for s in sessions if s["is_active"] and not s["is_expired"])
    
    return {
        "sessions": sessions,
        "active_count": active_count,
        "total_count": len(sessions),
    }


@router.delete("/{session_id}")
async def terminate_session(
    session_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Belirli bir oturumu sonlandır
    
    Kendi oturumlarınızı sonlandırabilirsiniz.
    """
    success = await session_service.terminate_session(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oturum bulunamadı"
        )
    
    # Audit log
    await audit_service.log(
        db=db,
        action=AuditAction.SESSION_TERMINATE,
        user_id=current_user.id,
        user_email=current_user.email,
        company_id=current_user.company_id,
        resource_type="session",
        resource_id=session_id,
        details={"terminated_session_id": session_id},
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    
    await db.commit()
    
    return {"message": "Oturum sonlandırıldı"}


@router.delete("")
async def terminate_all_sessions(
    request: Request,
    except_current: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Tüm oturumları sonlandır
    
    Args:
        except_current: True ise mevcut oturum hariç tutulur
    """
    # Mevcut token'ı al
    auth_header = request.headers.get("Authorization", "")
    current_token = None
    if except_current and auth_header.startswith("Bearer "):
        # Access token'dan refresh token'a ulaşamıyoruz
        # Bu yüzden mevcut oturumu korumak için ayrı bir mantık gerekiyor
        pass
    
    count = await session_service.terminate_all_sessions(
        db=db,
        user_id=current_user.id,
        except_current=except_current,
        current_token=current_user.refresh_token if except_current else None,
    )
    
    # Audit log
    await audit_service.log(
        db=db,
        action=AuditAction.SESSION_TERMINATE,
        user_id=current_user.id,
        user_email=current_user.email,
        company_id=current_user.company_id,
        details={
            "action": "terminate_all",
            "count": count,
            "except_current": except_current
        },
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    
    await db.commit()
    
    return {
        "message": f"{count} oturum sonlandırıldı",
        "terminated_count": count,
    }


@router.get("/count")
async def get_session_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Aktif oturum sayısını getir"""
    count = await session_service.get_active_session_count(
        db=db,
        user_id=current_user.id,
    )
    return {"active_sessions": count}


