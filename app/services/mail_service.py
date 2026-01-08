# -*- coding: utf-8 -*-
"""
Mail Service
- SMTP bağlantı
- Mail gönderim
- Tracking entegrasyonu
- Modern HTML şablon
"""

import ssl
import aiosmtplib
import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr
from typing import Optional, Dict, List
from datetime import datetime

from app.core.config import settings


class MailService:
    """Mail gönderim servisi"""
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
        use_tls: bool = True,
        sender_name: Optional[str] = None,
        tracking_base_url: Optional[str] = None,
        # Şablon ayarları
        company_name: Optional[str] = None,
        logo_path: Optional[str] = None,
        primary_color: str = "#3b82f6",
        secondary_color: str = "#1e40af",
        background_color: str = "#f8fafc",
        text_color: str = "#1e293b",
        header_text_color: str = "#ffffff",
        footer_text: str = "Bu mail otomatik olarak gönderilmiştir.\nLütfen yanıtlamayınız.",
        disclaimer_text: str = "Bu butona tıklayarak, bordronuzu görüntülediğinizi ve onaylayarak teslim aldığınızı beyan etmiş olursunuz.",
        show_logo: bool = True,
        logo_width: int = 150
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.use_tls = use_tls
        self.sender_name = sender_name
        self.tracking_base_url = tracking_base_url
        # Şablon ayarları
        self.company_name = company_name
        self.logo_path = logo_path
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.background_color = background_color
        self.text_color = text_color
        self.header_text_color = header_text_color
        self.footer_text = footer_text
        self.disclaimer_text = disclaimer_text
        self.show_logo = show_logo
        self.logo_width = logo_width
    
    async def test_connection(self) -> tuple[bool, str]:
        """SMTP bağlantısını test et"""
        try:
            if self.use_tls:
                # Port 587 - STARTTLS kullan
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=10
                )
                await smtp.connect()
                await smtp.starttls()
            else:
                # Port 465 - SSL/TLS kullan (Yandex, Gmail vb.)
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=10,
                    use_tls=True  # SSL bağlantı
                )
                await smtp.connect()
            
            await smtp.login(self.smtp_username, self.smtp_password)
            await smtp.quit()
            
            return True, "SMTP bağlantısı başarılı!"
            
        except aiosmtplib.SMTPAuthenticationError:
            return False, "Kimlik doğrulama hatası. Kullanıcı adı veya şifre yanlış."
        except aiosmtplib.SMTPConnectError as e:
            return False, f"Sunucuya bağlanılamadı. Sunucu adresi ve portu kontrol edin: {str(e)}"
        except Exception as e:
            return False, f"Bağlantı hatası: {str(e)}"
    
    async def send_payslip_email(
        self,
        to_email: str,
        employee_name: str,
        period: str,
        pdf_path: str,
        pdf_filename: str,
        tracking_id: str,
        subject_template: str,
        body_template: str
    ) -> tuple[bool, str]:
        """
        Bordro maili gönder
        
        Args:
            to_email: Alıcı email
            employee_name: Çalışan adı
            period: Dönem
            pdf_path: PDF dosya yolu
            pdf_filename: Eklenecek dosya adı
            tracking_id: Tracking ID
            subject_template: Konu şablonu
            body_template: İçerik şablonu
            
        Returns:
            tuple[bool, str]: (başarılı mı, mesaj)
        """
        try:
            # Şablon değişkenlerini değiştir
            subject = subject_template.replace("{name}", employee_name).replace("{period}", period)
            
            # Tracking URL'leri oluştur - önce instance değişkenine bak, yoksa config'den al
            tracking_base = self.tracking_base_url or settings.TRACKING_BASE_URL
            open_tracking_url = f"{tracking_base}/api/v1/tracking/pixel/{tracking_id}"
            download_url = f"{tracking_base}/api/v1/tracking/download/{tracking_id}"
            
            # HTML içerik oluştur
            html_body = self._create_html_body(
                body_template, 
                employee_name, 
                period, 
                download_url,
                open_tracking_url
            )
            
            # Mail oluştur
            msg = MIMEMultipart("alternative")
            
            # Gönderici
            if self.sender_name:
                msg['From'] = formataddr((str(Header(self.sender_name, 'utf-8')), self.smtp_username))
            else:
                msg['From'] = self.smtp_username
            
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Plain text versiyon
            plain_body = body_template.replace("{name}", employee_name).replace("{period}", period)
            plain_body += f"\n\nBordronuzu indirmek için: {download_url}"
            msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
            
            # HTML versiyon
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # PDF eki
            with open(pdf_path, 'rb') as f:
                pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
                pdf_attachment.add_header(
                    'Content-Disposition',
                    'attachment',
                    filename=pdf_filename
                )
                msg.attach(pdf_attachment)
            
            # Gönder
            if self.use_tls:
                # Port 587 - STARTTLS kullan
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=30
                )
                await smtp.connect()
                await smtp.starttls()
            else:
                # Port 465 - SSL/TLS kullan (Yandex, Gmail vb.)
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=30,
                    use_tls=True  # SSL bağlantı
                )
                await smtp.connect()
            
            await smtp.login(self.smtp_username, self.smtp_password)
            await smtp.sendmail(self.smtp_username, to_email, msg.as_string())
            await smtp.quit()
            
            return True, "Mail başarıyla gönderildi"
            
        except Exception as e:
            return False, f"Mail gönderilemedi: {str(e)}"
    
    def _create_html_body(
        self,
        body_template: str,
        employee_name: str,
        period: str,
        download_url: str,
        tracking_url: str
    ) -> str:
        """Modern HTML mail içeriği oluştur"""
        body_text = body_template.replace("{name}", employee_name).replace("{period}", period)
        if self.company_name:
            body_text = body_text.replace("{company}", self.company_name)
        body_text = body_text.replace("\n", "<br>")
        
        # Logo base64 encode
        logo_html = ""
        if self.show_logo and self.logo_path and os.path.exists(self.logo_path):
            try:
                with open(self.logo_path, 'rb') as f:
                    logo_data = base64.b64encode(f.read()).decode('utf-8')
                ext = self.logo_path.lower().split('.')[-1]
                mime_type = {
                    'png': 'image/png',
                    'jpg': 'image/jpeg', 
                    'jpeg': 'image/jpeg',
                    'svg': 'image/svg+xml',
                    'webp': 'image/webp'
                }.get(ext, 'image/png')
                logo_html = f'<img src="data:{mime_type};base64,{logo_data}" alt="Logo" style="display: block; margin: 0 auto 15px auto; max-width: {self.logo_width}px; height: auto;">'
            except Exception:
                pass
        
        footer_html = self.footer_text.replace("\n", "<br>") if self.footer_text else ""
        
        # Disclaimer metni
        disclaimer_html = ""
        if self.disclaimer_text:
            disclaimer_html = f'''
                            <!-- Disclaimer / Uyarı Metni -->
                            <div style="text-align: center; margin-top: 15px;">
                                <p style="color: #64748b; font-size: 12px; margin: 0; line-height: 1.5; font-style: italic;">
                                    ⚠️ {self.disclaimer_text}
                                </p>
                            </div>
            '''
        
        html = f"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bordro Bildirimi</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: {self.background_color};">
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="background-color: {self.background_color};">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="max-width: 600px; margin: 0 auto;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, {self.primary_color} 0%, {self.secondary_color} 100%); padding: 40px 30px; border-radius: 16px 16px 0 0; text-align: center;">
                            {logo_html}
                            <h1 style="color: {self.header_text_color}; margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">
                                📄 Bordro Bildirimi
                            </h1>
                            <div style="display: inline-block; background: rgba(255,255,255,0.2); color: {self.header_text_color}; padding: 8px 20px; border-radius: 20px; font-size: 14px; margin-top: 15px; font-weight: 500;">
                                {period}
                            </div>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="background: #ffffff; padding: 40px 30px; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0;">
                            <div style="color: {self.text_color}; font-size: 16px; line-height: 1.7;">
                                {body_text}
                            </div>
                            
                            <!-- Download Button -->
                            <div style="text-align: center; margin: 35px 0 15px 0;">
                                <a href="{download_url}" style="display: inline-block; background: linear-gradient(135deg, {self.primary_color} 0%, {self.secondary_color} 100%); color: #ffffff; padding: 16px 40px; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3); transition: all 0.3s ease;">
                                    📥 Bordroyu İndir
                                </a>
                            </div>
                            
                            {disclaimer_html}
                            
                            <!-- Info Box -->
                            <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-radius: 12px; padding: 20px; margin-top: 25px;">
                                <div style="display: flex; align-items: flex-start;">
                                    <span style="font-size: 20px; margin-right: 12px;">ℹ️</span>
                                    <div style="color: #0369a1; font-size: 14px; line-height: 1.6;">
                                        <strong>Bilgi:</strong> Bordronuz bu mailin ekinde de bulunmaktadır.<br>
                                        <strong>PDF Şifresi:</strong> TC Kimlik numaranızın son 6 hanesi
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background: #f8fafc; padding: 30px; border-radius: 0 0 16px 16px; border: 1px solid #e2e8f0; border-top: none; text-align: center;">
                            <p style="color: #64748b; font-size: 13px; margin: 0; line-height: 1.6;">
                                {footer_html}
                            </p>
                            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #e2e8f0;">
                                <p style="color: #94a3b8; font-size: 11px; margin: 0;">
                                    © {datetime.now().year} {self.company_name or 'BordroMaster'} • Tüm hakları saklıdır
                                </p>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
    <!-- Tracking Pixel -->
    <img src="{tracking_url}" width="1" height="1" style="display:none;" alt="">
