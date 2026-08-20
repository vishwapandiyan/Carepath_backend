-- ============================================
-- CHAT HISTORY FEATURE - DATABASE SCHEMA
-- ============================================
-- Created: 2026-08-20
-- Purpose: Enable ChatGPT-style conversation history with JSONB storage
-- Tables: chat_sessions, chat_messages

-- ============================================
-- TABLE 1: chat_sessions
-- ============================================
-- Stores metadata about each chat conversation

CREATE TABLE IF NOT EXISTS chat_sessions (
    -- Primary Key
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) UNIQUE NOT NULL DEFAULT ('CHAT_' || substr(md5(random()::text), 1, 12)),
    
    -- Ownership & Association
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    patient_id VARCHAR(50) REFERENCES patient_ehr(patient_id) ON DELETE SET NULL,
    
    -- Chat Metadata
    title VARCHAR(500) NOT NULL DEFAULT 'New Chat',
    is_title_auto_generated BOOLEAN DEFAULT TRUE,
    
    -- Message Counts
    message_count INTEGER DEFAULT 0,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_pinned BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

-- Indexes for performance
CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_patient_id ON chat_sessions(patient_id);
CREATE INDEX idx_chat_sessions_session_id ON chat_sessions(session_id);
CREATE INDEX idx_chat_sessions_created_at ON chat_sessions(created_at DESC);
CREATE INDEX idx_chat_sessions_last_message_at ON chat_sessions(last_message_at DESC);
CREATE INDEX idx_chat_sessions_is_active ON chat_sessions(is_active);
CREATE INDEX idx_chat_sessions_title_search ON chat_sessions USING gin(to_tsvector('english', title));

-- Comments
COMMENT ON TABLE chat_sessions IS 'Chat session metadata (like ChatGPT conversations)';
COMMENT ON COLUMN chat_sessions.session_id IS 'Public-facing unique chat identifier (CHAT_xxxxxxxxxxxx)';
COMMENT ON COLUMN chat_sessions.user_id IS 'User who owns this chat (patient or care manager)';
COMMENT ON COLUMN chat_sessions.patient_id IS 'Associated patient (NULL for care manager general chats)';
COMMENT ON COLUMN chat_sessions.title IS 'Chat title (auto-generated or user-edited)';
COMMENT ON COLUMN chat_sessions.is_title_auto_generated IS 'TRUE if title was AI-generated, FALSE if user-edited';
COMMENT ON COLUMN chat_sessions.is_pinned IS 'Allow users to pin important conversations';
COMMENT ON COLUMN chat_sessions.message_count IS 'Total number of messages in this chat';

-- ============================================
-- TABLE 2: chat_messages
-- ============================================
-- Stores individual messages within chat sessions using JSONB for flexible message structure

