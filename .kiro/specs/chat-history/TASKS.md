# 📋 Chat History Feature - Implementation Tasks

> **Spec**: [DESIGN.md](./DESIGN.md)  
> **Status**: Ready for Implementation  
> **Estimated Time**: 6-8 hours

---

## Task Breakdown

### ✅ Phase 1: Database Infrastructure (1-2 hours)

#### Task 1.1: Create Database Migration
- [ ] Create `migrations/create_chat_tables.sql`
- [ ] Define `chat_sessions` table with all columns
- [ ] Define `chat_messages` table with JSONB storage
- [ ] Add all indexes (performance optimization)
- [ ] Create auto-update triggers
- [ ] Add comments for documentation
- [ ] Test migration script

**Files**: 
- `migrations/create_chat_tables.sql` (NEW)

---

#### Task 1.2: Create SQLAlchemy Models
- [ ] Create `app/models/chat.py`
- [ ] Define `ChatSession` model
- [ ] Define `ChatMessage` model
- [ ] Add relationships between models
- [ ] Configure JSONB column type
- [ ] Add model validators
- [ ] Import in `app/db/base.py`

**Files**:
- `app/models/chat.py` (NEW)
- `app/db/base.py` (UPDATE)

---

#### Task 1.3: Create Pydantic Schemas
- [ ] Create `app/schemas/chat.py`
- [ ] Define request schemas:
  - `ChatCreateRequest`
  - `MessageSendRequest`
  - `TitleUpdateRequest`
  - `ChatSearchRequest`
- [ ] Define response schemas:
  - `ChatSessionResponse`
  - `MessageResponse`
  - `ChatListResponse`
  - `ChatDetailResponse`
  - `ExportResponse`
- [ ] Add validation rules
- [ ] Define JSONB message structure types

**Files**:
- `app/schemas/chat.py` (NEW)
- `app/schemas/__init__.py` (UPDATE - add exports)

---

### ✅ Phase 2: Service Layer (2-3 hours)

#### Task 2.1: Core Chat Service
- [ ] Create `app/services/chat_service.py`
- [ ] Implement `create_chat_session()`
- [ ] Implement `get_chat_by_session_id()`
- [ ] Implement `get_user_chats()` with pagination
- [ ] Implement `update_chat_title()`
- [ ] Implement `delete_chat()` (soft + hard delete)
- [ ] Implement `pin_chat()`
- [ ] Add error handling

**Files**:
- `app/services/chat_service.py` (NEW)

---

#### Task 2.2: Message Service
- [ ] Create message CRUD functions in `chat_service.py`:
  - `create_message()`
  - `get_chat_messages()`
  - `get_message_by_id()`
  - `delete_message()`
- [ ] Implement JSONB storage/retrieval
- [ ] Handle message versioning (for future edit feature)
- [ ] Generate `content_preview` (first 500 chars)

**Files**:
- `app/services/chat_service.py` (UPDATE)

---

#### Task 2.3: Search Service
- [ ] Implement full-text search in `chat_service.py`:
  - `search_chats()`
  - PostgreSQL tsvector queries
  - Relevance ranking
- [ ] Search across:
  - Chat titles
  - Message content
- [ ] Return matched snippets

**Files**:
- `app/services/chat_service.py` (UPDATE)

---

#### Task 2.4: Export Service
- [ ] Create `app/services/chat_export_service.py`
- [ ] Implement export formats:
  - `export_as_json()`
  - `export_as_text()`
  - `export_as_markdown()`
- [ ] Format timestamps
- [ ] Handle JSONB data serialization

**Files**:
- `app/services/chat_export_service.py` (NEW)

---

#### Task 2.5: Auto-Title Generation Service
- [ ] Create `app/services/title_generator.py`
- [ ] Implement `generate_chat_title()`:
  - Use Gemini API
  - Create prompt template
  - Handle API errors
  - Fallback to date-based titles
- [ ] Make async (non-blocking)
- [ ] Add retry logic

**Files**:
- `app/services/title_generator.py` (NEW)

---

### ✅ Phase 3: API Endpoints (2-3 hours)

#### Task 3.1: Create Chat Router
- [ ] Create `app/api/v1/endpoints/chat.py`
- [ ] Setup router with `/api/v1/chat` prefix
- [ ] Add authentication dependency
- [ ] Import in `app/api/v1/api.py`

**Files**:
- `app/api/v1/endpoints/chat.py` (NEW)
- `app/api/v1/api.py` (UPDATE)

---

#### Task 3.2: Core Chat Endpoints
- [ ] `POST /new` - Create new chat
- [ ] `GET /list` - List user's chats (with pagination)
- [ ] `GET /{session_id}` - Get chat details
- [ ] `PATCH /{session_id}/title` - Update title
- [ ] `DELETE /{session_id}` - Delete chat
- [ ] `PATCH /{session_id}/pin` - Pin/unpin chat
- [ ] Add authorization checks
- [ ] Add input validation
- [ ] Add error handling

