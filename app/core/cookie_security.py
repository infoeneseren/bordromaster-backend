# -*- coding: utf-8 -*-
"""
Cookie Güvenlik Modülü
- HttpOnly cookie yönetimi
- Secure flag zorunluluğu
- SameSite koruması
- HTTPS zorunluluğu
"""

import logging
from datetime import timedelta
from typing import Optional
from fastapi import Response, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

security_logger = logging.getLogger("security")


class CookieSecurityConfig:
    """Cookie güvenlik konfigürasyonu"""
    
    # Cookie isimleri
    ACCESS_TOKEN_COOKIE = "access_token"
    REFRESH_TOKEN_COOKIE = "refresh_token"
    
    # Varsayılan güvenlik ayarları
    DEFAULT_HTTPONLY = True
    DEFAULT_SECURE = True  # Production'da HTTPS zorunlu
    DEFAULT_SAMESITE = "strict"  # CSRF koruması için en sıkı ayar
    DEFAULT_PATH = "/"
    
    # Cookie süreleri (saniye)
    ACCESS_TOKEN_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    REFRESH_TOKEN_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def is_https_request(request: Request) -> bool:
    """
    İsteğin HTTPS üzerinden gelip gelmediğini kontrol et
    Proxy arkasındaki uygulamalar için X-Forwarded-Proto header'ını da kontrol eder
    """
    # Direkt HTTPS kontrolü
    if request.url.scheme == "https":
        return True
    
    # Proxy arkasındaysa X-Forwarded-Proto header'ını kontrol et
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
    if forwarded_proto == "https":
        return True
    
    # X-Forwarded-Ssl header'ını da kontrol et
    forwarded_ssl = request.headers.get("X-Forwarded-Ssl", "").lower()
    if forwarded_ssl == "on":
        return True
    
    return False


def should_use_secure_cookies(request: Request) -> bool:
    """
    Secure cookie kullanılıp kullanılmayacağını belirle
    - Production'da HTTPS zorunlu
    - Development'ta localhost için gevşetilmiş
    """
    # DEBUG modunda localhost için Secure flag'i devre dışı bırakılabilir
    if settings.DEBUG:
        host = request.headers.get("host", "").split(":")[0].lower()
        if host in ("localhost", "127.0.0.1"):
            return False
    
    # Production'da her zaman Secure
    return True


def set_auth_cookies(
    response: Response,
    request: Request,
    access_token: str,
    refresh_token: str
) -> Response:
    """
    Authentication cookie'lerini güvenli şekilde ayarla
    
    Args:
        response: FastAPI Response objesi
        request: FastAPI Request objesi (HTTPS kontrolü için)
        access_token: JWT access token
        refresh_token: JWT refresh token
    
    Returns:
        Cookie'ler eklenmiş response
    
    Security:
        - HttpOnly: JavaScript erişimini engeller (XSS koruması)
        - Secure: Sadece HTTPS üzerinden gönderilir
        - SameSite=Strict: CSRF saldırılarını engeller
        - Path=/: Tüm path'lerde geçerli
    """
    use_secure = should_use_secure_cookies(request)
    
    # Access Token Cookie
    response.set_cookie(
        key=CookieSecurityConfig.ACCESS_TOKEN_COOKIE,
        value=access_token,
        max_age=CookieSecurityConfig.ACCESS_TOKEN_MAX_AGE,
        httponly=CookieSecurityConfig.DEFAULT_HTTPONLY,
        secure=use_secure,
        samesite=CookieSecurityConfig.DEFAULT_SAMESITE,
        path=CookieSecurityConfig.DEFAULT_PATH,
    )
    
    # Refresh Token Cookie
    response.set_cookie(
        key=CookieSecurityConfig.REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        max_age=CookieSecurityConfig.REFRESH_TOKEN_MAX_AGE,
        httponly=CookieSecurityConfig.DEFAULT_HTTPONLY,
        secure=use_secure,
        samesite=CookieSecurityConfig.DEFAULT_SAMESITE,
        path=CookieSecurityConfig.DEFAULT_PATH,
    )
    
    security_logger.info(
        f"AUTH_COOKIES_SET | Secure: {use_secure} | SameSite: {CookieSecurityConfig.DEFAULT_SAMESITE}"
    )
    
    return response


def clear_auth_cookies(response: Response, request: Request) -> Response:
    """
    Authentication cookie'lerini temizle (logout için)
    
    Args:
        response: FastAPI Response objesi
        request: FastAPI Request objesi
    
    Returns:
        Cookie'ler temizlenmiş response
    """
    use_secure = should_use_secure_cookies(request)
    
    # Access Token Cookie'yi sil
    response.delete_cookie(
        key=CookieSecurityConfig.ACCESS_TOKEN_COOKIE,
        httponly=CookieSecurityConfig.DEFAULT_HTTPONLY,
        secure=use_secure,
        samesite=CookieSecurityConfig.DEFAULT_SAMESITE,
        path=CookieSecurityConfig.DEFAULT_PATH,
    )
    
    # Refresh Token Cookie'yi sil
    response.delete_cookie(
        key=CookieSecurityConfig.REFRESH_TOKEN_COOKIE,
        httponly=CookieSecurityConfig.DEFAULT_HTTPONLY,
        secure=use_secure,
        samesite=CookieSecurityConfig.DEFAULT_SAMESITE,
        path=CookieSecurityConfig.DEFAULT_PATH,
    )
    
    security_logger.info("AUTH_COOKIES_CLEARED")
    
    return response


def get_token_from_cookie(request: Request, token_type: str = "access") -> Optional[str]:
    """
    Cookie'den token al
    
    Args:
        request: FastAPI Request objesi
        token_type: "access" veya "refresh"
    
    Returns:
        Token string veya None
    """
    cookie_name = (
        CookieSecurityConfig.ACCESS_TOKEN_COOKIE 
        if token_type == "access" 
        else CookieSecurityConfig.REFRESH_TOKEN_COOKIE
    )
    
    return request.cookies.get(cookie_name)


def create_secure_response(
    content: dict,
    request: Request,
    access_token: str = None,
    refresh_token: str = None,
    status_code: int = 200
) -> JSONResponse:
    """
    Güvenli cookie'lerle JSON response oluştur
    
    Args:
        content: Response body
        request: FastAPI Request objesi
        access_token: Opsiyonel access token (cookie'ye eklenecek)
        refresh_token: Opsiyonel refresh token (cookie'ye eklenecek)
        status_code: HTTP status kodu
    
    Returns:
        Cookie'ler eklenmiş JSONResponse
    """
    response = JSONResponse(content=content, status_code=status_code)
    
    if access_token and refresh_token:
        set_auth_cookies(response, request, access_token, refresh_token)
    
    return response


