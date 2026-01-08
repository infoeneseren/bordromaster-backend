# -*- coding: utf-8 -*-
"""
Redis Servis Modülü
- Bağlantı yönetimi
- Token Blacklist
- Rate Limiting
- Brute Force Protection
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import redis.asyncio as redis

from app.core.config import settings

security_logger = logging.getLogger("security")


class RedisService:
    """
    Redis bağlantı ve işlem servisi
    
    Singleton pattern ile tek instance kullanılır.
    """
    
    _instance: Optional['RedisService'] = None
    _redis: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self):
        """Redis'e bağlan"""
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Bağlantı testi
                await self._redis.ping()
                security_logger.info("Redis bağlantısı başarılı")
            except Exception as e:
                security_logger.error(f"Redis bağlantı hatası: {e}")
                self._redis = None
                raise
    
    async def disconnect(self):
        """Redis bağlantısını kapat"""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    @property
    def client(self) -> Optional[redis.Redis]:
        return self._redis
    
    async def is_connected(self) -> bool:
        """Bağlantı durumunu kontrol et"""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except:
            return False


# ==================== TOKEN BLACKLIST ====================

class RedisTokenBlacklist:
    """
    Redis tabanlı Token Blacklist
    
    Özellikler:
    - Logout sonrası token'ları geçersiz kılar
    - TTL ile otomatik temizleme
    - Dağıtık sistemlerde çalışır
    """
    
    PREFIX = "blacklist:token:"
    
    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service
    
    async def add(self, token: str, expires_at: datetime):
        """
        Token'ı blacklist'e ekle
        
        Args:
            token: Blacklist'e eklenecek token
            expires_at: Token'ın expire olacağı zaman
        """
        client = self.redis_service.client
        if not client:
            security_logger.warning("Redis bağlantısı yok, token blacklist'e eklenemedi")
            return
        
        try:
            key = f"{self.PREFIX}{token}"
            
            # TTL hesapla (token expire olana kadar sakla)
            now = datetime.utcnow()
            ttl_seconds = int((expires_at - now).total_seconds())
            
            if ttl_seconds > 0:
                await client.setex(key, ttl_seconds, "1")
                security_logger.info(f"Token blacklist'e eklendi, TTL: {ttl_seconds}s")
        except Exception as e:
            security_logger.error(f"Token blacklist ekleme hatası: {e}")
    
    async def is_blacklisted(self, token: str) -> bool:
        """Token blacklist'te mi kontrol et"""
        client = self.redis_service.client
        if not client:
            return False
        
        try:
            key = f"{self.PREFIX}{token}"
            return await client.exists(key) > 0
        except Exception as e:
            security_logger.error(f"Token blacklist kontrol hatası: {e}")
            return False
    
    async def remove(self, token: str):
        """Token'ı blacklist'ten kaldır (genelde gerekmez, TTL ile silinir)"""
        client = self.redis_service.client
        if not client:
            return
        
        try:
            key = f"{self.PREFIX}{token}"
            await client.delete(key)
        except Exception as e:
            security_logger.error(f"Token blacklist silme hatası: {e}")


# ==================== RATE LIMITING ====================

