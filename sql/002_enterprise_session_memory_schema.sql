-- Travel Agent enterprise session / memory schema
-- Execute this file after:
--   sql/001_init_core_tables.sql
--
-- This migration keeps the existing users / sessions / messages tables
-- and adds the business-layer entities required by the enterprise design:
--   - plan_options
--   - plan comparisons
--   - trips
--   - user preferences
--   - history recall logs
--   - session events

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- 0) Extend existing core tables

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS active_plan_option_id UUID,
    ADD COLUMN IF NOT EXISTS active_comparison_id UUID;

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS plan_option_id UUID,
    ADD COLUMN IF NOT EXISTS comparison_id UUID,
    ADD COLUMN IF NOT EXISTS trip_id UUID,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;


-- 1) Plan options: candidate travel plans inside one session

CREATE TABLE IF NOT EXISTS plan_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_plan_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL,
    branch_root_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL,
    source_plan_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL,
    branch_name VARCHAR(120),
    title VARCHAR(200) NOT NULL DEFAULT '未命名方案',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    planning_mode VARCHAR(30) NOT NULL DEFAULT 'single_city',
    primary_destination VARCHAR(100),
    travel_start_date DATE,
    travel_end_date DATE,
    total_days INTEGER,
    traveler_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    budget_min NUMERIC(12, 2),
    budget_max NUMERIC(12, 2),
    pace VARCHAR(20),
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary TEXT,
    plan_markdown TEXT,
    version_no INTEGER NOT NULL DEFAULT 1,
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    CONSTRAINT chk_plan_options_status
        CHECK (status IN ('draft', 'active', 'compared', 'selected', 'archived', 'deleted')),
    CONSTRAINT chk_plan_options_planning_mode
        CHECK (planning_mode IN ('single_city', 'multi_city', 'compare_candidate')),
    CONSTRAINT chk_plan_options_total_days
        CHECK (total_days IS NULL OR total_days > 0),
    CONSTRAINT chk_plan_options_budget_range
        CHECK (
            budget_min IS NULL
            OR budget_max IS NULL
            OR budget_min <= budget_max
        ),
    CONSTRAINT chk_plan_options_pace
        CHECK (pace IS NULL OR pace IN ('relaxed', 'balanced', 'dense'))
);


-- 2) Destinations inside a single plan option

CREATE TABLE IF NOT EXISTS plan_option_destinations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_option_id UUID NOT NULL REFERENCES plan_options(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    destination_name VARCHAR(100) NOT NULL,
    destination_code VARCHAR(50),
    stay_days INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_plan_option_destinations_sequence
        UNIQUE (plan_option_id, sequence_no),
    CONSTRAINT chk_plan_option_destinations_stay_days
        CHECK (stay_days IS NULL OR stay_days > 0)
);


-- 3) Plan comparisons: compare multiple candidate options

CREATE TABLE IF NOT EXISTS plan_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL DEFAULT '方案比较',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    summary TEXT,
    comparison_dimensions JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    CONSTRAINT chk_plan_comparisons_status
        CHECK (status IN ('active', 'completed', 'archived'))
);

CREATE TABLE IF NOT EXISTS plan_comparison_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comparison_id UUID NOT NULL REFERENCES plan_comparisons(id) ON DELETE CASCADE,
    plan_option_id UUID NOT NULL REFERENCES plan_options(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    overall_score NUMERIC(8, 2),
    pros JSONB NOT NULL DEFAULT '[]'::jsonb,
    cons JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_plan_comparison_items_option
        UNIQUE (comparison_id, plan_option_id),
    CONSTRAINT uq_plan_comparison_items_sequence
        UNIQUE (comparison_id, sequence_no)
);


-- 4) Final trips: confirmed plans converted from candidate options

