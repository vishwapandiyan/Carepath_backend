"""
Chat Service Layer
Business logic for chat history feature
"""
import hashlib
import random
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.db.models import ChatSession, ChatMessage, User
from app.schemas.chat import (
    ChatCreateRequest,
    MessageSendRequest,
    ChatSessionResponse,
    MessageResponse,
)


class ChatService:
    """Service class for chat operations"""
    
    # ── Helper Methods ────────────────────────────────────────────────────────
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate unique chat session ID (CHAT_xxxxxxxxxxxx)"""
        random_str = f"{random.random()}{datetime.utcnow().isoformat()}"
        hash_str = hashlib.md5(random_str.encode()).hexdigest()[:12]
        return f"CHAT_{hash_str}"
    
    @staticmethod
    def generate_message_id() -> str:
        """Generate unique message ID (MSG_xxxxxxxxxxxx)"""
        random_str = f"{random.random()}{datetime.utcnow().isoformat()}"
        hash_str = hashlib.md5(random_str.encode()).hexdigest()[:12]
        return f"MSG_{hash_str}"
    
    @staticmethod
    def extract_content_preview(content: str, max_length: int = 500) -> str:
        """Extract preview from content (first N characters)"""
        if not content:
            return ""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."
    
    @staticmethod
    def create_message_data(
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create properly formatted JSONB message data"""
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
    
    # ── Chat Session Operations ───────────────────────────────────────────────
    
    async def create_chat_session(
        self,
        db: AsyncSession,
        user_id: int,
        patient_id: Optional[str] = None,
        title: str = "New Chat"
    ) -> ChatSession:
        """
        Create a new chat session
        
        Args:
            db: Database session
            user_id: Owner user ID
            patient_id: Optional associated patient ID
            title: Chat title
        
        Returns:
            ChatSession: Created chat session
        """
        session_id = self.generate_session_id()
        
        chat_session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            patient_id=patient_id,
            title=title,
            is_title_auto_generated=(title == "New Chat"),
            message_count=0,
            is_active=True,
            is_pinned=False,
        )
        
        db.add(chat_session)
        await db.commit()
        await db.refresh(chat_session)
        
        return chat_session
    
    async def get_chat_by_session_id(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: int
    ) -> Optional[ChatSession]:
        """
        Get chat session by session_id (with ownership check)
        
        Args:
            db: Database session
            session_id: Chat session ID
            user_id: User ID for ownership verification
        
        Returns:
            ChatSession or None
        """
        stmt = select(ChatSession).where(
            and_(
                ChatSession.session_id == session_id,
                ChatSession.user_id == user_id,
                ChatSession.is_active == True
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_user_chats(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        patient_id: Optional[str] = None,
        search: Optional[str] = None,
        is_pinned: Optional[bool] = None,
        sort_by: str = "last_message_at",
        sort_order: str = "desc"
    ) -> Tuple[List[ChatSession], int]:
        """
        Get paginated list of user's chats with optional filters
        
        Args:
            db: Database session
            user_id: User ID
            limit: Page size (max 100)
            offset: Offset for pagination
            patient_id: Filter by patient
            search: Search in titles
            is_pinned: Filter pinned chats
            sort_by: Sort field (created_at, last_message_at, title)
            sort_order: asc or desc
        
        Returns:
            Tuple of (list of ChatSession, total count)
        """
        # Build base query
        conditions = [
            ChatSession.user_id == user_id,
            ChatSession.is_active == True
        ]
        
        # Add filters
        if patient_id:
            conditions.append(ChatSession.patient_id == patient_id)
        
        if is_pinned is not None:
            conditions.append(ChatSession.is_pinned == is_pinned)
        
        if search:
            # Search in title using ILIKE (case-insensitive)
            conditions.append(ChatSession.title.ilike(f"%{search}%"))
        
        # Count query
        count_stmt = select(func.count()).select_from(ChatSession).where(and_(*conditions))
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()
        
        # Data query with sorting
        sort_column = getattr(ChatSession, sort_by, ChatSession.last_message_at)
        if sort_order == "desc":
            sort_column = sort_column.desc()
        else:
            sort_column = sort_column.asc()
        
        stmt = (
            select(ChatSession)
            .where(and_(*conditions))
            .order_by(sort_column)
            .limit(min(limit, 100))
            .offset(offset)
        )
        
        result = await db.execute(stmt)
        chats = result.scalars().all()
        
        return list(chats), total
    
    async def update_chat_title(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: int,
        title: str,
        is_auto_generated: bool = False
    ) -> ChatSession:
        """
        Update chat title
        
        Args:
            db: Database session
            session_id: Chat session ID
            user_id: User ID for ownership verification
            title: New title
            is_auto_generated: Whether title is AI-generated
        
        Returns:
            Updated ChatSession
        
        Raises:
            HTTPException: If chat not found or unauthorized
        """
        chat = await self.get_chat_by_session_id(db, session_id, user_id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        
        chat.title = title
        chat.is_title_auto_generated = is_auto_generated
        chat.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(chat)
        
        return chat
    
    async def pin_chat(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: int,
        is_pinned: bool
    ) -> ChatSession:
        """
        Pin or unpin a chat
        
        Args:
            db: Database session
            session_id: Chat session ID
            user_id: User ID for ownership verification
            is_pinned: Pin status
        
        Returns:
            Updated ChatSession
        """
        chat = await self.get_chat_by_session_id(db, session_id, user_id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        
        chat.is_pinned = is_pinned
        chat.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(chat)
        
        return chat
    
    async def delete_chat(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: int,
        permanent: bool = False
    ) -> Tuple[str, Optional[datetime]]:
        """
        Delete chat (soft or hard delete)
        
        Args:
            db: Database session
            session_id: Chat session ID
            user_id: User ID for ownership verification
            permanent: If True, hard delete; if False, soft delete
        
        Returns:
            Tuple of (session_id, deleted_at)
        """
        chat = await self.get_chat_by_session_id(db, session_id, user_id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        
        if permanent:
            # Hard delete (cascade will delete messages)
            await db.delete(chat)
            await db.commit()
            return session_id, None
        else:
            # Soft delete
            deleted_at = datetime.utcnow()
            chat.is_active = False
            chat.deleted_at = deleted_at
            await db.commit()
            return session_id, deleted_at
    
    # ── Message Operations ────────────────────────────────────────────────────
    
    async def create_message(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ChatMessage:
        """
        Create a new message in a chat session
        
        Args:
            db: Database session
            session_id: Chat session ID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
            attachments: Optional attachments
            context: Optional context
        
        Returns:
            ChatMessage: Created message
        """
        message_id = self.generate_message_id()
        message_data = self.create_message_data(role, content, metadata, attachments, context)
        content_preview = self.extract_content_preview(content)
        
        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            message_data=message_data,
            role=role,
            content_preview=content_preview,
            version=1,
            is_current_version=True,
            is_deleted=False,
        )
        
        db.add(message)
        await db.commit()
        await db.refresh(message)
        
        return message
    
    async def get_chat_messages(
        self,
        db: AsyncSession,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
        order: str = "asc"
    ) -> List[ChatMessage]:
        """
        Get messages for a chat session
        
        Args:
            db: Database session
            session_id: Chat session ID
            limit: Page size (max 500)
            offset: Offset for pagination
            order: Sort order (asc or desc)
        
        Returns:
            List of ChatMessage
        """
        sort_column = ChatMessage.created_at.asc() if order == "asc" else ChatMessage.created_at.desc()
        
        stmt = (
            select(ChatMessage)
            .where(
                and_(
                    ChatMessage.session_id == session_id,
                    ChatMessage.is_deleted == False,
                    ChatMessage.is_current_version == True
                )
            )
            .order_by(sort_column)
            .limit(min(limit, 500))
            .offset(offset)
        )
        
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        return list(messages)
    
    async def get_message_by_id(
        self,
        db: AsyncSession,
        message_id: str
    ) -> Optional[ChatMessage]:
        """Get message by message_id"""
        stmt = select(ChatMessage).where(ChatMessage.message_id == message_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    # ── Search Operations ─────────────────────────────────────────────────────
    
    async def search_chats(
        self,
        db: AsyncSession,
        user_id: int,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Search chats using full-text search
        
        Args:
            db: Database session
            user_id: User ID
            query: Search query
            limit: Page size
            offset: Offset
        
        Returns:
            Tuple of (search results, total count)
        """
        # Search in chat titles
        search_pattern = f"%{query}%"
        
        # Count query
        count_stmt = (
            select(func.count())
            .select_from(ChatSession)
            .where(
                and_(
                    ChatSession.user_id == user_id,
                    ChatSession.is_active == True,
                    ChatSession.title.ilike(search_pattern)
                )
            )
        )
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()
        
        # Data query
        stmt = (
            select(ChatSession)
            .where(
                and_(
                    ChatSession.user_id == user_id,
                    ChatSession.is_active == True,
                    ChatSession.title.ilike(search_pattern)
                )
            )
            .order_by(ChatSession.last_message_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(stmt)
        chats = result.scalars().all()
        
        # Format results
        search_results = []
        for chat in chats:
            # Get matched messages (search in content_preview)
            msg_stmt = (
                select(ChatMessage)
                .where(
                    and_(
                        ChatMessage.session_id == chat.session_id,
                        ChatMessage.is_deleted == False,
                        ChatMessage.content_preview.ilike(search_pattern)
                    )
                )
                .limit(3)
            )
            msg_result = await db.execute(msg_stmt)
            matched_messages = msg_result.scalars().all()
            
            search_results.append({
                "session_id": chat.session_id,
                "title": chat.title,
                "matched_messages": [
                    {
                        "message_id": msg.message_id,
                        "content_snippet": msg.content_preview[:200],
                        "created_at": msg.created_at
                    }
                    for msg in matched_messages
                ],
                "relevance_score": None,  # Can be enhanced with PostgreSQL ts_rank
                "created_at": chat.created_at,
                "last_message_at": chat.last_message_at
            })
        
        return search_results, total


# Create singleton instance
chat_service = ChatService()
