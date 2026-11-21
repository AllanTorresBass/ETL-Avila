-- One row per fiscal line, result sheet, or study order.
-- Apply with DATABASE_URL_UNPOOLED after 011_medico_especialidad.sql.
-- service_label is the short line, the same shape as authorization_line.service_description.
-- Page OCR stays in the local cache.

CREATE TABLE IF NOT EXISTS avila.invoice_service (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL REFERENCES avila.invoice (id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES avila.document (id) ON DELETE CASCADE,
  source text NOT NULL CHECK (source IN ('fiscal_line', 'result_page', 'study_order')),
  line_no integer NOT NULL CHECK (line_no >= 0),
  service_label text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('consulta', 'estudio', 'cargo')),
  procedimiento_id uuid REFERENCES avila.procedimiento (id) ON DELETE SET NULL,
  especialidad_id uuid REFERENCES avila.especialidad (id) ON DELETE SET NULL,
  link_status text NOT NULL CHECK (link_status IN ('matched', 'unmatched', 'review')),
  run_id uuid REFERENCES avila.etl_run (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT invoice_service_natural UNIQUE (invoice_id, source, document_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_avila_invoice_service_invoice ON avila.invoice_service (invoice_id);
CREATE INDEX IF NOT EXISTS idx_avila_invoice_service_kind ON avila.invoice_service (kind);
CREATE INDEX IF NOT EXISTS idx_avila_invoice_service_proc ON avila.invoice_service (procedimiento_id);
CREATE INDEX IF NOT EXISTS idx_avila_invoice_service_document ON avila.invoice_service (document_id);

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
    'invoice_service'
  )
);
