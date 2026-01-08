-- Migration: Add mail_disclaimer_text column to companies table
-- Date: 2026-01-08
-- Description: Adds disclaimer text field for email template (shown below download button)

ALTER TABLE companies ADD COLUMN IF NOT EXISTS mail_disclaimer_text TEXT DEFAULT 'Bu butona tıklayarak, bordronuzu görüntülediğinizi ve onaylayarak teslim aldığınızı beyan etmiş olursunuz.';

