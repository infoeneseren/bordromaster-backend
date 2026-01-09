# -*- coding: utf-8 -*-
"""
Tracking API Endpoints
- Mail acilma takibi (pixel)
- PDF indirme takibi
- Güvenlik: Rate limiting, imzalı URL, süre sınırı, Path Traversal koruması
"""

import os
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import Response, FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_download_signature, is_download_link_expired
from app.core.security_utils import sanitize_path, validate_tracking_id
from app.models import Payslip, PayslipStatus, TrackingEvent, EventType, Employee
from app.api.deps import get_client_ip, get_user_agent, get_current_user
from app.models import User
from app.schemas import TrackingStatsResponse, PayslipTrackingResponse, TrackingReportResponse, TrackingEventResponse

# Güvenlik logger'ı
security_logger = logging.getLogger("security")

router = APIRouter(prefix="/tracking", tags=["Tracking"])

# Rate limiting için basit in-memory storage (Production'da Redis kullanın)
download_attempts_by_ip = defaultdict(list)  # IP -> [timestamp listesi]
download_attempts_by_tracking = defaultdict(list)  # tracking_id -> [timestamp listesi]

# 1x1 seffaf PNG (base64)
TRANSPARENT_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def check_rate_limit(ip: str, tracking_id: str) -> tuple[bool, str]:
    """
    Rate limiting kontrolü
    
    Kurallar:
    - IP başına dakikada maksimum DOWNLOAD_IP_LIMIT_PER_MINUTE istek
    - Tracking ID başına günde (24 saat) maksimum DOWNLOAD_TRACKING_LIMIT_PER_DAY istek (IP farketmeksizin)
    
    Returns:
        tuple[bool, str]: (izin verildi mi, hata mesajı)
    """
    current_time = time.time()
    minute_ago = current_time - 60
    day_ago = current_time - 86400  # 24 saat
    
    # Limitler settings'den
    ip_limit = settings.DOWNLOAD_IP_LIMIT_PER_MINUTE
    tracking_limit = settings.DOWNLOAD_TRACKING_LIMIT_PER_DAY
    
    # 1. IP bazlı kontrol - Eski kayıtları temizle
    download_attempts_by_ip[ip] = [t for t in download_attempts_by_ip[ip] if t > minute_ago]
    
    # Son 1 dakikadaki IP başına istek sayısı
    if len(download_attempts_by_ip[ip]) >= ip_limit:
        return False, f"IP başına dakikada maksimum {ip_limit} istek hakkınız var. Lütfen bekleyin."
    
    # 2. Tracking ID bazlı kontrol - Eski kayıtları temizle
    download_attempts_by_tracking[tracking_id] = [
        t for t in download_attempts_by_tracking[tracking_id] if t > day_ago
    ]
    
    # Son 24 saatteki tracking_id başına istek sayısı
    if len(download_attempts_by_tracking[tracking_id]) >= tracking_limit:
        return False, f"Bu bordro için günlük indirme limiti ({tracking_limit}) aşıldı. 24 saat sonra tekrar deneyin."
    
    return True, ""


def record_download_attempt(ip: str, tracking_id: str):
    """İndirme denemesini kaydet"""
    current_time = time.time()
    download_attempts_by_ip[ip].append(current_time)
    download_attempts_by_tracking[tracking_id].append(current_time)


def log_security_event(event_type: str, ip: str, tracking_id: str, details: str = ""):
    """Güvenlik olayını logla"""
    security_logger.warning(
        f"SECURITY_EVENT | Type: {event_type} | IP: {ip} | TrackingID: {tracking_id} | Details: {details}"
    )


