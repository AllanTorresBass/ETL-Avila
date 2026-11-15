-- Ávila GPS invoice / person document schema (isolated schema on shared Neon).
-- Apply with DATABASE_URL_UNPOOLED.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS avila;

DO $$ BEGIN
  CREATE TYPE avila.identity_type AS ENUM ('cedula', 'pasaporte', 'rif', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE avila.invoice_person_role AS ENUM ('titular', 'beneficiario', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE avila.document_type AS ENUM (
    'factura_fiscal',
    'cedula_identidad',
    'pasaporte',
    'egreso',
    'ingreso',
    'informe_medico',
    'comprobante',
    'carta_aval',
    'presupuesto',
    'laboratorio',
    'imagenologia',
    'orden_servicio',
    'otro_anexo',
    'ilegible'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE avila.upload_status AS ENUM ('pending', 'uploaded', 'failed', 'skipped');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS avila.account (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  legal_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS avila.person (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identity_type avila.identity_type NOT NULL DEFAULT 'unknown',
  identity_number text,
  full_name text,
  provisional_key text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT person_identity_unique UNIQUE (identity_type, identity_number)
);

CREATE TABLE IF NOT EXISTS avila.invoice (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_number text NOT NULL UNIQUE,
  account_id uuid REFERENCES avila.account (id) ON DELETE SET NULL,
  control_number text,
  issue_date date,
  invoice_range text,
  year text,
  month text,
  lote text,
  workflow text,
  channel text,
  duplicate_group text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS avila.invoice_person (
  invoice_id uuid NOT NULL REFERENCES avila.invoice (id) ON DELETE CASCADE,
  person_id uuid NOT NULL REFERENCES avila.person (id) ON DELETE CASCADE,
  role avila.invoice_person_role NOT NULL DEFAULT 'unknown',
  PRIMARY KEY (invoice_id, person_id)
);

CREATE TABLE IF NOT EXISTS avila.source_file (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid REFERENCES avila.invoice (id) ON DELETE SET NULL,
  backup_path text NOT NULL UNIQUE,
  file_label text NOT NULL,
  rule_id text,
  confidence text,
  extension text,
  pages integer,
  bytes bigint,
  duplicate_group text,
  related_invoice_number text,
  account_raw text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS avila.document (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_file_id uuid NOT NULL REFERENCES avila.source_file (id) ON DELETE CASCADE,
  invoice_id uuid REFERENCES avila.invoice (id) ON DELETE SET NULL,
  person_id uuid REFERENCES avila.person (id) ON DELETE SET NULL,
  page_index integer NOT NULL,
  document_type avila.document_type NOT NULL,
  evidence text,
  blob_pathname text UNIQUE,
  blob_url text,
  content_type text,
  byte_size bigint,
  sha256 text,
  upload_status avila.upload_status NOT NULL DEFAULT 'pending',
  upload_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT document_source_page UNIQUE (source_file_id, page_index)
);

CREATE INDEX IF NOT EXISTS idx_avila_person_identity_number ON avila.person (identity_number);
CREATE INDEX IF NOT EXISTS idx_avila_invoice_account ON avila.invoice (account_id);
CREATE INDEX IF NOT EXISTS idx_avila_invoice_duplicate_group ON avila.invoice (duplicate_group);
CREATE INDEX IF NOT EXISTS idx_avila_source_file_invoice ON avila.source_file (invoice_id);
CREATE INDEX IF NOT EXISTS idx_avila_source_file_label ON avila.source_file (file_label);
CREATE INDEX IF NOT EXISTS idx_avila_document_type ON avila.document (document_type);
CREATE INDEX IF NOT EXISTS idx_avila_document_invoice ON avila.document (invoice_id);
CREATE INDEX IF NOT EXISTS idx_avila_document_person ON avila.document (person_id);
CREATE INDEX IF NOT EXISTS idx_avila_document_upload_status ON avila.document (upload_status);

-- Drop the accidental public.person stub created before schema isolation.
DROP TABLE IF EXISTS public.person;
DROP TYPE IF EXISTS public.identity_type;
DROP TYPE IF EXISTS public.invoice_person_role;
DROP TYPE IF EXISTS public.document_type;
DROP TYPE IF EXISTS public.upload_status;
