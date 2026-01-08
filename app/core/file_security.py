# -*- coding: utf-8 -*-
"""
Dosya Yükleme Güvenlik Servisi
- MIME type kontrolü
- Magic bytes doğrulama
- Boyut sınırları
- Dosya adı sanitization
"""

import os
import re
import hashlib
from typing import Optional, Tuple, List
from io import BytesIO
import logging

security_logger = logging.getLogger("security")


# Güvenli dosya tipleri ve magic bytes
ALLOWED_FILE_TYPES = {
    # PDF
    "application/pdf": {
        "extensions": [".pdf"],
        "magic_bytes": [b"%PDF-"],
        "max_size_mb": 50
    },
    # Excel
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "extensions": [".xlsx"],
        "magic_bytes": [b"PK\x03\x04"],  # ZIP formatı (XLSX)
        "max_size_mb": 10
    },
    "application/vnd.ms-excel": {
        "extensions": [".xls"],
        "magic_bytes": [b"\xd0\xcf\x11\xe0"],  # OLE2 formatı
        "max_size_mb": 10
    },
    # Resimler
    "image/png": {
        "extensions": [".png"],
        "magic_bytes": [b"\x89PNG\r\n\x1a\n"],
        "max_size_mb": 5
    },
    "image/jpeg": {
        "extensions": [".jpg", ".jpeg"],
        "magic_bytes": [b"\xff\xd8\xff"],
        "max_size_mb": 5
    },
    "image/webp": {
        "extensions": [".webp"],
        "magic_bytes": [b"RIFF"],  # RIFF....WEBP
        "max_size_mb": 5
    },
    "image/svg+xml": {
        "extensions": [".svg"],
        "magic_bytes": [b"<?xml", b"<svg"],  # SVG başlangıçları
        "max_size_mb": 2
    }
}


