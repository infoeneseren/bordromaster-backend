# -*- coding: utf-8 -*-
"""
Password Policy - Şifre Güvenlik Politikası
- Güçlü şifre kuralları
- Yaygın şifre kontrolü
- Kişisel bilgi kontrolü (ad, soyad, email)
"""

import re
import hashlib
import logging
from typing import Tuple, List, Optional

security_logger = logging.getLogger("security")

# En yaygın kullanılan zayıf şifreler listesi (Top 1000'den seçilmiş)
COMMON_PASSWORDS = {
    # En yaygın şifreler
    "123456", "123456789", "12345678", "1234567", "12345", "1234567890",
    "password", "password1", "password123", "password1234",
    "qwerty", "qwerty123", "qwertyuiop",
    "abc123", "abc12345", "abcd1234",
    "111111", "000000", "123123", "654321", "666666", "888888",
    "admin", "admin123", "admin1234", "administrator",
    "root", "root123", "toor",
    "letmein", "welcome", "welcome1", "welcome123",
    "monkey", "dragon", "master", "login", "princess", "sunshine",
    "football", "baseball", "soccer", "hockey", "basketball",
    "superman", "batman", "spiderman",
    "michael", "jennifer", "jessica", "michelle", "daniel",
    "iloveyou", "loveyou", "trustno1",
    "123qwe", "qwe123", "zaq12wsx", "1qaz2wsx",
    "passw0rd", "p@ssw0rd", "p@ssword", "pa$$word", "passw0rd!",
    
    # Türkçe yaygın şifreler
    "sifre", "sifre123", "sifre1234", "şifre", "şifre123",
    "parola", "parola123", "parola1234",
    "turkiye", "türkiye", "istanbul", "ankara", "izmir",
    "galatasaray", "fenerbahce", "besiktas", "trabzonspor",
    "mehmet", "ahmet", "mustafa", "ali", "ayse", "fatma",
    "asdasd", "asdqwe", "qweasd",
    "deneme", "deneme123", "test", "test123", "test1234",
    
    # Klavye pattern'leri
    "qazwsx", "wsxedc", "edcrfv", "rfvtgb",
    "zxcvbn", "zxcvbnm", "asdfgh", "asdfghjkl",
    "1q2w3e", "1q2w3e4r", "1q2w3e4r5t",
    "q1w2e3r4", "q1w2e3r4t5",
    
    # Tarih pattern'leri
    "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "2028", "2029", "2030",
    "01012020", "01012021", "01012022", "01012023", "01012024", "01012025",
    
    # Sayı dizileri
    "987654321", "0987654321", "1234", "4321",
    "0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999",
    "0123456789", "9876543210",
    
    # Şirket/Uygulama adları
    "bordro", "bordro123", "bordromaster", "bordro2024", "bordro2025",
    "company", "company123", "sirket", "firma",
}

# Yasaklı kelimeler (şifrede bulunmaması gereken)
BANNED_WORDS = {
    # Genel yasaklı kelimeler
    "password", "parola", "sifre", "şifre",
    "admin", "root", "user", "login", "guest",
    "qwerty", "asdf", "zxcv",
    
    # Şirket/Uygulama ile ilgili
    "bordro", "bordromaster", "sirket", "firma", "company",
    
    # Reeder ile ilgili tüm varyasyonlar
    "reeder", "reeeder", "reeeeder",
    "reepass", "reederpass", "reeder123", "reeder1234",
    "reeder2020", "reeder2021", "reeder2022", "reeder2023", "reeder2024", 
    "reeder2025", "reeder2026", "reeder2027", "reeder2028", "reeder2029", "reeder2030",
}


