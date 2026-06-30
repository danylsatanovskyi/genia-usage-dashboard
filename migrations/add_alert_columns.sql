-- Run this once in the Supabase SQL Editor
-- Adds alert state columns to project_metadata

ALTER TABLE project_metadata
  ADD COLUMN IF NOT EXISTS last_alert_status text,
  ADD COLUMN IF NOT EXISTS last_alert_sent   text;
