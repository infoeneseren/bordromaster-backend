# -*- coding: utf-8 -*-
"""
PDF debug scripti - sorunlu sayfaları tespit et
"""

import fitz
import re
import sys
import os

def turkce_karakter_duzelt(text):
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


def extract_info_debug(page, page_no):
    """Sayfadan TC, isim, soyisim ve tarih çıkar - DEBUG versiyonu"""
    blocks = page.get_text("dict")["blocks"]
    
    tc = None
    tc_bbox = None
    bordro_date = None
    
    all_11_digit_numbers = []  # Tüm 11 haneli sayıları topla
    
    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    text = turkce_karakter_duzelt(span["text"].strip())
                    
                    # 11 haneli TC kimlik numarası
                    if text.isdigit() and len(text) == 11:
                        all_11_digit_numbers.append((text, span["bbox"]))
                        tc = text
                        tc_bbox = span["bbox"]
                    
                    # Bordro tarihi (GG.AA.YYYY formatı)
                    if re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
                        bbox = span["bbox"]
                        if bbox[1] < 60:  # Üst kısımdaki tarih
                            bordro_date = text
    
    print(f"\n{'='*60}")
    print(f"SAYFA {page_no + 1}")
    print(f"{'='*60}")
    print(f"Bulunan 11 haneli sayılar: {len(all_11_digit_numbers)}")
    for num, bbox in all_11_digit_numbers:
        print(f"  TC: {num}, bbox: {bbox}")
    
    if tc is None or tc_bbox is None:
        print(f"❌ TC BULUNAMADI!")
        return None, None, None, None, "TC bulunamadı"
    
    print(f"✓ TC bulundu: {tc}")
    print(f"  TC bbox: {tc_bbox}")
    
    # TC'nin altındaki isim/soyisim bilgilerini bul
    tc_x0, tc_y0, tc_x1, tc_y1 = tc_bbox
    text_parts = []
    
    print(f"\nTC altındaki metinleri arıyorum (y > {tc_y0} ve y < {tc_y0 + 30})...")
    
    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    text = turkce_karakter_duzelt(span["text"].strip())
                    bbox = span["bbox"]
                    x0, y0, x1, y1 = bbox
                    
                    # TC'nin x koordinatına yakın ve altında olan metinler
                    x_match = abs(x0 - tc_x0) < 30 or (x0 > tc_x0 - 10 and x0 < tc_x0 + 50)
                    y_match = y0 > tc_y0 and y0 < tc_y0 + 30
                    
                    if x_match and y_match:
                        if text and not text.isdigit():
                            text_parts.append((y0, x0, text, bbox))
                            print(f"  + Metin bulundu: '{text}' @ ({x0:.1f}, {y0:.1f})")
    
    if not text_parts:
        print(f"❌ TC altında metin bulunamadı!")
        
        # Daha geniş aralıkta ara
        print(f"\nDaha geniş aralıkta arıyorum (y > {tc_y0} ve y < {tc_y0 + 50})...")
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = turkce_karakter_duzelt(span["text"].strip())
                        bbox = span["bbox"]
                        x0, y0, x1, y1 = bbox
                        
                        if y0 > tc_y0 and y0 < tc_y0 + 50:
                            if text and not text.isdigit() and len(text) > 1:
                                print(f"  ? Potansiyel: '{text}' @ ({x0:.1f}, {y0:.1f}) x_diff={abs(x0-tc_x0):.1f}")
    
    # Y koordinatına göre grupla
    rows = {}
    for y0, x0, text, bbox in text_parts:
        row_key = None
        for key in rows.keys():
            if abs(key - y0) < 5:
                row_key = key
                break
        if row_key is None:
            row_key = y0
            rows[row_key] = []
        rows[row_key].append((x0, text))
    
    # Satırları birleştir
    combined_rows = []
    for y0 in sorted(rows.keys()):
        parts = sorted(rows[y0], key=lambda x: x[0])
        combined_text = ''.join([p[1] for p in parts]).strip()
        if combined_text and len(combined_text) > 1:
            # Sadece harf ve boşluk kontrolü
            is_valid = all(c.isalpha() or c.isspace() for c in combined_text)
            print(f"  Satır y={y0:.1f}: '{combined_text}' (valid={is_valid})")
            if is_valid:
                combined_rows.append((y0, combined_text))
    
    first_name = None
    last_name = None
    
    if len(combined_rows) >= 2:
        first_name = combined_rows[0][1]
        last_name = combined_rows[1][1]
        print(f"✓ İsim: {first_name}, Soyisim: {last_name}")
    elif len(combined_rows) == 1:
        first_name = combined_rows[0][1]
        print(f"⚠️ Sadece isim bulundu: {first_name}")
    else:
        print(f"❌ İSİM/SOYİSİM BULUNAMADI!")
        return tc, None, None, bordro_date, "İsim bulunamadı"
    
    return tc, first_name, last_name, bordro_date, None


def analyze_pdf(pdf_path):
    """PDF'i analiz et ve sorunlu sayfaları bul"""
    print(f"\nPDF Analiz: {pdf_path}")
    print(f"{'='*80}")
    
    doc = fitz.open(pdf_path)
    total = len(doc)
    success = 0
    failed = 0
    failed_pages = []
    
    for page_no in range(total):
        page = doc[page_no]
        tc, first_name, last_name, date, error = extract_info_debug(page, page_no)
        
        if tc and first_name:
            success += 1
        else:
            failed += 1
            failed_pages.append((page_no + 1, error))
    
    doc.close()
    
    print(f"\n{'='*80}")
    print(f"ÖZET")
    print(f"{'='*80}")
    print(f"Toplam: {total} sayfa")
    print(f"Başarılı: {success}")
    print(f"Başarısız: {failed}")
    
    if failed_pages:
        print(f"\nBaşarısız sayfalar:")
        for page_no, error in failed_pages:
            print(f"  Sayfa {page_no}: {error}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python debug_pdf.py <pdf_dosyası>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Dosya bulunamadı: {pdf_path}")
        sys.exit(1)
    
    analyze_pdf(pdf_path)


