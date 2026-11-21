-- Who owns each service row. Apply with DATABASE_URL_UNPOOLED after 012_invoice_service.sql.
-- Null means the factura has no single patient. The reader joins invoice.issue_date for when.

ALTER TABLE avila.invoice_service
  ADD COLUMN IF NOT EXISTS person_id uuid REFERENCES avila.person (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_avila_invoice_service_person
  ON avila.invoice_service (person_id);
