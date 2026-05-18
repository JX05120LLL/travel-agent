-- OpenClaw / MCP wrapper external identity and conversation mapping tables.
-- Target database: PostgreSQL

CREATE TABLE IF NOT EXISTS external_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel VARCHAR(50) NOT NULL,
    external_user_id VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_external_identities_channel_user
        UNIQUE (channel, external_user_id)
);

CREATE TABLE IF NOT EXISTS external_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel VARCHAR(50) NOT NULL,
    external_user_id VARCHAR(255) NOT NULL,
    conversation_id VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_external_conversations_channel_thread
        UNIQUE (channel, external_user_id, conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_external_identities_user_id
    ON external_identities(user_id);

CREATE INDEX IF NOT EXISTS idx_external_conversations_user_id
    ON external_conversations(user_id);

CREATE INDEX IF NOT EXISTS idx_external_conversations_session_id
    ON external_conversations(session_id);

CREATE INDEX IF NOT EXISTS idx_external_conversations_last_message_at
    ON external_conversations(last_message_at DESC);
