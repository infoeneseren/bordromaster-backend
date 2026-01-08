# -*- coding: utf-8 -*-
"""
Kritik İşlem Koruma Servisi
- Toplu silme gibi kritik işlemler için ek güvenlik
- Şifre doğrulama ile onay
- Cooldown süresi
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import logging

security_logger = logging.getLogger("security")


class CriticalActionProtection:
    """
    Kritik işlemler için koruma katmanı
    
    Kullanım senaryoları:
    - Toplu silme (tüm çalışanları sil, tüm bordroları sil)
    - Hesap silme
    - Admin yetkisi verme/alma
    """
    
    def __init__(self):
        # Son onaylanan işlemler: {user_id: {"action": action, "timestamp": datetime}}
        self.recent_confirmations: Dict[int, Dict] = {}
        
        # Cooldown süresi (aynı işlem tekrar yapılamaz)
        self.cooldown_minutes = 5
    
    def require_password_confirmation(
        self,
        user_id: int,
        action: str,
        provided_password: str,
        actual_password_hash: str,
        verify_password_func
    ) -> Tuple[bool, str]:
        """
        Kritik işlem için şifre onayı gerektir
        
        Args:
            user_id: İşlemi yapan kullanıcı
            action: İşlem tipi (bulk_delete_employees, delete_all_payslips vb.)
            provided_password: Kullanıcının girdiği şifre
            actual_password_hash: Veritabanındaki şifre hash'i
            verify_password_func: Şifre doğrulama fonksiyonu
            
        Returns:
            Tuple[is_authorized, message]
        """
        # 1. Cooldown kontrolü
        if self._is_in_cooldown(user_id, action):
            remaining = self._get_cooldown_remaining(user_id, action)
            return False, f"Bu işlem için {remaining} dakika beklemeniz gerekiyor"
        
        # 2. Şifre doğrulama
        if not provided_password:
            return False, "Bu işlem için şifrenizi girmeniz gerekiyor"
        
        if not verify_password_func(provided_password, actual_password_hash):
            security_logger.warning(
                f"CRITICAL_ACTION_BLOCKED | User: {user_id} | "
                f"Action: {action} | Reason: Invalid password"
            )
            return False, "Şifre hatalı"
        
        # 3. Onayı kaydet
        self._record_confirmation(user_id, action)
        
        security_logger.info(
            f"CRITICAL_ACTION_AUTHORIZED | User: {user_id} | Action: {action}"
        )
        
        return True, "İşlem onaylandı"
    
    def _is_in_cooldown(self, user_id: int, action: str) -> bool:
        """Kullanıcı cooldown'da mı kontrol et"""
        key = f"{user_id}_{action}"
        if key not in self.recent_confirmations:
            return False
        
        last_confirmation = self.recent_confirmations[key]["timestamp"]
        cooldown_end = last_confirmation + timedelta(minutes=self.cooldown_minutes)
        
        return datetime.utcnow() < cooldown_end
    
    def _get_cooldown_remaining(self, user_id: int, action: str) -> int:
        """Kalan cooldown süresini döndür (dakika)"""
        key = f"{user_id}_{action}"
        if key not in self.recent_confirmations:
            return 0
        
        last_confirmation = self.recent_confirmations[key]["timestamp"]
        cooldown_end = last_confirmation + timedelta(minutes=self.cooldown_minutes)
        remaining = cooldown_end - datetime.utcnow()
        
        return max(0, int(remaining.total_seconds() / 60) + 1)
    
    def _record_confirmation(self, user_id: int, action: str):
        """Onayı kaydet"""
        key = f"{user_id}_{action}"
        self.recent_confirmations[key] = {
            "action": action,
            "timestamp": datetime.utcnow()
        }
        
        # Eski kayıtları temizle (memory leak önleme)
        self._cleanup_old_records()
    
    def _cleanup_old_records(self):
        """1 saatten eski kayıtları temizle"""
        cutoff = datetime.utcnow() - timedelta(hours=1)
        
        keys_to_remove = [
            key for key, data in self.recent_confirmations.items()
            if data["timestamp"] < cutoff
        ]
        
        for key in keys_to_remove:
            del self.recent_confirmations[key]
    
    def generate_confirmation_token(self, user_id: int, action: str, secret_key: str) -> str:
        """
        Onay token'ı oluştur (alternatif: token tabanlı onay)
        
        Token 10 dakika geçerli
        """
        timestamp = int(datetime.utcnow().timestamp())
        message = f"{user_id}:{action}:{timestamp}"
        
        signature = hmac.new(
            secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        
        return f"{timestamp}:{signature}"
    
    def verify_confirmation_token(
        self,
        user_id: int,
        action: str,
        token: str,
        secret_key: str,
        max_age_minutes: int = 10
    ) -> bool:
        """Onay token'ını doğrula"""
        try:
            timestamp_str, signature = token.split(":")
            timestamp = int(timestamp_str)
            
            # Süre kontrolü
            current = int(datetime.utcnow().timestamp())
            if current - timestamp > max_age_minutes * 60:
                return False
            
            # İmza kontrolü
            expected_message = f"{user_id}:{action}:{timestamp}"
            expected_signature = hmac.new(
                secret_key.encode(),
                expected_message.encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            
            return hmac.compare_digest(signature, expected_signature)
            
        except (ValueError, AttributeError):
            return False


# Singleton instance
critical_action_protection = CriticalActionProtection()


def get_critical_action_protection() -> CriticalActionProtection:
    """Critical action protection instance al"""
    return critical_action_protection

