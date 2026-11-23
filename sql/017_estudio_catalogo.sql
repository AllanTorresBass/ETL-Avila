-- The study types this clinic manages, and the specification under each one.
-- Apply with DATABASE_URL_UNPOOLED after 016_estudio.sql.
--
-- Level 1 is the service (Exámenes de laboratorio, Ecografía, Rayos X).
-- Level 2 is the named exam under that service (Hematología completa, Ecografía abdominal).
-- estudio.catalogo_id points at the most specific row. A page that only names
-- the service points at level 1. scripts/estudio_catalogo.py fills both.

CREATE TABLE IF NOT EXISTS avila.estudio_catalogo (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name_es text NOT NULL,
  estudio_tipo_code text NOT NULL REFERENCES avila.estudio_tipo (code),
  parent_id uuid REFERENCES avila.estudio_catalogo (id) ON DELETE CASCADE,
  level smallint NOT NULL CHECK (level IN (1, 2)),
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT estudio_catalogo_level_parent CHECK (
    (level = 1 AND parent_id IS NULL) OR (level = 2 AND parent_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_avila_estudio_catalogo_tipo
  ON avila.estudio_catalogo (estudio_tipo_code, level);

CREATE INDEX IF NOT EXISTS idx_avila_estudio_catalogo_parent
  ON avila.estudio_catalogo (parent_id);

ALTER TABLE avila.estudio
  ADD COLUMN IF NOT EXISTS catalogo_id uuid REFERENCES avila.estudio_catalogo (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_avila_estudio_catalogo
  ON avila.estudio (catalogo_id);