class RedisRateLimiter:
    """
    Redis tabanlı Rate Limiter
    
    Sliding window algoritması kullanır.
    Dağıtık sistemlerde tutarlı çalışır.
    """
    
    PREFIX = "ratelimit:"
    
    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service
    
    async def is_allowed(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        scope: str = "default"
    ) -> tuple[bool, int]:
        """
        İstek izinli mi kontrol et
        
        Args:
            identifier: IP adresi veya kullanıcı ID
            limit: Window içinde izin verilen maksimum istek
            window_seconds: Zaman penceresi (saniye)
            scope: Rate limit kapsamı (api, download, login vb.)
        
        Returns:
            (is_allowed, remaining_requests)
        """
        client = self.redis_service.client
        if not client:
            # Redis yoksa izin ver (fallback)
            return True, limit
        
        try:
            key = f"{self.PREFIX}{scope}:{identifier}"
            now = datetime.utcnow().timestamp()
            window_start = now - window_seconds
            
            # Pipeline ile atomic işlemler
            pipe = client.pipeline()
            
            # Eski kayıtları temizle
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Mevcut istek sayısını al
            pipe.zcard(key)
            
            # Yeni isteği ekle
            pipe.zadd(key, {str(now): now})
            
            # TTL ayarla
            pipe.expire(key, window_seconds)
            
            results = await pipe.execute()
            current_count = results[1]
            
            remaining = max(0, limit - current_count - 1)
            is_allowed = current_count < limit
            
            if not is_allowed:
                security_logger.warning(
                    f"RATE_LIMIT_EXCEEDED | Scope: {scope} | "
                    f"Identifier: {identifier} | Count: {current_count}/{limit}"
                )
            
            return is_allowed, remaining
            
        except Exception as e:
            security_logger.error(f"Rate limit kontrol hatası: {e}")
            return True, limit  # Hata durumunda izin ver
    
    async def get_remaining(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        scope: str = "default"
    ) -> int:
        """Kalan istek hakkını döndür"""
        client = self.redis_service.client
        if not client:
            return limit
        
        try:
            key = f"{self.PREFIX}{scope}:{identifier}"
            now = datetime.utcnow().timestamp()
            window_start = now - window_seconds
            
            # Eski kayıtları temizle ve say
            await client.zremrangebyscore(key, 0, window_start)
            current_count = await client.zcard(key)
            
            return max(0, limit - current_count)
            
        except Exception as e:
            security_logger.error(f"Rate limit remaining hatası: {e}")
            return limit
    
    async def reset(self, identifier: str, scope: str = "default"):
        """Rate limit sayacını sıfırla"""
        client = self.redis_service.client
        if not client:
            return
        
        try:
            key = f"{self.PREFIX}{scope}:{identifier}"
            await client.delete(key)
        except Exception as e:
            security_logger.error(f"Rate limit reset hatası: {e}")


# ==================== BRUTE FORCE PROTECTION ====================