</body>
</html>
"""
        return html
    
    def generate_preview_html(
        self,
        body_template: str,
        employee_name: str = "Örnek Çalışan",
        period: str = "Ocak 2024"
    ) -> str:
        """Mail önizleme HTML'i oluştur (tracking olmadan)"""
        return self._create_html_body(
            body_template=body_template,
            employee_name=employee_name,
            period=period,
            download_url="#",
            tracking_url=""
        )
    
    async def send_test_email(self, to_email: str) -> tuple[bool, str]:
        """Test maili gönder"""
        try:
            msg = MIMEMultipart()
            
            if self.sender_name:
                msg['From'] = formataddr((str(Header(self.sender_name, 'utf-8')), self.smtp_username))
            else:
                msg['From'] = self.smtp_username
            
            msg['To'] = to_email
            msg['Subject'] = "BordroMaster - Test Maili"
            
            body = """Bu bir test mailidir.

BordroMaster uygulaması üzerinden gönderilmiştir.
SMTP ayarlarınız doğru çalışıyor.

Saygılarımızla,
BordroMaster"""
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            if self.use_tls:
                # Port 587 - STARTTLS kullan
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=10
                )
                await smtp.connect()
                await smtp.starttls()
            else:
                # Port 465 - SSL/TLS kullan (Yandex, Gmail vb.)
                smtp = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=10,
                    use_tls=True  # SSL bağlantı
                )
                await smtp.connect()
            
            await smtp.login(self.smtp_username, self.smtp_password)
            await smtp.sendmail(self.smtp_username, to_email, msg.as_string())
            await smtp.quit()
            
            return True, f"Test maili {to_email} adresine gönderildi!"
            
        except Exception as e:
            return False, f"Test maili gönderilemedi: {str(e)}"