CREATE TABLE IF NOT EXISTS trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    source_plan_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL,
    selected_from_comparison_id UUID REFERENCES plan_comparisons(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL DEFAULT '未命名行程',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    primary_destination VARCHAR(100),
    travel_start_date DATE,
    travel_end_date DATE,
    total_days INTEGER,
    traveler_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    budget_min NUMERIC(12, 2),
    budget_max NUMERIC(12, 2),
    pace VARCHAR(20),
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary TEXT,
    plan_markdown TEXT,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    CONSTRAINT chk_trips_status
        CHECK (status IN ('draft', 'confirmed', 'booked', 'completed', 'cancelled', 'archived')),
    CONSTRAINT chk_trips_total_days
        CHECK (total_days IS NULL OR total_days > 0),
    CONSTRAINT chk_trips_budget_range
        CHECK (
            budget_min IS NULL
            OR budget_max IS NULL
            OR budget_min <= budget_max
        ),
    CONSTRAINT chk_trips_pace
        CHECK (pace IS NULL OR pace IN ('relaxed', 'balanced', 'dense'))
);

CREATE TABLE IF NOT EXISTS trip_destinations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    destination_name VARCHAR(100) NOT NULL,
    destination_code VARCHAR(50),
    stay_days INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_trip_destinations_sequence
        UNIQUE (trip_id, sequence_no),
    CONSTRAINT chk_trip_destinations_stay_days
        CHECK (stay_days IS NULL OR stay_days > 0)
);

CREATE TABLE IF NOT EXISTS trip_itinerary_days (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    day_no INTEGER NOT NULL,
    trip_date DATE,
    city_name VARCHAR(100),
    title VARCHAR(200),
    summary TEXT,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_trip_itinerary_days_day_no
        UNIQUE (trip_id, day_no),
    CONSTRAINT chk_trip_itinerary_days_day_no
        CHECK (day_no > 0)
);


-- 5) User preferences: long-term reusable memory

CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    preference_category VARCHAR(50) NOT NULL,
    preference_key VARCHAR(100) NOT NULL,
    preference_value JSONB NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'derived',
    confidence NUMERIC(5, 4) NOT NULL DEFAULT 0.7000,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source_session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    last_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_user_preferences_source
        CHECK (source IN ('user_explicit', 'derived', 'imported', 'system')),
    CONSTRAINT chk_user_preferences_confidence
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT uq_user_preferences_user_category_key
        UNIQUE (user_id, preference_category, preference_key)
);


-- 6) History recall logs: audit retrieval across sessions

CREATE TABLE IF NOT EXISTS history_recall_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    query_text TEXT NOT NULL,
    recall_type VARCHAR(20) NOT NULL DEFAULT 'none',
    matched_record_type VARCHAR(30),
    matched_record_id UUID,
    matched_count INTEGER NOT NULL DEFAULT 0,
    confidence NUMERIC(5, 4),
    recall_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_history_recall_logs_type
        CHECK (recall_type IN ('trip', 'plan_option', 'session', 'preference', 'none')),
    CONSTRAINT chk_history_recall_logs_confidence
        CHECK (
            confidence IS NULL
            OR (confidence >= 0 AND confidence <= 1)
        ),
    CONSTRAINT chk_history_recall_logs_matched_count
        CHECK (matched_count >= 0)
);


-- 7) Session events: enterprise audit trail for routing and state changes

CREATE TABLE IF NOT EXISTS session_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    plan_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL,
    comparison_id UUID REFERENCES plan_comparisons(id) ON DELETE SET NULL,
    trip_id UUID REFERENCES trips(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 8) Backfill foreign keys on existing tables

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_sessions_active_plan_option'
    ) THEN
        ALTER TABLE sessions
            ADD CONSTRAINT fk_sessions_active_plan_option
            FOREIGN KEY (active_plan_option_id)
            REFERENCES plan_options(id)
            ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_sessions_active_comparison'
    ) THEN
        ALTER TABLE sessions
            ADD CONSTRAINT fk_sessions_active_comparison
            FOREIGN KEY (active_comparison_id)
            REFERENCES plan_comparisons(id)
            ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_messages_plan_option'
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT fk_messages_plan_option
            FOREIGN KEY (plan_option_id)
            REFERENCES plan_options(id)
            ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_messages_comparison'
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT fk_messages_comparison
            FOREIGN KEY (comparison_id)
            REFERENCES plan_comparisons(id)
            ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_messages_trip'
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT fk_messages_trip
            FOREIGN KEY (trip_id)
            REFERENCES trips(id)
            ON DELETE SET NULL;
    END IF;
END $$;


-- 9) Indexes

CREATE INDEX IF NOT EXISTS idx_sessions_active_plan_option_id
    ON sessions(active_plan_option_id);

