# 📊 Chat History Feature - Quick Summary

> One-page overview for quick reference

---

## 🎯 What Are We Building?

**ChatGPT-style conversation history system** where users can:
- Create unlimited chat sessions
- Store messages as JSON in PostgreSQL
- Search past conversations
- Auto-generate titles with AI
- Export chat history

---

## 📋 Feature Checklist

| Feature | Status | Priority |
|---------|--------|----------|
| New chat button | ✅ Planned | High |
| Auto-title generation | ✅ Planned | High |
| Message history | ✅ Planned | High |
| Search history | ✅ Planned | High |
| Export chats | ✅ Planned | High |
| Session sidebar | ✅ Planned | High |
| Edit/regenerate | ⚠️ Optional | Low |

---

## 🗄️ Database Design (Simplified)

```sql
chat_sessions                    chat_messages
─────────────                    ─────────────
id (PK)                         id (PK)
session_id (CHAT_xxx)           message_id (MSG_xxx)
user_id (FK → users)            session_id (FK)
patient_id (FK → patient_ehr)   message_data (JSONB) ← All data here
title                           role (user/assistant)
message_count                   content_preview
is_active                       created_at
created_at
last_message_at
```

**Key Decision**: All message content stored as **JSONB** for flexibility!

---

## 🔌 Core API Endpoints

```
POST   /api/v1/chat/new                  Create chat
POST   /api/v1/chat/{id}/message         Send message (returns AI response)
GET    /api/v1/chat/list                 List chats (paginated)
GET    /api/v1/chat/{id}/messages        Get history
GET    /api/v1/chat/search?q=...         Search
GET    /api/v1/chat/{id}/export          Export (JSON/TXT/MD)
PATCH  /api/v1/chat/{id}/title           Update title
DELETE /api/v1/chat/{id}                 Delete
```

---

## 💾 Message JSONB Structure

```json
{
  "role": "user | assistant | system",
  "content": "actual message text",
  "metadata": {
    "model": "gemini-1.5-flash",
    "tokens": 150,
    "latency_ms": 1234
  },
  "attachments": [],
  "context": {
    "patient_id": "PAT_xxx",
    "action": "medication_query"
  }
}
```

**Why JSONB?**
- Flexible schema (add fields without migrations)
- Fast queries with GIN indexes
- Perfect for chat apps

---

## 🏗️ Architecture Flow

```
User → FastAPI Endpoint
          ↓
      Auth Middleware (JWT)
          ↓
      Chat Service
          ↓
      PostgreSQL (JSONB)
          ↓
      Return Response

[Async] Title Generation (Gemini API)
```

---

## 📁 New Files Created

```
.kiro/specs/chat-history/
├── README.md                 ← You are here
├── DESIGN.md                 ← Full technical spec
├── TASKS.md                  ← Implementation checklist
└── SUMMARY.md                ← This file

[To Be Created]
app/models/chat.py
app/schemas/chat.py
app/services/chat_service.py
app/services/chat_export_service.py
app/services/title_generator.py
app/api/v1/endpoints/chat.py
migrations/create_chat_tables.sql
tests/test_chat_integration.py
```

---

## ⏱️ Timeline

| Phase | Tasks | Time |
|-------|-------|------|
| 1. Database | Schema + Models | 1-2h |
| 2. Services | Business logic | 2-3h |
| 3. API | Endpoints | 2-3h |
| 4. Testing | Integration tests | 1-2h |
| 5. Docs | Documentation | 1h |
| **Total** | | **6-8h** |

---

## 🔐 Security

✅ JWT authentication required  
✅ Users can only access their own chats  
✅ Care managers can associate chats with patients  
✅ Patients' chats auto-link to their patient_id  

---

## 🎨 Example API Call

### Create Chat & Send Message
```bash
# 1. Create new chat
curl -X POST https://api.example.com/api/v1/chat/new \
  -H "Authorization: Bearer {jwt_token}" \
  -d '{"initial_message": "What are my meds?"}'

# Response
{
  "session_id": "CHAT_abc123",
  "title": "New Chat"  # Will be auto-updated
}

# 2. Send message (AI responds automatically)
curl -X POST https://api.example.com/api/v1/chat/CHAT_abc123/message \
  -H "Authorization: Bearer {jwt_token}" \
  -d '{"content": "What are the side effects?", "role": "user"}'

# Response
{
  "message_id": "MSG_xyz",
  "role": "user",
  "content": "What are the side effects?",
  "assistant_response": {
    "message_id": "MSG_abc",
    "role": "assistant",
    "content": "Based on your medications..."
  }
}
```

---

## 🧠 Smart Features

### Auto-Title Generation
After first user message, Gemini API generates a title:
- Input: "What are my diabetes medication side effects?"
- Output: "Diabetes Medication Side Effects"

### Full-Text Search
Search across:
- Chat titles
- Message content
Uses PostgreSQL `tsvector` for fast, relevant results

### Export Formats
- **JSON**: Complete data with metadata
- **Text**: Plain text conversation
- **Markdown**: Formatted with timestamps

---

## ✅ What Success Looks Like

- [ ] Care manager creates chat, asks about patient "PAT_123"
- [ ] System stores messages, generates AI responses
- [ ] Title auto-updates to "Patient PAT_123 Status Inquiry"
- [ ] Care manager can search "PAT_123" and find chat
- [ ] Export works in all 3 formats
- [ ] Patient logs in, sees only their own chats

---

## 🚀 Implementation Decision

**You chose**: Design First Approach ✅

**Current status**: Specification complete!

**What's next?**

Reply with:
- **"ok"** → Start implementing everything
- **"step by step"** → Implement phase by phase
- **Ask questions** → Clarify any part of the design

---

## 📚 Full Documentation

For complete details, see:
- **[README.md](./README.md)** - Overview & getting started
- **[DESIGN.md](./DESIGN.md)** - Complete technical specification
- **[TASKS.md](./TASKS.md)** - Step-by-step implementation plan

---

## 💡 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSONB storage | Flexibility, performance, no schema migrations |
| Separate tables | Fast metadata queries, efficient pagination |
| Auto-title AI | Better UX, easier to find conversations |
| PostgreSQL FTS | Native, fast, no external dependencies |
| Async title gen | Don't block message sending |
| Soft deletes | Data retention, recovery options |

---

## 🎯 Immediate Next Steps

1. Review this specification
2. Ask any clarifying questions
3. Approve design
4. Start implementation (I'll create all files)

---

**Ready to build this? Let me know!** 🚀
