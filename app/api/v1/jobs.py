# -*- coding: utf-8 -*-
"""
Jobs API Endpoints
- Background job durumu sorgulama
- Mail gönderim işleri
"""

import asyncio
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.config import settings
from app.models import User, Employee, Payslip, PayslipStatus, Company, TrackingEvent, EventType
from app.schemas import (
    PayslipSendRequest,
    JobStartResponse,
    JobStatusResponse,
    JobResultItem
)
from app.api.deps import get_current_user
from app.services import MailService, job_service, JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])


async def process_mail_job(
    job_id: str,
    payslip_ids: List[int],
    company_id: int,
    user_id: int,
    force_resend: bool = False
):
    """Background'da mail gönderim işini yürüt"""
    from app.core.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        try:
            # Job'u running yap
            await job_service.update_job(job_id, status=JobStatus.RUNNING)
            
            # Şirket bilgilerini al
            company_result = await db.execute(
                select(Company).where(Company.id == company_id)
            )
            company = company_result.scalar_one_or_none()
            
            if not company:
                await job_service.update_job(
                    job_id, 
                    status=JobStatus.FAILED, 
                    error_message="Şirket bulunamadı"
                )
                return
            
            # Bordroları al
            payslips_result = await db.execute(
                select(Payslip).options(
                    selectinload(Payslip.employee)
                ).where(
                    Payslip.id.in_(payslip_ids),
                    Payslip.company_id == company_id
                )
            )
            payslips = payslips_result.scalars().all()
            
            if not payslips:
                await job_service.update_job(
                    job_id, 
                    status=JobStatus.FAILED, 
                    error_message="Bordro bulunamadı"
                )
                return
            
            # Mail servisi oluştur
            mail_service = MailService(
                smtp_server=company.smtp_server,
                smtp_port=company.smtp_port,
                smtp_username=company.smtp_username,
                smtp_password=company.smtp_password,
                use_tls=company.smtp_use_tls,
                sender_name=company.smtp_sender_name,
                tracking_base_url=company.tracking_base_url,
                company_name=company.name,
                logo_path=company.logo_path,
                primary_color=company.mail_primary_color or "#3b82f6",
                secondary_color=company.mail_secondary_color or "#1e40af",
                background_color=company.mail_background_color or "#f8fafc",
                text_color=company.mail_text_color or "#1e293b",
                header_text_color=company.mail_header_text_color or "#ffffff",
                footer_text=company.mail_footer_text or "Bu mail otomatik olarak gönderilmiştir.\nLütfen yanıtlamayınız.",
                disclaimer_text=company.mail_disclaimer_text or "",
                show_logo=company.mail_show_logo if company.mail_show_logo is not None else True,
                logo_width=company.mail_logo_width or 150
            )
            
            try:
                for payslip in payslips:
                    employee = payslip.employee
                    
                    # Çalışan kontrolü
                    if not payslip.employee_id or not employee:
                        display_name = payslip.extracted_full_name or "Bilinmeyen"
                        await job_service.increment_progress(
                            job_id,
                            success=False,
                            result={
                                "payslip_id": payslip.id,
                                "employee_email": "",
                                "success": False,
                                "error": f"Çalışan eşleşmesi yok ({display_name})"
                            }
                        )
                        continue
                    
                    # Pasif çalışan kontrolü
                    if not employee.is_active:
                        await job_service.increment_progress(
                            job_id,
                            success=False,
                            result={
                                "payslip_id": payslip.id,
                                "employee_email": employee.email or "",
                                "success": False,
                                "error": "Çalışan pasif durumda"
                            }
                        )
                        continue
                    
                    # Email kontrolü
                    if not employee.email:
                        await job_service.increment_progress(
                            job_id,
                            success=False,
                            result={
                                "payslip_id": payslip.id,
                                "employee_email": "",
                                "success": False,
                                "error": "Çalışanın email adresi yok"
                            }
                        )
                        continue
                    
                    # Daha önce gönderilmiş mi kontrol et
                    if payslip.status == PayslipStatus.SENT and not force_resend:
                        await job_service.increment_progress(
                            job_id,
                            success=True,
                            result={
                                "payslip_id": payslip.id,
                                "employee_email": employee.email,
                                "success": True,
                                "error": None
                            }
                        )
                        continue
                    
                    # PDF dosya adı
                    pdf_filename = f"Bordro_{employee.first_name}_{employee.last_name}_{payslip.period}.pdf"
                    
                    # Mail gönder
                    success, message = await mail_service.send_payslip_email(
                        to_email=employee.email,
                        employee_name=employee.full_name,
                        period=payslip.period_label or payslip.period,
                        pdf_path=payslip.pdf_path,
                        pdf_filename=pdf_filename,
                        tracking_id=payslip.tracking_id,
                        subject_template=company.mail_subject,
                        body_template=company.mail_body
                    )
                    
                    if success:
                        payslip.status = PayslipStatus.SENT
                        # Timezone-naive datetime kullan (PostgreSQL uyumluluğu için)
                        payslip.sent_at = datetime.utcnow()
                        payslip.sent_by = user_id
                        payslip.send_error = None
                        
                        # Tracking event ekle
                        event = TrackingEvent(
                            payslip_id=payslip.id,
                            event_type=EventType.EMAIL_SENT
                        )
                        db.add(event)
                    else:
                        payslip.status = PayslipStatus.FAILED
                        payslip.send_error = message
                    
                    await job_service.increment_progress(
                        job_id,
                        success=success,
                        result={
                            "payslip_id": payslip.id,
                            "employee_email": employee.email,
                            "success": success,
                            "error": None if success else message
                        }
                    )
                    
                    # SMTP rate limit koruması için dinamik bekleme
                    if len(payslips) > 1:
                        # Rate limit hatası alındıysa daha uzun bekle (ENV'den al)
                        if not success and ("450" in message or "Too many" in message):
                            # Rate limit - ENV'den belirlenen süre kadar bekle
                            await asyncio.sleep(settings.MAIL_RATE_LIMIT_DELAY)
                        else:
                            # Normal bekleme - Önce şirket ayarı, yoksa ENV
                            delay = company.mail_delay_seconds if company.mail_delay_seconds > 0 else settings.MAIL_DELAY_SECONDS
                            if delay > 0:
                                await asyncio.sleep(delay)
                
                await db.commit()
                
            finally:
                await mail_service.close_connection()
            
            # Job'u tamamlandı olarak işaretle
            await job_service.update_job(job_id, status=JobStatus.COMPLETED)
            
        except Exception as e:
            await job_service.update_job(
                job_id, 
                status=JobStatus.FAILED, 
                error_message=str(e)
            )


