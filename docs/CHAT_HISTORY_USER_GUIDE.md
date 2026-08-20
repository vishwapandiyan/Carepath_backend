# 💬 Chat History Feature - User Guide

## Quick Start

### 1. Start the Server

```bash
# Activate virtual environment
source venv/bin/activate  # or: . venv/bin/activate

# Start FastAPI server
uvicorn app.main:app --reload
```

Server will run at: `http://localhost:8000`  
API Docs: `http://localhost:8000/docs`

### 2. Run Integration Tests

```bash
# In a new terminal
python test_chat_integration.py
```

This will test all chat endpoints automatically.

---

## API Usage Examples

### Authentication First

All chat endpoints require authentication. Get a token:

```bash
# Login as care manager or patient
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "role": "CARE_MANAGER"
}
```

Save the `access_token` for subsequent requests.

---

## Core Workflows

### Workflow 1: Create Chat and Send Messages

```bash
# Step 1: Create new chat
curl -X POST http://localhost:8000/api/v1/chat/new \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "initial_message": "I need help with patient medication management"
  }'
```

Response:
```json
{
  "session_id": "CHAT_abc123xyz456",
  "title": "Patient Medication Management Help",
  "is_title_auto_generated": true,
  "message_count": 1,
  "created_at": "2026-08-20T10:30:00Z"
}
```

```bash
# Step 2: Continue conversation
curl -X POST http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/message \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What are best practices for post-discharge follow-up?",
    "role": "user"
  }'
```

Response:
```json
{
  "user_message": {
    "message_id": "MSG_user123",
    "role": "user",
    "content": "What are best practices...",
    "created_at": "2026-08-20T10:31:00Z"
  },
  "assistant_response": {
    "message_id": "MSG_asst456",
    "role": "assistant",
    "content": "Here are the best practices...",
    "metadata": {
      "model": "gemini-1.5-flash",
      "tokens": 250
    },
    "created_at": "2026-08-20T10:31:02Z"
  }
}
```

---

### Workflow 2: View Chat History

```bash
# List all your chats
curl -X GET "http://localhost:8000/api/v1/chat/list?limit=20&offset=0" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "chats": [
    {
      "session_id": "CHAT_abc123xyz456",
      "title": "Patient Medication Management",
      "message_count": 5,
      "last_message_at": "2026-08-20T10:45:00Z",
      "preview": "I need help with patient medication..."
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

```bash
# Get specific chat messages
curl -X GET "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/messages" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "session_id": "CHAT_abc123xyz456",
  "title": "Patient Medication Management",
  "message_count": 5,
  "messages": [
    {
      "message_id": "MSG_user123",
      "role": "user",
      "content": "I need help with...",
      "created_at": "2026-08-20T10:30:00Z"
    },
    {
      "message_id": "MSG_asst456",
      "role": "assistant",
      "content": "I can help you with...",
      "created_at": "2026-08-20T10:30:02Z"
    }
  ]
}
```

---

### Workflow 3: Search Conversations

```bash
# Search for chats about "medication"
curl -X GET "http://localhost:8000/api/v1/chat/search?q=medication&limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "results": [
    {
      "session_id": "CHAT_abc123xyz456",
      "title": "Patient Medication Management",
      "matched_messages": [
        {
          "message_id": "MSG_user123",
          "content_snippet": "...medication management...",
          "created_at": "2026-08-20T10:30:00Z"
        }
      ],
      "relevance_score": 0.89
    }
  ],
  "total": 1,
  "query": "medication"
}
```

---

### Workflow 4: Manage Chats

```bash
# Update chat title
curl -X PATCH http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/title \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Medication Management Discussion - Patient A"
  }'
```

```bash
# Pin important chat
curl -X PATCH http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/pin \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_pinned": true
  }'
```

```bash
# Delete chat (soft delete - can be recovered)
curl -X DELETE "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456?permanent=false" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

```bash
# Permanent delete (cannot be recovered)
curl -X DELETE "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456?permanent=true" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### Workflow 5: Export Conversations

```bash
# Export as JSON (complete data)
curl -X GET "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/export?format=json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o chat_export.json

# Export as plain text
curl -X GET "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/export?format=txt" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o chat_export.txt

