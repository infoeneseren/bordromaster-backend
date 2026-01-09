# -*- coding: utf-8 -*-
"""
Güvenlik Middleware'leri
- SecurityHeadersMiddleware: HTTP güvenlik başlıkları
- RateLimitMiddleware: İstek hız sınırlama
- RequestLoggingMiddleware: İstek loglama
"""

import time
import logging
from typing import Dict, Optional, Callable
from collections import defaultdict
from datetime import datetime, timedelta

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.types import ASGIApp

# Logger
security_logger = logging.getLogger("security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    HTTP Güvenlik Başlıkları Middleware'i
    
    Tüm yanıtlara güvenlik başlıkları ekler:
    - X-Content-Type-Options: MIME type sniffing'i engeller
    - X-Frame-Options: Clickjacking saldırılarını engeller
    - X-XSS-Protection: XSS koruması
    - Strict-Transport-Security: HTTPS zorunlu kılar
    - Content-Security-Policy: XSS ve injection saldırılarını engeller
    - Referrer-Policy: Referrer bilgisini kontrol eder
    - Permissions-Policy: Browser özelliklerini kısıtlar
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Güvenlik başlıklarını ekle
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content-Security-Policy
        # /docs ve /redoc için Swagger UI CDN kaynaklarına izin ver
        path = str(request.url.path)
        if path in ["/docs", "/redoc", "/openapi.json"] or path.startswith("/docs/"):
            # Swagger UI için gerekli CDN kaynakları
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'"
            )
        else:
            # API için sıkı CSP
            response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        
        # Cache kontrolü (hassas veriler için)
        if "/api/" in path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate Limiting Middleware'i
    
    IP bazlı istek hız sınırlaması yapar.
    Redis varsa Redis kullanır, yoksa memory tabanlı çalışır.
    """
    
    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        # Memory tabanlı storage (Redis yoksa)
        self.minute_requests: Dict[str, list] = defaultdict(list)
        self.hour_requests: Dict[str, list] = defaultdict(list)
    
    def _get_client_ip(self, request: Request) -> str:
        """İstemci IP adresini al"""
        # Proxy arkasındaysa X-Forwarded-For header'ını kontrol et
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # X-Real-IP header'ını kontrol et
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Doğrudan bağlantı
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _cleanup_old_requests(self, ip: str, now: float):
        """Eski istekleri temizle"""
        minute_ago = now - 60
        hour_ago = now - 3600
        
        self.minute_requests[ip] = [
            t for t in self.minute_requests[ip] if t > minute_ago
        ]
        self.hour_requests[ip] = [
            t for t in self.hour_requests[ip] if t > hour_ago
        ]
    
    def _is_rate_limited(self, ip: str) -> tuple[bool, Optional[str]]:
        """Rate limit kontrolü yap"""
        now = time.time()
        self._cleanup_old_requests(ip, now)
        
        # Dakikalık limit kontrolü
        if len(self.minute_requests[ip]) >= self.requests_per_minute:
            return True, f"Dakika başına {self.requests_per_minute} istek limiti aşıldı"
        
        # Saatlik limit kontrolü
        if len(self.hour_requests[ip]) >= self.requests_per_hour:
            return True, f"Saat başına {self.requests_per_hour} istek limiti aşıldı"
        
        # İstek kaydı
        self.minute_requests[ip].append(now)
        self.hour_requests[ip].append(now)
        
        return False, None
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Health check ve static dosyalar için rate limit uygulanmaz
        if request.url.path in ["/health", "/", "/favicon.ico"]:
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        is_limited, message = self._is_rate_limited(client_ip)
        
        if is_limited:
            security_logger.warning(
                f"Rate limit aşıldı - IP: {client_ip}, Path: {request.url.path}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Çok fazla istek. Lütfen bir süre bekleyin.",
                    "error_code": "RATE_LIMIT_EXCEEDED"
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0"
                }
            )
        
        # Rate limit bilgisini response header'larına ekle
        response = await call_next(request)
        remaining = self.requests_per_minute - len(self.minute_requests[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    İstek Loglama Middleware'i
    
    Tüm istekleri loglar:
    - İstek zamanı
    - HTTP metodu
    - URL path
    - İstemci IP
    - Yanıt durumu
    - İşlem süresi
    """
    
    # Loglanmayacak path'ler
    EXCLUDED_PATHS = {"/health", "/favicon.ico"}
    
    def _get_client_ip(self, request: Request) -> str:
        """İstemci IP adresini al"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Excluded path'leri loglamadan geç
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)
        
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        
        # İsteği işle
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            security_logger.error(
                f"Request Error - {request.method} {request.url.path} - IP: {client_ip} - Error: {str(e)}"
            )
            raise
        
        # İşlem süresini hesapla
        process_time = time.time() - start_time
        
        # Log seviyesini belirle
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO
        
        # Log mesajı
        log_message = (
            f"{request.method} {request.url.path} - "
            f"Status: {status_code} - "
            f"IP: {client_ip} - "
            f"Duration: {process_time:.3f}s"
        )
        
        security_logger.log(log_level, log_message)
        
        # İşlem süresini response header'ına ekle
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        
        return response

