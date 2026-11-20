-- Staff accounts for the invoice reader.
-- Passwords are never stored here. Seed super admins with scripts/seed_app_users.mjs.

CREATE TABLE IF NOT EXISTS avila.app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  full_name text,
  role text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT app_user_role_check CHECK (role IN ('super_admin', 'revisor', 'lector'))
);

CREATE TABLE IF NOT EXISTS avila.app_session (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES avila.app_user(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_session_user_idx ON avila.app_session (user_id);
CREATE INDEX IF NOT EXISTS app_session_expires_idx ON avila.app_session (expires_at);
