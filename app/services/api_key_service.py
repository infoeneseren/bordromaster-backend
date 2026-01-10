# -*- coding: utf-8 -*-
"""
API Key Rotasyon Servisi
- API key oluşturma ve yönetim
- Otomatik rotasyon
- Kullanım doğrulama
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from app.models.api_key import APIKey, APIKeyStatus, APIKeyScope
from app.models import AuditAction
from app.services.audit_service import audit_service

security_logger = logging.getLogger("security")


class APIKeyRotationService:
    """
    API Key Rotasyon Servisi
    
    Özellikler:
    - Güvenli key oluşturma
    - Otomatik rotasyon (grace period ile)
    - Kullanım doğrulama ve takip
    - IP kısıtlaması
    """
    
    # Rotasyon grace period (gün) - bu süre boyunca hem eski hem yeni key geçerli
    ROTATION_GRACE_PERIOD_DAYS = 7
    
    # Varsayılan rotasyon aralığı (gün)
    DEFAULT_ROTATION_INTERVAL = 90
    
    @staticmethod
    async def create_api_key(
        db: AsyncSession,
        company_id: int,
        name: str,
        created_by_user_id: int = None,
        description: str = None,
        scope: APIKeyScope = APIKeyScope.FULL,
        expires_in_days: int = None,
        auto_rotate: bool = True,
        rotation_interval_days: int = None,
        allowed_ips: str = None,
    ) -> Tuple[APIKey, str]:
        """
        Yeni API key oluştur
        
        Args:
            db: Database session
            company_id: Şirket ID
            name: Key adı
            created_by_user_id: Oluşturan kullanıcı ID
            description: Açıklama
            scope: Yetki kapsamı
            expires_in_days: Geçerlilik süresi (gün), None = süresiz
            auto_rotate: Otomatik rotasyon aktif mi
            rotation_interval_days: Rotasyon aralığı (gün)
            allowed_ips: İzin verilen IP'ler (virgülle ayrılmış)
        
        Returns:
            Tuple[APIKey, full_key] - full_key sadece bir kez gösterilir!
        
        Security:
            - full_key sadece bu fonksiyondan döner
            - Veritabanında hash olarak saklanır
            - Bir daha okunamaz!
        """
        # Key oluştur
        full_key, key_prefix, key_hash = APIKey.generate_key()
        
        # Expire zamanı hesapla
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        # Rotasyon aralığı
        rotation_days = rotation_interval_days or APIKeyRotationService.DEFAULT_ROTATION_INTERVAL
        
        # Sonraki rotasyon zamanı
        next_rotation = None
        if auto_rotate:
            next_rotation = datetime.utcnow() + timedelta(days=rotation_days)
        
        # API Key oluştur
        api_key = APIKey(
            company_id=company_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            key_prefix=key_prefix,
            key_hash=key_hash,
            status=APIKeyStatus.ACTIVE,
            scope=scope,
            expires_at=expires_at,
            auto_rotate=auto_rotate,
            rotation_interval_days=rotation_days,
            next_rotation_at=next_rotation,
            allowed_ips=allowed_ips,
        )
        
        db.add(api_key)
        
        # Audit log
        await audit_service.log(
            db=db,
            action=AuditAction.SETTINGS_UPDATE,
            user_id=created_by_user_id,
            company_id=company_id,
            resource_type="api_key",
            resource_name=name,
            details={"action": "create", "scope": scope.value},
        )
        
        security_logger.info(
            f"API_KEY_CREATED | Company: {company_id} | Name: {name} | "
            f"Scope: {scope.value} | AutoRotate: {auto_rotate}"
        )
        
        return api_key, full_key
    
    @staticmethod
    async def validate_api_key(
        db: AsyncSession,
        provided_key: str,
        ip_address: str = None,
        required_scope: APIKeyScope = None,
    ) -> Tuple[bool, Optional[APIKey], str]:
        """
        API key'i doğrula
        
        Args:
            db: Database session
            provided_key: Kullanıcının gönderdiği key
            ip_address: İstemci IP adresi
            required_scope: Gerekli yetki kapsamı
        
        Returns:
            Tuple[is_valid, api_key, error_message]
        """
        if not provided_key:
            return False, None, "API key gerekli"
        
        # Key hash'i hesapla
        key_hash = APIKey.hash_key(provided_key)
        
        # Key'i bul (hash ile)
        result = await db.execute(
            select(APIKey).where(
                and_(
                    APIKey.status.in_([APIKeyStatus.ACTIVE, APIKeyStatus.ROTATING]),
                    # Ana hash veya rotasyon sürecindeki eski hash
                    (APIKey.key_hash == key_hash) | (APIKey.previous_key_hash == key_hash)
                )
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            security_logger.warning(f"API_KEY_INVALID | Provided prefix: {provided_key[:8]}...")
            return False, None, "Geçersiz API key"
        
        # Süre kontrolü
        if api_key.is_expired():
            security_logger.warning(f"API_KEY_EXPIRED | Key: {api_key.key_prefix}...")
            return False, api_key, "API key süresi dolmuş"
        
        # IP kontrolü
        if ip_address and not api_key.is_ip_allowed(ip_address):
            security_logger.warning(
                f"API_KEY_IP_BLOCKED | Key: {api_key.key_prefix}... | IP: {ip_address}"
            )
            return False, api_key, "Bu IP adresi için yetki yok"
        
        # Scope kontrolü
        if required_scope:
            if api_key.scope == APIKeyScope.READ_ONLY and required_scope == APIKeyScope.FULL:
                return False, api_key, "Bu işlem için yetkiniz yok"
        
        # Kullanım kaydı
        api_key.record_usage(ip_address)
        
        security_logger.info(
            f"API_KEY_VALIDATED | Key: {api_key.key_prefix}... | "
            f"Company: {api_key.company_id} | IP: {ip_address}"
        )
        
        return True, api_key, ""
    
    @staticmethod
    async def rotate_api_key(
        db: AsyncSession,
        api_key_id: int,
        user_id: int = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        API key rotasyonu başlat
        
        Args:
            db: Database session
            api_key_id: API key ID
            user_id: İşlemi yapan kullanıcı
        
        Returns:
            Tuple[success, message, new_full_key]
            - new_full_key sadece bir kez döner!
        """
        result = await db.execute(
            select(APIKey).where(APIKey.id == api_key_id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            return False, "API key bulunamadı", None
        
        if api_key.status == APIKeyStatus.ROTATING:
            return False, "Bu key zaten rotasyon sürecinde", None
        
        if api_key.status in [APIKeyStatus.EXPIRED, APIKeyStatus.REVOKED]:
            return False, "Bu key aktif değil", None
        
        # Rotasyonu başlat
        full_key, key_prefix, key_hash = api_key.start_rotation()
        
        # Audit log
        await audit_service.log(
            db=db,
            action=AuditAction.SETTINGS_UPDATE,
            user_id=user_id,
            company_id=api_key.company_id,
            resource_type="api_key",
            resource_id=api_key.id,
            resource_name=api_key.name,
            details={"action": "rotate", "new_prefix": key_prefix},
        )
        
        security_logger.warning(
            f"API_KEY_ROTATED | Key: {api_key.name} | "
            f"Company: {api_key.company_id} | New prefix: {key_prefix}"
        )
        
        return True, "Rotasyon başlatıldı. Yeni key 7 gün içinde aktif olacak.", full_key
    
    @staticmethod
    async def complete_rotation(
        db: AsyncSession,
        api_key_id: int,
    ) -> bool:
        """
        Rotasyonu tamamla (eski key artık geçersiz)
        
        Grace period sonunda otomatik çağrılır
        """
        result = await db.execute(
            select(APIKey).where(
                and_(
                    APIKey.id == api_key_id,
                    APIKey.status == APIKeyStatus.ROTATING
                )
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            return False
        
        # Grace period kontrolü
        if api_key.rotation_started_at:
            grace_end = api_key.rotation_started_at + timedelta(
                days=APIKeyRotationService.ROTATION_GRACE_PERIOD_DAYS
            )
            if datetime.utcnow() < grace_end:
                return False  # Grace period henüz bitmedi
        
        api_key.complete_rotation()
        
        security_logger.info(
            f"API_KEY_ROTATION_COMPLETED | Key: {api_key.name} | Company: {api_key.company_id}"
        )
        
        return True
    
    @staticmethod
    async def revoke_api_key(
        db: AsyncSession,
        api_key_id: int,
        user_id: int = None,
        reason: str = None,
    ) -> bool:
        """
        API key'i iptal et
        """
        result = await db.execute(
            select(APIKey).where(APIKey.id == api_key_id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            return False
        
        api_key.revoke()
        
        # Audit log
        await audit_service.log(
            db=db,
            action=AuditAction.SETTINGS_UPDATE,
            user_id=user_id,
            company_id=api_key.company_id,
            resource_type="api_key",
            resource_id=api_key.id,
            resource_name=api_key.name,
            details={"action": "revoke", "reason": reason},
        )
        
        security_logger.warning(
            f"API_KEY_REVOKED | Key: {api_key.name} | Company: {api_key.company_id} | Reason: {reason}"
        )
        
        return True
    
    @staticmethod
    async def get_company_keys(
        db: AsyncSession,
        company_id: int,
        include_revoked: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Şirketin tüm API key'lerini getir
        """
        query = select(APIKey).where(APIKey.company_id == company_id)
        
        if not include_revoked:
            query = query.where(
                APIKey.status.notin_([APIKeyStatus.REVOKED, APIKeyStatus.EXPIRED])
            )
        
        result = await db.execute(query.order_by(APIKey.created_at.desc()))
        keys = result.scalars().all()
        
        return [key.to_dict() for key in keys]
    
    @staticmethod
    async def process_pending_rotations(db: AsyncSession) -> int:
        """
        Bekleyen rotasyonları işle (cron job için)
        
        1. Rotasyon zamanı gelmiş key'leri rotate et
        2. Grace period bitmiş rotasyonları tamamla
        
        Returns:
            İşlenen key sayısı
        """
        processed = 0
        
        # 1. Rotasyon zamanı gelmiş key'ler
        result = await db.execute(
            select(APIKey).where(
                and_(
                    APIKey.status == APIKeyStatus.ACTIVE,
                    APIKey.auto_rotate == True,
                    APIKey.next_rotation_at <= datetime.utcnow()
                )
            )
        )
        keys_to_rotate = result.scalars().all()
        
        for key in keys_to_rotate:
            key.start_rotation()
            processed += 1
            security_logger.info(f"AUTO_ROTATION_STARTED | Key: {key.name}")
        
        # 2. Grace period bitmiş rotasyonlar
        grace_cutoff = datetime.utcnow() - timedelta(
            days=APIKeyRotationService.ROTATION_GRACE_PERIOD_DAYS
        )
        
        result = await db.execute(
            select(APIKey).where(
                and_(
                    APIKey.status == APIKeyStatus.ROTATING,
                    APIKey.rotation_started_at <= grace_cutoff
                )
            )
        )
        keys_to_complete = result.scalars().all()
        
        for key in keys_to_complete:
            key.complete_rotation()
            processed += 1
            security_logger.info(f"AUTO_ROTATION_COMPLETED | Key: {key.name}")
        
        return processed


# Singleton instance
api_key_service = APIKeyRotationService()


