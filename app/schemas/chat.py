"""
Chat History Pydantic Schemas
Request and response models for chat API endpoints
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    """Message role types"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ExportFormat(str, Enum):
    """Export format options"""
    JSON = "json"
    TEXT = "txt"
    MARKDOWN = "markdown"


class SortOrder(str, Enum):
    """Sort order options"""
    ASC = "asc"
    DESC = "desc"


# ── Message Metadata Schemas ──────────────────────────────────────────────────

class MessageMetadata(BaseModel):
    """AI response metadata"""
    model: Optional[str] = Field(None, description="AI model used (e.g., gemini-1.5-flash)")
    tokens: Optional[int] = Field(None, description="Token count")
    finish_reason: Optional[str] = Field(None, description="stop, length, error")
    latency_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    temperature: Optional[float] = Field(None, description="AI temperature setting")
    
    class Config:
        json_schema_extra = {
            "example": {
                "model": "gemini-1.5-flash",
                "tokens": 150,
                "finish_reason": "stop",
                "latency_ms": 1234,
                "temperature": 0.7
            }
        }


class MessageAttachment(BaseModel):
    """Message attachment (image, file, document)"""
    type: str = Field(..., description="image, file, document")
    url: str = Field(..., description="Attachment URL")
    filename: str = Field(..., description="Original filename")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    mime_type: Optional[str] = Field(None, description="MIME type")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "image",
                "url": "https://storage.example.com/images/abc123.png",
                "filename": "lab_results.png",
                "size_bytes": 245678,
                "mime_type": "image/png"
            }
        }


class MessageContext(BaseModel):
    """Additional context for the message"""
    patient_id: Optional[str] = Field(None, description="Associated patient ID")
    prediction_type: Optional[str] = Field(None, description="readmission, ed_avoidable, etc.")
    action: Optional[str] = Field(None, description="Action context (e.g., medication_query)")
    additional_data: Optional[Dict[str, Any]] = Field(None, description="Any additional context")
    
    class Config:
        json_schema_extra = {
            "example": {
                "patient_id": "PAT_abc123",
                "prediction_type": "readmission",
                "action": "medication_query"
            }
        }


# ── Request Schemas ───────────────────────────────────────────────────────────

class ChatCreateRequest(BaseModel):
    """Request to create a new chat session"""
    patient_id: Optional[str] = Field(None, description="Associate chat with a specific patient")
    initial_message: Optional[str] = Field(None, description="Optional first message", max_length=10000)
    title: Optional[str] = Field(None, description="Custom title (default: 'New Chat')", max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {
                "patient_id": "PAT_abc123",
                "initial_message": "What are my medication side effects?",
                "title": None
            }
        }


class MessageSendRequest(BaseModel):
    """Request to send a message in a chat"""
    content: str = Field(..., description="Message content", min_length=1, max_length=10000)
    role: MessageRole = Field(MessageRole.USER, description="Message role (usually 'user')")
    attachments: Optional[List[MessageAttachment]] = Field(None, description="Optional attachments")
    context: Optional[MessageContext] = Field(None, description="Optional context")
    
    @validator('content')
    def content_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Content cannot be empty or whitespace only')
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "What are the side effects of my diabetes medication?",
                "role": "user",
                "context": {
                    "patient_id": "PAT_abc123",
                    "action": "medication_query"
                }
            }
        }


class TitleUpdateRequest(BaseModel):
    """Request to update chat title"""
    title: str = Field(..., description="New chat title", min_length=1, max_length=500)
    
    @validator('title')
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Title cannot be empty or whitespace only')
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Diabetes Medication Discussion"
            }
        }


class PinUpdateRequest(BaseModel):
    """Request to pin/unpin a chat"""
    is_pinned: bool = Field(..., description="Pin (true) or unpin (false)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_pinned": True
            }
        }


# ── Response Schemas ──────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    """Response model for a single message"""
    message_id: str
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None
    created_at: datetime
    version: int = 1
    is_current_version: bool = True
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "message_id": "MSG_xyz789",
                "role": "user",
                "content": "What are my medication side effects?",
                "metadata": None,
                "attachments": None,
                "context": {"patient_id": "PAT_abc123"},
                "created_at": "2026-08-20T10:31:00Z",
                "version": 1,
                "is_current_version": True
            }
        }