class RedisBruteForceProtection:
    """
    Redis tabanlı Brute Force koruması
    
    IP ve email bazlı deneme takibi yapar.
    Dağıtık sistemlerde tutarlı çalışır.
    """
    
    PREFIX_IP = "bruteforce:ip:"
    PREFIX_EMAIL = "bruteforce:email:"
    PREFIX_LOCK = "bruteforce:lock:"
    
    def __init__(
        self,
        redis_service: RedisService,
        max_attempts: int = 5,
        lockout_minutes: int = 15,
        reset_minutes: int = 30
    ):
        self.redis_service = redis_service
        self.max_attempts = max_attempts
        self.lockout_minutes = lockout_minutes
        self.reset_minutes = reset_minutes
    
    async def is_blocked(self, ip: str, email: str = None) -> tuple[bool, str]:
        """
        IP veya email engellenmiş mi kontrol et
        
        Returns:
            (is_blocked, message)
        """
        client = self.redis_service.client
        if not client:
            return False, ""
        
        try:
            # IP kilidi kontrolü
            ip_lock_key = f"{self.PREFIX_LOCK}ip:{ip}"
            ip_lock_ttl = await client.ttl(ip_lock_key)
            
            if ip_lock_ttl > 0:
                remaining_minutes = ip_lock_ttl // 60 + 1
                return True, f"IP adresiniz {remaining_minutes} dakika boyunca engellenmiştir."
            
            # Email kilidi kontrolü
            if email:
                email_lock_key = f"{self.PREFIX_LOCK}email:{email.lower()}"
                email_lock_ttl = await client.ttl(email_lock_key)
                
                if email_lock_ttl > 0:
                    remaining_minutes = email_lock_ttl // 60 + 1
                    return True, f"Bu hesap {remaining_minutes} dakika boyunca kilitlenmiştir."
            
            return False, ""
            
        except Exception as e:
            security_logger.error(f"Brute force kontrol hatası: {e}")
            return False, ""
    
    async def record_attempt(self, ip: str, email: str, success: bool):
        """
        Login denemesini kaydet
        """
        client = self.redis_service.client
        if not client:
            return
        
        try:
            if success:
                # Başarılı giriş - sayaçları sıfırla
                await self._reset_attempts(ip, email)
                security_logger.info(f"LOGIN_SUCCESS | IP: {ip}")
                return
            
            # Başarısız giriş
            security_logger.warning(f"LOGIN_FAILED | IP: {ip}")
            
            # IP denemelerini artır
            ip_key = f"{self.PREFIX_IP}{ip}"
            ip_count = await client.incr(ip_key)
            await client.expire(ip_key, self.reset_minutes * 60)
            
            # Email denemelerini artır
            if email:
                email_key = f"{self.PREFIX_EMAIL}{email.lower()}"
                email_count = await client.incr(email_key)
                await client.expire(email_key, self.reset_minutes * 60)
            else:
                email_count = 0
            
            # Limit aşımı kontrolü - IP
            if ip_count >= self.max_attempts:
                ip_lock_key = f"{self.PREFIX_LOCK}ip:{ip}"
                await client.setex(ip_lock_key, self.lockout_minutes * 60, "1")
                security_logger.critical(
                    f"IP_LOCKED | IP: {ip} | Attempts: {ip_count}"
                )
            
            # Limit aşımı kontrolü - Email
            if email and email_count >= self.max_attempts:
                email_lock_key = f"{self.PREFIX_LOCK}email:{email.lower()}"
                await client.setex(email_lock_key, self.lockout_minutes * 60, "1")
                security_logger.critical(
                    f"ACCOUNT_LOCKED | Email: {email[:3]}*** | Attempts: {email_count}"
                )
                
        except Exception as e:
            security_logger.error(f"Brute force kayıt hatası: {e}")
    
    async def _reset_attempts(self, ip: str, email: str):
        """Başarılı giriş sonrası sayaçları sıfırla"""
        client = self.redis_service.client
        if not client:
            return
        
        try:
            keys_to_delete = [f"{self.PREFIX_IP}{ip}"]
            if email:
                keys_to_delete.append(f"{self.PREFIX_EMAIL}{email.lower()}")
            
            await client.delete(*keys_to_delete)
        except Exception as e:
            security_logger.error(f"Brute force reset hatası: {e}")
    
    async def get_remaining_attempts(self, ip: str, email: str = None) -> int:
        """Kalan deneme hakkını döndür"""
        client = self.redis_service.client
        if not client:
            return self.max_attempts
        
        try:
            ip_key = f"{self.PREFIX_IP}{ip}"
            ip_count = await client.get(ip_key)
            ip_count = int(ip_count) if ip_count else 0
            ip_remaining = self.max_attempts - ip_count
            
            if email:
                email_key = f"{self.PREFIX_EMAIL}{email.lower()}"
                email_count = await client.get(email_key)
                email_count = int(email_count) if email_count else 0
                email_remaining = self.max_attempts - email_count
                return min(ip_remaining, email_remaining)
            
            return ip_remaining
            
        except Exception as e:
            security_logger.error(f"Brute force remaining hatası: {e}")
            return self.max_attempts


# ==================== SINGLETON INSTANCES ====================

# Global Redis servisi
redis_service = RedisService()

# Token blacklist
token_blacklist = RedisTokenBlacklist(redis_service)

# Rate limiter
rate_limiter = RedisRateLimiter(redis_service)

# Brute force protection
brute_force_protection = RedisBruteForceProtection(
    redis_service,
    max_attempts=5,
    lockout_minutes=15,
    reset_minutes=30
)


# ==================== HELPER FUNCTIONS ====================

async def init_redis():
    """Redis'i başlat (uygulama başlangıcında çağrılır)"""
    await redis_service.connect()


async def close_redis():
    """Redis bağlantısını kapat (uygulama kapanışında çağrılır)"""
    await redis_service.disconnect()

