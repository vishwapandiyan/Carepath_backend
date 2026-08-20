# 💬 Chat History Feature - Design Specification

> **Status**: Draft  
> **Created**: 2026-08-20  
> **Approach**: Design First (Technical Architecture → Implementation)  
> **Reference**: ChatGPT-style conversation history with JSON storage in PostgreSQL

---

## 🎯 Feature Overview

Implement a complete chat history system that allows users (patients and care managers) to:
- Create new chat sessions
- Store conversation messages as JSON in PostgreSQL
- View past conversations
- Search chat history
- Auto-generate chat titles
- Edit and regenerate messages
- Export conversations

---

## 🏗️ System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend Layer                        │
│  (Future: React/Vue - Not part of this backend spec)       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Chat API Endpoints (/api/v1/chat/*)                │   │
│  │  - Create chat                                       │   │
│  │  - Send message                                      │   │
│  │  - List chats                                        │   │
│  │  - Get chat history                                  │   │
│  │  - Search chats                                      │   │
│  │  - Update/Delete                                     │   │
│  │  - Export chat                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                              ↓                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Chat Service Layer                                  │   │
│  │  - Business logic                                    │   │
│  │  - Title generation (Gemini AI)                      │   │
│  │  - Message formatting                                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
│  - chat_sessions table                                      │
│  - chat_messages table (with JSONB storage)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Database Schema Design

### Table 1: `chat_sessions`

Stores metadata about each chat conversation.

```sql
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
COMMENT ON COLUMN chat_sessions.session_id IS 'Public-facing unique chat identifier';
COMMENT ON COLUMN chat_sessions.user_id IS 'User who owns this chat (patient or care manager)';
COMMENT ON COLUMN chat_sessions.patient_id IS 'Associated patient (NULL for care manager general chats)';
COMMENT ON COLUMN chat_sessions.title IS 'Chat title (auto-generated or user-edited)';
COMMENT ON COLUMN chat_sessions.is_title_auto_generated IS 'TRUE if title was AI-generated, FALSE if user-edited';
COMMENT ON COLUMN chat_sessions.is_pinned IS 'Allow users to pin important conversations';
```

### Table 2: `chat_messages`

Stores individual messages within chat sessions using JSONB for flexible message structure.

```sql
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
            "latency_ms": 1234
        },
        "attachments": [
            {"type": "image", "url": "...", "filename": "..."},
            {"type": "file", "url": "...", "filename": "..."}
        ],
        "context": {
            "patient_id": "PAT_abc123",
            "prediction_type": "readmission"
        }
    }
    */
    
    -- Denormalized fields for quick queries (extracted from JSONB)
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content_preview TEXT,  -- First 500 chars for search/preview
    
    -- Versioning (for edit/regenerate feature)
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
COMMENT ON COLUMN chat_messages.message_data IS 'Full message content stored as JSONB (role, content, metadata, attachments)';
COMMENT ON COLUMN chat_messages.content_preview IS 'Denormalized preview for search (first 500 chars)';
COMMENT ON COLUMN chat_messages.parent_message_id IS 'Reference to parent message (for edit/regenerate branching)';
COMMENT ON COLUMN chat_messages.version IS 'Message version number (for edit history)';
```

### Auto-Update Trigger

```sql
-- Trigger to update chat_sessions.updated_at and last_message_at
CREATE OR REPLACE FUNCTION update_chat_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chat_sessions
    SET 
        updated_at = CURRENT_TIMESTAMP,
        last_message_at = CURRENT_TIMESTAMP,
        message_count = message_count + 1
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_chat_on_new_message
    AFTER INSERT ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_session_timestamp();
```

---

## 🔌 API Endpoint Design

### Base Path: `/api/v1/chat`

All endpoints require authentication (JWT token).

---

### 1️⃣ **Create New Chat**

**Endpoint**: `POST /api/v1/chat/new`

**Auth**: Required (Patient or Care Manager)

**Request Body**:
```json
{
    "patient_id": "PAT_abc123",  // Optional: associate chat with specific patient
    "initial_message": "Hello, I need help with medication adherence"  // Optional
}
```

**Response** (`201 Created`):
```json
{
    "session_id": "CHAT_a1b2c3d4e5f6",
    "title": "New Chat",
    "created_at": "2026-08-20T10:30:00Z",
    "message_count": 0,
    "is_active": true
}
```

**Logic**:
1. Create new chat session record
2. If `initial_message` provided, create first message
3. Return session metadata

---

### 2️⃣ **Send Message to Chat**

**Endpoint**: `POST /api/v1/chat/{session_id}/message`

**Auth**: Required (Owner only)

**Request Body**:
```json
{
    "content": "What are my medication side effects?",
    "role": "user",
    "context": {
        "patient_id": "PAT_abc123",
        "action": "medication_query"
    }
}
```

**Response** (`200 OK`):
```json
{
    "message_id": "MSG_xyz789",
    "session_id": "CHAT_a1b2c3d4e5f6",
    "role": "user",
    "content": "What are my medication side effects?",
    "created_at": "2026-08-20T10:31:00Z",
    "assistant_response": {
        "message_id": "MSG_xyz790",
        "role": "assistant",
        "content": "Based on your medications...",
        "metadata": {
            "model": "gemini-1.5-flash",
            "tokens": 250,
            "latency_ms": 1500
        },
        "created_at": "2026-08-20T10:31:02Z"
    }
}
```

**Logic**:
1. Validate session ownership
2. Store user message as JSONB
3. Generate AI response (using existing chatbot logic)
4. Store AI response
5. Update session `last_message_at`
6. Auto-generate title if first user message (async)

---

### 3️⃣ **List All Chats**

**Endpoint**: `GET /api/v1/chat/list`

**Auth**: Required

**Query Parameters**:
- `limit` (default: 20, max: 100)
- `offset` (default: 0)
- `patient_id` (optional: filter by patient)
- `search` (optional: search in titles and message content)
- `is_pinned` (optional: filter pinned chats)
- `sort_by` (default: `last_message_at`, options: `created_at`, `title`)
- `sort_order` (default: `desc`, options: `asc`)

**Response** (`200 OK`):
```json
{
    "chats": [
        {
            "session_id": "CHAT_a1b2c3d4e5f6",
            "title": "Medication Side Effects Discussion",
            "is_title_auto_generated": true,
            "message_count": 12,
            "last_message_at": "2026-08-20T10:45:00Z",
            "created_at": "2026-08-20T10:30:00Z",
            "is_pinned": false,
            "preview": "What are my medication side effects?..."
        }
    ],
    "total": 45,
    "limit": 20,
    "offset": 0
}
```

---

### 4️⃣ **Get Chat History**

**Endpoint**: `GET /api/v1/chat/{session_id}/messages`

**Auth**: Required (Owner only)

**Query Parameters**:
- `limit` (default: 50, max: 500)
- `offset` (default: 0)
- `order` (default: `asc`, options: `desc`)

**Response** (`200 OK`):
```json
{
    "session_id": "CHAT_a1b2c3d4e5f6",
    "title": "Medication Side Effects Discussion",
    "message_count": 12,
    "messages": [
        {
            "message_id": "MSG_xyz789",
            "role": "user",
            "content": "What are my medication side effects?",
            "created_at": "2026-08-20T10:31:00Z",
            "version": 1,
            "is_current_version": true
        },
        {
            "message_id": "MSG_xyz790",
            "role": "assistant",
            "content": "Based on your medications...",
            "metadata": {
                "model": "gemini-1.5-flash",
                "tokens": 250
            },
            "created_at": "2026-08-20T10:31:02Z",
            "version": 1,
            "is_current_version": true
        }
    ]
}
```

---

### 5️⃣ **Update Chat Title**

**Endpoint**: `PATCH /api/v1/chat/{session_id}/title`

**Auth**: Required (Owner only)

**Request Body**:
```json
{
    "title": "My Custom Chat Title"
}
```

**Response** (`200 OK`):
```json
{
    "session_id": "CHAT_a1b2c3d4e5f6",
    "title": "My Custom Chat Title",
    "is_title_auto_generated": false,
    "updated_at": "2026-08-20T10:50:00Z"
}
```

---

### 6️⃣ **Delete Chat**

**Endpoint**: `DELETE /api/v1/chat/{session_id}`

**Auth**: Required (Owner only)

**Query Parameters**:
- `permanent` (default: false) - If true, hard delete; if false, soft delete

**Response** (`200 OK`):
```json
{
    "message": "Chat deleted successfully",
    "session_id": "CHAT_a1b2c3d4e5f6",
    "deleted_at": "2026-08-20T10:55:00Z"
}
```

---

### 7️⃣ **Search Chats**

**Endpoint**: `GET /api/v1/chat/search`

**Auth**: Required

**Query Parameters**:
- `q` (required): search query
- `limit` (default: 20)
- `offset` (default: 0)

**Response** (`200 OK`):
```json
{
    "results": [
        {
            "session_id": "CHAT_a1b2c3d4e5f6",
            "title": "Medication Side Effects Discussion",
            "matched_messages": [
                {
                    "message_id": "MSG_xyz789",
                    "content_snippet": "...medication side effects...",
                    "created_at": "2026-08-20T10:31:00Z"
                }
            ],
            "relevance_score": 0.89
        }
    ],
    "total": 3
}
```

**Uses PostgreSQL Full-Text Search on**:
- Chat titles
- Message content (via `content_preview`)

---

### 8️⃣ **Export Chat**

**Endpoint**: `GET /api/v1/chat/{session_id}/export`

**Auth**: Required (Owner only)

**Query Parameters**:
- `format` (default: `json`, options: `json`, `txt`, `markdown`)

**Response**:
- `json`: Returns full JSONB message data
- `txt`: Plain text conversation
- `markdown`: Formatted markdown with timestamps

---

### 9️⃣ **Regenerate Message (Optional - Future)**

**Endpoint**: `POST /api/v1/chat/{session_id}/regenerate/{message_id}`

**Auth**: Required (Owner only)

**Response**: Creates new version of assistant message

---

### 🔟 **Pin/Unpin Chat**

**Endpoint**: `PATCH /api/v1/chat/{session_id}/pin`

**Auth**: Required (Owner only)

**Request Body**:
```json
{
    "is_pinned": true
}
```

**Response** (`200 OK`):
```json
{
    "session_id": "CHAT_a1b2c3d4e5f6",
    "is_pinned": true,
    "updated_at": "2026-08-20T11:00:00Z"
}
```

---

## 🧠 Auto-Title Generation

### Strategy

When a chat is created with the first user message:

1. **Trigger**: After first user message is saved
2. **Method**: Use Gemini API to generate concise title
3. **Prompt Template**:
   ```
   Generate a concise 3-7 word title for this conversation based on the first user message.
   The title should capture the main topic clearly.
   
   User message: "{first_user_message}"
   
   Return only the title, nothing else.
   ```
4. **Fallback**: If API fails, use "Chat from {date}"
5. **Update**: Set `title` and `is_title_auto_generated = TRUE`

### Implementation

```python
async def generate_chat_title(session_id: str, first_message: str):
    """Generate title using Gemini API"""
    try:
        prompt = f"""Generate a concise 3-7 word title for this healthcare conversation.
        User message: "{first_message}"
        Return only the title."""
        
        # Call Gemini API
        title = await gemini_service.generate_title(prompt)
        
        # Update session
        await update_session_title(session_id, title, auto_generated=True)
    except Exception as e:
        # Fallback to date-based title
        fallback_title = f"Chat from {datetime.now().strftime('%B %d, %Y')}"
        await update_session_title(session_id, fallback_title, auto_generated=True)
```

---

## 🔐 Security & Authorization

### Access Control Rules

1. **Chat Sessions**:
   - Users can only access their own chats
   - Care managers can access chats they created
   - Patients can only access their own chats

2. **Patient Association**:
   - Care managers can create chats associated with any patient
   - Patients' chats are automatically associated with their patient_id

3. **Data Isolation**:
   - Query filters by `user_id` for all list/search operations
   - Validate ownership before update/delete operations

### Authorization Middleware

```python
async def verify_chat_ownership(
    session_id: str,
    current_user: User,
    db: AsyncSession
) -> ChatSession:
    """Verify user owns the chat session"""
    chat = await get_chat_by_session_id(db, session_id)
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return chat
```

---

## 📁 File Structure

```
app/
├── api/
│   └── v1/
│       └── endpoints/
│           └── chat.py              # NEW: Chat API endpoints
├── models/
│   └── chat.py                      # NEW: SQLAlchemy models
├── schemas/
│   └── chat.py                      # NEW: Pydantic schemas
├── services/
│   ├── chat_service.py              # NEW: Business logic
│   └── title_generator.py           # NEW: AI title generation
└── db/
    └── base.py                       # Import new models

migrations/
└── create_chat_tables.sql            # NEW: Database migration

tests/
└── test_chat_integration.py          # NEW: Integration tests
```

---

## 🔄 Integration Points

### With Existing Systems

1. **Authentication**: Use existing JWT auth system
2. **User Management**: Reference existing `users` table
3. **Patient EHR**: Link chats to `patient_ehr.patient_id`
4. **Gemini AI**: Leverage existing chatbot service for responses
5. **Database**: Extend existing PostgreSQL schema

---

## 📊 Data Flow Diagram

```
User sends message
       ↓
  [POST /chat/{id}/message]
       ↓
  Validate session ownership
       ↓
  Store user message (JSONB)
       ↓
  Generate AI response (existing chatbot)
       ↓
  Store AI message (JSONB)
       ↓
  Update session metadata
       ↓
  [IF first message] → Generate title (async)
       ↓
  Return both messages to user
```

---

## 🎨 Message JSONB Schema

```typescript
interface MessageData {
    role: "user" | "assistant" | "system";
    content: string;
    
    // Optional metadata
    metadata?: {
        model?: string;           // "gemini-1.5-flash"
        tokens?: number;          // Token count
        finish_reason?: string;   // "stop", "length", "error"
        latency_ms?: number;      // Response time
        temperature?: number;     // AI temperature setting
    };
    
    // Optional attachments
    attachments?: Array<{
        type: "image" | "file" | "document";
        url: string;
        filename: string;
        size_bytes?: number;
        mime_type?: string;
    }>;
    
    // Optional context
    context?: {
        patient_id?: string;
        prediction_type?: string;  // "readmission", "ed_avoidable"
        action?: string;
        [key: string]: any;        // Flexible for future use
    };
}
```

---

## ⚡ Performance Considerations

1. **Pagination**: All list endpoints support limit/offset
2. **Indexes**: Critical indexes on foreign keys, timestamps, and search fields
3. **JSONB Indexing**: GIN indexes for fast JSONB queries
4. **Caching** (Future):
   - Cache recent chat lists per user
   - Cache message counts
5. **Async Operations**:
   - Title generation happens asynchronously
   - Don't block message send on title generation

---

## 🧪 Testing Strategy

### Unit Tests
- Chat creation
- Message storage/retrieval
- Title generation
- Authorization checks

### Integration Tests
- Complete chat flow (create → message → list → search → delete)
- Multi-user isolation
- JSONB query operations
- Export functionality

### Test Data
```python
# Create test chat
test_user = create_test_user(role="PATIENT")
test_chat = create_test_chat(user_id=test_user.id)
test_message = create_test_message(
    session_id=test_chat.session_id,
    role="user",
    content="Test message"
)
```

---

## 🚀 Implementation Phases

### Phase 1: Core Infrastructure ✅ PLANNED
- Database schema creation
- SQLAlchemy models
- Pydantic schemas
- Basic CRUD service layer

### Phase 2: API Endpoints ✅ PLANNED
- Create chat
- Send message
- List chats
- Get chat history
- Update title
- Delete chat

### Phase 3: Advanced Features ✅ PLANNED
- Search functionality
- Auto-title generation
- Export functionality
- Pin/unpin chats

### Phase 4: Testing & Documentation ✅ PLANNED
- Integration tests
- API documentation (OpenAPI)
- Performance testing

### Phase 5: Future Enhancements 🔮 OPTIONAL
- Message regeneration
- Conversation branching (edit history)
- Shared chats (between care manager & patient)
- Chat categories/folders
- Voice message support

---

## 📝 Sample Use Cases

### Use Case 1: Patient Asks About Medication
```
1. Patient logs in
2. Clicks "New Chat"
3. Types: "What are the side effects of my diabetes medication?"
4. System:
   - Creates chat session
   - Stores user message
   - Generates AI response using existing chatbot
   - Stores AI response
   - Auto-generates title: "Diabetes Medication Side Effects"
5. Patient receives response
6. Patient can continue conversation or start new chat
```

### Use Case 2: Care Manager Reviews Patient History
```
1. Care manager logs in
2. Views chat list filtered by patient "PAT_abc123"
3. Searches for "readmission risk"
4. Opens relevant chat
5. Reviews conversation history
6. Exports chat as PDF for documentation
```

---

## 🔧 Configuration

### Environment Variables

Add to `.env`:
```bash
# Chat Settings
CHAT_MAX_MESSAGES_PER_SESSION=1000
CHAT_DEFAULT_PAGE_SIZE=20
CHAT_MAX_PAGE_SIZE=100
CHAT_TITLE_MAX_LENGTH=500
CHAT_ENABLE_AUTO_TITLE=true
CHAT_ENABLE_EXPORT=true

# Title Generation
CHAT_TITLE_MODEL=gemini-1.5-flash
CHAT_TITLE_TIMEOUT_SECONDS=10
```

---

## ✅ Acceptance Criteria

- [ ] Database schema created and migrated
- [ ] All API endpoints functional
- [ ] Messages stored as JSONB with proper structure
- [ ] Auto-title generation works
- [ ] Search returns relevant results
- [ ] Export functionality works (JSON format minimum)
- [ ] Authorization properly enforced
- [ ] Integration tests passing
- [ ] API documentation updated

---

## 📚 References

- **ChatGPT UX**: Reference for UI/UX patterns (frontend)
- **PostgreSQL JSONB**: [Official Docs](https://www.postgresql.org/docs/current/datatype-json.html)
- **Full-Text Search**: [PostgreSQL Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- **FastAPI AsyncIO**: [Async Best Practices](https://fastapi.tiangolo.com/async/)

---

## 🎯 Next Steps

Once this design is approved:
1. Create database migration SQL file
2. Implement SQLAlchemy models
3. Create Pydantic schemas
4. Implement service layer
5. Build API endpoints
6. Add integration tests
7. Update API documentation

---

**Ready to proceed with implementation?** 🚀
