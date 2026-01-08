# -*- coding: utf-8 -*-
"""
Güvenlik Yardımcı Fonksiyonları
- Path Sanitization (Path Traversal koruması)
- Input Validation
- IDOR koruması
"""

import os
import re
import html
from typing import Optional
import logging

security_logger = logging.getLogger("security")


def sanitize_path(path: str, base_dir: str) -> Optional[str]:
    """
    Dosya yolunu güvenli hale getir (Path Traversal koruması)
    
    Args:
        path: Kontrol edilecek dosya yolu
        base_dir: İzin verilen temel dizin
    
    Returns:
        Güvenli path veya None (güvenli değilse)
    
    Örnek Saldırılar:
        - ../../../etc/passwd
        - ..\\..\\..\\windows\\system32
        - /etc/passwd
        - C:\\Windows\\System32
    """
    if not path or not base_dir:
        return None
    
    try:
        # Path'i normalize et
        normalized_path = os.path.normpath(path)
        normalized_base = os.path.normpath(base_dir)
        
        # Absolute path'e çevir
        abs_path = os.path.abspath(normalized_path)
        abs_base = os.path.abspath(normalized_base)
        
        # Path, base dizinin içinde mi kontrol et
        common_path = os.path.commonpath([abs_path, abs_base])
        
        if common_path != abs_base:
            security_logger.warning(
                f"PATH_TRAVERSAL_ATTEMPT | Path: {path} | Base: {base_dir} | "
                f"Resolved: {abs_path}"
            )
            return None
        
        return abs_path
        
    except (ValueError, TypeError) as e:
        security_logger.warning(
            f"PATH_SANITIZATION_ERROR | Path: {path} | Base: {base_dir} | Error: {e}"
        )
        return None


def validate_tracking_id(tracking_id: str) -> bool:
    """
    Tracking ID formatını doğrula
    
    Beklenen format: URL-safe base64, 64 karakter
    """
    if not tracking_id:
        return False
    
    # Uzunluk kontrolü
    if len(tracking_id) < 32 or len(tracking_id) > 128:
        return False
    
    # Sadece URL-safe karakterler (base64 URL-safe)
    pattern = r'^[A-Za-z0-9_-]+$'
    if not re.match(pattern, tracking_id):
        security_logger.warning(
            f"INVALID_TRACKING_ID_FORMAT | ID: {tracking_id[:20]}..."
        )
        return False
    
    return True


def sanitize_filename(filename: str) -> str:
    """
    Dosya adını güvenli hale getir
    
    - Tehlikeli karakterleri kaldır
    - Path traversal karakterlerini kaldır
    - Maksimum uzunluk sınırı
    """
    if not filename:
        return "untitled"
    
    # Sadece güvenli karakterler
    safe_chars = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Path traversal karakterlerini kaldır
    safe_chars = safe_chars.replace('..', '_')
    
    # Başta ve sonda nokta olmasın
    safe_chars = safe_chars.strip('.')
    
    # Maksimum uzunluk
    if len(safe_chars) > 200:
        name, ext = os.path.splitext(safe_chars)
        safe_chars = name[:200-len(ext)] + ext
    
    return safe_chars or "untitled"


def sanitize_search_input(search_term: str, max_length: int = 100) -> str:
    """
    Arama terimini güvenli hale getir (SQL Injection koruması)
    
    SQLAlchemy ORM kullanıldığı için SQL injection riski düşük,
    ancak ilike için özel karakterler sorun çıkarabilir
    """
    if not search_term:
        return ""
    
    # Uzunluk sınırı
    search_term = search_term[:max_length]
    
    # SQL wildcard karakterlerini escape et
    # % ve _ LIKE sorgularında özel anlam taşır
    search_term = search_term.replace('%', r'\%')
    search_term = search_term.replace('_', r'\_')
    
    # Bazı tehlikeli karakterleri kaldır
    search_term = re.sub(r'[\'";\\]', '', search_term)
    
    return search_term.strip()


def sanitize_html(text: str) -> str:
    """
    HTML içeriğini güvenli hale getir (XSS koruması)
    """
    if not text:
        return ""
    
    return html.escape(text)


def validate_email_format(email: str) -> bool:
    """
    Email formatını doğrula
    """
    if not email:
        return False
    
    # Basit email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_tc_no(tc_no: str) -> bool:
    """
    TC Kimlik numarasını doğrula
    
    - 11 haneli olmalı
    - Sadece rakam içermeli
    - 0 ile başlamamalı
    """
    if not tc_no:
        return False
    
    # Sadece rakam
    if not tc_no.isdigit():
        return False
    
    # 11 haneli
    if len(tc_no) != 11:
        return False
    
    # 0 ile başlamamalı
    if tc_no[0] == '0':
        return False
    
    # TC algoritma kontrolü (opsiyonel ama önerilir)
    try:
        digits = [int(d) for d in tc_no]
        
        # 10. hane kontrolü
        odd_sum = sum(digits[0:9:2])
        even_sum = sum(digits[1:8:2])
        digit_10 = (odd_sum * 7 - even_sum) % 10
        
        if digit_10 != digits[9]:
            return False
        
        # 11. hane kontrolü
        digit_11 = sum(digits[0:10]) % 10
        
        if digit_11 != digits[10]:
            return False
        
        return True
        
    except (ValueError, IndexError):
        return False


def mask_sensitive_data(data: str, visible_chars: int = 4, mask_char: str = '*') -> str:
    """
    Hassas veriyi maskele
    
    Örnek: "12345678901" -> "*******8901"
    """
    if not data:
        return ""
    
    if len(data) <= visible_chars:
        return mask_char * len(data)
    
    masked_length = len(data) - visible_chars
    return mask_char * masked_length + data[-visible_chars:]


def generate_audit_log(
    action: str,
    user_id: int,
    resource_type: str,
    resource_id: int,
    ip_address: str,
    details: str = ""
) -> dict:
    """
    Audit log kaydı oluştur
    """
    from datetime import datetime
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "ip_address": ip_address,
        "details": details
    }

