# -*- coding: utf-8 -*-
"""
BordroMaster API - Main Application
Güvenlik özellikleri eklenmiş versiyon
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import init_db, close_db, AsyncSessionLocal, engine
from app.core.security import get_password_hash
from app.core.security_middleware import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware
)
from app.core.request_id_middleware import RequestIDMiddleware
from app.core.https_enforcement import HTTPSEnforcementMiddleware, get_secure_cors_origins
from app.core.csp_nonce import CSPNonceMiddleware  # Yeni: CSP Nonce
from app.core.redis_service import init_redis, close_redis
from app.api.v1 import api_router
from app.models import Company, User, UserRole

# Güvenlik logger'ını yapılandır
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.INFO)


async def run_migrations():
    """Veritabanı migration'larını çalıştır"""
    async with engine.begin() as conn:
        # Payslips tablosunda tc_no sütunu var mı kontrol et
        try:
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'payslips' AND column_name = 'tc_no'
            """))
            tc_no_exists = result.fetchone() is not None
            
            if not tc_no_exists:
                print("Running migration: Adding new columns to payslips table...")
                
                # employee_id nullable yap
                await conn.execute(text("""
                    ALTER TABLE payslips ALTER COLUMN employee_id DROP NOT NULL
                """))
                
                # Yeni sütunları ekle
                await conn.execute(text("""
                    ALTER TABLE payslips ADD COLUMN IF NOT EXISTS tc_no VARCHAR(11)
                """))
                await conn.execute(text("""
                    ALTER TABLE payslips ADD COLUMN IF NOT EXISTS extracted_full_name VARCHAR(200)
                """))
                
                # Index ekle
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_payslips_tc_no ON payslips(tc_no)
                """))
                
                # Status enum'una yeni değer ekle
                try:
                    await conn.execute(text("""
                        ALTER TYPE payslipstatus ADD VALUE IF NOT EXISTS 'no_employee'
                    """))
                except Exception as enum_err:
                    print(f"Enum update skipped (may already exist): {enum_err}")
                
                print("Migration completed successfully!")
        except Exception as e:
            print(f"Migration check/run error (may be normal on first run): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup/shutdown"""
    # Startup
    print("Starting BordroMaster API...")
    
    # Database başlat
    await init_db()
    
    # Redis başlat
    try:
        await init_redis()
        print("Redis bağlantısı başarılı")
    except Exception as e:
        print(f"Redis bağlantı hatası (devam ediliyor): {e}")
    
    # Migration'ları çalıştır
    await run_migrations()
    
    # Ilk admin ve sirket olustur
    await create_initial_data()
    
    yield
    
    # Shutdown
    print("Shutting down BordroMaster API...")
    await close_redis()
    await close_db()


async def create_initial_data():
    """Ilk calistirmada varsayilan sirket ve admin olustur"""
    async with AsyncSessionLocal() as db:
        # Sirket var mi kontrol et
        result = await db.execute(select(Company).limit(1))
        company = result.scalar_one_or_none()
        
        if not company:
            # Varsayilan sirket olustur
            company = Company(
                name="Varsayilan Sirket",
                mail_subject="Bordronuz Hakkinda",
                mail_body="Sayin {name},\n\nEkte {period} donemine ait bordronuz bulunmaktadir.\n\nSaygilarimizla"
            )
            db.add(company)
            await db.flush()
            
            # Admin kullanici olustur
            admin = User(
                company_id=company.id,
                email=settings.FIRST_ADMIN_EMAIL,
                password_hash=get_password_hash(settings.FIRST_ADMIN_PASSWORD),
                full_name="Admin",
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True
            )
            db.add(admin)
            await db.commit()
            
            print(f"Initial admin created: {settings.FIRST_ADMIN_EMAIL}")


# FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="BordroMaster - PDF Bordro Yonetim Sistemi API",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,  # Production'da docs kapalı
    redoc_url="/redoc" if settings.DEBUG else None
)

# Güvenlik Middleware'leri (sıra önemli!)
# 1. Request ID (en dışta - tüm isteklere ID atar)
app.add_middleware(RequestIDMiddleware)

# 2. CSP Nonce (XSS koruması için)
app.add_middleware(CSPNonceMiddleware, enable_nonce=True)

# 3. Request Logging
app.add_middleware(RequestLoggingMiddleware)

# 4. HTTPS Enforcement (Production'da HTTP'yi reddeder)
if not settings.DEBUG:
    app.add_middleware(
        HTTPSEnforcementMiddleware,
        redirect_to_https=True,
        exclude_paths=["/health", "/", "/favicon.ico"]
    )

# 5. Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# 6. Rate Limiting
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    requests_per_hour=1000,
    upload_requests_per_minute=settings.UPLOAD_RATE_LIMIT_PER_MINUTE  # Upload için yüksek limit
)

# 7. CORS (en içte) - Güvenli origin'ler ile
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_secure_cors_origins(),  # HTTPS-only origin'ler
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Sadece gerekli metodlar
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Correlation-ID", "X-CSP-Nonce"],  # CSP Nonce eklendi
    expose_headers=["X-Request-ID", "X-Correlation-ID", "X-Process-Time", "X-CSP-Nonce"],  # CSP Nonce eklendi
    max_age=600,  # Preflight cache süresi (10 dakika)
)

# API Router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