@router.post("/send", response_model=JobStartResponse)
async def start_send_job(
    request: PayslipSendRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mail gönderim işini başlat - Hemen job_id döner, gönderim arka planda devam eder.
    Cloudflare timeout sorununu çözer.
    """
    # Şirket kontrolü
    company_result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = company_result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı")
    
    if not company.smtp_server or not company.smtp_username or not company.smtp_password:
        raise HTTPException(status_code=400, detail="SMTP ayarları yapılandırılmamış")
    
    # Bordro sayısını kontrol et
    payslips_result = await db.execute(
        select(Payslip).where(
            Payslip.id.in_(request.payslip_ids),
            Payslip.company_id == current_user.company_id
        )
    )
    payslips = payslips_result.scalars().all()
    
    if not payslips:
        raise HTTPException(status_code=404, detail="Bordro bulunamadı")
    
    # Daha önce gönderilenleri kontrol et
    already_sent = [p for p in payslips if p.status == PayslipStatus.SENT]
    if already_sent and not request.force_resend:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{len(already_sent)} bordro daha önce gönderilmiş. Tekrar göndermek için onaylayın.",
                "already_sent_count": len(already_sent),
                "already_sent_ids": [p.id for p in already_sent]
            }
        )
    
    # Job oluştur
    job_id = await job_service.create_job(
        job_type="mail_send",
        total_items=len(payslips),
        company_id=current_user.company_id,
        user_id=current_user.id,
        metadata={"force_resend": request.force_resend}
    )
    
    # Background task başlat
    background_tasks.add_task(
        process_mail_job,
        job_id,
        request.payslip_ids,
        current_user.company_id,
        current_user.id,
        request.force_resend
    )
    
    return JobStartResponse(
        job_id=job_id,
        message=f"{len(payslips)} bordro gönderimi başlatıldı",
        total=len(payslips)
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Job durumunu sorgula"""
    job = await job_service.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job bulunamadı")
    
    # Sadece kendi şirketinin job'larını görebilsin
    if job.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=403, detail="Bu job'a erişim yetkiniz yok")
    
    total = job.get("total", 0)
    completed = job.get("completed", 0)
    progress_percent = (completed / total * 100) if total > 0 else 0
    
    # Results'ı JobResultItem'a dönüştür
    results = []
    for r in job.get("results", []):
        results.append(JobResultItem(
            payslip_id=r.get("payslip_id", 0),
            employee_email=r.get("employee_email", ""),
            success=r.get("success", False),
            error=r.get("error")
        ))
    
    return JobStatusResponse(
        id=job["id"],
        status=JobStatus(job["status"]),
        total=total,
        completed=completed,
        success_count=job.get("success_count", 0),
        error_count=job.get("error_count", 0),
        progress_percent=round(progress_percent, 1),
        results=results,
        created_at=job.get("created_at"),
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        error_message=job.get("error_message")
    )

