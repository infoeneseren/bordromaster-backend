# -*- coding: utf-8 -*-
"""
CSP Nonce (Content Security Policy Nonce) Middleware
- Her istek için benzersiz nonce oluşturur
- XSS saldırılarına karşı ekstra koruma sağlar
- Inline script'ler sadece doğru nonce ile çalışır
"""

import secrets
import logging
from typing import Callable, Optional
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings

security_logger = logging.getLogger("security")

# Context variable for CSP nonce (async-safe)
csp_nonce_ctx: ContextVar[Optional[str]] = ContextVar("csp_nonce", default=None)


def generate_nonce(length: int = 32) -> str:
    """
    Kriptografik olarak güvenli CSP nonce oluştur
    
    Args:
        length: Nonce uzunluğu (byte cinsinden)
    
    Returns:
        Base64 encoded nonce string
    """
    return secrets.token_urlsafe(length)


def get_csp_nonce() -> Optional[str]:
    """
    Mevcut request'in CSP nonce'unu al
    Template'lerde ve handler'larda kullanılır
    
    Returns:
        Nonce string veya None
    """
    return csp_nonce_ctx.get()


class CSPNonceMiddleware(BaseHTTPMiddleware):
    """
    CSP Nonce Middleware
    
    Her HTTP isteğine benzersiz bir nonce atar ve
    Content-Security-Policy header'ına ekler.
    
    Güvenlik:
    - XSS saldırılarını engeller
    - Sadece nonce'lu inline script'ler çalışır
    - Her istekte farklı nonce
    
    Kullanım:
        Template'de: <script nonce="{{ csp_nonce }}">...</script>
        Handler'da: nonce = get_csp_nonce()
    """
    
    def __init__(
        self,
        app: ASGIApp,
        enable_nonce: bool = True,
        report_uri: Optional[str] = None
    ):
        """
        Args:
            app: ASGI uygulaması
            enable_nonce: Nonce kullanımını aktifleştir
            report_uri: CSP ihlalleri için rapor URL'i
        """
        super().__init__(app)
        self.enable_nonce = enable_nonce
        self.report_uri = report_uri
    
    def _build_csp_header(self, nonce: str) -> str:
        """
        Content-Security-Policy header'ı oluştur
        
        Args:
            nonce: Benzersiz nonce değeri
        
        Returns:
            CSP header değeri
        """
        # Temel CSP direktifleri
        directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline'",  # Style için unsafe-inline gerekebilir
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ]
        
        # Rapor URI varsa ekle
        if self.report_uri:
            directives.append(f"report-uri {self.report_uri}")
        
        return "; ".join(directives)
    
    def _build_api_csp_header(self) -> str:
        """
        API endpoint'leri için sıkı CSP header'ı
        
        Returns:
            CSP header değeri
        """
        return "default-src 'none'; frame-ancestors 'none'"
    
    def _is_api_request(self, path: str) -> bool:
        """API isteği mi kontrol et"""
        return path.startswith("/api/")
    
    def _is_docs_request(self, path: str) -> bool:
        """Docs isteği mi kontrol et (Swagger UI)"""
        return path in ["/docs", "/redoc", "/openapi.json"] or path.startswith("/docs/")
    
    def _build_docs_csp_header(self, nonce: str) -> str:
        """
        Swagger UI için CSP header'ı
        CDN kaynaklarına izin verir
        """
        return (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' 'unsafe-inline' https://cdn.jsdelivr.net; "
            f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "frame-ancestors 'none'"
        )
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Nonce oluştur
        nonce = generate_nonce() if self.enable_nonce else None
        
        # Context variable'a kaydet
        token = csp_nonce_ctx.set(nonce) if nonce else None
        
        # Request state'e de kaydet (handler'lardan erişim için)
        if nonce:
            request.state.csp_nonce = nonce
        
        try:
            # İsteği işle
            response = await call_next(request)
            
            # CSP header'ı ekle
            path = request.url.path
            
            if self._is_api_request(path):
                # API için sıkı CSP
                response.headers["Content-Security-Policy"] = self._build_api_csp_header()
            elif self._is_docs_request(path) and settings.DEBUG:
                # Docs için CDN izinli CSP
                response.headers["Content-Security-Policy"] = self._build_docs_csp_header(nonce)
            elif nonce:
                # Normal sayfalar için nonce'lu CSP
                response.headers["Content-Security-Policy"] = self._build_csp_header(nonce)
            
            # Nonce'u response header'ına da ekle (frontend için)
            if nonce:
                response.headers["X-CSP-Nonce"] = nonce
            
            return response
            
        finally:
            # Context variable'ı temizle
            if token:
                csp_nonce_ctx.reset(token)


def get_nonce_script_tag(script_content: str) -> str:
    """
    Nonce'lu script tag'i oluştur
    
    Args:
        script_content: Script içeriği
    
    Returns:
        Nonce'lu script tag HTML
    """
    nonce = get_csp_nonce()
    if nonce:
        return f'<script nonce="{nonce}">{script_content}</script>'
    return f'<script>{script_content}</script>'


def get_nonce_style_tag(style_content: str) -> str:
    """
    Nonce'lu style tag'i oluştur
    
    Args:
        style_content: Style içeriği
    
    Returns:
        Nonce'lu style tag HTML
    """
    nonce = get_csp_nonce()
    if nonce:
        return f'<style nonce="{nonce}">{style_content}</style>'
    return f'<style>{style_content}</style>'


