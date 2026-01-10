# -*- coding: utf-8 -*-
"""
Security Event Alerting Service
- Şüpheli aktivite tespiti
- Email ile bildirim
- Real-time güvenlik izleme
"""

import logging
import asyncio
import aiosmtplib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

security_logger = logging.getLogger("security")


class AlertSeverity(str, Enum):
    """Uyarı şiddeti seviyeleri"""
    LOW = "low"           # Bilgilendirme
    MEDIUM = "medium"     # Dikkat gerektiren
    HIGH = "high"         # Acil müdahale gerektiren
    CRITICAL = "critical" # Kritik güvenlik ihlali


class AlertType(str, Enum):
    """Uyarı tipleri"""
    # Authentication
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    ACCOUNT_LOCKED = "account_locked"
    SUSPICIOUS_LOGIN = "suspicious_login"
    LOGIN_FROM_NEW_LOCATION = "login_from_new_location"
    MULTIPLE_FAILED_LOGINS = "multiple_failed_logins"
    
    # Rate Limiting
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DDOS_SUSPECTED = "ddos_suspected"
    
    # API Security
    INVALID_API_KEY = "invalid_api_key"
    API_KEY_ABUSE = "api_key_abuse"
    
    # Data Security
    IDOR_ATTEMPT = "idor_attempt"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    
    # Session Security
    SESSION_HIJACK_SUSPECTED = "session_hijack_suspected"
    CONCURRENT_SESSIONS = "concurrent_sessions"
    
    # File Security
    MALICIOUS_FILE_UPLOAD = "malicious_file_upload"
    
    # General
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SECURITY_CONFIG_CHANGE = "security_config_change"


# Türkçe alert başlıkları
ALERT_TITLES = {
    AlertType.BRUTE_FORCE_ATTEMPT: "🚨 Brute Force Saldırısı",
    AlertType.ACCOUNT_LOCKED: "🔒 Hesap Kilitlendi",
    AlertType.SUSPICIOUS_LOGIN: "⚠️ Şüpheli Giriş",
    AlertType.LOGIN_FROM_NEW_LOCATION: "📍 Yeni Konum Girişi",
    AlertType.MULTIPLE_FAILED_LOGINS: "❌ Çoklu Başarısız Giriş",
    AlertType.RATE_LIMIT_EXCEEDED: "⏱️ Rate Limit Aşıldı",
    AlertType.DDOS_SUSPECTED: "🛑 DDoS Şüphesi",
    AlertType.INVALID_API_KEY: "🔑 Geçersiz API Key",
    AlertType.API_KEY_ABUSE: "⚡ API Key Kötüye Kullanım",
    AlertType.IDOR_ATTEMPT: "🎯 IDOR Saldırısı",
    AlertType.SQL_INJECTION_ATTEMPT: "💉 SQL Injection Denemesi",
    AlertType.XSS_ATTEMPT: "🔴 XSS Saldırısı",
    AlertType.PATH_TRAVERSAL_ATTEMPT: "📁 Path Traversal Saldırısı",
    AlertType.SESSION_HIJACK_SUSPECTED: "👤 Oturum Çalma Şüphesi",
    AlertType.CONCURRENT_SESSIONS: "👥 Eşzamanlı Oturum",
    AlertType.MALICIOUS_FILE_UPLOAD: "📎 Zararlı Dosya Yükleme",
    AlertType.SUSPICIOUS_ACTIVITY: "🔍 Şüpheli Aktivite",
    AlertType.SECURITY_CONFIG_CHANGE: "⚙️ Güvenlik Ayarı Değişikliği",
}


@dataclass
class SecurityAlert:
    """Güvenlik uyarısı veri yapısı"""
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    ip_address: Optional[str] = None
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    company_id: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.details is None:
            self.details = {}
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['alert_type'] = self.alert_type.value
        data['severity'] = self.severity.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


