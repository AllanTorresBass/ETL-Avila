-- Médico, especialidad taxonomy, and per-report atención (encounter) links.
-- Apply with DATABASE_URL_UNPOOLED after 010_invoice_role_cohort.sql.
--
-- especialidad_area > especialidad (level 1) > especialidad (level 2, parent_id set).
-- especialidad_term maps every cleaned spelling to a concept and a kind; the
-- catalog itself is loaded from scripts/data/*.csv by scripts/especialidad_catalog.py.
-- especialidad_observation keeps how / where each term was matched (no page text).

CREATE TABLE IF NOT EXISTS avila.especialidad_area (
  code text PRIMARY KEY,
  name_es text NOT NULL,
  sort_order integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS avila.especialidad (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name_es text NOT NULL,
  name_practitioner_m text,
  name_practitioner_f text,
  area_code text NOT NULL REFERENCES avila.especialidad_area (code),
  parent_id uuid REFERENCES avila.especialidad (id) ON DELETE RESTRICT,
  level smallint NOT NULL DEFAULT 1 CHECK (level IN (1, 2)),
  marketing_category text,
  external_code text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT especialidad_level_parent CHECK (
    (level = 1 AND parent_id IS NULL) OR (level = 2 AND parent_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_avila_especialidad_parent ON avila.especialidad (parent_id);
CREATE INDEX IF NOT EXISTS idx_avila_especialidad_area ON avila.especialidad (area_code);

CREATE TABLE IF NOT EXISTS avila.procedimiento (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name_es text NOT NULL,
  especialidad_id uuid REFERENCES avila.especialidad (id) ON DELETE SET NULL,
  modality text NOT NULL CHECK (
    modality IN ('imagen', 'endoscopia', 'laboratorio', 'quirurgico', 'consulta', 'funcional')
  ),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS avila.especialidad_term (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  term_folded text NOT NULL UNIQUE,
  kind text NOT NULL CHECK (
    kind IN ('discipline', 'practitioner', 'adjective', 'procedure', 'role', 'degree', 'stop')
  ),
  especialidad_id uuid REFERENCES avila.especialidad (id) ON DELETE CASCADE,
  procedimiento_id uuid REFERENCES avila.procedimiento (id) ON DELETE CASCADE,
  degree_code text,
  source text NOT NULL DEFAULT 'seed' CHECK (source IN ('seed', 'review')),
  note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT especialidad_term_target CHECK (
    (kind IN ('discipline', 'practitioner', 'adjective') AND especialidad_id IS NOT NULL)
    OR (kind = 'procedure' AND procedimiento_id IS NOT NULL)
    OR (kind = 'role')
    OR (kind = 'degree' AND degree_code IS NOT NULL)
    OR (kind = 'stop' AND especialidad_id IS NULL AND procedimiento_id IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS avila.especialidad_observation (
  id bigserial PRIMARY KEY,
  raw_term text NOT NULL,
  l1_term text NOT NULL,
  context text NOT NULL CHECK (
    context IN (
      'label', 'doctor_title', 'report_title', 'referral',
      'fiscal_line', 'workbook_servicio', 'auth_line', 'directory'
    )
  ),
  source_ref text NOT NULL,
  match_method text NOT NULL CHECK (
    match_method IN ('exact', 'phrase', 'suffix_fragment', 'fuzzy', 'none')
  ),
  distance smallint,
  term_id uuid REFERENCES avila.especialidad_term (id) ON DELETE SET NULL,
  run_id uuid REFERENCES avila.etl_run (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT especialidad_observation_unique UNIQUE (source_ref, context, l1_term)
);

CREATE INDEX IF NOT EXISTS idx_avila_esp_obs_method_term
  ON avila.especialidad_observation (match_method, l1_term);

CREATE TABLE IF NOT EXISTS avila.medico (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text CHECK (title IS NULL OR title IN ('dr', 'dra')),
  full_name text NOT NULL,
  name_folded text NOT NULL,
  degree text,
  degree_university text,
  mpps text UNIQUE,
  colegio_number text,
  rif text,
  provisional_key text UNIQUE,
  is_gps_staff boolean NOT NULL DEFAULT false,
  merged_into uuid REFERENCES avila.medico (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT medico_has_key CHECK (mpps IS NOT NULL OR provisional_key IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_avila_medico_name_folded ON avila.medico (name_folded);

CREATE TABLE IF NOT EXISTS avila.medico_especialidad (
  medico_id uuid NOT NULL REFERENCES avila.medico (id) ON DELETE CASCADE,
  especialidad_id uuid NOT NULL REFERENCES avila.especialidad (id) ON DELETE CASCADE,
  source text NOT NULL CHECK (source IN ('ocr_label', 'ocr_title', 'review')),
  evidence_count integer NOT NULL DEFAULT 0,
  is_primary boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (medico_id, especialidad_id)
);

CREATE TABLE IF NOT EXISTS avila.medico_mention (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES avila.document (id) ON DELETE CASCADE,
  medico_id uuid REFERENCES avila.medico (id) ON DELETE SET NULL,
  role text NOT NULL CHECK (role IN ('tratante', 'firmante', 'solicitante', 'referido')),
  zone text NOT NULL CHECK (zone IN ('header', 'body', 'footer')),
  mpps_raw_hash text,
  name_folded text NOT NULL,
  confidence numeric CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  rule_id text NOT NULL,
  run_id uuid REFERENCES avila.etl_run (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT medico_mention_unique UNIQUE (document_id, role, name_folded)
);

CREATE INDEX IF NOT EXISTS idx_avila_medico_mention_medico ON avila.medico_mention (medico_id);

CREATE TABLE IF NOT EXISTS avila.atencion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  primary_document_id uuid NOT NULL UNIQUE REFERENCES avila.document (id) ON DELETE CASCADE,
  document_ids uuid[] NOT NULL DEFAULT '{}',
  invoice_id uuid REFERENCES avila.invoice (id) ON DELETE SET NULL,
  person_id uuid REFERENCES avila.person (id) ON DELETE SET NULL,
  medico_id uuid REFERENCES avila.medico (id) ON DELETE SET NULL,
  especialidad_id uuid REFERENCES avila.especialidad (id) ON DELETE SET NULL,
  procedimiento_id uuid REFERENCES avila.procedimiento (id) ON DELETE SET NULL,
  referred_especialidad_id uuid REFERENCES avila.especialidad (id) ON DELETE SET NULL,
  especialidad_source text CHECK (
    especialidad_source IS NULL OR especialidad_source IN (
      'label', 'doctor_title', 'report_title', 'fiscal_line', 'auth_line',
      'medico_primary', 'procedure', 'review'
    )
  ),
  person_link_rule text CHECK (
    person_link_rule IS NULL OR person_link_rule IN (
      'ci_exact', 'name_on_invoice', 'sole_beneficiario', 'self_visit', 'review'
    )
  ),
  encounter_date date,
  diagnosis_text text,
  report_kind text NOT NULL DEFAULT 'informe' CHECK (
    report_kind IN ('informe', 'orden', 'laboratorio', 'imagen')
  ),
  link_status text NOT NULL DEFAULT 'partial' CHECK (
    link_status IN ('complete', 'partial', 'review', 'unmatched', 'duplicate')
  ),
  duplicate_of uuid REFERENCES avila.atencion (id) ON DELETE SET NULL,
  confidence numeric CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  extractor_version text NOT NULL,
  text_fingerprint text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_avila_atencion_person ON avila.atencion (person_id);
CREATE INDEX IF NOT EXISTS idx_avila_atencion_medico ON avila.atencion (medico_id);
CREATE INDEX IF NOT EXISTS idx_avila_atencion_invoice ON avila.atencion (invoice_id);
CREATE INDEX IF NOT EXISTS idx_avila_atencion_especialidad ON avila.atencion (especialidad_id);
CREATE INDEX IF NOT EXISTS idx_avila_atencion_status ON avila.atencion (link_status);
CREATE INDEX IF NOT EXISTS idx_avila_atencion_fingerprint ON avila.atencion (text_fingerprint);

ALTER TABLE avila.authorization_line
  ADD COLUMN IF NOT EXISTS especialidad_id uuid REFERENCES avila.especialidad (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS procedimiento_id uuid REFERENCES avila.procedimiento (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS aps_code text;

CREATE INDEX IF NOT EXISTS idx_avila_auth_especialidad ON avila.authorization_line (especialidad_id);

-- One row per patient / médico / especialidad, duplicates excluded.
CREATE OR REPLACE VIEW avila.v_person_medico AS
SELECT
  a.person_id,
  a.medico_id,
  a.especialidad_id,
  min(a.encounter_date) AS first_seen,
  max(a.encounter_date) AS last_seen,
  count(*)::int AS atenciones,
  count(DISTINCT a.invoice_id)::int AS invoices
FROM avila.atencion a
WHERE a.person_id IS NOT NULL
  AND a.medico_id IS NOT NULL
  AND a.link_status <> 'duplicate'
GROUP BY a.person_id, a.medico_id, a.especialidad_id;

-- Taxonomy tree with counts rolled up from subespecialidad to its parent.
CREATE OR REPLACE VIEW avila.v_especialidad_tree AS
WITH own AS (
  SELECT
    e.id,
    (SELECT count(*) FROM avila.atencion a
      WHERE a.especialidad_id = e.id AND a.link_status <> 'duplicate')::int AS atenciones,
    (SELECT count(*) FROM avila.medico_especialidad me
      JOIN avila.medico m ON m.id = me.medico_id AND m.merged_into IS NULL
      WHERE me.especialidad_id = e.id)::int AS medicos,
    (SELECT count(*) FROM avila.procedimiento p WHERE p.especialidad_id = e.id)::int AS procedimientos,
    (SELECT count(*) FROM avila.especialidad_term t WHERE t.especialidad_id = e.id)::int AS terms
  FROM avila.especialidad e
)
SELECT
  e.id,
  e.code,
  e.name_es,
  e.level,
  e.parent_id,
  p.code AS parent_code,
  e.area_code,
  ar.name_es AS area_name,
  ar.sort_order AS area_sort,
  e.marketing_category,
  e.active,
  o.atenciones AS own_atenciones,
  o.atenciones + coalesce((
    SELECT sum(c.atenciones) FROM own c
    JOIN avila.especialidad ce ON ce.id = c.id
    WHERE ce.parent_id = e.id
  ), 0)::int AS atenciones,
  o.medicos AS own_medicos,
  o.medicos + coalesce((
    SELECT sum(c.medicos) FROM own c
    JOIN avila.especialidad ce ON ce.id = c.id
    WHERE ce.parent_id = e.id
  ), 0)::int AS medicos,
  o.procedimientos,
  o.terms
FROM avila.especialidad e
JOIN own o ON o.id = e.id
JOIN avila.especialidad_area ar ON ar.code = e.area_code
LEFT JOIN avila.especialidad p ON p.id = e.parent_id;

CREATE TABLE IF NOT EXISTS avila.clinical_verify_snapshot (
  id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  computed_at timestamptz NOT NULL DEFAULT now(),
  counters jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Provenance entities and review kinds for the clinical phase.
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
  FOR r IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'avila.review_item'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%kind%'
  LOOP
    EXECUTE format('ALTER TABLE avila.review_item DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;

ALTER TABLE avila.field_provenance ADD CONSTRAINT field_provenance_entity_check CHECK (
  entity IN (
    'person', 'invoice_person', 'document', 'invoice', 'authorization_line',
    'medico', 'atencion', 'medico_especialidad', 'especialidad', 'especialidad_term'
  )
);

ALTER TABLE avila.review_item
  ADD COLUMN IF NOT EXISTS medico_id uuid REFERENCES avila.medico (id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS other_medico_id uuid REFERENCES avila.medico (id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS atencion_id uuid REFERENCES avila.atencion (id) ON DELETE CASCADE;

ALTER TABLE avila.review_item ADD CONSTRAINT review_item_kind_check CHECK (
  kind IN (
    'duplicate_candidate',
    'ci_conflict',
    'workbook_titular',
    'multiple_ci',
    'dob_conflict',
    'phone_conflict',
    'address_conflict',
    'auth_match',
    'segment_review',
    'acta_titular',
    'medico_duplicate',
    'medico_mpps_conflict',
    'atencion_patient',
    'especialidad_unknown'
  )
);
