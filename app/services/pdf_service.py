# -*- coding: utf-8 -*-
"""
PDF Service
- PDF bölme
- PDF şifreleme
- TC, isim, soyisim çıkarma
"""

import os
import re
import uuid
import secrets
import shutil
from typing import List, Dict, Tuple, Optional
from datetime import datetime

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


def turkce_karakter_duzelt(text: str) -> str:
    """PDF'deki bozuk font encoding'ini düzeltir"""
    if not text:
        return text
    
    result = []
    for c in text:
        code = ord(c)
        if code == 286:  # Ğ -> İ
            result.append('İ')
        elif code == 287:  # ğ -> Ş
            result.append('Ş')
        elif code == 190:  # ¾ -> Ğ
            result.append('Ğ')
        elif code == 219:  # Û -> ı
            result.append('ı')
        elif code == 8355:  # ₣ -> ğ
            result.append('ğ')
        else:
            result.append(c)
    
    return ''.join(result)


class PDFService:
    """PDF işlemlerini yöneten servis"""
    
    def __init__(self, output_dir: str):
        if not FITZ_AVAILABLE:
            raise ImportError("PyMuPDF modülü yüklü değil")
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def process_pdf(
        self, 
        pdf_path: str, 
        company_id: int,
        period: str
    ) -> Tuple[List[Dict], List[str]]:
        """
        PDF'i böl ve şifrele
        
        Args:
            pdf_path: PDF dosyasının yolu
            company_id: Şirket ID
            period: Dönem (YYYY-MM)
            
        Returns:
            Tuple[List[Dict], List[str]]: (başarılı sayfalar, hatalar)
        """
        results = []
        errors = []
        
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            errors.append(f"PDF açılamadı: {str(e)}")
            return results, errors
        
        # Şifreleme ayarları
        encryption_settings = {
            "encryption": fitz.PDF_ENCRYPT_AES_256,
            "permissions": fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ
        }
        
        # Şirket klasörünü oluştur
        company_dir = os.path.join(self.output_dir, str(company_id), period)
        os.makedirs(company_dir, exist_ok=True)
        
        for page_no in range(len(doc)):
            page = doc[page_no]
            
            # TC, isim, soyisim ve tarih çıkar (eski kodla birebir aynı)
            tc, isim, soyisim, bordro_tarihi = self._extract_info(page)
            
            if tc and isim and soyisim:
                # Dosya adı oluştur (eski kodla birebir aynı)
                isim_temiz = self._clean_filename(isim)
                soyisim_temiz = self._clean_filename(soyisim)
                
                # Benzersiz ve kriptografik olarak güvenli tracking ID (64 karakter)
                tracking_id = secrets.token_urlsafe(48)
                
                # Dosya adı
                if bordro_tarihi:
                    tarih_temiz = bordro_tarihi.replace(".", "-")
                    filename = f"{tc}_{isim_temiz}_{soyisim_temiz}_{tarih_temiz}.pdf"
                else:
                    filename = f"{tc}_{isim_temiz}_{soyisim_temiz}.pdf"
                
                output_path = os.path.join(company_dir, filename)
                
                # Şifre (TC'nin son 6 hanesi)
                sifre = tc[-6:]
                
                # PDF oluştur ve şifrele
                try:
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=page_no, to_page=page_no)
                    new_doc.save(
                        output_path,
                        encryption=encryption_settings["encryption"],
                        user_pw=sifre,
                        owner_pw=sifre + "admin",
                        permissions=encryption_settings["permissions"]
                    )
                    new_doc.close()
                    
                    results.append({
                        "page": page_no + 1,
                        "tc_no": tc,
                        "first_name": isim,
                        "last_name": soyisim,
                        "pdf_path": output_path,
                        "pdf_password": sifre,
                        "tracking_id": tracking_id,
                        "period_date": bordro_tarihi
                    })
                    
                except Exception as e:
                    errors.append(f"Sayfa {page_no + 1}: PDF oluşturulamadı - {str(e)}")
            else:
                errors.append(f"Sayfa {page_no + 1}: TC veya isim bulunamadı")
        
        doc.close()
        return results, errors
    
    def _extract_info(self, page) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Sayfadan TC, isim, soyisim ve tarih çıkar - bordro_boler_gui.py ile birebir aynı"""
        blocks = page.get_text("dict")["blocks"]
        
        tc = None
        tc_bbox = None
        bordro_tarihi = None
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Türkçe karakter düzeltme eklendi (eski kodla aynı)
                        text = turkce_karakter_duzelt(span["text"].strip())
                        # 11 haneli TC kimlik numarası
                        if text.isdigit() and len(text) == 11:
                            tc = text
                            tc_bbox = span["bbox"]
                        # Bordro tarihi (GG.AA.YYYY formatı)
                        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
                            bbox = span["bbox"]
                            if bbox[1] < 60:
                                bordro_tarihi = text
        
        if tc is None or tc_bbox is None:
            return None, None, None, None
        
        tc_x0, tc_y0, tc_x1, tc_y1 = tc_bbox
        metin_parcalari = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Türkçe karakter düzeltme eklendi (eski kodla aynı)
                        text = turkce_karakter_duzelt(span["text"].strip())
                        bbox = span["bbox"]
                        x0, y0, x1, y1 = bbox
                        
                        # TC'nin x koordinatına yakın (aynı sütunda) ve altında olan metinler
                        if abs(x0 - tc_x0) < 30 or (x0 > tc_x0 - 10 and x0 < tc_x0 + 50):
                            if y0 > tc_y0 and y0 < tc_y0 + 30:
                                # Sayı değilse ve boş değilse
                                if text and not text.isdigit():
                                    metin_parcalari.append((y0, x0, text, bbox))
        
        # Y koordinatına göre grupla (aynı satırdaki metinler)
        satirlar = {}
        for y0, x0, text, bbox in metin_parcalari:
            satir_key = None
            for key in satirlar.keys():
                if abs(key - y0) < 5:
                    satir_key = key
                    break
            if satir_key is None:
                satir_key = y0
                satirlar[satir_key] = []
            satirlar[satir_key].append((x0, text))
        
        # Her satırdaki metinleri x koordinatına göre sırala ve birleştir
        birlesik_satirlar = []
        for y0 in sorted(satirlar.keys()):
            parcalar = sorted(satirlar[y0], key=lambda x: x[0])
            birlesik_metin = ''.join([p[1] for p in parcalar]).strip()
            if birlesik_metin and len(birlesik_metin) > 1:
                # Sadece harf ve boşluk içermeli
                if all(c.isalpha() or c.isspace() for c in birlesik_metin):
                    birlesik_satirlar.append((y0, birlesik_metin))
        
        isim = None
        soyisim = None
        
        if len(birlesik_satirlar) >= 2:
            isim = birlesik_satirlar[0][1]
            soyisim = birlesik_satirlar[1][1]
        elif len(birlesik_satirlar) == 1:
            isim = birlesik_satirlar[0][1]
        
        return tc, isim, soyisim, bordro_tarihi
    
    def _clean_filename(self, text: str) -> str:
        """Dosya adı için geçersiz karakterleri temizle"""
        if text is None:
            return "BILINMEYEN"
        
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            text = text.replace(char, '')
        
        return text.strip()
    
    def get_pdf_path(self, company_id: int, period: str, filename: str) -> str:
        """PDF dosya yolunu al"""
        return os.path.join(self.output_dir, str(company_id), period, filename)
    
    def delete_period_pdfs(self, company_id: int, period: str) -> bool:
        """Dönem PDF'lerini sil"""
        period_dir = os.path.join(self.output_dir, str(company_id), period)
        if os.path.exists(period_dir):
            shutil.rmtree(period_dir)
            return True
        return False



