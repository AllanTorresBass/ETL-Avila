-- Titular / beneficiario verification cohorts (scripts/role_verify.py).
-- role_cohort is denormalized per invoice so the reader can filter without OCR.
-- role_verify_snapshot holds the last counts-only verify run (no PHI).
-- Apply with DATABASE_URL_UNPOOLED after 009_contact_gaps.sql.

ALTER TABLE avila.invoice
  ADD COLUMN IF NOT EXISTS role_cohort text;

CREATE INDEX IF NOT EXISTS idx_avila_invoice_role_cohort
  ON avila.invoice (role_cohort)
  WHERE role_cohort IS NOT NULL;

ALTER TABLE avila.invoice DROP CONSTRAINT IF EXISTS invoice_role_cohort_check;
ALTER TABLE avila.invoice ADD CONSTRAINT invoice_role_cohort_check CHECK (
  role_cohort IS NULL OR role_cohort IN (
    'multi_titular',
    'blocked_review',
    'no_titular',
    'id_docs_no_ci',
    'mismatch_no_beneficiario',
    'nameless_titular',
    'self_visit_ok',
    'resolved_pair',
    'unknown_links',
    'weak_evidence'
  )
);

CREATE TABLE IF NOT EXISTS avila.role_verify_snapshot (
  id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  computed_at timestamptz NOT NULL DEFAULT now(),
  counters jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Structural counts from the denormalized column (updated by role_verify --write-cohort --apply).
CREATE OR REPLACE VIEW avila.v_invoice_role_cohort AS
SELECT
  count(*)::int AS invoices,
  count(*) FILTER (WHERE role_cohort = 'multi_titular')::int AS multi_titular,
  count(*) FILTER (WHERE role_cohort = 'blocked_review')::int AS blocked_review,
  count(*) FILTER (WHERE role_cohort = 'no_titular')::int AS no_titular,
  count(*) FILTER (WHERE role_cohort = 'id_docs_no_ci')::int AS id_docs_no_ci,
  count(*) FILTER (WHERE role_cohort = 'mismatch_no_beneficiario')::int AS mismatch_no_beneficiario,
  count(*) FILTER (WHERE role_cohort = 'nameless_titular')::int AS nameless_titular,
  count(*) FILTER (WHERE role_cohort = 'self_visit_ok')::int AS self_visit_ok,
  count(*) FILTER (WHERE role_cohort = 'resolved_pair')::int AS resolved_pair,
  count(*) FILTER (WHERE role_cohort = 'unknown_links')::int AS unknown_links,
  count(*) FILTER (WHERE role_cohort = 'weak_evidence')::int AS weak_evidence,
  count(*) FILTER (WHERE role_cohort IS NULL)::int AS unset_cohort
FROM avila.invoice;
