# -*- coding: utf-8 -*-
"""
Employee API Endpoints
- Employee CRUD
- Excel import
"""

import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete
import math

from app.core.database import get_db
from app.models import User, Employee, Payslip, TrackingEvent
from app.schemas import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    EmployeeImportResult
)
from app.api.deps import get_current_user
from app.services.excel_service import ExcelService
from app.core.security_utils import sanitize_search_input

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("", response_model=EmployeeListResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Çalışanları listele"""
    # Base query
    query = select(Employee).where(Employee.company_id == current_user.company_id)
    count_query = select(func.count(Employee.id)).where(Employee.company_id == current_user.company_id)
    
    # Arama filtresi (Sanitized)
    if search:
        safe_search = sanitize_search_input(search)
        if safe_search:
            search_filter = or_(
                Employee.first_name.ilike(f"%{safe_search}%"),
                Employee.last_name.ilike(f"%{safe_search}%"),
                Employee.email.ilike(f"%{safe_search}%"),
                Employee.tc_no.ilike(f"%{safe_search}%"),
                Employee.department.ilike(f"%{safe_search}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)
    
    # Aktiflik filtresi
    if is_active is not None:
        query = query.where(Employee.is_active == is_active)
        count_query = count_query.where(Employee.is_active == is_active)
    
    # Toplam sayı
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Sayfalama
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Employee.last_name, Employee.first_name)
    
    result = await db.execute(query)
    employees = result.scalars().all()
    
    # Response hazırla
    items = []
    for emp in employees:
        items.append(EmployeeResponse(
            id=emp.id,
            tc_no=emp.tc_no,
            tc_masked=emp.tc_masked,
            email=emp.email,
            first_name=emp.first_name,
            last_name=emp.last_name,
            full_name=emp.full_name,
            department=emp.department,
            is_active=emp.is_active,
            created_at=emp.created_at
        ))
    
    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1
    )


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    employee_data: EmployeeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Yeni çalışan oluştur"""
    # TC kontrolü (aynı şirkette)
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == current_user.company_id,
            Employee.tc_no == employee_data.tc_no
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu TC kimlik numarası zaten kayıtlı"
        )
    
    # Çalışan oluştur
    new_employee = Employee(
        company_id=current_user.company_id,
        tc_no=employee_data.tc_no,
        email=employee_data.email,
        first_name=employee_data.first_name,
        last_name=employee_data.last_name,
        department=employee_data.department,
        is_active=True
    )
    
    db.add(new_employee)
    await db.commit()
    await db.refresh(new_employee)
    
    return EmployeeResponse(
        id=new_employee.id,
        tc_no=new_employee.tc_no,
        tc_masked=new_employee.tc_masked,
        email=new_employee.email,
        first_name=new_employee.first_name,
        last_name=new_employee.last_name,
        full_name=new_employee.full_name,
        department=new_employee.department,
        is_active=new_employee.is_active,
        created_at=new_employee.created_at
    )


@router.get("/select/all")
async def get_all_employee_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Tüm çalışan ID'lerini getir (toplu seçim için)"""
    result = await db.execute(
        select(Employee.id).where(Employee.company_id == current_user.company_id)
    )
    ids = [row[0] for row in result.fetchall()]
    return {"ids": ids, "count": len(ids)}


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Çalışan detayı"""
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.company_id == current_user.company_id
        )
    )
    employee = result.scalar_one_or_none()
    
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Çalışan bulunamadı"
        )
    
    return EmployeeResponse(
        id=employee.id,
        tc_no=employee.tc_no,
        tc_masked=employee.tc_masked,
        email=employee.email,
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=employee.full_name,
        department=employee.department,
        is_active=employee.is_active,
        created_at=employee.created_at
    )


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    employee_data: EmployeeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Çalışan güncelle"""
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.company_id == current_user.company_id
        )
    )
    employee = result.scalar_one_or_none()
    
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Çalışan bulunamadı"
        )
    
    # Güncelle
    update_data = employee_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(employee, field, value)
    
    await db.commit()
    await db.refresh(employee)
    
    return EmployeeResponse(
        id=employee.id,
        tc_no=employee.tc_no,
        tc_masked=employee.tc_masked,
        email=employee.email,
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=employee.full_name,
        department=employee.department,
        is_active=employee.is_active,
        created_at=employee.created_at
    )


