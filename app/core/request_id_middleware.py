# -*- coding: utf-8 -*-
"""
Request ID / Correlation ID Middleware
- Her isteğe benzersiz ID atar
- Log tracking için kullanılır
- Distributed tracing desteği
"""

import uuid
import time
import logging
from typing import Callable, Optional
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable for request ID (async-safe)
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# Logger
security_logger = logging.getLogger("security")


def get_request_id() -> Optional[str]:
    """
    Mevcut request ID'yi al
    Herhangi bir yerden çağrılabilir (async-safe)
    """
    return request_id_ctx.get()


def generate_request_id() -> str:
    """
    Benzersiz request ID oluştur
    Format: UUID4'ün kısa versiyonu (8 karakter)
    """
    return uuid.uuid4().hex[:16]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Request ID Middleware
    
    Her HTTP isteğine benzersiz bir ID atar ve response header'larına ekler.
    Bu ID, distributed sistemlerde log tracking için kritiktir.
    
    Headers:
        - X-Request-ID: Gelen istekteki ID (varsa kullanılır)
        - X-Correlation-ID: Response'a eklenen ID (tracking için)
    
    Kullanım:
        - Tüm loglar bu ID ile etiketlenebilir
        - Hata debug'ı kolaylaşır
        - Microservice iletişiminde trace edilebilir
    """
    
    # Header isimleri
    REQUEST_ID_HEADER = "X-Request-ID"
    CORRELATION_ID_HEADER = "X-Correlation-ID"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Request ID'yi al veya oluştur
        # İstemci kendi request ID'sini gönderebilir (distributed tracing için)
        request_id = request.headers.get(self.REQUEST_ID_HEADER)
        
        if not request_id:
            request_id = generate_request_id()
        else:
            # Güvenlik: Gelen ID'yi sanitize et (sadece alfanumerik)
            request_id = ''.join(c for c in request_id if c.isalnum() or c == '-')[:64]
        
        # 2. Context variable'a kaydet (async-safe)
        token = request_id_ctx.set(request_id)
        
        # 3. Request state'e de kaydet (handler'lardan erişim için)
        request.state.request_id = request_id
        
        # 4. İşlem başlangıç zamanı
        start_time = time.time()
        
        try:
            # 5. İsteği işle
            response = await call_next(request)
            
            # 6. İşlem süresini hesapla
            process_time = time.time() - start_time
            
            # 7. Response header'larına ekle
            response.headers[self.CORRELATION_ID_HEADER] = request_id
            response.headers[self.REQUEST_ID_HEADER] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.4f}"
            
            return response
            
        except Exception as e:
            # Hata durumunda da request ID'yi logla
            security_logger.error(
                f"REQUEST_ERROR | RequestID: {request_id} | "
                f"Path: {request.url.path} | Error: {str(e)}"
            )
            raise
            
        finally:
            # Context variable'ı temizle
            request_id_ctx.reset(token)


class RequestIDLogFilter(logging.Filter):
    """
    Log Filter - Request ID'yi otomatik olarak log kayıtlarına ekler
    
    Kullanım:
        logger = logging.getLogger("mylogger")
        logger.addFilter(RequestIDLogFilter())
        
        # Artık tüm loglar request_id içerir
        logger.info("Something happened")  # [RequestID: abc123] Something happened
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id()
        record.request_id = request_id or "NO_REQUEST"
        return True


def setup_request_id_logging(logger_name: str = None):
    """
    Logger'a Request ID filter ekle
    
    Args:
        logger_name: Logger adı (None = root logger)
    """
    logger = logging.getLogger(logger_name)
    logger.addFilter(RequestIDLogFilter())
    
    # Format'ı güncelle (request_id ekle)
    for handler in logger.handlers:
        if handler.formatter:
            fmt = handler.formatter._fmt
            if "request_id" not in fmt:
                new_fmt = f"[%(request_id)s] {fmt}"
                handler.setFormatter(logging.Formatter(new_fmt))


