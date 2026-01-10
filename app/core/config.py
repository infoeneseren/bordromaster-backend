# -*- coding: utf-8 -*-
"""
Uygulama Konfigürasyonu
- Tüm ayarlar .env dosyasından yüklenir
- Farklı projeler için sadece .env dosyasını değiştirmeniz yeterli
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """
    Uygulama ayarları - Tüm değerler .env dosyasından okunur
    """
    
    # ==================== UYGULAMA ====================
    APP_NAME: str
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    DEV_MODE: bool = False  # True yapılırsa şifre politikası gevşer
    API_V1_PREFIX: str = "/api/v1"
    
    # ==================== JWT GÜVENLİĞİ ====================
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # ==================== PASSWORD PEPPER ====================
    # Şifre hash'lerine eklenen gizli değer (veritabanı sızıntısına karşı ekstra koruma)
    # ⚠️ Bu değer değiştirilirse TÜM kullanıcı şifreleri geçersiz olur!
    PASSWORD_PEPPER: str = ""  # .env'den okunacak, boşsa kullanılmaz
    
    # ==================== DOWNLOAD LİNK GÜVENLİĞİ ====================
    DOWNLOAD_LINK_SECRET: str
    DOWNLOAD_LINK_EXPIRE_DAYS: int = 30
    
    # ==================== RATE LIMITING ====================
    RATE_LIMIT_PER_MINUTE: int = 60
    DOWNLOAD_RATE_LIMIT_PER_MINUTE: int = 10
    DOWNLOAD_RATE_LIMIT_PER_HOUR: int = 50
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 200  # Upload işlemleri için yüksek limit
    
    # İndirme limitleri (yeni)
    DOWNLOAD_IP_LIMIT_PER_MINUTE: int = 3  # IP başına dakikada maksimum istek
    DOWNLOAD_TRACKING_LIMIT_PER_DAY: int = 6  # Tracking ID başına günde maksimum istek
    
    # ==================== SMTP RATE LIMIT KORUMASI ====================
    # Mail gönderiminde rate limit hatası almamak için bekleme süreleri
    MAIL_DELAY_SECONDS: int = 3  # Her mail arası bekleme (saniye) - Varsayılan 3 saniye
    MAIL_RETRY_MAX_ATTEMPTS: int = 3  # Rate limit hatası alındığında maksimum tekrar deneme
    MAIL_RETRY_BASE_DELAY: int = 60  # İlk retry için bekleme süresi (saniye) - Sonraki denemeler katlanarak artar
    MAIL_RATE_LIMIT_DELAY: int = 60  # Rate limit (450) hatası alındığında bekleme süresi
    MAIL_BATCH_SIZE: int = 10  # Batch başına maksimum mail sayısı (ileride batch gönderim için)
    MAIL_BATCH_DELAY: int = 30  # Batch'ler arası bekleme süresi (saniye)
    
    # ==================== BRUTE FORCE KORUMASI ====================
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    
    # ==================== GÜVENLİK BAŞLIKLARI ====================
    SECURITY_HEADERS: bool = True
    
    # ==================== GÜVENLİK UYARILARI ====================
    # Email bildirimleri şirket SMTP ayarları ile gönderilir
    # Admin kullanıcılara otomatik bildirim yapılır
    
    # ==================== CORS AYARLARI ====================
    # Virgülle ayırarak birden fazla origin yazılabilir
    CORS_ORIGINS: str = "http://localhost:3000"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins'i liste olarak döndür"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
    
    # ==================== VERİTABANI ====================
    DATABASE_URL: str
    DATABASE_ECHO: bool = False
    
    # ==================== REDIS ====================
    REDIS_URL: str
    
    # ==================== DOSYA YÜKLEMELERİ ====================
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE: int = 52428800  # 50MB
    ALLOWED_EXTENSIONS: str = ".pdf,.xlsx,.xls"
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """İzin verilen uzantıları liste olarak döndür"""
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",") if ext.strip()]
    
    # ==================== PDF AYARLARI ====================
    PDF_OUTPUT_DIR: str = "/app/uploads/pdfs"
    
    # ==================== LOGO AYARLARI ====================
    LOGO_DIR: str = "/app/uploads/logos"
    MAX_LOGO_SIZE: int = 5242880  # 5MB
    ALLOWED_LOGO_EXTENSIONS: str = ".png,.jpg,.jpeg,.webp,.svg"
    
    @property
    def allowed_logo_extensions_list(self) -> List[str]:
        """İzin verilen logo uzantılarını liste olarak döndür"""
        return [ext.strip() for ext in self.ALLOWED_LOGO_EXTENSIONS.split(",") if ext.strip()]
    
    # ==================== TRACKING ====================
    TRACKING_BASE_URL: str
    
    # ==================== İLK ADMİN ====================
    FIRST_ADMIN_EMAIL: str
    FIRST_ADMIN_PASSWORD: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
        
    def validate_production_settings(self) -> List[str]:
        """
        Production ortamı için güvenlik kontrolü
        Returns: Uyarı listesi
        """
        warnings = []
        
        if self.DEBUG:
            warnings.append("⚠️ DEBUG modu açık! Production'da kapatın.")
        
        if self.FIRST_ADMIN_PASSWORD == "admin123456":
            warnings.append("⚠️ Varsayılan admin şifresi kullanılıyor! Değiştirin.")
        
        if "localhost" in self.CORS_ORIGINS:
            warnings.append("⚠️ CORS origins'te localhost var. Production'da kaldırın.")
        
        if len(self.SECRET_KEY) < 32:
            warnings.append("⚠️ SECRET_KEY çok kısa. En az 32 karakter olmalı.")
        
        return warnings


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


settings = get_settings()

# Production uyarılarını başlangıçta göster
if not settings.DEBUG:
    warnings = settings.validate_production_settings()
    if warnings:
        import logging
        logger = logging.getLogger("security")
        for warning in warnings:
            logger.warning(warning)
