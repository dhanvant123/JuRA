-- Initial schema migration for JuRA backend

CREATE TABLE IF NOT EXISTS users (
    email VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    ph_no VARCHAR(20) UNIQUE
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_chat_sessions_user FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_email ON chat_sessions (email);

CREATE TABLE IF NOT EXISTS legal_items (
    id UUID PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(1000) NOT NULL,
    citation JSONB NOT NULL,
    question TEXT NOT NULL,
    year INT NOT NULL,
    source VARCHAR(1000) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_legal_items_type ON legal_items (type);
CREATE INDEX IF NOT EXISTS idx_legal_items_year ON legal_items (year);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY,
    chat_session_id UUID NOT NULL,
    role VARCHAR(20) NOT NULL,
    citation JSONB,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    CONSTRAINT fk_chat_messages_session FOREIGN KEY (chat_session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages (chat_session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages (created_at);

CREATE TABLE IF NOT EXISTS bookmarks (
    email VARCHAR(255) NOT NULL,
    legal_item_id UUID NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (email, legal_item_id),
    CONSTRAINT fk_bookmarks_user FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE,
    CONSTRAINT fk_bookmarks_legal_item FOREIGN KEY (legal_item_id) REFERENCES legal_items (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_email ON bookmarks (email);
