# -*- coding: utf-8 -*-
"""
Payslip API Endpoints
- PDF upload ve bolme
- Toplu mail gonderim
"""

import os
import uuid
import asyncio
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, BackgroundTasks, Body
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, or_
from sqlalchemy.orm import selectinload
import math
import aiofiles

from app.core.database import get_db
from app.core.config import settings
from app.models import User, Employee, Payslip, PayslipStatus, Company, TrackingEvent, EventType
from app.schemas import (
    PayslipResponse,
    PayslipListResponse,
    PayslipUploadResponse,
    PayslipSendRequest,
    PayslipBulkSendResponse,
    PayslipSendResult,
    JobStartResponse,
    JobStatusResponse,
    JobResultItem
)
from app.api.deps import get_current_user
from app.services import PDFService, MailService, job_service, JobStatus
from app.services.excel_service import ExcelService
from app.core.security_utils import sanitize_search_input
from app.core.security import generate_signed_download_url

router = APIRouter(prefix="/payslips", tags=["Payslips"])


@router.get("", response_model=PayslipListResponse)
async def list_payslips(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    period: Optional[str] = Query(None),
    status_filter: Optional[PayslipStatus] = Query(None, alias="status"),
    employee_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="İsim veya TC ile arama"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Payslip).where(Payslip.company_id == current_user.company_id)
    count_query = select(func.count(Payslip.id)).where(Payslip.company_id == current_user.company_id)
    
    if period:
        query = query.where(Payslip.period == period)
        count_query = count_query.where(Payslip.period == period)
    
    if status_filter:
        if status_filter == PayslipStatus.NO_EMPLOYEE:
            # Çalışan yok = employee_id NULL olanlar
            query = query.where(Payslip.employee_id == None)
            count_query = count_query.where(Payslip.employee_id == None)
        else:
            query = query.where(Payslip.status == status_filter)
            count_query = count_query.where(Payslip.status == status_filter)
    
    if employee_id:
        query = query.where(Payslip.employee_id == employee_id)
        count_query = count_query.where(Payslip.employee_id == employee_id)
    
    # Arama filtresi - isim veya TC (Sanitized)
    if search:
        safe_search = sanitize_search_input(search)
        if safe_search:
            search_filter = or_(
                Payslip.extracted_full_name.ilike(f"%{safe_search}%"),
                Payslip.tc_no.ilike(f"%{safe_search}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Payslip.created_at.desc())
    
    result = await db.execute(query)
    payslips = result.scalars().all()
    
    items = []
    for p in payslips:
        # Çalışan bilgisi
        emp = None
        if p.employee_id:
            emp_result = await db.execute(select(Employee).where(Employee.id == p.employee_id))
            emp = emp_result.scalar_one_or_none()
        
        # Tracking olayları
        events_result = await db.execute(
            select(TrackingEvent).where(TrackingEvent.payslip_id == p.id)
        )
        events = events_result.scalars().all()
        
        is_opened = any(e.event_type == EventType.EMAIL_OPENED for e in events)
        is_downloaded = any(e.event_type == EventType.PDF_DOWNLOADED for e in events)
        opened_at = next((e.created_at for e in events if e.event_type == EventType.EMAIL_OPENED), None)
        downloaded_at = next((e.created_at for e in events if e.event_type == EventType.PDF_DOWNLOADED), None)
        download_count = sum(1 for e in events if e.event_type == EventType.PDF_DOWNLOADED)
        
        # İsim ve email belirleme
        if emp:
            display_name = emp.full_name
            display_email = emp.email
        else:
            # PDF'den çıkarılan bilgileri kullan
            display_name = p.extracted_full_name or "Bilinmeyen"
            display_email = None
        
        # TC maskeleme
        tc_masked = f"****{p.tc_no[-4:]}" if p.tc_no and len(p.tc_no) >= 4 else p.tc_no
        
        # İmzalı download URL oluştur
        download_url = generate_signed_download_url(settings.TRACKING_BASE_URL, p.tracking_id)
        
        items.append(PayslipResponse(
            id=p.id,
            employee_id=p.employee_id,
            employee_name=display_name,
            employee_email=display_email,
            period=p.period,
            period_label=p.period_label,
            status=p.status,
            tracking_id=p.tracking_id,
            download_url=download_url,
            sent_at=p.sent_at,
            send_error=p.send_error,
            created_at=p.created_at,
            tc_no=tc_masked,
            extracted_name=display_name if not emp else None,
            is_opened=is_opened,
            is_downloaded=is_downloaded,
            opened_at=opened_at,
            downloaded_at=downloaded_at,
            download_count=download_count,
            has_employee=emp is not None
        ))
    
    return PayslipListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1
    )


@router.post("/upload", response_model=PayslipUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Sadece PDF dosyalari kabul edilir")
    
    temp_path = os.path.join(settings.UPLOAD_DIR, f"temp_{uuid.uuid4().hex}.pdf")
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    
    async with aiofiles.open(temp_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    try:
        pdf_service = PDFService(settings.PDF_OUTPUT_DIR)
        results, errors = pdf_service.process_pdf(temp_path, current_user.company_id, period)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
    # Çalışanları TC'ye göre indexle
    emp_result = await db.execute(
        select(Employee).where(Employee.company_id == current_user.company_id)
    )
    employees = {emp.tc_no: emp for emp in emp_result.scalars().all()}
    
    payslips = []
    no_employee_count = 0
    
    for r in results:
        tc = r["tc_no"]
        emp = employees.get(tc)
        
        # PDF'den çıkarılan ad soyad birleştir
        full_name_parts = []
        if r.get("first_name"):
            full_name_parts.append(r["first_name"])
        if r.get("last_name"):
            full_name_parts.append(r["last_name"])
        extracted_full_name = " ".join(full_name_parts) if full_name_parts else None
        
        # Çalışan bulunsun veya bulunmasın, bordro kaydı oluştur
        new_payslip = Payslip(
            company_id=current_user.company_id,
            employee_id=emp.id if emp else None,  # Çalışan yoksa None
            tc_no=tc,
            extracted_full_name=extracted_full_name,
            period=period,
            period_label=r.get("period_date"),
            pdf_path=r["pdf_path"],
            pdf_password=r["pdf_password"],
            tracking_id=r["tracking_id"],
            status=PayslipStatus.PENDING if emp else PayslipStatus.NO_EMPLOYEE
        )
        db.add(new_payslip)
        await db.flush()
        
        # İsim belirleme (çalışan varsa onun adı, yoksa PDF'den çıkarılan)
        if emp:
            display_name = emp.full_name
            display_email = emp.email
        else:
            display_name = extracted_full_name or "Bilinmeyen"
            display_email = None
            no_employee_count += 1
        
        # TC maskeleme (güvenlik için)
        tc_masked = f"****{tc[-4:]}" if tc and len(tc) >= 4 else tc
        
        payslips.append(PayslipResponse(
            id=new_payslip.id,
            employee_id=emp.id if emp else None,
            employee_name=display_name,
            employee_email=display_email,
            period=period,
            period_label=new_payslip.period_label,
            status=new_payslip.status,
            tracking_id=new_payslip.tracking_id,
            sent_at=None,
            send_error=None,
            created_at=new_payslip.created_at,
            tc_no=tc_masked,
            extracted_name=display_name if not emp else None,
            is_opened=False,
            is_downloaded=False,
            opened_at=None,
            downloaded_at=None,
            download_count=0,
            has_employee=emp is not None
        ))
    
    await db.commit()
    
    # Çalışan bulunamayan kayıtlar için uyarı ekle
    if no_employee_count > 0:
        errors.append(f"⚠️ {no_employee_count} bordro için çalışan bulunamadı (bordro kaydedildi, ancak gönderim için çalışan tanımlanmalı)")
    
    return PayslipUploadResponse(
        total_pages=len(results) + len([e for e in errors if "TC veya isim bulunamadı" in e or "PDF oluşturulamadı" in e]),
        success_count=len(payslips),
        error_count=len(errors),
        payslips=payslips,
        errors=errors
    )


@router.post("/send", response_model=PayslipBulkSendResponse)
async def send_payslips(
    request: PayslipSendRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Bordrolari mail ile gonder - Optimize edilmiş versiyon"""
    # Sirket bilgilerini al
    company_result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = company_result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    if not company.smtp_server or not company.smtp_username or not company.smtp_password:
        raise HTTPException(status_code=400, detail="SMTP ayarlari yapilanmamis")
    
    # Bordrolari ve çalışanları tek sorguda al (N+1 sorgu problemi çözümü)
    payslips_result = await db.execute(
        select(Payslip).options(
            selectinload(Payslip.employee)
        ).where(
            Payslip.id.in_(request.payslip_ids),
            Payslip.company_id == current_user.company_id
        )
    )
    payslips = payslips_result.scalars().all()
    
    if not payslips:
        raise HTTPException(status_code=404, detail="Bordro bulunamadi")
    
    # Daha önce gönderilenleri kontrol et
    already_sent = [p for p in payslips if p.status == PayslipStatus.SENT]
    if already_sent and not request.force_resend:
        # Uyarı dön - frontend'de kullanıcıya gösterilecek
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{len(already_sent)} bordro daha önce gönderilmiş. Tekrar göndermek için onaylayın.",
                "already_sent_count": len(already_sent),
                "already_sent_ids": [p.id for p in already_sent]
            }
        )
    
    # Mail servisi olustur
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
    
    results = []
    success_count = 0
    error_count = 0
    
    try:
        for payslip in payslips:
            # Çalışan zaten yüklendi (selectinload ile)
            employee = payslip.employee
            
            # Önce çalışan kontrolü yap
            if not payslip.employee_id or not employee:
                # Çalışan eşleşmesi yok
                display_name = payslip.extracted_full_name or "Bilinmeyen"
                
                results.append(PayslipSendResult(
                    payslip_id=payslip.id,
                    employee_email="",
                    success=False,
                    error=f"Calisan eslesmesi yok ({display_name} - TC: ****{payslip.tc_no[-4:] if payslip.tc_no else '????'})"
                ))
                error_count += 1
                continue
            
            # Pasif çalışanları atla
            if not employee.is_active:
                results.append(PayslipSendResult(
                    payslip_id=payslip.id,
                    employee_email=employee.email,
                    success=False,
                    error="Calisan pasif durumda"
                ))
                error_count += 1
                continue
            
            # Email kontrolü
            if not employee.email:
                results.append(PayslipSendResult(
                    payslip_id=payslip.id,
                    employee_email="",
                    success=False,
                    error="Calisanin email adresi yok"
                ))
                error_count += 1
                continue
            
            # PDF dosya adini olustur (TC olmadan)
            pdf_filename = f"Bordro_{employee.first_name}_{employee.last_name}_{payslip.period}.pdf"
            
            # Mail gonder
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
                payslip.sent_at = datetime.utcnow()
                payslip.sent_by = current_user.id
                payslip.send_error = None
                
                # Tracking event ekle
                event = TrackingEvent(
                    payslip_id=payslip.id,
                    event_type=EventType.EMAIL_SENT
                )
                db.add(event)
                
                success_count += 1
            else:
                payslip.status = PayslipStatus.FAILED
                payslip.send_error = message
                error_count += 1
            
            results.append(PayslipSendResult(
                payslip_id=payslip.id,
                employee_email=employee.email,
                success=success,
                error=None if success else message
            ))
            
            # Bekleme süresi - sadece çoklu gönderimde uygula (spam koruması)
            if len(payslips) > 1 and company.mail_delay_seconds > 0:
                await asyncio.sleep(company.mail_delay_seconds)
        
        await db.commit()
    finally:
        # SMTP bağlantısını kapat
        await mail_service.close_connection()
    
    return PayslipBulkSendResponse(
        total=len(payslips),
        success_count=success_count,
        error_count=error_count,
        results=results
    )


@router.get("/periods")
async def get_periods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mevcut dönemleri listele"""
    result = await db.execute(
        select(Payslip.period).where(
            Payslip.company_id == current_user.company_id
        ).distinct().order_by(Payslip.period.desc())
    )
    periods = [row[0] for row in result.fetchall()]
    return {"periods": periods}


@router.get("/select/pending")
async def get_pending_payslip_ids(
    period: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Tüm bekleyen (PENDING) bordroların ID'lerini getir"""
    query = select(Payslip.id).where(
        Payslip.company_id == current_user.company_id,
        Payslip.status == PayslipStatus.PENDING,
        Payslip.employee_id.isnot(None)  # Sadece çalışanı olanlar
    )
    
    if period:
        query = query.where(Payslip.period == period)
    
    result = await db.execute(query)
    ids = [row[0] for row in result.fetchall()]
    
    return {"ids": ids, "count": len(ids)}


@router.get("/select/all")
async def get_all_payslip_ids(
    period: Optional[str] = Query(None),
    status_filter: Optional[PayslipStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Tüm bordroların ID'lerini getir (filtreli)"""
    query = select(Payslip.id).where(
        Payslip.company_id == current_user.company_id
    )
    
    if period:
        query = query.where(Payslip.period == period)
    
    if status_filter:
        query = query.where(Payslip.status == status_filter)
    
    result = await db.execute(query)
    ids = [row[0] for row in result.fetchall()]
    
    return {"ids": ids, "count": len(ids)}


@router.post("/bulk-delete")
async def bulk_delete_payslips(
    payslip_ids: List[int] = Body(..., embed=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toplu bordro silme"""
    if not payslip_ids:
        raise HTTPException(status_code=400, detail="Silinecek bordro seçilmedi")
    
    result = await db.execute(
        select(Payslip).where(
            Payslip.id.in_(payslip_ids),
            Payslip.company_id == current_user.company_id
        )
    )
    payslips = result.scalars().all()
    
    deleted_count = 0
    for payslip in payslips:
        # Önce tracking eventlerini sil
        await db.execute(
            delete(TrackingEvent).where(TrackingEvent.payslip_id == payslip.id)
        )
        
        # PDF dosyasını sil
        if payslip.pdf_path and os.path.exists(payslip.pdf_path):
            try:
                os.remove(payslip.pdf_path)
            except:
                pass
        await db.delete(payslip)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"{deleted_count} bordro silindi",
        "deleted_count": deleted_count
    }


@router.delete("/all")
async def delete_all_payslips(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Tüm bordroları sil"""
    result = await db.execute(
        select(Payslip).where(Payslip.company_id == current_user.company_id)
    )
    payslips = result.scalars().all()
    
    deleted_count = 0
    for payslip in payslips:
        # Önce tracking eventlerini sil
        await db.execute(
            delete(TrackingEvent).where(TrackingEvent.payslip_id == payslip.id)
        )
        
        if payslip.pdf_path and os.path.exists(payslip.pdf_path):
            try:
                os.remove(payslip.pdf_path)
            except:
                pass
        await db.delete(payslip)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"{deleted_count} bordro silindi",
        "deleted_count": deleted_count
    }


@router.delete("/period/{period}")
async def delete_period_payslips(
    period: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Belirli bir dönemin tüm bordrolarını sil"""
    result = await db.execute(
        select(Payslip).where(
            Payslip.period == period,
            Payslip.company_id == current_user.company_id
        )
    )
    payslips = result.scalars().all()
    
    deleted_count = 0
    for payslip in payslips:
        # Önce tracking eventlerini sil
        await db.execute(
            delete(TrackingEvent).where(TrackingEvent.payslip_id == payslip.id)
        )
        
        if payslip.pdf_path and os.path.exists(payslip.pdf_path):
            try:
                os.remove(payslip.pdf_path)
            except:
                pass
        await db.delete(payslip)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"{deleted_count} bordro silindi",
        "deleted_count": deleted_count
    }


@router.delete("/{payslip_id}")
async def delete_payslip(
    payslip_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Bordro sil"""
    result = await db.execute(
        select(Payslip).where(
            Payslip.id == payslip_id,
            Payslip.company_id == current_user.company_id
        )
    )
    payslip = result.scalar_one_or_none()
    
    if not payslip:
        raise HTTPException(status_code=404, detail="Bordro bulunamadi")
    
    # Önce tracking eventlerini sil
    await db.execute(
        delete(TrackingEvent).where(TrackingEvent.payslip_id == payslip.id)
    )
    
    # PDF dosyasini sil
    if payslip.pdf_path and os.path.exists(payslip.pdf_path):
        try:
            os.remove(payslip.pdf_path)
        except:
            pass
    
    await db.delete(payslip)
    await db.commit()
    
    return {"message": "Bordro silindi"}


@router.get("/report/period/{period}")
async def download_period_report(
    period: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Dönem bazlı bordro raporunu Excel olarak indir"""
    from io import BytesIO
    
    # Bordroları al
    result = await db.execute(
        select(Payslip).where(
            Payslip.period == period,
            Payslip.company_id == current_user.company_id
        ).order_by(Payslip.created_at.desc())
    )
    payslips = result.scalars().all()
    
    if not payslips:
        raise HTTPException(status_code=404, detail="Bu dönemde bordro bulunamadı")
    
    # Rapor verilerini hazırla
    report_data = []
    for p in payslips:
        # Çalışan bilgisi
        emp = None
        if p.employee_id:
            emp_result = await db.execute(select(Employee).where(Employee.id == p.employee_id))
            emp = emp_result.scalar_one_or_none()
        
        # Tracking olayları
        events_result = await db.execute(
            select(TrackingEvent).where(TrackingEvent.payslip_id == p.id)
        )
        events = events_result.scalars().all()
        
        # Okunma ve indirme bilgileri
        opened_at = next((e.created_at for e in events if e.event_type == EventType.EMAIL_OPENED), None)
        downloaded_at = next((e.created_at for e in events if e.event_type == EventType.PDF_DOWNLOADED), None)
        download_count = sum(1 for e in events if e.event_type == EventType.PDF_DOWNLOADED)
        
        # İsim belirleme
        if emp:
            display_name = emp.full_name
            display_email = emp.email
        else:
            display_name = p.extracted_full_name or "Bilinmeyen"
            display_email = "-"
        
        # Durum belirleme
        if p.status == PayslipStatus.SENT:
            status = "Başarılı"
        elif p.status == PayslipStatus.NO_EMPLOYEE:
            status = "Çalışan Yok"
        elif p.status == PayslipStatus.FAILED:
            status = "Hatalı"
        else:
            status = "Bekliyor"
        
        report_data.append({
            "employee_name": display_name,
            "employee_email": display_email,
            "tc_no": p.tc_no,
            "period": p.period_label or p.period,
            "status": status,
            "error": p.send_error,
            "sent_at": p.sent_at,
            "opened_at": opened_at,
            "downloaded_at": downloaded_at,
            "download_count": download_count
        })
    
    # Excel oluştur
    excel_service = ExcelService()
    excel_content = excel_service.create_send_report(report_data)
    
    # Dosya adı
    filename = f"bordro_rapor_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/send-with-report", response_model=PayslipBulkSendResponse)
async def send_payslips_with_report(
    request: PayslipSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Bordroları mail ile gönder ve rapor oluştur.
    Bu endpoint send ile aynı işi yapar ama sonuç olarak rapor indirme linki de döner.
    """
    # Önce normal send işlemini yap
    company_result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = company_result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    if not company.smtp_server or not company.smtp_username or not company.smtp_password:
        raise HTTPException(status_code=400, detail="SMTP ayarlari yapilanmamis")
    
    # Bordrolari al
    payslips_result = await db.execute(
        select(Payslip).where(
            Payslip.id.in_(request.payslip_ids),
            Payslip.company_id == current_user.company_id
        )
    )
    payslips = payslips_result.scalars().all()
    
    if not payslips:
        raise HTTPException(status_code=404, detail="Bordro bulunamadi")
    
    # Mail servisi olustur
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
    
    results = []
    success_count = 0
    error_count = 0
    
    for payslip in payslips:
        if not payslip.employee_id:
            display_name = payslip.extracted_full_name or "Bilinmeyen"
            
            results.append(PayslipSendResult(
                payslip_id=payslip.id,
                employee_email="",
                success=False,
                error=f"Calisan eslesmesi yok ({display_name})"
            ))
            error_count += 1
            continue
        
        emp_result = await db.execute(
            select(Employee).where(Employee.id == payslip.employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        
        if not employee:
            results.append(PayslipSendResult(
                payslip_id=payslip.id,
                employee_email="",
                success=False,
                error="Calisan bulunamadi"
            ))
            error_count += 1
            continue
        
        if not employee.is_active:
            results.append(PayslipSendResult(
                payslip_id=payslip.id,
                employee_email=employee.email,
                success=False,
                error="Calisan pasif durumda"
            ))
            error_count += 1
            continue
        
        if not employee.email:
            results.append(PayslipSendResult(
                payslip_id=payslip.id,
                employee_email="",
                success=False,
                error="Calisanin email adresi yok"
            ))
            error_count += 1
            continue
        
        pdf_filename = f"Bordro_{employee.first_name}_{employee.last_name}_{payslip.period}.pdf"
        
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
            payslip.sent_at = datetime.now(timezone.utc)
            payslip.sent_by = current_user.id
            payslip.send_error = None
            
            event = TrackingEvent(
                payslip_id=payslip.id,
                event_type=EventType.EMAIL_SENT
            )
            db.add(event)
            
            success_count += 1
        else:
            payslip.status = PayslipStatus.FAILED
            payslip.send_error = message
            error_count += 1
        
        results.append(PayslipSendResult(
            payslip_id=payslip.id,
            employee_email=employee.email,
            success=success,
            error=None if success else message
        ))
        
        await asyncio.sleep(company.mail_delay_seconds)
    
    await db.commit()
    
    return PayslipBulkSendResponse(
        total=len(payslips),
        success_count=success_count,
        error_count=error_count,
        results=results
    )
