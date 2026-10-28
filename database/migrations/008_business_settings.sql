-- Shared Super Bajaar operating settings. Safe to apply repeatedly.
BEGIN;
CREATE TABLE IF NOT EXISTS app_business_settings (
  settings_key TEXT PRIMARY KEY CHECK (settings_key = 'global'),
  settings JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_by BIGINT REFERENCES app_users(id) ON DELETE SET NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(settings) = 'object')
);
INSERT INTO app_business_settings (settings_key, settings)
VALUES ('global', '{}'::jsonb)
ON CONFLICT (settings_key) DO NOTHING;
COMMIT;
