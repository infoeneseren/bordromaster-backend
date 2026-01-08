# -*- coding: utf-8 -*-
"""
Settings API Endpoints
- Sirket ayarlari
- SMTP ayarlari
- Logo yukleme
- Mail önizleme
"""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles

from app.core.database import get_db
from app.core.config import settings
from app.models import User, Company
from app.schemas import (
    CompanyResponse,
    CompanyDetailResponse,
    CompanyUpdate,
    CompanySMTPUpdate,
    CompanyMailTemplateUpdate,
    CompanySMTPTest,
    MailPreviewRequest,
    MailPreviewResponse
)
from app.api.deps import get_current_user, get_current_admin_user
from app.services import MailService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/company", response_model=CompanyDetailResponse)
async def get_company_settings(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Sirket ayarlarini al (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    return CompanyDetailResponse(
        id=company.id,
        name=company.name,
        logo_path=company.logo_path,
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
        smtp_server=company.smtp_server,
        smtp_port=company.smtp_port,
        smtp_username=company.smtp_username,
        smtp_use_tls=company.smtp_use_tls,
        smtp_sender_name=company.smtp_sender_name,
        mail_subject=company.mail_subject,
        mail_body=company.mail_body,
        mail_delay_seconds=company.mail_delay_seconds,
        mail_batch_size=company.mail_batch_size,
        mail_batch_delay=company.mail_batch_delay,
        tracking_base_url=company.tracking_base_url,
        # Renk ayarları
        mail_primary_color=company.mail_primary_color or "#3b82f6",
        mail_secondary_color=company.mail_secondary_color or "#1e40af",
        mail_background_color=company.mail_background_color or "#f8fafc",
        mail_text_color=company.mail_text_color or "#1e293b",
        mail_header_text_color=company.mail_header_text_color or "#ffffff",
        mail_footer_text=company.mail_footer_text or "Bu mail otomatik olarak gönderilmiştir.\nLütfen yanıtlamayınız.",
        mail_show_logo=company.mail_show_logo if company.mail_show_logo is not None else True,
        mail_logo_width=company.mail_logo_width or 150
    )


@router.put("/company", response_model=CompanyResponse)
async def update_company(
    data: CompanyUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Sirket bilgilerini guncelle (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    
    await db.commit()
    await db.refresh(company)
    
    return CompanyResponse.model_validate(company)


@router.put("/smtp")
async def update_smtp_settings(
    data: CompanySMTPUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """SMTP ayarlarini guncelle (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    
    await db.commit()
    
    return {"message": "SMTP ayarlari guncellendi"}


@router.post("/smtp/test")
async def test_smtp_connection(
    data: CompanySMTPTest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """SMTP baglantisini test et (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    if not company.smtp_server or not company.smtp_username or not company.smtp_password:
        raise HTTPException(status_code=400, detail="SMTP ayarlari eksik")
    
    mail_service = MailService(
        smtp_server=company.smtp_server,
        smtp_port=company.smtp_port,
        smtp_username=company.smtp_username,
        smtp_password=company.smtp_password,
        use_tls=company.smtp_use_tls,
        sender_name=company.smtp_sender_name
    )
    
    success, message = await mail_service.send_test_email(data.test_email)
    
    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.put("/mail-template")
async def update_mail_template(
    data: CompanyMailTemplateUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Mail sablonunu guncelle (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    
    await db.commit()
    
    return {"message": "Mail sablonu guncellendi"}


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Logo yukle (admin only)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dosya adi gerekli")
    
    ext = file.filename.lower().split(".")[-1]
    if ext not in ["png", "jpg", "jpeg", "svg", "webp"]:
        raise HTTPException(status_code=400, detail="Gecersiz dosya formati")
    
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    # Eski logoyu sil
    if company.logo_path and os.path.exists(company.logo_path):
        os.remove(company.logo_path)
    
    # Yeni logo kaydet
    logo_dir = os.path.join(settings.LOGO_DIR, str(current_user.company_id))
    os.makedirs(logo_dir, exist_ok=True)
    
    filename = f"logo_{uuid.uuid4().hex}.{ext}"
    logo_path = os.path.join(logo_dir, filename)
    
    async with aiofiles.open(logo_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    company.logo_path = logo_path
    await db.commit()
    
    return {"message": "Logo yuklendi", "logo_path": logo_path}


@router.get("/logo")
async def get_logo(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Şirket logosunu al"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company or not company.logo_path:
        raise HTTPException(status_code=404, detail="Logo bulunamadi")
    
    if not os.path.exists(company.logo_path):
        raise HTTPException(status_code=404, detail="Logo dosyasi bulunamadi")
    
    return FileResponse(company.logo_path)


@router.delete("/logo")
async def delete_logo(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Logoyu sil (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    if company.logo_path and os.path.exists(company.logo_path):
        os.remove(company.logo_path)
    
    company.logo_path = None
    await db.commit()
    
    return {"message": "Logo silindi"}


@router.post("/mail-preview", response_model=MailPreviewResponse)
async def get_mail_preview(
    data: MailPreviewRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Mail şablonu önizlemesi oluştur (admin only)"""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Sirket bulunamadi")
    
    # Mail servisi oluştur
    mail_service = MailService(
        smtp_server=company.smtp_server or "",
        smtp_port=company.smtp_port or 587,
        smtp_username=company.smtp_username or "",
        smtp_password="",
        use_tls=company.smtp_use_tls,
        sender_name=company.smtp_sender_name,
        company_name=company.name,
        logo_path=company.logo_path,
        primary_color=company.mail_primary_color or "#3b82f6",
        secondary_color=company.mail_secondary_color or "#1e40af",
        background_color=company.mail_background_color or "#f8fafc",
        text_color=company.mail_text_color or "#1e293b",
        header_text_color=company.mail_header_text_color or "#ffffff",
        footer_text=company.mail_footer_text or "Bu mail otomatik olarak gönderilmiştir.\nLütfen yanıtlamayınız.",
        disclaimer_text=company.mail_disclaimer_text or "Bu butona tıklayarak, bordronuzu görüntülediğinizi ve onaylayarak teslim aldığınızı beyan etmiş olursunuz.",
        show_logo=company.mail_show_logo if company.mail_show_logo is not None else True,
        logo_width=company.mail_logo_width or 150
    )
    
    # Önizleme HTML'i oluştur
    html_content = mail_service.generate_preview_html(
        body_template=company.mail_body or "Sayın {name},\n\n{period} dönemi bordronuz ekte yer almaktadır.\n\nSaygılarımızla",
        employee_name=data.employee_name,
        period=data.period
    )
    
    # Konu oluştur
    subject = (company.mail_subject or "{period} Dönemi Bordronuz").replace("{name}", data.employee_name).replace("{period}", data.period)
    
    return MailPreviewResponse(
        subject=subject,
        html_content=html_content
    )