@router.post("/import", response_model=EmployeeImportResult)
async def import_employees(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Excel'den çalışan içe aktar"""
    # Dosya uzantısı kontrolü
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dosya adı gerekli"
        )
    
    ext = file.filename.lower().split(".")[-1]
    if ext not in ["xlsx", "xls"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sadece Excel dosyaları (.xlsx, .xls) kabul edilir"
        )
    
    # Excel'i oku
    excel_service = ExcelService()
    content = await file.read()
    
    try:
        employees_data, errors = excel_service.read_employees_from_excel(content, ext)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel okuma hatası: {str(e)}"
        )
    
    # Mevcut TC'leri al
    result = await db.execute(
        select(Employee.tc_no).where(Employee.company_id == current_user.company_id)
    )
    existing_tcs = set(row[0] for row in result.fetchall())
    
    # Çalışanları ekle
    success_count = 0
    for emp_data in employees_data:
        if emp_data["tc_no"] in existing_tcs:
            errors.append(f"TC {emp_data['tc_no'][-4:]}****: Zaten kayıtlı")
            continue
        
        new_employee = Employee(
            company_id=current_user.company_id,
            tc_no=emp_data["tc_no"],
            email=emp_data["email"],
            first_name=emp_data.get("first_name"),
            last_name=emp_data.get("last_name"),
            department=emp_data.get("department"),
            is_active=True
        )
        db.add(new_employee)
        existing_tcs.add(emp_data["tc_no"])
        success_count += 1
    
    await db.commit()
    
    return EmployeeImportResult(
        success_count=success_count,
        error_count=len(errors),
        errors=errors
    )


@router.post("/bulk-delete")
async def bulk_delete_employees(
    employee_ids: List[int] = Body(..., embed=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toplu çalışan silme - İlişkili bordrolar da silinir"""
    if not employee_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Silinecek çalışan seçilmedi"
        )
    
    # Çalışanları al
    result = await db.execute(
        select(Employee).where(
            Employee.id.in_(employee_ids),
            Employee.company_id == current_user.company_id
        )
    )
    employees = result.scalars().all()
    
    if not employees:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Silinecek çalışan bulunamadı"
        )
    
    deleted_count = 0
    deleted_payslips = 0
    
    for emp in employees:
        # Önce çalışana ait bordroları bul
        payslips_result = await db.execute(
            select(Payslip).where(Payslip.employee_id == emp.id)
        )
        payslips = payslips_result.scalars().all()
        
        # Her bordro için tracking eventleri ve PDF dosyalarını sil
        for payslip in payslips:
            # Tracking eventlerini sil
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
            deleted_payslips += 1
        
        # Çalışanı sil
        await db.delete(emp)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"{deleted_count} çalışan ve {deleted_payslips} bordro silindi",
        "deleted_count": deleted_count,
        "deleted_payslips": deleted_payslips
    }


@router.delete("/all")
async def delete_all_employees(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Tüm çalışanları sil - İlişkili bordrolar da silinir"""
    # Önce şirkete ait tüm bordroları bul
    payslips_result = await db.execute(
        select(Payslip).where(Payslip.company_id == current_user.company_id)
    )
    payslips = payslips_result.scalars().all()
    
    deleted_payslips = 0
    
    # Her bordro için tracking eventleri ve PDF dosyalarını sil
    for payslip in payslips:
        # Tracking eventlerini sil
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
        deleted_payslips += 1
    
    # Şimdi çalışanları sil
    result = await db.execute(
        select(Employee).where(Employee.company_id == current_user.company_id)
    )
    employees = result.scalars().all()
    
    deleted_count = 0
    for emp in employees:
        await db.delete(emp)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"{deleted_count} çalışan ve {deleted_payslips} bordro silindi",
        "deleted_count": deleted_count,
        "deleted_payslips": deleted_payslips
    }


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Çalışan sil - İlişkili bordrolar da silinir"""
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.company_id == current_user.company_id
        )
    )
    employee = result.scalar_one_or_none()
    
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Çalışan bulunamadı"
        )
    
    # Önce çalışana ait bordroları bul
    payslips_result = await db.execute(
        select(Payslip).where(Payslip.employee_id == employee_id)
    )
    payslips = payslips_result.scalars().all()
    
    deleted_payslips = 0
    
    # Her bordro için tracking eventleri ve PDF dosyalarını sil
    for payslip in payslips:
        # Tracking eventlerini sil
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
        deleted_payslips += 1
    
    # Çalışanı sil
    await db.delete(employee)
    await db.commit()
    
    return {
        "message": f"Çalışan ve {deleted_payslips} bordro silindi",
        "deleted_payslips": deleted_payslips
    }