class ChatSessionResponse(BaseModel):
    """Response model for chat session metadata"""
    session_id: str
    title: str
    is_title_auto_generated: bool
    message_count: int
    is_active: bool
    is_pinned: bool
    patient_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime
    preview: Optional[str] = Field(None, description="Preview of last message")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "session_id": "CHAT_a1b2c3d4e5f6",
                "title": "Medication Side Effects Discussion",
                "is_title_auto_generated": True,
                "message_count": 12,
                "is_active": True,
                "is_pinned": False,
                "patient_id": "PAT_abc123",
                "created_at": "2026-08-20T10:30:00Z",
                "updated_at": "2026-08-20T10:45:00Z",
                "last_message_at": "2026-08-20T10:45:00Z",
                "preview": "What are my medication side effects?..."
            }
        }


class ChatDetailResponse(BaseModel):
    """Response model for chat with messages"""
    session_id: str
    title: str
    is_title_auto_generated: bool
    message_count: int
    is_pinned: bool
    patient_id: Optional[str] = None
    created_at: datetime
    messages: List[MessageResponse]
    
    class Config:
        from_attributes = True


class MessageSendResponse(BaseModel):
    """Response after sending a message (includes AI response)"""
    user_message: MessageResponse
    assistant_response: Optional[MessageResponse] = None
    session_updated_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_message": {
                    "message_id": "MSG_xyz789",
                    "role": "user",
                    "content": "What are my meds?",
                    "created_at": "2026-08-20T10:31:00Z"
                },
                "assistant_response": {
                    "message_id": "MSG_xyz790",
                    "role": "assistant",
                    "content": "Based on your records...",
                    "metadata": {"model": "gemini-1.5-flash", "tokens": 250},
                    "created_at": "2026-08-20T10:31:02Z"
                },
                "session_updated_at": "2026-08-20T10:31:02Z"
            }
        }


class ChatListResponse(BaseModel):
    """Response model for list of chats (paginated)"""
    chats: List[ChatSessionResponse]
    total: int
    limit: int
    offset: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "chats": [
                    {
                        "session_id": "CHAT_a1b2c3d4e5f6",
                        "title": "Medication Discussion",
                        "message_count": 12,
                        "last_message_at": "2026-08-20T10:45:00Z",
                        "preview": "What are my medication side effects?..."
                    }
                ],
                "total": 45,
                "limit": 20,
                "offset": 0
            }
        }


class ChatSearchResult(BaseModel):
    """Single search result"""
    session_id: str
    title: str
    matched_messages: List[Dict[str, Any]]
    relevance_score: Optional[float] = None
    created_at: datetime
    last_message_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "CHAT_a1b2c3d4e5f6",
                "title": "Medication Side Effects Discussion",
                "matched_messages": [
                    {
                        "message_id": "MSG_xyz789",
                        "content_snippet": "...medication side effects...",
                        "created_at": "2026-08-20T10:31:00Z"
                    }
                ],
                "relevance_score": 0.89,
                "created_at": "2026-08-20T10:30:00Z",
                "last_message_at": "2026-08-20T10:45:00Z"
            }
        }


class ChatSearchResponse(BaseModel):
    """Response for chat search"""
    results: List[ChatSearchResult]
    total: int
    query: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "session_id": "CHAT_a1b2c3d4e5f6",
                        "title": "Medication Discussion",
                        "matched_messages": [],
                        "relevance_score": 0.89
                    }
                ],
                "total": 3,
                "query": "medication"
            }
        }


class ChatDeleteResponse(BaseModel):
    """Response after deleting a chat"""
    message: str
    session_id: str
    deleted_at: Optional[datetime] = None
    permanent: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Chat deleted successfully",
                "session_id": "CHAT_a1b2c3d4e5f6",
                "deleted_at": "2026-08-20T10:55:00Z",
                "permanent": False
            }
        }


class TitleUpdateResponse(BaseModel):
    """Response after updating title"""
    session_id: str
    title: str
    is_title_auto_generated: bool
    updated_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "CHAT_a1b2c3d4e5f6",
                "title": "My Custom Title",
                "is_title_auto_generated": False,
                "updated_at": "2026-08-20T10:50:00Z"
            }
        }


class ExportResponse(BaseModel):
    """Response for chat export"""
    session_id: str
    title: str
    format: str
    content: str
    exported_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "CHAT_a1b2c3d4e5f6",
                "title": "Medication Discussion",
                "format": "json",
                "content": "{...}",
                "exported_at": "2026-08-20T11:00:00Z"
            }
        }