CREATE INDEX IF NOT EXISTS idx_sessions_active_comparison_id
    ON sessions(active_comparison_id);

CREATE INDEX IF NOT EXISTS idx_messages_plan_option_id
    ON messages(plan_option_id);

CREATE INDEX IF NOT EXISTS idx_messages_comparison_id
    ON messages(comparison_id);

CREATE INDEX IF NOT EXISTS idx_messages_trip_id
    ON messages(trip_id);

CREATE INDEX IF NOT EXISTS idx_plan_options_session_id
    ON plan_options(session_id);

CREATE INDEX IF NOT EXISTS idx_plan_options_user_id
    ON plan_options(user_id);

CREATE INDEX IF NOT EXISTS idx_plan_options_parent_plan_option_id
    ON plan_options(parent_plan_option_id);

CREATE INDEX IF NOT EXISTS idx_plan_options_branch_root_option_id
    ON plan_options(branch_root_option_id);

CREATE INDEX IF NOT EXISTS idx_plan_options_status
    ON plan_options(status);

CREATE INDEX IF NOT EXISTS idx_plan_options_primary_destination
    ON plan_options(primary_destination);

CREATE INDEX IF NOT EXISTS idx_plan_options_updated_at
    ON plan_options(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_plan_option_destinations_plan_option_id
    ON plan_option_destinations(plan_option_id);

CREATE INDEX IF NOT EXISTS idx_plan_option_destinations_name
    ON plan_option_destinations(destination_name);

CREATE INDEX IF NOT EXISTS idx_plan_comparisons_session_id
    ON plan_comparisons(session_id);

CREATE INDEX IF NOT EXISTS idx_plan_comparisons_user_id
    ON plan_comparisons(user_id);

CREATE INDEX IF NOT EXISTS idx_plan_comparison_items_comparison_id
    ON plan_comparison_items(comparison_id);

CREATE INDEX IF NOT EXISTS idx_plan_comparison_items_plan_option_id
    ON plan_comparison_items(plan_option_id);

CREATE INDEX IF NOT EXISTS idx_trips_user_id
    ON trips(user_id);

CREATE INDEX IF NOT EXISTS idx_trips_session_id
    ON trips(session_id);

CREATE INDEX IF NOT EXISTS idx_trips_source_plan_option_id
    ON trips(source_plan_option_id);

CREATE INDEX IF NOT EXISTS idx_trips_primary_destination
    ON trips(primary_destination);

CREATE INDEX IF NOT EXISTS idx_trips_status
    ON trips(status);

CREATE INDEX IF NOT EXISTS idx_trip_destinations_trip_id
    ON trip_destinations(trip_id);

CREATE INDEX IF NOT EXISTS idx_trip_destinations_name
    ON trip_destinations(destination_name);

CREATE INDEX IF NOT EXISTS idx_trip_itinerary_days_trip_id
    ON trip_itinerary_days(trip_id);

CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id
    ON user_preferences(user_id);

CREATE INDEX IF NOT EXISTS idx_user_preferences_category
    ON user_preferences(preference_category);

CREATE INDEX IF NOT EXISTS idx_user_preferences_active
    ON user_preferences(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_history_recall_logs_user_id_created_at
    ON history_recall_logs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_history_recall_logs_session_id
    ON history_recall_logs(session_id);

CREATE INDEX IF NOT EXISTS idx_session_events_session_id_created_at
    ON session_events(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_session_events_user_id
    ON session_events(user_id);

CREATE INDEX IF NOT EXISTS idx_session_events_event_type
    ON session_events(event_type);

CREATE INDEX IF NOT EXISTS idx_plan_options_preferences_gin
    ON plan_options USING GIN (preferences);

CREATE INDEX IF NOT EXISTS idx_plan_options_constraints_gin
    ON plan_options USING GIN (constraints);

CREATE INDEX IF NOT EXISTS idx_plan_options_traveler_profile_gin
    ON plan_options USING GIN (traveler_profile);

CREATE INDEX IF NOT EXISTS idx_trips_preferences_gin
    ON trips USING GIN (preferences);

CREATE INDEX IF NOT EXISTS idx_trips_constraints_gin
    ON trips USING GIN (constraints);

CREATE INDEX IF NOT EXISTS idx_user_preferences_value_gin
    ON user_preferences USING GIN (preference_value);

COMMIT;