CREATE TABLE IF NOT EXISTS chat_messages (
    -- Primary Key
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(50) UNIQUE NOT NULL DEFAULT ('MSG_' || substr(md5(random()::text), 1, 12)),
    
    -- Association
    session_id VARCHAR(50) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    
    -- Message Content (JSONB for flexibility)
    message_data JSONB NOT NULL,
    /*
    Expected JSONB structure:
    {
        "role": "user" | "assistant" | "system",
        "content": "message text",
        "metadata": {
            "model": "gemini-1.5-flash",
            "tokens": 150,
            "finish_reason": "stop",
            "latency_ms": 1234,
            "temperature": 0.7
        },
        "attachments": [
            {
                "type": "image" | "file" | "document",
                "url": "...",
                "filename": "...",
                "size_bytes": 12345,
                "mime_type": "image/png"
            }
        ],
        "context": {
            "patient_id": "PAT_abc123",
            "prediction_type": "readmission",
            "action": "medication_query"
        }
    }
    */
    
    -- Denormalized fields for quick queries (extracted from JSONB)
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content_preview TEXT,  -- First 500 chars for search/preview
    
    -- Versioning (for edit/regenerate feature - future)
    parent_message_id VARCHAR(50) REFERENCES chat_messages(message_id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    is_current_version BOOLEAN DEFAULT TRUE,
    
    -- Status
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_message_id ON chat_messages(message_id);
CREATE INDEX idx_chat_messages_role ON chat_messages(role);
CREATE INDEX idx_chat_messages_created_at ON chat_messages(created_at);
CREATE INDEX idx_chat_messages_is_current ON chat_messages(is_current_version);
CREATE INDEX idx_chat_messages_content_search ON chat_messages USING gin(to_tsvector('english', content_preview));
CREATE INDEX idx_chat_messages_jsonb ON chat_messages USING gin(message_data);

-- Comments
COMMENT ON TABLE chat_messages IS 'Individual chat messages stored as JSONB for flexibility';
COMMENT ON COLUMN chat_messages.message_data IS 'Full message content stored as JSONB (role, content, metadata, attachments, context)';
COMMENT ON COLUMN chat_messages.content_preview IS 'Denormalized preview for search (first 500 chars of content)';
COMMENT ON COLUMN chat_messages.parent_message_id IS 'Reference to parent message (for edit/regenerate branching - future feature)';
COMMENT ON COLUMN chat_messages.version IS 'Message version number (for edit history - future feature)';
COMMENT ON COLUMN chat_messages.is_current_version IS 'TRUE if this is the current version (for branching conversations)';

-- ============================================
-- TRIGGERS
-- ============================================

-- Trigger 1: Auto-update chat_sessions.updated_at
CREATE OR REPLACE FUNCTION update_chat_sessions_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_chat_sessions_timestamp
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_sessions_timestamp();

-- Trigger 2: Update chat_sessions when new message is added
CREATE OR REPLACE FUNCTION update_chat_session_on_new_message()
RETURNS TRIGGER AS $$
BEGIN
    -- Only update if message is not deleted
    IF NEW.is_deleted = FALSE THEN
        UPDATE chat_sessions
        SET 
            updated_at = CURRENT_TIMESTAMP,
            last_message_at = CURRENT_TIMESTAMP,
            message_count = message_count + 1
        WHERE session_id = NEW.session_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_chat_on_new_message
    AFTER INSERT ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_session_on_new_message();

-- Trigger 3: Auto-update chat_messages.updated_at
CREATE OR REPLACE FUNCTION update_chat_messages_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_chat_messages_timestamp
    BEFORE UPDATE ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_messages_timestamp();

-- ============================================
-- HELPER FUNCTION: Extract content preview from JSONB
-- ============================================

CREATE OR REPLACE FUNCTION extract_content_preview(message_data JSONB)
RETURNS TEXT AS $$
BEGIN
    -- Extract 'content' field from JSONB and limit to 500 characters
    RETURN LEFT(message_data->>'content', 500);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- VERIFICATION QUERIES (for testing)
-- ============================================

-- Uncomment to verify table creation:
-- SELECT table_name FROM information_schema.tables WHERE table_name IN ('chat_sessions', 'chat_messages');

-- Uncomment to verify indexes:
-- SELECT indexname FROM pg_indexes WHERE tablename IN ('chat_sessions', 'chat_messages');

-- Uncomment to verify triggers:
-- SELECT trigger_name FROM information_schema.triggers WHERE event_object_table IN ('chat_sessions', 'chat_messages');

-- ============================================
-- SAMPLE DATA (for testing) - OPTIONAL
-- ============================================

-- Insert sample chat session (uncomment to use):
/*
INSERT INTO chat_sessions (user_id, patient_id, title, is_title_auto_generated)
VALUES (1, 'PAT_abc123', 'Sample Chat', TRUE)
RETURNING session_id;

-- Insert sample message (replace CHAT_xxx with actual session_id):
INSERT INTO chat_messages (session_id, message_data, role, content_preview)
VALUES (
    'CHAT_xxx',
    '{"role": "user", "content": "Hello, I need help with medications", "context": {"patient_id": "PAT_abc123"}}'::jsonb,
    'user',
    'Hello, I need help with medications'
);
*/

-- ============================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================

-- Uncomment to drop everything:
/*
DROP TRIGGER IF EXISTS trigger_update_chat_on_new_message ON chat_messages;
DROP TRIGGER IF EXISTS trigger_update_chat_sessions_timestamp ON chat_sessions;
DROP TRIGGER IF EXISTS trigger_update_chat_messages_timestamp ON chat_messages;
DROP FUNCTION IF EXISTS update_chat_session_on_new_message();
DROP FUNCTION IF EXISTS update_chat_sessions_timestamp();
DROP FUNCTION IF EXISTS update_chat_messages_timestamp();
DROP FUNCTION IF EXISTS extract_content_preview(JSONB);
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;
*/

-- ============================================
-- END OF MIGRATION
-- ============================================

COMMENT ON SCHEMA public IS 'Chat History Feature - Migration completed successfully';
