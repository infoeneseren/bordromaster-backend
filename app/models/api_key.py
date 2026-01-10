# -*- coding: utf-8 -*-
"""
API Key Model
- Şirket bazlı API anahtarları
- Otomatik rotasyon desteği
- Kullanım takibi
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class APIKeyStatus(str, enum.Enum):
    """API Key durumları"""
    ACTIVE = "active"           # Aktif kullanımda
    ROTATING = "rotating"       # Rotasyon sürecinde (hem eski hem yeni geçerli)
    EXPIRED = "expired"         # Süresi dolmuş
    REVOKED = "revoked"         # Manuel olarak iptal edilmiş


class APIKeyScope(str, enum.Enum):
    """API Key yetki kapsamları"""
    FULL = "full"               # Tam erişim
    READ_ONLY = "read_only"     # Sadece okuma
    WEBHOOK = "webhook"         # Sadece webhook
    REPORTS = "reports"         # Sadece raporlar


class APIKey(Base):
    """
    API Key modeli
    
    Her şirket için benzersiz API anahtarları.
    Otomatik rotasyon ve kullanım takibi destekler.
    """
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # İlişkiler
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # API Key bilgileri
    name = Column(String(100), nullable=False)  # Anahtar adı (örn: "Production API")
    description = Column(Text, nullable=True)    # Açıklama
    
    # Anahtar değerleri (hash'lenmiş)
    key_prefix = Column(String(8), nullable=False, index=True)  # Gösterim için ilk 8 karakter
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 hash
    
    # Rotasyon için önceki anahtar
    previous_key_hash = Column(String(64), nullable=True)  # Rotasyon sürecinde eski hash
    rotation_started_at = Column(DateTime, nullable=True)  # Rotasyon başlangıç zamanı
    
    # Durum ve kapsam
    status = Column(SQLEnum(APIKeyStatus), default=APIKeyStatus.ACTIVE)
    scope = Column(SQLEnum(APIKeyScope), default=APIKeyScope.FULL)
    
    # Zaman bilgileri
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # None = süresiz
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    
    # Rotasyon ayarları
    auto_rotate = Column(Boolean, default=True)  # Otomatik rotasyon aktif mi
    rotation_interval_days = Column(Integer, default=90)  # Kaç günde bir rotasyon
    last_rotated_at = Column(DateTime, nullable=True)
    next_rotation_at = Column(DateTime, nullable=True)
    
    # Kullanım istatistikleri
    usage_count = Column(Integer, default=0)
    last_ip_address = Column(String(45), nullable=True)
    
    # IP kısıtlaması (opsiyonel)
    allowed_ips = Column(Text, nullable=True)  # Virgülle ayrılmış IP listesi
    
    # İlişkiler
    company = relationship("Company", back_populates="api_keys")
    
    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """
        Yeni API key oluştur
        
        Returns:
            tuple[full_key, key_prefix, key_hash]
            - full_key: Kullanıcıya gösterilecek tam anahtar (sadece bir kez!)
            - key_prefix: Görüntüleme için ilk 8 karakter
            - key_hash: Veritabanında saklanacak hash
        """
        # 32 byte = 256 bit güvenli random
        full_key = f"bm_{secrets.token_urlsafe(32)}"
        key_prefix = full_key[:8]
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        
        return full_key, key_prefix, key_hash
    
    @staticmethod
    def hash_key(key: str) -> str:
        """API key'i hashle"""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def verify_key(self, provided_key: str) -> bool:
        """
        Verilen key'in doğruluğunu kontrol et
        
        Rotasyon sürecindeyse hem eski hem yeni key kabul edilir
        """
        provided_hash = self.hash_key(provided_key)
        
        # Mevcut key kontrolü
        if provided_hash == self.key_hash:
            return True
        
        # Rotasyon sürecindeyse eski key de geçerli
        if (
            self.status == APIKeyStatus.ROTATING 
            and self.previous_key_hash 
            and provided_hash == self.previous_key_hash
        ):
            return True
        
        return False
    
    def is_expired(self) -> bool:
        """Süresi dolmuş mu kontrol et"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_active(self) -> bool:
        """Aktif mi kontrol et"""
        return (
            self.status in [APIKeyStatus.ACTIVE, APIKeyStatus.ROTATING]
            and not self.is_expired()
        )
    
    def needs_rotation(self) -> bool:
        """Rotasyon gerekli mi kontrol et"""
        if not self.auto_rotate:
            return False
        
        if self.next_rotation_at is None:
            return False
        
        return datetime.utcnow() >= self.next_rotation_at
    
    def start_rotation(self) -> tuple[str, str, str]:
        """
        Rotasyon başlat
        
        Returns:
            Yeni key bilgileri (full_key, key_prefix, key_hash)
        """
        # Eski key'i yedekle
        self.previous_key_hash = self.key_hash
        self.rotation_started_at = datetime.utcnow()
        self.status = APIKeyStatus.ROTATING
        
        # Yeni key oluştur
        full_key, key_prefix, key_hash = self.generate_key()
        self.key_prefix = key_prefix
        self.key_hash = key_hash
        self.last_rotated_at = datetime.utcnow()
        
        # Sonraki rotasyon zamanını hesapla
        self.next_rotation_at = datetime.utcnow() + timedelta(days=self.rotation_interval_days)
        
        return full_key, key_prefix, key_hash
    
    def complete_rotation(self):
        """
        Rotasyonu tamamla
        
        Eski key artık geçersiz olur
        """
        self.previous_key_hash = None
        self.rotation_started_at = None
        self.status = APIKeyStatus.ACTIVE
    
    def revoke(self):
        """API key'i iptal et"""
        self.status = APIKeyStatus.REVOKED
        self.revoked_at = datetime.utcnow()
    
    def record_usage(self, ip_address: str = None):
        """Kullanım kaydı"""
        self.usage_count += 1
        self.last_used_at = datetime.utcnow()
        if ip_address:
            self.last_ip_address = ip_address
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """IP adresi izinli mi kontrol et"""
        if not self.allowed_ips:
            return True  # Kısıtlama yoksa hepsine izin ver
        
        allowed_list = [ip.strip() for ip in self.allowed_ips.split(",")]
        return ip_address in allowed_list
    
    @property
    def masked_key(self) -> str:
        """Maskelenmiş key gösterimi"""
        return f"{self.key_prefix}...{'*' * 20}"
    
    def to_dict(self) -> dict:
        """Model'i dictionary'ye çevir"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "key_prefix": self.key_prefix,
            "masked_key": self.masked_key,
            "status": self.status.value,
            "scope": self.scope.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_rotated_at": self.last_rotated_at.isoformat() if self.last_rotated_at else None,
            "next_rotation_at": self.next_rotation_at.isoformat() if self.next_rotation_at else None,
            "usage_count": self.usage_count,
            "auto_rotate": self.auto_rotate,
            "rotation_interval_days": self.rotation_interval_days,
        }


