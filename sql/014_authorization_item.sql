-- One authorization_line stays the request header.
-- Items are the studies on that request. Sources are the workbook rows that carry it.
-- Apply with DATABASE_URL_UNPOOLED after 013_invoice_service_person.sql.

ALTER TABLE avila.authorization_line
  ADD COLUMN IF NOT EXISTS titular_person_id uuid REFERENCES avila.person (id) ON DELETE SET NULL;

ALTER TABLE avila.authorization_line
  ADD COLUMN IF NOT EXISTS duplicate_of uuid REFERENCES avila.authorization_line (id) ON DELETE SET NULL;

ALTER TABLE avila.authorization_line DROP CONSTRAINT IF EXISTS authorization_line_duplicate_not_self;
ALTER TABLE avila.authorization_line
  ADD CONSTRAINT authorization_line_duplicate_not_self
  CHECK (duplicate_of IS NULL OR duplicate_of <> id);

CREATE TABLE IF NOT EXISTS avila.authorization_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  authorization_line_id uuid NOT NULL REFERENCES avila.authorization_line (id) ON DELETE CASCADE,
  position integer NOT NULL CHECK (position >= 1),
  kind text NOT NULL CHECK (kind IN ('consulta', 'estudio', 'servicio')),
  label text NOT NULL,
  quantity numeric,
  source_row text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT authorization_item_line_row UNIQUE (authorization_line_id, source_row)
);

CREATE INDEX IF NOT EXISTS idx_avila_authorization_item_line
  ON avila.authorization_item (authorization_line_id, position);

CREATE TABLE IF NOT EXISTS avila.authorization_source (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  authorization_line_id uuid NOT NULL REFERENCES avila.authorization_line (id) ON DELETE CASCADE,
  source_file text NOT NULL,
  source_row text NOT NULL,
  source_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT authorization_source_hash UNIQUE (source_hash)
);

ALTER TABLE avila.authorization_source DROP CONSTRAINT IF EXISTS authorization_source_file_row;

CREATE INDEX IF NOT EXISTS idx_avila_authorization_source_line
  ON avila.authorization_source (authorization_line_id);

CREATE INDEX IF NOT EXISTS idx_avila_authorization_line_duplicate_of
  ON avila.authorization_line (duplicate_of)
  WHERE duplicate_of IS NOT NULL;

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'avila.field_provenance'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%entity%'
  LOOP
    EXECUTE format('ALTER TABLE avila.field_provenance DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;

ALTER TABLE avila.field_provenance ADD CONSTRAINT field_provenance_entity_check CHECK (
  entity IN (
    'person', 'invoice_person', 'document', 'invoice', 'authorization_line',
    'medico', 'atencion', 'medico_especialidad', 'especialidad', 'especialidad_term',
    'invoice_service', 'authorization_item', 'authorization_source'
  )
);