# Export as Markdown
curl -X GET "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/export?format=markdown" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o chat_export.md
```

---

## Advanced Features

### Filtering & Sorting

```bash
# List only pinned chats
curl -X GET "http://localhost:8000/api/v1/chat/list?is_pinned=true" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Filter by patient
curl -X GET "http://localhost:8000/api/v1/chat/list?patient_id=PAT_abc123" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Search in titles
curl -X GET "http://localhost:8000/api/v1/chat/list?search=medication" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Sort by creation date (oldest first)
curl -X GET "http://localhost:8000/api/v1/chat/list?sort_by=created_at&sort_order=asc" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pagination

```bash
# Get next page of chats
curl -X GET "http://localhost:8000/api/v1/chat/list?limit=20&offset=20" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get specific page of messages
curl -X GET "http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/messages?limit=50&offset=50" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Message Context

```bash
# Send message with context
curl -X POST http://localhost:8000/api/v1/chat/CHAT_abc123xyz456/message \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the readmission risk?",
    "role": "user",
    "context": {
      "patient_id": "PAT_abc123",
      "prediction_type": "readmission",
      "action": "risk_assessment"
    }
  }'
```

---

## Using Swagger UI

The easiest way to test the API is through Swagger UI:

1. Go to `http://localhost:8000/docs`
2. Click "Authorize" button (top right)
3. Enter your JWT token: `Bearer YOUR_TOKEN`
4. Click "Authorize"
5. Now you can test all endpoints interactively!

---

## Python Client Example

```python
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"

async def chat_example():
    async with httpx.AsyncClient() as client:
        # Login
        login_response = await client.post(
            f"{BASE_URL}/auth/login",
            json={
                "username": "care_manager",
                "password": "password123"
            }
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create chat
        chat_response = await client.post(
            f"{BASE_URL}/chat/new",
            json={
                "initial_message": "Help with discharge planning"
            },
            headers=headers
        )
        session_id = chat_response.json()["session_id"]
        print(f"Created chat: {session_id}")
        
        # Send message
        message_response = await client.post(
            f"{BASE_URL}/chat/{session_id}/message",
            json={
                "content": "What are the key steps?",
                "role": "user"
            },
            headers=headers
        )
        print("Assistant:", message_response.json()["assistant_response"]["content"])
        
        # List chats
        list_response = await client.get(
            f"{BASE_URL}/chat/list",
            headers=headers
        )
        print(f"Total chats: {list_response.json()['total']}")

asyncio.run(chat_example())
```

---

## Troubleshooting

### Error: 401 Unauthorized
- Check your JWT token is valid
- Token might have expired (default: 30 minutes)
- Re-login to get a new token

### Error: 404 Chat not found
- Verify the session_id is correct
- Check you own the chat (user_id matches)
- Chat might have been deleted

### Error: 500 Internal Server Error
- Check server logs
- Verify database connection
- Ensure all migrations ran successfully

### Database Issues
```bash
# Verify chat tables exist
psql -U vishwa -d carepath_db -c "\dt chat*"

# Should show:
#  chat_messages
#  chat_sessions

# If missing, run migration:
psql -U vishwa -d carepath_db -f migrations/create_chat_tables.sql
```

---

## Performance Tips

1. **Use pagination**: Don't fetch all messages at once
2. **Cache token**: Don't login on every request
3. **Batch operations**: Create multiple chats/messages in bulk if needed
4. **Search efficiently**: Use specific search terms
5. **Export only when needed**: Exports can be large

---

## Security Best Practices

1. **Never share JWT tokens**: They provide full account access
2. **Use HTTPS in production**: Encrypt all traffic
3. **Rotate tokens regularly**: Implement token refresh
4. **Validate input**: Don't trust client data
5. **Rate limiting**: Implement in production

---

## API Reference

Full API documentation available at:
- **Interactive Docs**: `http://localhost:8000/docs`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Support

For issues or questions:
1. Check `CHAT_HISTORY_IMPLEMENTATION_COMPLETE.md`
2. Review `.kiro/specs/chat-history/DESIGN.md`
3. Run integration tests: `python test_chat_integration.py`
4. Check server logs for errors

---

Happy chatting! 💬
