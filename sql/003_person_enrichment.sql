-- Person enrichment: demographics, role provenance, authorization lines.
-- Apply with DATABASE_URL_UNPOOLED after 001_schema.sql.

ALTER TABLE avila.person
  ADD COLUMN IF NOT EXISTS birth_date date,
  ADD COLUMN IF NOT EXISTS phone text,
  ADD COLUMN IF NOT EXISTS address text,
  ADD COLUMN IF NOT EXISTS notes text;

CREATE INDEX IF NOT EXISTS idx_avila_person_phone ON avila.person (phone);

ALTER TABLE avila.invoice_person
  ADD COLUMN IF NOT EXISTS parentesco text,
  ADD COLUMN IF NOT EXISTS source text;

CREATE TABLE IF NOT EXISTS avila.authorization_line (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid REFERENCES avila.invoice (id) ON DELETE SET NULL,
  person_id uuid REFERENCES avila.person (id) ON DELETE SET NULL,
  clave_rms text,
  contratante text,
  service_date date,
  request_date date,
  diagnosis text,
  service_description text,
  provider_name text,
  provider_rif text,
  amount_bs numeric,
  amount_usd numeric,
  coverage_amount numeric,
  authorized_amount numeric,
  source_file text NOT NULL,
  source_row text NOT NULL,
  source_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_avila_auth_invoice ON avila.authorization_line (invoice_id);
CREATE INDEX IF NOT EXISTS idx_avila_auth_person ON avila.authorization_line (person_id);
CREATE INDEX IF NOT EXISTS idx_avila_auth_clave ON avila.authorization_line (clave_rms);
