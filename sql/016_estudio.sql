-- Studies saved by type, with each documentation page or image file attached.
-- Apply with DATABASE_URL_UNPOOLED after 015_authorization_lifecycle.sql.
--
-- estudio_tipo is the family (Laboratorio, Rayos X, …).
-- estudio.label is the specific test (Hemograma, Rayos X de tórax).
-- Rows group by that name, the patient, and the factura.
-- An order with no procedimiento stays its own estudio.
-- estudio_archivo is one source page: documentacion (factura, orden, informe)
-- or imagen (laboratorio / imagenología result sheet).
-- invoice_service remains the line. rebuild_estudios projects these tables from it.
-- Line provenance stays on invoice_service; these rows carry run_id only.

CREATE TABLE IF NOT EXISTS avila.estudio_tipo (
  code text PRIMARY KEY,
  name_es text NOT NULL,
  sort_order integer NOT NULL DEFAULT 0
);

INSERT INTO avila.estudio_tipo (code, name_es, sort_order) VALUES
  ('laboratorio', 'Laboratorio', 10),
  ('corazon', 'Corazón', 20),
  ('ecografia', 'Ecografía', 30),
  ('rayos_x', 'Rayos X', 40),
  ('tomografia', 'Tomografía', 50),
  ('resonancia', 'Resonancia', 60),
  ('endoscopia', 'Endoscopia', 70),
  ('mamografia', 'Mamografía', 80),
  ('densitometria', 'Densitometría', 90),
  ('anatomia_patologica', 'Biopsia / citología', 100),
  ('funcional', 'Pruebas funcionales', 110),
  ('medicina_nuclear', 'Medicina nuclear', 120),
  ('oftalmologia', 'Oftalmología', 130)
ON CONFLICT (code) DO UPDATE
  SET name_es = EXCLUDED.name_es,
      sort_order = EXCLUDED.sort_order;

ALTER TABLE avila.procedimiento
  ADD COLUMN IF NOT EXISTS estudio_tipo_code text REFERENCES avila.estudio_tipo (code);

CREATE INDEX IF NOT EXISTS idx_avila_procedimiento_estudio_tipo
  ON avila.procedimiento (estudio_tipo_code);

UPDATE avila.procedimiento AS p
SET estudio_tipo_code = v.tipo
FROM (
  VALUES
    ('examenes_laboratorio', 'laboratorio'),
    ('serologia', 'laboratorio'),
    ('antibiograma', 'laboratorio'),
    ('citologia', 'anatomia_patologica'),
    ('biopsia', 'anatomia_patologica'),
    ('rayos_x', 'rayos_x'),
    ('fistulografia', 'rayos_x'),
    ('ecografia', 'ecografia'),
    ('ecomamografia', 'ecografia'),
    ('mamografia', 'mamografia'),
    ('tomografia', 'tomografia'),
    ('angiotomografia', 'tomografia'),
    ('resonancia', 'resonancia'),
    ('densitometria', 'densitometria'),
    ('gammagrama', 'medicina_nuclear'),
    ('fluororetinografia', 'oftalmologia'),
    ('campo_visual', 'oftalmologia'),
    ('ecocardiograma', 'corazon'),
    ('electrocardiograma', 'corazon'),
    ('holter', 'corazon'),
    ('prueba_esfuerzo', 'corazon'),
    ('coronariografia', 'corazon'),
    ('mapa', 'corazon'),
    ('endoscopia_digestiva', 'endoscopia'),
    ('colonoscopia', 'endoscopia'),
    ('colposcopia', 'endoscopia'),
    ('cistoscopia', 'endoscopia'),
    ('laringoscopia', 'endoscopia'),
    ('audiometria', 'funcional'),
    ('electromiografia', 'funcional'),
    ('electroencefalograma', 'funcional'),
    ('espirometria', 'funcional'),
    ('flujometria', 'funcional')
) AS v(code, tipo)
WHERE p.code = v.code
  AND p.estudio_tipo_code IS DISTINCT FROM v.tipo;

