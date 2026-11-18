-- Why nacimiento / teléfono / dirección stayed empty, and reviews for a second value.
-- Apply with DATABASE_URL_UNPOOLED after 008_invoice_fiscal_fields.sql.

ALTER TABLE avila.person
  ADD COLUMN IF NOT EXISTS contact_gap jsonb NOT NULL DEFAULT '{}'::jsonb;

DO $$
DECLARE
  r record;
BEGIN
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
    'acta_titular'
  )
);