class PasswordPolicy:
    """Şifre politikası sınıfı"""
    
    def __init__(
        self,
        min_length: int = 8,
        max_length: int = 128,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True,
        check_common: bool = True,
        check_banned_words: bool = True,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special
        self.check_common = check_common
        self.check_banned_words = check_banned_words
    
    def validate(
        self, 
        password: str, 
        email: str = None,
        first_name: str = None,
        last_name: str = None,
        full_name: str = None
    ) -> Tuple[bool, List[str]]:
        """
        Şifreyi doğrula
        
        Args:
            password: Kontrol edilecek şifre
            email: Kullanıcı email'i (şifrede olmamalı)
            first_name: Kullanıcı adı (şifrede olmamalı)
            last_name: Kullanıcı soyadı (şifrede olmamalı)
            full_name: Kullanıcı tam adı (şifrede olmamalı)
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        password_lower = password.lower()
        
        # Türkçe karakterleri normalize et
        password_normalized = self._normalize_turkish(password_lower)
        
        # 1. Uzunluk kontrolü
        if len(password) < self.min_length:
            errors.append(f"Şifre en az {self.min_length} karakter olmalıdır")
        
        if len(password) > self.max_length:
            errors.append(f"Şifre en fazla {self.max_length} karakter olmalıdır")
        
        # 2. Karakter çeşitliliği kontrolleri
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("En az 1 büyük harf içermelidir (A-Z)")
        
        if self.require_lowercase and not re.search(r'[a-z]', password):
            errors.append("En az 1 küçük harf içermelidir (a-z)")
        
        if self.require_digit and not re.search(r'\d', password):
            errors.append("En az 1 rakam içermelidir (0-9)")
        
        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`]', password):
            errors.append("En az 1 özel karakter içermelidir (!@#$%^&*)")
        
        # 3. Yaygın şifre kontrolü
        if self.check_common:
            if password_lower in COMMON_PASSWORDS or password_normalized in COMMON_PASSWORDS:
                errors.append("Bu şifre çok yaygın ve güvensizdir. Farklı bir şifre seçin")
                security_logger.warning(f"COMMON_PASSWORD_ATTEMPT | Password hash: {self._hash_password(password)[:16]}...")
        
        # 4. Yasaklı kelime kontrolü
        if self.check_banned_words:
            for word in BANNED_WORDS:
                if word in password_lower or word in password_normalized:
                    errors.append(f"Şifre yasaklı kelime içeriyor. Farklı bir şifre seçin")
                    security_logger.warning(f"BANNED_WORD_ATTEMPT | Word: {word}")
                    break
        
        # 5. Email kontrolü (şifrede email olmamalı)
        if email:
            email_parts = email.lower().split('@')
            username = email_parts[0]
            if username and len(username) >= 3:
                if username in password_lower or username in password_normalized:
                    errors.append("Şifre e-posta adresinizi içeremez")
        
        # 6. Ad kontrolü (şifrede kullanıcı adı olmamalı)
        if first_name:
            first_name_lower = first_name.lower().strip()
            first_name_normalized = self._normalize_turkish(first_name_lower)
            if len(first_name_lower) >= 3:
                if first_name_lower in password_lower or first_name_normalized in password_normalized:
                    errors.append("Şifre adınızı içeremez")
        
        # 7. Soyad kontrolü (şifrede kullanıcı soyadı olmamalı)
        if last_name:
            last_name_lower = last_name.lower().strip()
            last_name_normalized = self._normalize_turkish(last_name_lower)
            if len(last_name_lower) >= 3:
                if last_name_lower in password_lower or last_name_normalized in password_normalized:
                    errors.append("Şifre soyadınızı içeremez")
        
        # 8. Tam ad kontrolü (full_name varsa parçala ve kontrol et)
        if full_name:
            name_parts = full_name.lower().strip().split()
            for part in name_parts:
                part_normalized = self._normalize_turkish(part)
                if len(part) >= 3:
                    if part in password_lower or part_normalized in password_normalized:
                        errors.append("Şifre adınızı veya soyadınızı içeremez")
                        break
        
        # 9. Ardışık karakter kontrolü (aaaa, 1111 gibi)
        if self._has_repeated_chars(password, 4):
            errors.append("Şifre 4 veya daha fazla ardışık aynı karakter içeremez")
        
        # 10. Sıralı karakter kontrolü (1234, abcd gibi)
        if self._has_sequential_chars(password, 4):
            errors.append("Şifre 4 veya daha fazla ardışık sıralı karakter içeremez")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def _normalize_turkish(self, text: str) -> str:
        """Türkçe karakterleri normalize et"""
        replacements = {
            'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
            'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
            'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
        }
        for tr_char, en_char in replacements.items():
            text = text.replace(tr_char, en_char)
        return text
    
    def _has_repeated_chars(self, password: str, count: int) -> bool:
        """Ardışık tekrar eden karakter kontrolü (aaaa gibi)"""
        for i in range(len(password) - count + 1):
            if len(set(password[i:i+count])) == 1:
                return True
        return False
    
    def _has_sequential_chars(self, password: str, count: int) -> bool:
        """Sıralı karakter kontrolü (1234, abcd gibi)"""
        sequences = [
            "0123456789",
            "9876543210",
            "abcdefghijklmnopqrstuvwxyz",
            "zyxwvutsrqponmlkjihgfedcba",
            "qwertyuiop",
            "asdfghjkl",
            "zxcvbnm",
        ]
        
        password_lower = password.lower()
        
        for seq in sequences:
            for i in range(len(seq) - count + 1):
                if seq[i:i+count] in password_lower:
                    return True
        return False
    
    def _hash_password(self, password: str) -> str:
        """Şifreyi hashle (loglama için)"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def get_strength_score(self, password: str) -> Tuple[int, str]:
        """
        Şifre güç skoru hesapla (0-100)
        
        Returns:
            (score, strength_label)
        """
        score = 0
        
        # Uzunluk puanı (max 25)
        length = len(password)
        if length >= 8: score += 10
        if length >= 12: score += 10
        if length >= 16: score += 5
        
        # Karakter çeşitliliği puanı (max 40)
        if re.search(r'[a-z]', password): score += 10
        if re.search(r'[A-Z]', password): score += 10
        if re.search(r'\d', password): score += 10
        if re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`]', password): score += 10
        
        # Benzersizlik puanı (max 20)
        unique_ratio = len(set(password)) / len(password) if password else 0
        score += int(unique_ratio * 20)
        
        # Yaygın şifre cezası (-30)
        if password.lower() in COMMON_PASSWORDS:
            score -= 30
        
        # Ardışık karakter cezası (-10)
        if self._has_repeated_chars(password, 3):
            score -= 10
        
        # Sıralı karakter cezası (-10)
        if self._has_sequential_chars(password, 3):
            score -= 10
        
        # Skor sınırla
        score = max(0, min(100, score))
        
        # Etiket belirle
        if score >= 80:
            label = "Çok Güçlü"
        elif score >= 60:
            label = "Güçlü"
        elif score >= 40:
            label = "Orta"
        elif score >= 20:
            label = "Zayıf"
        else:
            label = "Çok Zayıf"
        
        return score, label


# Singleton instance
password_policy = PasswordPolicy()


def validate_password(
    password: str, 
    email: str = None,
    first_name: str = None,
    last_name: str = None,
    full_name: str = None
) -> str:
    """
    Şifreyi doğrula - Pydantic validator için
    
    Args:
        password: Kontrol edilecek şifre
        email: Kullanıcı email'i
        first_name: Kullanıcı adı
        last_name: Kullanıcı soyadı
        full_name: Kullanıcı tam adı
    
    Returns:
        Geçerli şifre
    
    Raises:
        ValueError: Şifre geçersizse
    """
    is_valid, errors = password_policy.validate(
        password, 
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name
    )
    
    if not is_valid:
        raise ValueError("; ".join(errors))
    
    return password


def check_password_strength(password: str) -> dict:
    """
    Şifre gücünü kontrol et (API için)
    
    Returns:
        {
            "score": 75,
            "strength": "Güçlü",
            "is_valid": True,
            "errors": [],
            "suggestions": []
        }
    """
    is_valid, errors = password_policy.validate(password)
    score, strength = password_policy.get_strength_score(password)
    
    suggestions = []
    if len(password) < 12:
        suggestions.append("Daha uzun bir şifre kullanın (12+ karakter)")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        suggestions.append("Özel karakterler ekleyin")
    if score < 60:
        suggestions.append("Daha karmaşık bir şifre seçin")
    
    return {
        "score": score,
        "strength": strength,
        "is_valid": is_valid,
        "errors": errors,
        "suggestions": suggestions
    }