class SecurityAlertingService:
    """
    Security Event Alerting Service
    
    Güvenlik olaylarını tespit eder ve email ile bildirim gönderir.
    
    Özellikler:
    - Threshold-based detection (eşik değer tespiti)
    - Email bildirimleri (şirket SMTP ayarları ile)
    - Alert aggregation (benzer uyarıları gruplama)
    - Cooldown period (spam önleme)
    """
    
    # Cooldown süreleri (saniye)
    COOLDOWN_PERIODS = {
        AlertSeverity.LOW: 3600,        # 1 saat
        AlertSeverity.MEDIUM: 1800,     # 30 dakika
        AlertSeverity.HIGH: 600,        # 10 dakika
        AlertSeverity.CRITICAL: 60,     # 1 dakika
    }
    
    # Severity renkleri (HTML email için)
    SEVERITY_COLORS = {
        AlertSeverity.LOW: "#3b82f6",      # Mavi
        AlertSeverity.MEDIUM: "#f59e0b",   # Turuncu
        AlertSeverity.HIGH: "#ef4444",     # Kırmızı
        AlertSeverity.CRITICAL: "#7c2d12", # Koyu kırmızı
    }
    
    SEVERITY_LABELS = {
        AlertSeverity.LOW: "Düşük",
        AlertSeverity.MEDIUM: "Orta",
        AlertSeverity.HIGH: "Yüksek",
        AlertSeverity.CRITICAL: "Kritik",
    }
    
    def __init__(self):
        self._recent_alerts: Dict[str, datetime] = {}
        self._alert_counts: Dict[str, int] = {}
    
    def _get_alert_key(self, alert: SecurityAlert) -> str:
        """Uyarı için benzersiz key oluştur (deduplication için)"""
        return f"{alert.alert_type.value}:{alert.ip_address}:{alert.user_id}"
    
    def _should_send_alert(self, alert: SecurityAlert) -> bool:
        """Bu uyarı gönderilmeli mi kontrol et (cooldown ve dedup)"""
        key = self._get_alert_key(alert)
        cooldown = self.COOLDOWN_PERIODS.get(alert.severity, 3600)
        
        last_alert_time = self._recent_alerts.get(key)
        if last_alert_time:
            elapsed = (datetime.utcnow() - last_alert_time).total_seconds()
            if elapsed < cooldown:
                return False
        
        self._recent_alerts[key] = datetime.utcnow()
        return True
    
    def _build_alert_email_html(self, alert: SecurityAlert) -> str:
        """HTML email şablonu oluştur"""
        severity_color = self.SEVERITY_COLORS.get(alert.severity, "#3b82f6")
        severity_label = self.SEVERITY_LABELS.get(alert.severity, "Bilinmiyor")
        alert_title = ALERT_TITLES.get(alert.alert_type, alert.title)
        
        details_html = ""
        if alert.details:
            details_rows = "".join([
                f'<tr><td style="padding:8px;border-bottom:1px solid #e2e8f0;color:#64748b;">{k}</td>'
                f'<td style="padding:8px;border-bottom:1px solid #e2e8f0;color:#1e293b;font-weight:500;">{v}</td></tr>'
                for k, v in alert.details.items()
            ])
            details_html = f'''
            <table style="width:100%;border-collapse:collapse;margin-top:16px;">
                <tr style="background:#f8fafc;">
                    <th style="padding:8px;text-align:left;color:#64748b;">Detay</th>
                    <th style="padding:8px;text-align:left;color:#64748b;">Değer</th>
                </tr>
                {details_rows}
            </table>
            '''
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background-color:#f1f5f9;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                            <!-- Header -->
                            <tr>
                                <td style="background:linear-gradient(135deg,{severity_color},#1e293b);padding:32px;border-radius:12px 12px 0 0;">
                                    <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:600;">
                                        🛡️ BordroMaster Güvenlik Uyarısı
                                    </h1>
                                </td>
                            </tr>
                            
                            <!-- Alert Badge -->
                            <tr>
                                <td style="padding:24px 32px 0;">
                                    <span style="display:inline-block;background:{severity_color};color:#ffffff;padding:6px 16px;border-radius:20px;font-size:12px;font-weight:600;text-transform:uppercase;">
                                        {severity_label} Öncelik
                                    </span>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding:24px 32px;">
                                    <h2 style="margin:0 0 16px;color:#1e293b;font-size:20px;">
                                        {alert_title}
                                    </h2>
                                    <p style="margin:0 0 24px;color:#475569;font-size:16px;line-height:1.6;">
                                        {alert.description}
                                    </p>
                                    
                                    <!-- Info Box -->
                                    <div style="background:#f8fafc;border-left:4px solid {severity_color};padding:16px;border-radius:0 8px 8px 0;">
                                        <table style="width:100%;">
                                            <tr>
                                                <td style="color:#64748b;padding:4px 0;">IP Adresi:</td>
                                                <td style="color:#1e293b;font-weight:500;">{alert.ip_address or 'Bilinmiyor'}</td>
                                            </tr>
                                            <tr>
                                                <td style="color:#64748b;padding:4px 0;">Kullanıcı:</td>
                                                <td style="color:#1e293b;font-weight:500;">{alert.user_email or alert.user_id or 'Bilinmiyor'}</td>
                                            </tr>
                                            <tr>
                                                <td style="color:#64748b;padding:4px 0;">Zaman:</td>
                                                <td style="color:#1e293b;font-weight:500;">{alert.timestamp.strftime('%d.%m.%Y %H:%M:%S')} UTC</td>
                                            </tr>
                                        </table>
                                    </div>
                                    
                                    {details_html}
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="padding:24px 32px;border-top:1px solid #e2e8f0;">
                                    <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center;">
                                        Bu otomatik bir güvenlik bildirimidir.<br>
                                        Şüpheli aktivite tespit edildiğinde gönderilir.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        '''
    
    async def _get_admin_emails(self, company_id: int = None) -> List[str]:
        """Şirketin admin email adreslerini al"""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models import User, UserRole
            
            async with AsyncSessionLocal() as db:
                query = select(User.email).where(
                    User.role == UserRole.ADMIN,
                    User.is_active == True
                )
                if company_id:
                    query = query.where(User.company_id == company_id)
                
                result = await db.execute(query)
                emails = [row[0] for row in result.fetchall()]
                return emails
        except Exception as e:
            security_logger.error(f"Admin email alınamadı: {e}")
            return []
    
    async def _get_company_smtp_settings(self, company_id: int = None) -> Optional[Dict]:
        """Şirketin SMTP ayarlarını al"""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models import Company
            from app.core.smtp_encryption import decrypt_smtp_password
            
            async with AsyncSessionLocal() as db:
                if company_id:
                    result = await db.execute(
                        select(Company).where(Company.id == company_id)
                    )
                else:
                    # İlk şirketi al
                    result = await db.execute(select(Company).limit(1))
                
                company = result.scalar_one_or_none()
                
                if company and company.smtp_server and company.smtp_username:
                    # Şifreyi decrypt et
                    smtp_password = company.smtp_password
                    if smtp_password:
                        try:
                            smtp_password = decrypt_smtp_password(smtp_password)
                        except:
                            pass  # Zaten düz metin olabilir
                    
                    return {
                        "smtp_server": company.smtp_server,
                        "smtp_port": company.smtp_port or 587,
                        "smtp_username": company.smtp_username,
                        "smtp_password": smtp_password,
                        "use_tls": company.smtp_use_tls if company.smtp_use_tls is not None else True,
                        "sender_name": company.smtp_sender_name or company.name,
                    }
                return None
        except Exception as e:
            security_logger.error(f"SMTP ayarları alınamadı: {e}")
            return None
    
    async def _send_email_alert(self, alert: SecurityAlert, admin_emails: List[str], smtp_settings: Dict):
        """Email ile uyarı gönder"""
        if not admin_emails or not smtp_settings:
            security_logger.warning("Email gönderilemiyor: Admin email veya SMTP ayarı yok")
            return
        
        try:
            # Email içeriği oluştur
            html_content = self._build_alert_email_html(alert)
            alert_title = ALERT_TITLES.get(alert.alert_type, alert.title)
            severity_label = self.SEVERITY_LABELS.get(alert.severity, "")
            
            subject = f"[{severity_label}] {alert_title} - BordroMaster Güvenlik"
            
            # Her admin'e gönder
            for admin_email in admin_emails:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = formataddr((
                        smtp_settings.get("sender_name", "BordroMaster Güvenlik"),
                        smtp_settings["smtp_username"]
                    ))
                    msg["To"] = admin_email
                    
                    # Plain text alternatifi
                    text_content = f"""
BordroMaster Güvenlik Uyarısı

{alert_title}
Şiddet: {severity_label}

{alert.description}

IP Adresi: {alert.ip_address or 'Bilinmiyor'}
Kullanıcı: {alert.user_email or alert.user_id or 'Bilinmiyor'}
Zaman: {alert.timestamp.strftime('%d.%m.%Y %H:%M:%S')} UTC

Bu otomatik bir güvenlik bildirimidir.
                    """
                    
                    msg.attach(MIMEText(text_content, "plain", "utf-8"))
                    msg.attach(MIMEText(html_content, "html", "utf-8"))
                    
                    # SMTP bağlantısı ve gönderim
                    if smtp_settings.get("use_tls", True):
                        smtp = aiosmtplib.SMTP(
                            hostname=smtp_settings["smtp_server"],
                            port=smtp_settings["smtp_port"],
                            timeout=30
                        )
                        await smtp.connect()
                        await smtp.starttls()
                    else:
                        smtp = aiosmtplib.SMTP(
                            hostname=smtp_settings["smtp_server"],
                            port=smtp_settings["smtp_port"],
                            timeout=30,
                            use_tls=True
                        )
                        await smtp.connect()
                    
                    await smtp.login(smtp_settings["smtp_username"], smtp_settings["smtp_password"])
                    await smtp.send_message(msg)
                    await smtp.quit()
                    
                    security_logger.info(
                        f"SECURITY_ALERT_EMAIL_SENT | To: {admin_email} | Type: {alert.alert_type.value}"
                    )
                    
                except Exception as e:
                    security_logger.error(f"Email gönderim hatası ({admin_email}): {e}")
                    
        except Exception as e:
            security_logger.error(f"Email alert hatası: {e}")
    
    async def send_alert(self, alert: SecurityAlert) -> bool:
        """
        Güvenlik uyarısı gönder
        
        Args:
            alert: SecurityAlert objesi
        
        Returns:
            Uyarı gönderildi mi
        """
        # Cooldown kontrolü
        if not self._should_send_alert(alert):
            security_logger.debug(f"ALERT_SKIPPED (cooldown) | Type: {alert.alert_type.value}")
            return False
        
        # Log'a yaz
        log_level = {
            AlertSeverity.LOW: logging.INFO,
            AlertSeverity.MEDIUM: logging.WARNING,
            AlertSeverity.HIGH: logging.ERROR,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }.get(alert.severity, logging.WARNING)
        
        security_logger.log(
            log_level,
            f"SECURITY_ALERT | Type: {alert.alert_type.value} | "
            f"Severity: {alert.severity.value} | Title: {alert.title} | "
            f"IP: {alert.ip_address} | User: {alert.user_email or alert.user_id}"
        )
        
        # Email gönder (CRITICAL ve HIGH için)
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            # Admin emaillerini al
            admin_emails = await self._get_admin_emails(alert.company_id)
            
            # SMTP ayarlarını al
            smtp_settings = await self._get_company_smtp_settings(alert.company_id)
            
            if admin_emails and smtp_settings:
                await self._send_email_alert(alert, admin_emails, smtp_settings)
            else:
                security_logger.warning(
                    f"ALERT_EMAIL_SKIPPED | No admin emails or SMTP settings | "
                    f"Company: {alert.company_id}"
                )
        
        return True
    
    # ==================== HAZIR ALERT FACTORY'LERİ ====================
    
    async def alert_brute_force(
        self,
        ip_address: str,
        email: str = None,
        attempt_count: int = 0,
        company_id: int = None
    ):
        """Brute force saldırısı uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.BRUTE_FORCE_ATTEMPT,
            severity=AlertSeverity.HIGH,
            title="Brute Force Saldırısı Tespit Edildi",
            description=f"IP {ip_address} adresinden {attempt_count} başarısız giriş denemesi yapıldı. Bu IP adresi şüpheli aktivite nedeniyle kilitlendi.",
            ip_address=ip_address,
            user_email=email,
            company_id=company_id,
            details={
                "Deneme Sayısı": attempt_count,
                "Hedef Hesap": email or "Bilinmiyor",
                "Durum": "IP Kilitlendi"
            }
        )
        await self.send_alert(alert)
    
    async def alert_account_locked(
        self,
        ip_address: str,
        email: str,
        lockout_minutes: int = 15,
        company_id: int = None
    ):
        """Hesap kilitleme uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.ACCOUNT_LOCKED,
            severity=AlertSeverity.MEDIUM,
            title="Hesap Kilitlendi",
            description=f"{email} hesabı çok fazla başarısız giriş denemesi nedeniyle {lockout_minutes} dakika süreyle kilitlendi.",
            ip_address=ip_address,
            user_email=email,
            company_id=company_id,
            details={
                "Kilitlenen Hesap": email,
                "Kilit Süresi": f"{lockout_minutes} dakika",
                "Saldırgan IP": ip_address
            }
        )
        await self.send_alert(alert)
    
    async def alert_rate_limit(
        self,
        ip_address: str,
        endpoint: str,
        hit_count: int,
        company_id: int = None
    ):
        """Rate limit aşımı uyarısı"""
        severity = AlertSeverity.MEDIUM
        if hit_count > 100:
            severity = AlertSeverity.HIGH
        
        alert = SecurityAlert(
            alert_type=AlertType.RATE_LIMIT_EXCEEDED,
            severity=severity,
            title="Rate Limit Aşıldı",
            description=f"IP {ip_address} adresinden {endpoint} endpoint'ine aşırı miktarda istek yapıldı.",
            ip_address=ip_address,
            company_id=company_id,
            details={
                "Endpoint": endpoint,
                "İstek Sayısı": hit_count,
                "Durum": "Geçici Engellendi"
            }
        )
        await self.send_alert(alert)
    
    async def alert_suspicious_login(
        self,
        ip_address: str,
        email: str,
        user_id: int = None,
        reason: str = None,
        company_id: int = None
    ):
        """Şüpheli giriş uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.SUSPICIOUS_LOGIN,
            severity=AlertSeverity.HIGH,
            title="Şüpheli Giriş Tespit Edildi",
            description=f"{email} hesabına {ip_address} adresinden şüpheli bir giriş yapıldı.",
            ip_address=ip_address,
            user_id=user_id,
            user_email=email,
            company_id=company_id,
            details={
                "Hesap": email,
                "Şüphe Nedeni": reason or "Bilinmiyor",
                "Önerilen Aksiyon": "Şifreyi değiştirin ve oturumları kontrol edin"
            }
        )
        await self.send_alert(alert)
    
    async def alert_idor_attempt(
        self,
        ip_address: str,
        user_id: int,
        resource_type: str,
        resource_id: int,
        company_id: int = None
    ):
        """IDOR saldırısı uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.IDOR_ATTEMPT,
            severity=AlertSeverity.HIGH,
            title="IDOR Saldırısı Tespit Edildi",
            description=f"Kullanıcı #{user_id}, yetkisi olmayan bir kaynağa erişmeye çalıştı.",
            ip_address=ip_address,
            user_id=user_id,
            company_id=company_id,
            details={
                "Kaynak Tipi": resource_type,
                "Kaynak ID": resource_id,
                "Saldırgan Kullanıcı ID": user_id,
                "Sonuç": "Erişim Engellendi"
            }
        )
        await self.send_alert(alert)
    
    async def alert_path_traversal(
        self,
        ip_address: str,
        attempted_path: str,
        user_id: int = None,
        company_id: int = None
    ):
        """Path traversal saldırısı uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.PATH_TRAVERSAL_ATTEMPT,
            severity=AlertSeverity.CRITICAL,
            title="Path Traversal Saldırısı",
            description=f"Sistemde yetkisiz dosya erişimi denemesi tespit edildi.",
            ip_address=ip_address,
            user_id=user_id,
            company_id=company_id,
            details={
                "Denenen Yol": attempted_path[:100] + "..." if len(attempted_path) > 100 else attempted_path,
                "Tehlike Seviyesi": "Kritik",
                "Sonuç": "Erişim Engellendi"
            }
        )
        await self.send_alert(alert)
    
    async def alert_malicious_file(
        self,
        ip_address: str,
        filename: str,
        reason: str,
        user_id: int = None,
        company_id: int = None
    ):
        """Zararlı dosya yükleme uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.MALICIOUS_FILE_UPLOAD,
            severity=AlertSeverity.CRITICAL,
            title="Zararlı Dosya Yükleme Denemesi",
            description=f"Sisteme zararlı olabilecek bir dosya yüklenmeye çalışıldı.",
            ip_address=ip_address,
            user_id=user_id,
            company_id=company_id,
            details={
                "Dosya Adı": filename,
                "Engelleme Nedeni": reason,
                "Sonuç": "Yükleme Engellendi"
            }
        )
        await self.send_alert(alert)
    
    async def alert_api_key_abuse(
        self,
        ip_address: str,
        key_prefix: str,
        company_id: int,
        reason: str
    ):
        """API key kötüye kullanım uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.API_KEY_ABUSE,
            severity=AlertSeverity.HIGH,
            title="API Key Kötüye Kullanımı",
            description=f"Bir API anahtarının kötüye kullanıldığı tespit edildi.",
            ip_address=ip_address,
            company_id=company_id,
            details={
                "API Key": f"{key_prefix}...",
                "Kötüye Kullanım Türü": reason,
                "Önerilen Aksiyon": "API anahtarını yenileyin"
            }
        )
        await self.send_alert(alert)
    
    async def alert_config_change(
        self,
        user_id: int,
        user_email: str,
        config_type: str,
        ip_address: str = None,
        company_id: int = None
    ):
        """Güvenlik konfigürasyonu değişikliği uyarısı"""
        alert = SecurityAlert(
            alert_type=AlertType.SECURITY_CONFIG_CHANGE,
            severity=AlertSeverity.MEDIUM,
            title="Güvenlik Ayarları Değiştirildi",
            description=f"Sistem güvenlik ayarlarında değişiklik yapıldı.",
            ip_address=ip_address,
            user_id=user_id,
            user_email=user_email,
            company_id=company_id,
            details={
                "Değiştiren": user_email,
                "Değişiklik Türü": config_type,
                "Not": "Bu değişikliği siz yapmadıysanız derhal kontrol edin"
            }
        )
        await self.send_alert(alert)
    
    async def alert_password_change(
        self,
        user_id: int,
        user_email: str,
        ip_address: str,
        company_id: int = None,
        sessions_terminated: int = 0
    ):
        """Şifre değişikliği bilgilendirmesi"""
        alert = SecurityAlert(
            alert_type=AlertType.SECURITY_CONFIG_CHANGE,
            severity=AlertSeverity.LOW,
            title="Şifre Değiştirildi",
            description=f"{user_email} hesabının şifresi değiştirildi.",
            ip_address=ip_address,
            user_id=user_id,
            user_email=user_email,
            company_id=company_id,
            details={
                "Hesap": user_email,
                "Sonlandırılan Oturum": sessions_terminated,
                "Not": "Bu işlemi siz yapmadıysanız derhal şifrenizi yenileyin"
            }
        )
        await self.send_alert(alert)


# Singleton instance
security_alerting = SecurityAlertingService()
