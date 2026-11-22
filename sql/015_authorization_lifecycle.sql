-- Authorization lifecycle: insurer, date origin, normalized provider, and why a line is or is not on a factura.
-- Apply with DATABASE_URL_UNPOOLED after 014_authorization_item.sql.
--
-- date_source:
--   request      request_date read from the workbook column
--   service      service_date read from the workbook column
--   period_day   the date cell held only a day; month and year come from the sheet or file
--   period       only the month is known (period_month), from the sheet or file
-- match_status:
--   linked       match_auth_lines linked it (score >= 0.70 and margin >= 0.15)
--   review       an auth_match review is open or was decided by staff
--   low_score    candidates exist but none reached the review band
--   no_candidate the person or titular has no factura in that insurer
--   no_person    the line names no person and no titular
--   duplicate    the line copies another request (duplicate_of)
--   staff        a person linked or unlinked it in /autorizaciones; the matcher leaves it alone

ALTER TABLE avila.authorization_line
  ADD COLUMN IF NOT EXISTS account_id uuid REFERENCES avila.account (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS date_source text,
  ADD COLUMN IF NOT EXISTS period_month date,
  ADD COLUMN IF NOT EXISTS provider_code text,
  ADD COLUMN IF NOT EXISTS match_status text,
  ADD COLUMN IF NOT EXISTS match_score numeric,
  ADD COLUMN IF NOT EXISTS match_signals text[],
  ADD COLUMN IF NOT EXISTS matched_at timestamptz;

ALTER TABLE avila.authorization_line DROP CONSTRAINT IF EXISTS authorization_line_date_source_check;
ALTER TABLE avila.authorization_line
  ADD CONSTRAINT authorization_line_date_source_check
  CHECK (date_source IS NULL OR date_source IN ('request', 'service', 'period_day', 'period'));

ALTER TABLE avila.authorization_line DROP CONSTRAINT IF EXISTS authorization_line_match_status_check;
ALTER TABLE avila.authorization_line
  ADD CONSTRAINT authorization_line_match_status_check
  CHECK (
    match_status IS NULL OR match_status IN (
      'linked', 'review', 'low_score', 'no_candidate', 'no_person', 'duplicate', 'staff'
    )
  );

ALTER TABLE avila.authorization_line DROP CONSTRAINT IF EXISTS authorization_line_period_first_day;
ALTER TABLE avila.authorization_line
  ADD CONSTRAINT authorization_line_period_first_day
  CHECK (period_month IS NULL OR extract(day FROM period_month) = 1);

CREATE INDEX IF NOT EXISTS idx_avila_auth_account ON avila.authorization_line (account_id);
CREATE INDEX IF NOT EXISTS idx_avila_auth_match_status ON avila.authorization_line (match_status);
CREATE INDEX IF NOT EXISTS idx_avila_auth_period_month ON avila.authorization_line (period_month);
CREATE INDEX IF NOT EXISTS idx_avila_auth_titular ON avila.authorization_line (titular_person_id);
