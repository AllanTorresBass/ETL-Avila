-- Add carnet (e.g. BDV employee badge) as a first-class document type.
-- Apply with DATABASE_URL_UNPOOLED after 001_schema.sql.

DO $$ BEGIN
  ALTER TYPE avila.document_type ADD VALUE IF NOT EXISTS 'carnet';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
