-- Provenance, run tracking, and review queue.
-- Apply with DATABASE_URL_UNPOOLED after 005_identity_document_types.sql.
-- field_provenance stores value hashes and source references, never OCR text.

CREATE TABLE IF NOT EXISTS avila.etl_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  script text NOT NULL,
  args jsonb NOT NULL DEFAULT '{}'::jsonb,
  git_sha text,
  mode text NOT NULL CHECK (mode IN ('dry', 'apply')),
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  counters jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_avila_etl_run_started ON avila.etl_run (started_at DESC);

CREATE TABLE IF NOT EXISTS avila.field_provenance (
  id bigserial PRIMARY KEY,
  entity text NOT NULL CHECK (
    entity IN ('person', 'invoice_person', 'document', 'invoice', 'authorization_line')
  ),
  entity_id text NOT NULL,
  field text NOT NULL,
  old_value_hash text,
  new_value_hash text,
  source_kind text NOT NULL CHECK (
    source_kind IN ('workbook', 'ocr', 'path', 'case_evidence', 'manual', 'review', 'derived')
  ),
  source_ref text,
  rule_id text NOT NULL,
  confidence numeric CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  reason text,
  run_id uuid REFERENCES avila.etl_run (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_avila_prov_entity ON avila.field_provenance (entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_avila_prov_run ON avila.field_provenance (run_id);
CREATE INDEX IF NOT EXISTS idx_avila_prov_rule ON avila.field_provenance (rule_id);

CREATE TABLE IF NOT EXISTS avila.review_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (
    kind IN (
      'duplicate_candidate',
      'ci_conflict',
      'workbook_titular',
      'multiple_ci',
      'dob_conflict',
      'auth_match',
      'segment_review',
      'acta_titular'
    )
  ),
  dedupe_key text NOT NULL UNIQUE,
  person_id uuid REFERENCES avila.person (id) ON DELETE CASCADE,
  other_person_id uuid REFERENCES avila.person (id) ON DELETE CASCADE,
  invoice_id uuid REFERENCES avila.invoice (id) ON DELETE CASCADE,
  document_id uuid REFERENCES avila.document (id) ON DELETE CASCADE,
  authorization_line_id uuid REFERENCES avila.authorization_line (id) ON DELETE CASCADE,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  score numeric,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'rejected')),
  resolved_by text,
  resolved_at timestamptz,
  run_id uuid REFERENCES avila.etl_run (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_avila_review_status_kind ON avila.review_item (status, kind);
CREATE INDEX IF NOT EXISTS idx_avila_review_person ON avila.review_item (person_id);
CREATE INDEX IF NOT EXISTS idx_avila_review_invoice ON avila.review_item (invoice_id);

-- invoice_person.source becomes a closed vocabulary of rule ids.
UPDATE avila.invoice_person SET source = 'case_evidence'
WHERE source IS NOT NULL AND source LIKE 'repair\_%';
UPDATE avila.invoice_person SET source = 'legacy_unknown' WHERE source IS NULL OR source = '';

ALTER TABLE avila.invoice_person ALTER COLUMN source SET DEFAULT 'legacy_unknown';
ALTER TABLE avila.invoice_person ALTER COLUMN source SET NOT NULL;

DO $$ BEGIN
  ALTER TABLE avila.invoice_person ADD CONSTRAINT invoice_person_source_known CHECK (
    source IN (
      'workbook',
      'path',
      'ocr',
      'ocr_cedula',
      'fiscal_ocr',
      'scan_packet',
      'auth_match',
      'resolver',
      'review',
      'case_evidence',
      'manual',
      'legacy_unknown'
    )
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
