# -*- coding: utf-8 -*-
"""
Schemas package exports
"""

from .auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetConfirm
)

from .user import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserPasswordUpdate,
    UserResponse,
    UserMeResponse
)

from .company import (
    CompanyBase,
    CompanyCreate,
    CompanyUpdate,
    CompanySMTPUpdate,
    CompanyMailTemplateUpdate,
    CompanyResponse,
    CompanyDetailResponse,
    CompanySMTPTest,
    MailPreviewRequest,
    MailPreviewResponse
)

from .employee import (
    EmployeeBase,
    EmployeeCreate,
    EmployeeBulkCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    EmployeeImportResult
)

from .payslip import (
    PayslipBase,
    PayslipCreate,
    PayslipResponse,
    PayslipListResponse,
    PayslipUploadResponse,
    PayslipSendRequest,
    PayslipSendResult,
    PayslipBulkSendResponse
)

from .tracking import (
    TrackingEventResponse,
    TrackingStatsResponse,
    PayslipTrackingResponse,
    TrackingReportResponse
)

from .job import (
    JobStatus,
    JobStartResponse,
    JobResultItem,
    JobStatusResponse
)

__all__ = [
    # Auth
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    # User
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserPasswordUpdate",
    "UserResponse",
    "UserMeResponse",
    # Company
    "CompanyBase",
    "CompanyCreate",
    "CompanyUpdate",
    "CompanySMTPUpdate",
    "CompanyMailTemplateUpdate",
    "CompanyResponse",
    "CompanyDetailResponse",
    "CompanySMTPTest",
    "MailPreviewRequest",
    "MailPreviewResponse",
    # Employee
    "EmployeeBase",
    "EmployeeCreate",
    "EmployeeBulkCreate",
    "EmployeeUpdate",
    "EmployeeResponse",
    "EmployeeListResponse",
    "EmployeeImportResult",
    # Payslip
    "PayslipBase",
    "PayslipCreate",
    "PayslipResponse",
    "PayslipListResponse",
    "PayslipUploadResponse",
    "PayslipSendRequest",
    "PayslipSendResult",
    "PayslipBulkSendResponse",
    # Tracking
    "TrackingEventResponse",
    "TrackingStatsResponse",
    "PayslipTrackingResponse",
    "TrackingReportResponse",
    # Job
    "JobStatus",
    "JobStartResponse",
    "JobResultItem",
    "JobStatusResponse"
]



