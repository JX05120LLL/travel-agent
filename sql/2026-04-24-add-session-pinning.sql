ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_user_pin_order
ON sessions (user_id, is_pinned DESC, pinned_at ASC, last_message_at DESC);
