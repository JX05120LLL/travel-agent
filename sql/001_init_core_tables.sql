-- Travel Agent core tables
-- First version: users / sessions / messages
-- Target database: PostgreSQL

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- 1) Users
-- Stores the account identity. Later we can extend this with
-- avatar, phone, oauth fields, preference profile, and auth metadata.
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    CONSTRAINT chk_users_status
        CHECK (status IN ('active', 'disabled'))
);


-- 2) Sessions
-- One user can own multiple chat sessions.
-- The summary field is reserved for later context compression.
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL DEFAULT '新对话',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    summary TEXT,
    latest_user_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    CONSTRAINT chk_sessions_status
        CHECK (status IN ('active', 'archived', 'deleted'))
);


-- 3) Messages
-- Stores each message in a session.
-- sequence_no preserves the exact order of messages in one session.
-- user_id is kept for easier future querying and auditing.
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    content_format VARCHAR(20) NOT NULL DEFAULT 'text',
    tool_name VARCHAR(100),
    tool_call_id VARCHAR(100),
    sequence_no INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_messages_role
        CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    CONSTRAINT chk_messages_content_format
        CHECK (content_format IN ('text', 'markdown', 'json')),
    CONSTRAINT uq_messages_session_sequence
        UNIQUE (session_id, sequence_no)
);


-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user_id
    ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_last_message_at
    ON sessions(last_message_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_session_id
    ON messages(session_id);

CREATE INDEX IF NOT EXISTS idx_messages_user_id
    ON messages(user_id);

CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
    ON messages(session_id, created_at);
