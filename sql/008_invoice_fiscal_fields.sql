-- Fields read from the fiscal sheet OCR (scripts/fiscal_extract.py).
-- Values written here also get a row in avila.field_provenance (entity = 'invoice').

ALTER TABLE avila.invoice
  ADD COLUMN IF NOT EXISTS total_bs numeric,
  ADD COLUMN IF NOT EXISTS total_usd numeric,
  ADD COLUMN IF NOT EXISTS clave text,
  ADD COLUMN IF NOT EXISTS fiscal_extracted_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_avila_invoice_clave ON avila.invoice (clave);
CREATE INDEX IF NOT EXISTS idx_avila_invoice_issue_date ON avila.invoice (issue_date);
CREATE INDEX IF NOT EXISTS idx_avila_auth_request_date ON avila.authorization_line (request_date);
