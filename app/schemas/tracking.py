# -*- coding: utf-8 -*-
"""
Pydantic Schemas - Tracking (Takip)
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.tracking import EventType


class TrackingEventResponse(BaseModel):
    """Takip olayı response şeması"""
    id: int
    event_type: EventType
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class TrackingStatsResponse(BaseModel):
    """Tracking istatistikleri şeması"""
    total_sent: int
    total_opened: int
    total_downloaded: int
    open_rate: float  # Yüzde
    download_rate: float  # Yüzde


class PayslipTrackingResponse(BaseModel):
    """Bordro tracking detayı şeması"""
    payslip_id: int
    employee_name: str
    employee_email: str
    period: str
    status: str
    sent_at: Optional[datetime] = None
    is_opened: bool
    opened_at: Optional[datetime] = None
    is_downloaded: bool
    downloaded_at: Optional[datetime] = None
    download_count: int
    events: List[TrackingEventResponse]


class TrackingReportResponse(BaseModel):
    """Tracking rapor şeması"""
    period: str
    stats: TrackingStatsResponse
    payslips: List[PayslipTrackingResponse]



