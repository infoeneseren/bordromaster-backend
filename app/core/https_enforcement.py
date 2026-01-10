# -*- coding: utf-8 -*-
"""
HTTPS Zorunluluğu Middleware
- Production'da HTTP isteklerini reddeder
- HTTPS'e yönlendirme desteği
- Güvenlik başlıkları ekler
"""

import logging
from typing import Callable, List
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse, RedirectResponse
from starlette.types import ASGIApp

from app.core.config import settings

security_logger = logging.getLogger("security")


class HTTPSEnforcementMiddleware(BaseHTTPMiddleware):
    """
    HTTPS Zorunluluğu Middleware
    
    Production ortamında HTTP isteklerini reddeder veya yönlendirir.
    Development modunda (DEBUG=true) bu kontrol atlanır.
    
    Güvenlik Önlemleri:
    1. HTTP isteklerini HTTPS'e yönlendirir (veya reddeder)
    2. HSTS header ekler
    3. Güvensiz protokol kullanımını loglar
    """
    
    def __init__(
        self,
        app: ASGIApp,
        redirect_to_https: bool = True,
        exclude_paths: List[str] = None
    ):
        """
        Args:
            app: ASGI uygulaması
            redirect_to_https: True = yönlendir, False = 403 döndür
            exclude_paths: HTTPS kontrolünden muaf path'ler (health check vb.)
        """
        super().__init__(app)
        self.redirect_to_https = redirect_to_https
        self.exclude_paths = exclude_paths or ["/health", "/", "/favicon.ico"]
    
    def _is_https(self, request: Request) -> bool:
        """
        İsteğin HTTPS üzerinden gelip gelmediğini kontrol et
        Proxy arkasındaki uygulamalar için header'ları da kontrol eder
        """
        # 1. Direkt scheme kontrolü
        if request.url.scheme == "https":
            return True
        
        # 2. X-Forwarded-Proto header (reverse proxy arkasında)
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
        if forwarded_proto == "https":
            return True
        
        # 3. X-Forwarded-Ssl header (bazı proxy'ler)
        forwarded_ssl = request.headers.get("X-Forwarded-Ssl", "").lower()
        if forwarded_ssl == "on":
            return True
        
        # 4. Front-End-Https header (Microsoft IIS)
        front_end_https = request.headers.get("Front-End-Https", "").lower()
        if front_end_https == "on":
            return True
        
        return False
    
    def _is_local_request(self, request: Request) -> bool:
        """Localhost isteği mi kontrol et"""
        host = request.headers.get("host", "").split(":")[0].lower()
        return host in ("localhost", "127.0.0.1", "0.0.0.0")
    
    def _should_skip_check(self, request: Request) -> bool:
        """Bu istek için HTTPS kontrolü atlanmalı mı"""
        # 1. Debug modunda ve localhost'tan gelen istekler atlanır
        if settings.DEBUG and self._is_local_request(request):
            return True
        
        # 2. Muaf path'ler
        if request.url.path in self.exclude_paths:
            return True
        
        return False
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Kontrol atlanacak mı
        if self._should_skip_check(request):
            return await call_next(request)
        
        # HTTPS kontrolü
        if not self._is_https(request):
            client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            if not client_ip and request.client:
                client_ip = request.client.host
            
            security_logger.warning(
                f"HTTP_REQUEST_BLOCKED | IP: {client_ip} | "
                f"Path: {request.url.path} | Host: {request.headers.get('host')}"
            )
            
            if self.redirect_to_https:
                # HTTPS'e yönlendir
                https_url = str(request.url).replace("http://", "https://", 1)
                return RedirectResponse(
                    url=https_url,
                    status_code=301,  # Permanent redirect
                    headers={
                        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
                    }
                )
            else:
                # 403 Forbidden döndür
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "HTTPS gereklidir. HTTP istekleri kabul edilmez.",
                        "error_code": "HTTPS_REQUIRED"
                    }
                )
        
        # İsteği işle
        response = await call_next(request)
        
        # HSTS header ekle (HTTPS isteklerinde)
        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        return response


def validate_cors_origins(origins: List[str]) -> List[str]:
    """
    CORS origin'lerini doğrula
    
    - Production'da sadece HTTPS origin'lere izin verir
    - HTTP origin'leri filtreler ve loglar
    
    Args:
        origins: Origin listesi
    
    Returns:
        Filtrelenmiş origin listesi
    """
    if settings.DEBUG:
        # Debug modunda tüm origin'lere izin ver
        return origins
    
    valid_origins = []
    invalid_origins = []
    
    for origin in origins:
        parsed = urlparse(origin)
        
        # Localhost kontrolü (development için)
        is_localhost = parsed.hostname in ("localhost", "127.0.0.1")
        
        if parsed.scheme == "https":
            valid_origins.append(origin)
        elif is_localhost and settings.DEBUG:
            # Debug modunda localhost HTTP'ye izin ver
            valid_origins.append(origin)
        else:
            invalid_origins.append(origin)
    
    if invalid_origins:
        security_logger.warning(
            f"CORS_HTTP_ORIGINS_FILTERED | Removed: {invalid_origins}"
        )
    
    return valid_origins


def get_secure_cors_origins() -> List[str]:
    """
    Güvenli CORS origin listesi al
    
    Production'da:
    - Sadece HTTPS origin'ler
    - HTTP origin'ler filtrelenir
    
    Development'ta:
    - Localhost HTTP'ye izin verilir
    """
    origins = settings.cors_origins_list
    return validate_cors_origins(origins)