**Files**:
- `app/api/v1/endpoints/chat.py` (UPDATE)

---

#### Task 3.3: Message Endpoints
- [ ] `POST /{session_id}/message` - Send message
  - Store user message
  - Generate AI response (integrate existing chatbot)
  - Store AI response
  - Trigger title generation on first message
  - Return both messages
- [ ] `GET /{session_id}/messages` - Get message history (with pagination)
- [ ] Add ownership validation

**Files**:
- `app/api/v1/endpoints/chat.py` (UPDATE)

---

#### Task 3.4: Search & Export Endpoints
- [ ] `GET /search` - Search chats
- [ ] `GET /{session_id}/export` - Export chat
  - Support multiple formats (query param)
  - Return appropriate content-type
- [ ] Add rate limiting considerations

**Files**:
- `app/api/v1/endpoints/chat.py` (UPDATE)

---

### ✅ Phase 4: Integration & Testing (1-2 hours)

#### Task 4.1: Database Setup
- [ ] Run migration script on development database
- [ ] Verify tables created correctly
- [ ] Test indexes
- [ ] Seed test data

**Commands**:
```bash
psql -U carepath_user -d carepath_healthcare -f migrations/create_chat_tables.sql
```

---

#### Task 4.2: Integration with Existing Chatbot
- [ ] Identify existing chatbot service
- [ ] Create adapter/wrapper if needed
- [ ] Integrate in message endpoint
- [ ] Test AI response generation
- [ ] Handle streaming responses (if applicable)

**Files**:
- `app/api/v1/endpoints/chat.py` (UPDATE)
- Existing chatbot service files (UPDATE if needed)

---

#### Task 4.3: Write Integration Tests
- [ ] Create `tests/test_chat_integration.py`
- [ ] Test complete flow:
  - User login
  - Create chat
  - Send messages
  - List chats
  - Search
  - Export
  - Delete
- [ ] Test authorization (user isolation)
- [ ] Test JSONB operations
- [ ] Test pagination
- [ ] Test error cases

**Files**:
- `tests/test_chat_integration.py` (NEW)

---

#### Task 4.4: Manual Testing
- [ ] Test with care manager account
- [ ] Test with patient account
- [ ] Test cross-user isolation
- [ ] Test auto-title generation
- [ ] Test search functionality
- [ ] Test export in all formats
- [ ] Test edge cases:
  - Empty chats
  - Very long messages
  - Special characters in JSONB
  - Concurrent message sends

---

### ✅ Phase 5: Documentation & Deployment (1 hour)

#### Task 5.1: Update API Documentation
- [ ] Add chat endpoints to OpenAPI/Swagger docs
- [ ] Document request/response schemas
- [ ] Add usage examples
- [ ] Document error codes

**Files**:
- Auto-generated via FastAPI

---

#### Task 5.2: Update Environment Config
- [ ] Add chat settings to `.env.example`
- [ ] Document configuration options
- [ ] Set sensible defaults

**Files**:
- `.env.example` (UPDATE)
- `app/config.py` (UPDATE if needed)

---

#### Task 5.3: Update Database Schema Documentation
- [ ] Add chat tables to `database_schema.sql` master file
- [ ] Update `PROJECT_STRUCTURE.md` or README
- [ ] Document JSONB message structure

**Files**:
- `database_schema.sql` (UPDATE - add comments/references)
- `README.md` or `PROJECT_STRUCTURE.md` (UPDATE)

---

#### Task 5.4: Create User Guide
- [ ] Create `docs/CHAT_HISTORY_GUIDE.md`
- [ ] Explain feature usage
- [ ] Add API examples (curl/Postman)
- [ ] Document data retention policies

**Files**:
- `docs/CHAT_HISTORY_GUIDE.md` (NEW)

---

## 📊 Implementation Checklist Summary

### Database
- [ ] Migration SQL created
- [ ] Tables created in database
- [ ] Indexes verified
- [ ] Triggers tested

### Backend Code
- [ ] SQLAlchemy models
- [ ] Pydantic schemas
- [ ] Chat service layer
- [ ] Export service
- [ ] Title generator service
- [ ] API endpoints
- [ ] Chatbot integration

### Testing
- [ ] Unit tests (optional)
- [ ] Integration tests
- [ ] Manual testing completed

### Documentation
- [ ] API docs updated
- [ ] Environment variables documented
- [ ] User guide created
- [ ] Database schema documented

---

## 🚀 Ready to Start Implementation?

Reply with:
- **"ok"** or **"proceed"** → I'll start implementing all tasks
- **"step by step"** → I'll implement phase by phase and wait for approval
- **"modify tasks"** → You want to change the task breakdown

---

## 📝 Notes

- Estimated total time: **6-8 hours**
- Can be broken into smaller sessions
- Each phase can be tested independently
- Phases can be implemented in parallel by multiple developers

---

**Current Status**: ⏸️ Awaiting approval to begin implementation
