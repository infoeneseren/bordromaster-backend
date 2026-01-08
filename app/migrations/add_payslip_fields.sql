-- Migration: Payslip tablosuna yeni alanlar ekleme
-- Tarih: 2026-01-07
-- Açıklama: Çalışan bulunamasa bile bordro kaydı oluşturabilmek için gerekli alanlar

-- employee_id nullable yap
ALTER TABLE payslips ALTER COLUMN employee_id DROP NOT NULL;

-- Yeni alanları ekle
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS tc_no VARCHAR(11);
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS extracted_first_name VARCHAR(100);
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS extracted_last_name VARCHAR(100);

-- tc_no için index ekle
CREATE INDEX IF NOT EXISTS ix_payslips_tc_no ON payslips(tc_no);

-- Status enum'una yeni değer ekle (PostgreSQL'de)
-- Önce mevcut enum değerlerini kontrol et
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'no_employee' AND enumtypid = 'payslipstatus'::regtype) THEN
        ALTER TYPE payslipstatus ADD VALUE 'no_employee';
    END IF;
EXCEPTION
    WHEN others THEN
        NULL;
END $$;


