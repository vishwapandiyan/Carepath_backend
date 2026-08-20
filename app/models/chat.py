"""
Chat History Models
SQLAlchemy models for chat sessions and messages with JSONB storage
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.db.base import Base


class ChatSession(Base):
    """
    Chat Session model - stores metadata about conversations
    Similar to ChatGPT conversation sessions
    """
    __tablename__ = "chat_sessions"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(50), unique=True, index=True, nullable=False)  # CHAT_xxxxxxxxxxxx
    
    # Ownership & Association
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(50), ForeignKey("patient_ehr.patient_id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Chat Metadata
    title = Column(String(500), nullable=False, default="New Chat")
    is_title_auto_generated = Column(Boolean, default=True, nullable=False)
    
    # Message Counts
    message_count = Column(Integer, default=0, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_pinned = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ChatSession(session_id='{self.session_id}', title='{self.title}', message_count={self.message_count})>"
    
    @property
    def is_deleted(self):
        """Check if chat is soft-deleted"""
        return self.deleted_at is not None
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "is_title_auto_generated": self.is_title_auto_generated,
            "message_count": self.message_count,
            "is_active": self.is_active,
            "is_pinned": self.is_pinned,
            "patient_id": self.patient_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }


class ChatMessage(Base):
    """
    Chat Message model - stores individual messages as JSONB
    Flexible schema allows for attachments, metadata, and context
    """
    __tablename__ = "chat_messages"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(50), unique=True, index=True, nullable=False)  # MSG_xxxxxxxxxxxx
    
    # Association
    session_id = Column(String(50), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Message Content (JSONB for flexibility)
    message_data = Column(JSONB, nullable=False)
    """
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
    """
    
    # Denormalized fields for quick queries (extracted from JSONB)
    role = Column(String(20), nullable=False, index=True)  # user, assistant, system
    content_preview = Column(Text, nullable=True)  # First 500 chars for search/preview
    
    # Versioning (for edit/regenerate feature - future)
    parent_message_id = Column(String(50), ForeignKey("chat_messages.message_id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    is_current_version = Column(Boolean, default=True, nullable=False, index=True)
    
    # Status
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    
    def __repr__(self):
        return f"<ChatMessage(message_id='{self.message_id}', role='{self.role}', session_id='{self.session_id}')>"
    
    @property
    def content(self):
        """Extract content from JSONB data"""
        return self.message_data.get("content", "") if self.message_data else ""
    
    @property
    def metadata(self):
        """Extract metadata from JSONB data"""
        return self.message_data.get("metadata", {}) if self.message_data else {}
    
    @property
    def attachments(self):
        """Extract attachments from JSONB data"""
        return self.message_data.get("attachments", []) if self.message_data else []
    
    @property
    def context(self):
        """Extract context from JSONB data"""
        return self.message_data.get("context", {}) if self.message_data else {}
    
    def to_dict(self, include_full_data=True):
        """Convert to dictionary for API responses"""
        base_dict = {
            "message_id": self.message_id,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "version": self.version,
            "is_current_version": self.is_current_version,
        }
        
        if include_full_data:
            # Include full JSONB data
            base_dict.update({
                "content": self.content,
                "metadata": self.metadata,
                "attachments": self.attachments,
                "context": self.context,
            })
        else:
            # Only include preview
            base_dict["content_preview"] = self.content_preview
        
        return base_dict
    
    @staticmethod
    def create_message_data(role: str, content: str, metadata: dict = None, attachments: list = None, context: dict = None):
        """
        Helper to create properly formatted JSONB message data
        
        Args:
            role: "user", "assistant", or "system"
            content: Message text
            metadata: Optional metadata (model, tokens, etc.)
            attachments: Optional list of attachments
            context: Optional context (patient_id, action, etc.)
        
        Returns:
            dict: Properly formatted message_data for JSONB storage
        """
        message_data = {
            "role": role,
            "content": content,
        }
        
        if metadata:
            message_data["metadata"] = metadata
        
        if attachments:
            message_data["attachments"] = attachments
        
        if context:
            message_data["context"] = context
        
        return message_data
    
    @staticmethod
    def extract_content_preview(content: str, max_length: int = 500) -> str:
        """
        Extract preview from content (first N characters)
        
        Args:
            content: Full message content
            max_length: Maximum length of preview
        
        Returns:
            str: Truncated preview
        """
        if not content:
            return ""
        
        if len(content) <= max_length:
            return content
        
        return content[:max_length] + "..."
