# -*- coding: utf-8 -*-
"""API v1 router"""

from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router
from .employees import router as employees_router
from .payslips import router as payslips_router
from .tracking import router as tracking_router
from .settings import router as settings_router
from .jobs import router as jobs_router
from .audit import router as audit_router
from .sessions import router as sessions_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(employees_router)
api_router.include_router(payslips_router)
api_router.include_router(tracking_router)
api_router.include_router(settings_router)
api_router.include_router(jobs_router)
api_router.include_router(audit_router)
api_router.include_router(sessions_router)
