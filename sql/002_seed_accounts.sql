-- Canonical billed accounts (insurers / companies). Codes match invoice_rules labels.

INSERT INTO avila.account (code, legal_name) VALUES
  ('la_previsora', 'La Previsora'),
  ('altamira', 'Altamira'),
  ('latitud', 'Latitud'),
  ('seguros_miranda', 'Seguros Miranda'),
  ('constitucion', 'Constitucion'),
  ('seniat', 'SENIAT'),
  ('hispana', 'Hispana'),
  ('cemento_andino', 'Cemento Andino'),
  ('seguros_venezuela', 'Seguros Venezuela'),
  ('fasmee', 'FASMEE'),
  ('corporacion', 'Corporacion'),
  ('piramide', 'Piramide'),
  ('saren', 'SAREN'),
  ('corpoelec', 'CORPOELEC'),
  ('bicentenario', 'Bicentenario'),
  ('cuidamed', 'Cuidamed'),
  ('cantv', 'CANTV'),
  ('pueblo_soberano', 'Pueblo Soberano')
ON CONFLICT (code) DO UPDATE SET legal_name = EXCLUDED.legal_name;
