-- Proper names for identity packet pages (collage sheet + birth certificate).
-- Apply with DATABASE_URL_UNPOOLED after 004_carnet_document_type.sql.

DO $$ BEGIN
  ALTER TYPE avila.document_type ADD VALUE IF NOT EXISTS 'documentos_identificacion';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TYPE avila.document_type ADD VALUE IF NOT EXISTS 'acta_nacimiento';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
