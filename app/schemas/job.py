# -*- coding: utf-8 -*-
"""
Job Schemas - Background işler için şemalar
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from enum import Enum


class JobStatus(str, Enum):
    """Job durumları"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStartResponse(BaseModel):
    """Job başlatma yanıtı"""
    job_id: str
    message: str
    total: int


class JobResultItem(BaseModel):
    """Tek bir işlem sonucu"""
    payslip_id: int
    employee_email: str
    success: bool
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Job durum yanıtı"""
    id: str
    status: JobStatus
    total: int
    completed: int
    success_count: int
    error_count: int
    progress_percent: float
    results: List[JobResultItem] = []
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None