CREATE TABLE IF NOT EXISTS avila.estudio (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  group_key text NOT NULL UNIQUE,
  invoice_id uuid NOT NULL REFERENCES avila.invoice (id) ON DELETE CASCADE,
  person_id uuid REFERENCES avila.person (id) ON DELETE SET NULL,
  estudio_tipo_code text REFERENCES avila.estudio_tipo (code),
  procedimiento_id uuid REFERENCES avila.procedimiento (id) ON DELETE SET NULL,
  label text NOT NULL,
  link_status text NOT NULL CHECK (link_status IN ('matched', 'unmatched', 'review')),
  run_id uuid REFERENCES avila.etl_run (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_avila_estudio_tipo ON avila.estudio (estudio_tipo_code);
CREATE INDEX IF NOT EXISTS idx_avila_estudio_invoice ON avila.estudio (invoice_id);
CREATE INDEX IF NOT EXISTS idx_avila_estudio_person ON avila.estudio (person_id);
CREATE INDEX IF NOT EXISTS idx_avila_estudio_proc ON avila.estudio (procedimiento_id);

CREATE TABLE IF NOT EXISTS avila.estudio_archivo (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  estudio_id uuid NOT NULL REFERENCES avila.estudio (id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES avila.document (id) ON DELETE CASCADE,
  invoice_service_id uuid NOT NULL UNIQUE REFERENCES avila.invoice_service (id) ON DELETE CASCADE,
  origen text NOT NULL CHECK (origen IN ('documentacion', 'imagen')),
  source text NOT NULL CHECK (source IN ('fiscal_line', 'result_page', 'study_order')),
  line_no integer NOT NULL CHECK (line_no >= 0),
  service_label text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT estudio_archivo_natural UNIQUE (estudio_id, document_id, source, line_no)
);

CREATE INDEX IF NOT EXISTS idx_avila_estudio_archivo_document
  ON avila.estudio_archivo (document_id);
CREATE INDEX IF NOT EXISTS idx_avila_estudio_archivo_origen
  ON avila.estudio_archivo (origen);

CREATE OR REPLACE FUNCTION avila.rebuild_estudios(p_run uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  DELETE FROM avila.estudio;

  INSERT INTO avila.estudio (
    group_key, invoice_id, person_id, estudio_tipo_code, procedimiento_id,
    label, link_status, run_id
  )
  SELECT
    g.group_key,
    g.invoice_id,
    g.person_id,
    pr.estudio_tipo_code,
    g.procedimiento_id,
    g.service_label,
    CASE
      WHEN g.any_review THEN 'review'
      WHEN g.procedimiento_id IS NULL THEN 'unmatched'
      ELSE 'matched'
    END,
    p_run
  FROM (
    SELECT
      CASE
        WHEN s.procedimiento_id IS NOT NULL THEN
          'spec:' || s.invoice_id::text || ':' || coalesce(s.person_id::text, '-')
            || ':' || s.procedimiento_id::text || ':' || lower(btrim(s.service_label))
        ELSE
          'line:' || s.id::text
      END AS group_key,
      s.invoice_id,
      s.person_id,
      s.procedimiento_id,
      min(s.service_label) AS service_label,
      bool_or(s.link_status = 'review') AS any_review
    FROM avila.invoice_service s
    WHERE s.kind = 'estudio'
    GROUP BY 1, 2, 3, 4
  ) g
  LEFT JOIN avila.procedimiento pr ON pr.id = g.procedimiento_id;

  INSERT INTO avila.estudio_archivo (
    estudio_id, document_id, invoice_service_id, origen, source, line_no, service_label
  )
  SELECT
    e.id,
    s.document_id,
    s.id,
    CASE
      WHEN s.source = 'result_page' AND d.document_type::text IN ('laboratorio', 'imagenologia') THEN 'imagen'
      ELSE 'documentacion'
    END,
    s.source,
    s.line_no,
    s.service_label
  FROM avila.invoice_service s
  JOIN avila.document d ON d.id = s.document_id
  JOIN avila.estudio e ON e.group_key = (
    CASE
      WHEN s.procedimiento_id IS NOT NULL THEN
        'spec:' || s.invoice_id::text || ':' || coalesce(s.person_id::text, '-')
          || ':' || s.procedimiento_id::text || ':' || lower(btrim(s.service_label))
      ELSE
        'line:' || s.id::text
    END
  )
  WHERE s.kind = 'estudio';
END;
$$;

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
    'invoice_service', 'authorization_item', 'authorization_source',
    'estudio', 'estudio_archivo'
  )
);

SELECT avila.rebuild_estudios(NULL);