class FileUploadValidator:
    """Dosya yükleme güvenlik doğrulayıcı"""
    
    def __init__(self):
        self.allowed_types = ALLOWED_FILE_TYPES
    
    def validate(
        self,
        file_content: bytes,
        filename: str,
        allowed_mimes: List[str] = None,
        max_size_mb: int = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Dosyayı doğrula
        
        Args:
            file_content: Dosya içeriği (bytes)
            filename: Orijinal dosya adı
            allowed_mimes: İzin verilen MIME tipleri (None = tümü)
            max_size_mb: Maksimum boyut (MB) (None = varsayılan)
        
        Returns:
            Tuple[is_valid, error_message, detected_mime]
        """
        if not file_content:
            return False, "Dosya içeriği boş", None
        
        if not filename:
            return False, "Dosya adı gerekli", None
        
        # 1. Dosya uzantısı kontrolü
        ext = os.path.splitext(filename.lower())[1]
        detected_mime = self._get_mime_by_extension(ext)
        
        if not detected_mime:
            security_logger.warning(f"FILE_UPLOAD_BLOCKED | Invalid extension: {ext}")
            return False, f"Geçersiz dosya uzantısı: {ext}", None
        
        # 2. İzin verilen tipler kontrolü
        if allowed_mimes and detected_mime not in allowed_mimes:
            return False, f"Bu dosya tipi kabul edilmiyor: {ext}", detected_mime
        
        # 3. Boyut kontrolü
        type_config = self.allowed_types.get(detected_mime, {})
        allowed_max = max_size_mb or type_config.get("max_size_mb", 50)
        file_size_mb = len(file_content) / (1024 * 1024)
        
        if file_size_mb > allowed_max:
            return False, f"Dosya çok büyük. Maksimum: {allowed_max}MB", detected_mime
        
        # 4. Magic bytes kontrolü (gerçek dosya tipi doğrulama)
        magic_valid, magic_error = self._validate_magic_bytes(file_content, detected_mime)
        if not magic_valid:
            security_logger.warning(
                f"FILE_UPLOAD_BLOCKED | Magic bytes mismatch | "
                f"Expected: {detected_mime} | File: {filename}"
            )
            return False, magic_error, detected_mime
        
        # 5. Dosya adı sanitization kontrolü
        safe_filename = self.sanitize_filename(filename)
        if not safe_filename:
            return False, "Geçersiz dosya adı", detected_mime
        
        return True, "", detected_mime
    
    def _get_mime_by_extension(self, ext: str) -> Optional[str]:
        """Uzantıdan MIME type bul"""
        for mime, config in self.allowed_types.items():
            if ext in config.get("extensions", []):
                return mime
        return None
    
    def _validate_magic_bytes(self, content: bytes, expected_mime: str) -> Tuple[bool, str]:
        """Magic bytes ile gerçek dosya tipini doğrula"""
        type_config = self.allowed_types.get(expected_mime)
        
        if not type_config:
            return False, "Bilinmeyen dosya tipi"
        
        magic_bytes_list = type_config.get("magic_bytes", [])
        
        if not magic_bytes_list:
            # Magic bytes tanımlı değilse atlat
            return True, ""
        
        # SVG için özel kontrol (text tabanlı)
        if expected_mime == "image/svg+xml":
            content_start = content[:1000].decode('utf-8', errors='ignore').strip()
            if content_start.startswith("<?xml") or content_start.startswith("<svg"):
                return True, ""
            return False, "Geçersiz SVG dosyası"
        
        # WEBP için özel kontrol (RIFF formatı)
        if expected_mime == "image/webp":
            if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
                return True, ""
            return False, "Geçersiz WEBP dosyası"
        
        # Diğer tipler için magic bytes kontrolü
        for magic in magic_bytes_list:
            if content[:len(magic)] == magic:
                return True, ""
        
        return False, "Dosya içeriği beklenen formatla eşleşmiyor"
    
    def sanitize_filename(self, filename: str, max_length: int = 200) -> str:
        """
        Dosya adını güvenli hale getir
        
        - Tehlikeli karakterleri kaldır
        - Path traversal karakterlerini kaldır
        - Unicode normalize et
        - Maksimum uzunluk sınırla
        """
        if not filename:
            return "untitled"
        
        # Sadece dosya adını al (path varsa kaldır)
        filename = os.path.basename(filename)
        
        # Güvenli karakterler: harf, rakam, nokta, tire, alt çizgi
        safe_chars = re.sub(r'[^a-zA-Z0-9._\-ğüşıöçĞÜŞİÖÇ]', '_', filename)
        
        # Çift nokta ve path traversal kaldır
        safe_chars = safe_chars.replace('..', '_')
        safe_chars = safe_chars.replace('/', '_')
        safe_chars = safe_chars.replace('\\', '_')
        
        # Başta ve sonda nokta olmasın
        safe_chars = safe_chars.strip('.')
        
        # Maksimum uzunluk
        name, ext = os.path.splitext(safe_chars)
        if len(safe_chars) > max_length:
            safe_chars = name[:max_length - len(ext)] + ext
        
        return safe_chars or "untitled"
    
    def calculate_checksum(self, content: bytes) -> str:
        """Dosya checksum'ı hesapla (SHA-256)"""
        return hashlib.sha256(content).hexdigest()


# PDF Validator
class PDFValidator(FileUploadValidator):
    """PDF dosyası için özelleştirilmiş doğrulayıcı"""
    
    def validate_pdf(self, content: bytes, filename: str) -> Tuple[bool, str]:
        """PDF dosyasını doğrula"""
        return self.validate(
            file_content=content,
            filename=filename,
            allowed_mimes=["application/pdf"],
            max_size_mb=50
        )[:2]


# Excel Validator
class ExcelValidator(FileUploadValidator):
    """Excel dosyası için özelleştirilmiş doğrulayıcı"""
    
    def validate_excel(self, content: bytes, filename: str) -> Tuple[bool, str]:
        """Excel dosyasını doğrula"""
        return self.validate(
            file_content=content,
            filename=filename,
            allowed_mimes=[
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel"
            ],
            max_size_mb=10
        )[:2]


# Logo/Image Validator
class ImageValidator(FileUploadValidator):
    """Resim dosyası için özelleştirilmiş doğrulayıcı"""
    
    def validate_image(self, content: bytes, filename: str) -> Tuple[bool, str]:
        """Logo/resim dosyasını doğrula"""
        return self.validate(
            file_content=content,
            filename=filename,
            allowed_mimes=[
                "image/png",
                "image/jpeg",
                "image/webp",
                "image/svg+xml"
            ],
            max_size_mb=5
        )[:2]


# Singleton instances
file_validator = FileUploadValidator()
pdf_validator = PDFValidator()
excel_validator = ExcelValidator()
image_validator = ImageValidator()

