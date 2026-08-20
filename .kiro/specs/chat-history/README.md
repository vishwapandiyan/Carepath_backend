# 💬 Chat History Feature Specification

> **ChatGPT-style conversation history with JSON storage in PostgreSQL**

---

## 📁 Specification Documents

1. **[DESIGN.md](./DESIGN.md)** - Complete technical design specification
   - Database schema
   - API endpoints
   - Architecture diagrams
   - Security considerations
   - Integration points

2. **[TASKS.md](./TASKS.md)** - Implementation task breakdown
   - Phase-by-phase tasks
   - File-by-file checklist
   - Estimated timeline
   - Testing strategy

---

## 🎯 Feature Summary

### What We're Building
A complete chat history system that allows patients and care managers to:
- ✅ Create new chat sessions
- ✅ Send and receive messages (stored as JSON in PostgreSQL)
- ✅ View conversation history
- ✅ Search past conversations
- ✅ Auto-generate chat titles using AI
- ✅ Export conversations (JSON/Text/Markdown)
- ✅ Pin important chats
- ⚠️ Edit/regenerate messages (future phase)

---

## 🏗️ Technical Stack

- **Database**: PostgreSQL with JSONB storage
- **Backend**: FastAPI (Python)
- **ORM**: SQLAlchemy (async)
- **Auth**: JWT (existing system)
- **AI**: Google Gemini (for title generation & responses)
- **Search**: PostgreSQL Full-Text Search

---

## 📊 Database Tables

### `chat_sessions`
Stores chat metadata (titles, timestamps, ownership)

### `chat_messages`
Stores messages as JSONB with flexible structure:
```json
{
  "role": "user" | "assistant" | "system",
  "content": "message text",
  "metadata": { "model": "...", "tokens": 150 },
  "attachments": [...],
  "context": { "patient_id": "..." }
}
```

---

## 🔌 Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/new` | Create new chat |
| `POST` | `/api/v1/chat/{id}/message` | Send message |
| `GET` | `/api/v1/chat/list` | List all chats |
| `GET` | `/api/v1/chat/{id}/messages` | Get chat history |
| `GET` | `/api/v1/chat/search` | Search chats |
| `PATCH` | `/api/v1/chat/{id}/title` | Update title |
| `DELETE` | `/api/v1/chat/{id}` | Delete chat |
| `GET` | `/api/v1/chat/{id}/export` | Export chat |

---

## 🔐 Security

- All endpoints require JWT authentication
- Users can only access their own chats
- Care managers can create chats associated with patients
- Patients' chats auto-associate with their patient_id

---

## 📦 File Structure

```
.kiro/specs/chat-history/
├── README.md          # This file (overview)
├── DESIGN.md          # Complete technical design
└── TASKS.md           # Implementation checklist

app/
├── models/chat.py                    # NEW: SQLAlchemy models
├── schemas/chat.py                   # NEW: Pydantic schemas
├── services/
│   ├── chat_service.py               # NEW: Core business logic
│   ├── chat_export_service.py        # NEW: Export functionality
│   └── title_generator.py            # NEW: AI title generation
└── api/v1/endpoints/chat.py          # NEW: API routes

migrations/
└── create_chat_tables.sql            # NEW: Database schema

tests/
└── test_chat_integration.py          # NEW: Integration tests
```

---

## ⏱️ Implementation Timeline

| Phase | Description | Time |
|-------|-------------|------|
| **Phase 1** | Database schema & models | 1-2 hours |
| **Phase 2** | Service layer | 2-3 hours |
| **Phase 3** | API endpoints | 2-3 hours |
| **Phase 4** | Testing & integration | 1-2 hours |
| **Phase 5** | Documentation | 1 hour |
| **Total** | | **6-8 hours** |

---

## 🎯 Implementation Status

- [x] Requirements gathering
- [x] Design specification completed
- [x] Task breakdown completed
- [ ] Implementation (awaiting approval)
- [ ] Testing
- [ ] Documentation
- [ ] Deployment

---

## 🚀 Next Steps

**You said**: "I recommend Option 2 (Design First)"

**Current Status**: ✅ Design specification complete!

**Ready to proceed?** Say:
- **"ok"** or **"proceed"** → Start full implementation
- **"step by step"** → Implement phase by phase
- **"review design"** → Discuss design changes

---

## 📚 Reference Documents in Project

- `database_schema.sql` - Existing schema
- `app/models/ehr.py` - Patient EHR model
- `app/api/v1/endpoints/auth.py` - Auth patterns
- `.env.example` - Configuration template

---

## 💡 Design Highlights

### Why JSONB?
- Flexible message structure (attachments, metadata, context)
- Fast queries with GIN indexes
- No schema migrations for new message fields
- Natural fit for chat applications

### Why Auto-Title Generation?
- Better user experience (like ChatGPT)
- Easier to find old conversations
- Uses existing Gemini AI integration

### Why Separate Tables?
- `chat_sessions`: Fast metadata queries (list, search)
- `chat_messages`: Efficient message storage with pagination

---

## 🎨 Example Usage

### Create Chat & Send Message
```bash
# Create new chat
POST /api/v1/chat/new
{
  "patient_id": "PAT_abc123",
  "initial_message": "What are my medication side effects?"
}

# Response
{
  "session_id": "CHAT_a1b2c3d4e5f6",
  "title": "New Chat",
  "created_at": "2026-08-20T10:30:00Z"
}
```

### List Chats
```bash
GET /api/v1/chat/list?limit=20&search=medication

# Response
{
  "chats": [
    {
      "session_id": "CHAT_a1b2c3d4e5f6",
      "title": "Medication Side Effects Discussion",
      "message_count": 12,
      "last_message_at": "2026-08-20T10:45:00Z",
      "preview": "What are my medication side effects?..."
    }
  ],
  "total": 45
}
```

---

## ✅ Acceptance Criteria

- [ ] Can create new chats
- [ ] Can send messages and receive AI responses
- [ ] Messages stored as JSONB
- [ ] Can list and paginate chats
- [ ] Can search chat content
- [ ] Auto-title generation works
- [ ] Can export chats (JSON format minimum)
- [ ] Authorization enforced (users see only their chats)
- [ ] Integration tests passing

---

## 📞 Questions?

Review the detailed documents:
- **Technical details** → See [DESIGN.md](./DESIGN.md)
- **Implementation plan** → See [TASKS.md](./TASKS.md)

---

**Ready when you are!** 🚀
