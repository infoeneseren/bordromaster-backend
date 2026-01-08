# -*- coding: utf-8 -*-
"""
Şifreleme Servisi
- Hassas verilerin şifrelenmesi/çözülmesi
- SMTP şifresi, API anahtarları vb.
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

security_logger = logging.getLogger("security")


class EncryptionService:
    """
    Fernet simetrik şifreleme servisi
    
    Kullanım:
        enc = EncryptionService()
        encrypted = enc.encrypt("secret_password")
        decrypted = enc.decrypt(encrypted)
    """
    
    def __init__(self, key: str = None):
        """
        Args:
            key: Şifreleme anahtarı (None ise settings'den alınır)
        """
        from app.core.config import settings
        
        # Master key - .env'den veya settings'den
        master_key = key or os.getenv("ENCRYPTION_KEY") or settings.SECRET_KEY
        
        # Fernet key oluştur (PBKDF2 ile türet)
        self.fernet = self._create_fernet(master_key)
    
    def _create_fernet(self, master_key: str) -> Fernet:
        """Master key'den Fernet key oluştur"""
        # Salt (sabit - key değişikliğinde veri kaybı olmaması için)
        salt = b"bordromaster_encryption_salt_v1"
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Metni şifrele
        
        Args:
            plaintext: Şifrelenecek metin
            
        Returns:
            Base64 encoded şifreli metin
        """
        if not plaintext:
            return ""
        
        try:
            encrypted = self.fernet.encrypt(plaintext.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            security_logger.error(f"ENCRYPTION_ERROR | {e}")
            raise ValueError("Şifreleme hatası")
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Şifreli metni çöz
        
        Args:
            ciphertext: Base64 encoded şifreli metin
            
        Returns:
            Çözülmüş metin
        """
        if not ciphertext:
            return ""
        
        try:
            encrypted = base64.urlsafe_b64decode(ciphertext.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            security_logger.error(f"DECRYPTION_ERROR | {e}")
            raise ValueError("Şifre çözme hatası")
    
    def is_encrypted(self, value: str) -> bool:
        """
        Değerin şifrelenmiş olup olmadığını kontrol et
        
        Basit kontrol: Decrypt edebiliyorsa şifrelidir
        """
        if not value:
            return False
        
        try:
            self.decrypt(value)
            return True
        except:
            return False


# Singleton instance
_encryption_service = None


def get_encryption_service() -> EncryptionService:
    """Singleton encryption service instance"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_sensitive_data(data: str) -> str:
    """Hassas veriyi şifrele"""
    return get_encryption_service().encrypt(data)


def decrypt_sensitive_data(data: str) -> str:
    """Şifreli veriyi çöz"""
    return get_encryption_service().decrypt(data)