@router.get("/pixel/{tracking_id}")
async def track_open(
    tracking_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Mail acilma takibi - Tracking pixel
    
    Güvenlik:
    - Tracking ID format doğrulaması
    - Rate limiting (pixel endpoint için ayrı)
    """
    client_ip = get_client_ip(request)
    
    # 1. Tracking ID format doğrulaması
    if not validate_tracking_id(tracking_id):
        log_security_event("INVALID_TRACKING_ID", client_ip, tracking_id, "Pixel endpoint")
        # Hata döndürme, sadece boş pixel dön (güvenlik için)
        return Response(
            content=TRANSPARENT_PIXEL,
            media_type="image/png",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    
    # 2. Bordroyu bul
    result = await db.execute(
        select(Payslip).where(Payslip.tracking_id == tracking_id)
    )
    payslip = result.scalar_one_or_none()
    
    if payslip:
        # Tracking event ekle (aynı IP'den tekrar gelirse de kaydet - açılma sayısı için)
        event = TrackingEvent(
            payslip_id=payslip.id,
            event_type=EventType.EMAIL_OPENED,
            ip_address=client_ip,
            user_agent=get_user_agent(request)
        )
        db.add(event)
        
        # Durumu guncelle (sadece ilk açılmada)
        if payslip.status == PayslipStatus.SENT:
            payslip.status = PayslipStatus.OPENED
        
        await db.commit()
    else:
        # Geçersiz tracking_id - sadece logla
        log_security_event("UNKNOWN_TRACKING_ID", client_ip, tracking_id, "Pixel endpoint")
    
    # Seffaf pixel dondur
    return Response(
        content=TRANSPARENT_PIXEL,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/download/{tracking_id}")
async def track_download(
    tracking_id: str,
    request: Request,
    t: int = Query(..., description="Timestamp (zorunlu)"),
    s: str = Query(..., description="Signature (zorunlu)"),
    db: AsyncSession = Depends(get_db)
):
    """
    PDF indirme - Güvenli Tracking ile
    
    Güvenlik Özellikleri:
    - İmzalı URL doğrulaması (ZORUNLU)
    - Rate limiting (IP başına)
    - Süre sınırı kontrolü
    - Tracking ID format doğrulaması
    - Path traversal koruması
    - Güvenlik loglama
    """
    client_ip = get_client_ip(request)
    user_agent = get_user_agent(request)
    
    # 0. Tracking ID format doğrulaması
    if not validate_tracking_id(tracking_id):
        log_security_event("INVALID_TRACKING_ID", client_ip, tracking_id, "Download endpoint")
        raise HTTPException(status_code=400, detail="Geçersiz indirme linki")
    
    # 1. Rate Limiting Kontrolü (IP ve Tracking ID bazlı)
    rate_limit_ok, rate_limit_msg = check_rate_limit(client_ip, tracking_id)
    if not rate_limit_ok:
        log_security_event("RATE_LIMIT_EXCEEDED", client_ip, tracking_id, f"UA: {user_agent} | {rate_limit_msg}")
        raise HTTPException(
            status_code=429, 
            detail=rate_limit_msg,
            headers={"Retry-After": "60"}
        )
    
    # 2. İmza Doğrulaması (ZORUNLU)
    if not verify_download_signature(tracking_id, t, s):
        log_security_event("INVALID_SIGNATURE", client_ip, tracking_id, f"t={t}, s={s[:8] if s else 'None'}...")
        raise HTTPException(status_code=403, detail="Geçersiz indirme linki")
    
    # 3. Süre kontrolü
    if is_download_link_expired(t):
        log_security_event("EXPIRED_LINK", client_ip, tracking_id, f"Created: {t}")
        raise HTTPException(status_code=410, detail="İndirme linkinin süresi dolmuş. Lütfen yeni bir link isteyin.")
    
    # 4. Bordroyu bul
    result = await db.execute(
        select(Payslip).where(Payslip.tracking_id == tracking_id)
    )
    payslip = result.scalar_one_or_none()
    
    if not payslip:
        log_security_event("INVALID_TRACKING_ID", client_ip, tracking_id, "Bordro bulunamadi")
        raise HTTPException(status_code=404, detail="Bordro bulunamadi")
    
    # 5. PATH TRAVERSAL KORUMASI
    safe_path = sanitize_path(payslip.pdf_path, settings.PDF_OUTPUT_DIR)
    if safe_path is None:
        log_security_event(
            "PATH_TRAVERSAL_BLOCKED", 
            client_ip, 
            tracking_id, 
            f"Attempted path: {payslip.pdf_path}"
        )
        raise HTTPException(status_code=403, detail="Dosyaya erişim reddedildi")
    
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="PDF dosyasi bulunamadi")
    
    # 6. Tracking event ekle
    event = TrackingEvent(
        payslip_id=payslip.id,
        event_type=EventType.PDF_DOWNLOADED,
        ip_address=client_ip,
        user_agent=user_agent
    )
    db.add(event)
    
    # Durumu guncelle
    if payslip.status in [PayslipStatus.SENT, PayslipStatus.OPENED]:
        payslip.status = PayslipStatus.DOWNLOADED
    
    await db.commit()
    
    # 7. Rate limit kaydı ekle (başarılı indirme sonrası)
    record_download_attempt(client_ip, tracking_id)
    
    # 8. Calisan bilgisini al
    emp_result = await db.execute(
        select(Employee).where(Employee.id == payslip.employee_id)
    )
    employee = emp_result.scalar_one_or_none()
    
    # Dosya adini olustur
    if employee:
        filename = f"Bordro_{employee.first_name}_{employee.last_name}_{payslip.period}.pdf"
    else:
        filename = f"Bordro_{payslip.period}.pdf"
    
    # Güvenlik başarılı log
    log_security_event("DOWNLOAD_SUCCESS", client_ip, tracking_id, f"File: {filename}")
    
    return FileResponse(
        safe_path,  # Sanitize edilmiş path kullan
        media_type="application/pdf",
        filename=filename,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block"
        }
    )


@router.get("/stats", response_model=TrackingStatsResponse)
async def get_tracking_stats(
    period: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Tracking istatistikleri"""
    # Base query
    base_query = select(Payslip).where(Payslip.company_id == current_user.company_id)
    
    if period:
        base_query = base_query.where(Payslip.period == period)
    
    # Toplam gonderilen
    sent_query = base_query.where(Payslip.status != PayslipStatus.PENDING)
    sent_result = await db.execute(select(func.count()).select_from(sent_query.subquery()))
    total_sent = sent_result.scalar() or 0
    
    # Acilanlar
    opened_query = base_query.where(Payslip.status.in_([PayslipStatus.OPENED, PayslipStatus.DOWNLOADED]))
    opened_result = await db.execute(select(func.count()).select_from(opened_query.subquery()))
    total_opened = opened_result.scalar() or 0
    
    # Indirilenler
    downloaded_query = base_query.where(Payslip.status == PayslipStatus.DOWNLOADED)
    downloaded_result = await db.execute(select(func.count()).select_from(downloaded_query.subquery()))
    total_downloaded = downloaded_result.scalar() or 0
    
    # Oranlar
    open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
    download_rate = (total_downloaded / total_sent * 100) if total_sent > 0 else 0
    
    return TrackingStatsResponse(
        total_sent=total_sent,
        total_opened=total_opened,
        total_downloaded=total_downloaded,
        open_rate=round(open_rate, 1),
        download_rate=round(download_rate, 1)
    )


@router.get("/report", response_model=TrackingReportResponse)
async def get_tracking_report(
    period: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Donem bazli tracking raporu"""
    # Bordrolari al
    result = await db.execute(
        select(Payslip).where(
            Payslip.company_id == current_user.company_id,
            Payslip.period == period
        ).order_by(Payslip.created_at.desc())
    )
    payslips = result.scalars().all()
    
    # Istatistikler
    stats = await get_tracking_stats(period=period, current_user=current_user, db=db)
    
    # Detayli liste
    payslip_details = []
    for p in payslips:
        # Calisan bilgisi
        emp_result = await db.execute(
            select(Employee).where(Employee.id == p.employee_id)
        )
        emp = emp_result.scalar_one_or_none()
        
        # Tracking olaylari
        events_result = await db.execute(
            select(TrackingEvent).where(TrackingEvent.payslip_id == p.id).order_by(TrackingEvent.created_at)
        )
        events = events_result.scalars().all()
        
        is_opened = any(e.event_type == EventType.EMAIL_OPENED for e in events)
        is_downloaded = any(e.event_type == EventType.PDF_DOWNLOADED for e in events)
        opened_at = next((e.created_at for e in events if e.event_type == EventType.EMAIL_OPENED), None)
        downloaded_at = next((e.created_at for e in events if e.event_type == EventType.PDF_DOWNLOADED), None)
        download_count = sum(1 for e in events if e.event_type == EventType.PDF_DOWNLOADED)
        
        payslip_details.append(PayslipTrackingResponse(
            payslip_id=p.id,
            employee_name=emp.full_name if emp else "Bilinmiyor",
            employee_email=emp.email if emp else "",
            period=p.period,
            status=p.status.value,
            sent_at=p.sent_at,
            is_opened=is_opened,
            opened_at=opened_at,
            is_downloaded=is_downloaded,
            downloaded_at=downloaded_at,
            download_count=download_count,
            events=[TrackingEventResponse(
                id=e.id,
                event_type=e.event_type,
                ip_address=e.ip_address,
                user_agent=e.user_agent,
                created_at=e.created_at
            ) for e in events]
        ))
    
    return TrackingReportResponse(
        period=period,
        stats=stats,
        payslips=payslip_details
    )
