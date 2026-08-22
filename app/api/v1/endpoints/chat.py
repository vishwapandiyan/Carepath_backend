"""
Chat History API Endpoints
FastAPI routes for chat functionality
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.db.models import User, ChatSession, ChatMessage
from app.schemas.chat import (
    # Requests
    ChatCreateRequest,
    MessageSendRequest,
    TitleUpdateRequest,
    PinUpdateRequest,
    # Responses
    ChatSessionResponse,
    ChatDetailResponse,
    MessageSendResponse,
    ChatListResponse,
    ChatSearchResponse,
    ChatDeleteResponse,
    TitleUpdateResponse,
    ExportResponse,
    MessageResponse,
    # Enums
    ExportFormat,
    SortOrder,
)
from app.services.chat_service import chat_service
from app.services.chat_export_service import chat_export_service
from app.services.title_generator import title_generator

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helper Functions ──────────────────────────────────────────────────────────

async def verify_chat_ownership(
    session_id: str,
    user: User,
    db: AsyncSession
) -> ChatSession:
    """
    Verify that the current user owns the chat session
    
    Raises:
        HTTPException: 404 if chat not found, 403 if unauthorized
    """
    chat = await chat_service.get_chat_by_session_id(db, session_id, user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or you don't have access"
        )
    return chat


def format_chat_response(chat: ChatSession, preview: Optional[str] = None) -> ChatSessionResponse:
    """Format ChatSession to ChatSessionResponse"""
    return ChatSessionResponse(
        session_id=chat.session_id,
        title=chat.title,
        is_title_auto_generated=chat.is_title_auto_generated,
        message_count=chat.message_count,
        is_active=chat.is_active,
        is_pinned=chat.is_pinned,
        patient_id=chat.patient_id,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        last_message_at=chat.last_message_at,
        preview=preview
    )


def format_message_response(message: ChatMessage) -> MessageResponse:
    """Format ChatMessage to MessageResponse"""
    return MessageResponse(
        message_id=message.message_id,
        role=message.role,
        content=message.message_data.get("content", ""),
        metadata=message.message_data.get("metadata"),
        attachments=message.message_data.get("attachments"),
        context=message.message_data.get("context"),
        created_at=message.created_at,
        version=message.version,
        is_current_version=message.is_current_version
    )


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.post("/new", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    request: ChatCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new chat session
    
    - **patient_id**: Optional - associate chat with a patient
    - **initial_message**: Optional - send first message immediately
    - **title**: Optional - custom title (default: "New Chat")
    """
    try:
        # Determine patient_id (patients' chats auto-associate)
        patient_id = request.patient_id
        if current_user.role.value == "PATIENT" and current_user.patient_id:
            patient_id = current_user.patient_id
        
        # Create chat session
        title = request.title or "New Chat"
        chat = await chat_service.create_chat_session(
            db=db,
            user_id=current_user.id,
            patient_id=patient_id,
            title=title
        )
        
        # If initial message provided, create it
        if request.initial_message:
            await chat_service.create_message(
                db=db,
                session_id=chat.session_id,
                role="user",
                content=request.initial_message,
                context={"patient_id": patient_id} if patient_id else None
            )
            
            # Trigger title generation asynchronously (don't wait)
            # In production, this should be a background task
            try:
                generated_title = await title_generator.generate_title(request.initial_message)
                await chat_service.update_chat_title(
                    db=db,
                    session_id=chat.session_id,
                    user_id=current_user.id,
                    title=generated_title,
                    is_auto_generated=True
                )
                chat.title = generated_title
            except Exception as e:
                logger.warning(f"Title generation failed: {e}")
        
        logger.info(f"Created chat {chat.session_id} for user {current_user.id}")
        return format_chat_response(chat)
        
    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chat"
        )


@router.post("/{session_id}/message", response_model=MessageSendResponse)
async def send_message(
    session_id: str,
    request: MessageSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a message in a chat session
    
    This endpoint:
    1. Stores the message (user or assistant)
    2. If user message: generates AI response (TODO: integrate with chatbot)
    3. If assistant message (role_override): just stores it (for intake bot integration)
    4. Auto-generates title if first user message
    
    Returns user message and optional assistant response
    """
    try:
        # Verify ownership
        chat = await verify_chat_ownership(session_id, current_user, db)
        
        # Prepare context
        context = request.context.dict() if request.context else {}
        if not context.get("patient_id") and chat.patient_id:
            context["patient_id"] = chat.patient_id
        
        # Check if this is a role override (assistant message being saved directly)
        role_override = context.get("role_override")
        message_role = role_override if role_override in ["user", "assistant", "system"] else request.role.value
        
        # Create the message
        saved_message = await chat_service.create_message(
            db=db,
            session_id=session_id,
            role=message_role,
            content=request.content,
            attachments=[att.dict() for att in request.attachments] if request.attachments else None,
            context=context
        )
        
        assistant_message = None
        
        # Only generate AI response if this is a user message (not a role override)
        if message_role == "user" and not role_override:
            # Generate AI response
            # TODO: Integrate with existing chatbot service
            # For now, return a placeholder response
            assistant_content = "I'm here to help! This is a placeholder response. (Full chatbot integration coming soon)"
            
            assistant_message = await chat_service.create_message(
                db=db,
                session_id=session_id,
                role="assistant",
                content=assistant_content,
                metadata={
                    "model": "gemini-1.5-flash",
                    "timestamp": datetime.utcnow().isoformat()
                },
                context=context
            )
            
            # Auto-generate title if this is the first user message
            if chat.message_count <= 2 and chat.is_title_auto_generated and chat.title == "New Chat":
                try:
                    generated_title = await title_generator.generate_title_with_context(
                        first_message=request.content,
                        patient_id=chat.patient_id,
                        context=context
                    )
                    await chat_service.update_chat_title(
                        db=db,
                        session_id=session_id,
                        user_id=current_user.id,
                        title=generated_title,
                        is_auto_generated=True
                    )
                except Exception as e:
                    logger.warning(f"Auto title generation failed: {e}")
        
        # Refresh chat to get updated timestamp
        await db.refresh(chat)
        
        logger.info(f"Message sent in chat {session_id} by user {current_user.id} (role: {message_role})")
        
        return MessageSendResponse(
            user_message=format_message_response(saved_message),
            assistant_response=format_message_response(assistant_message) if assistant_message else None,
            session_updated_at=chat.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message"
        )


@router.get("/list", response_model=ChatListResponse)
async def list_chats(
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
    search: Optional[str] = Query(None, description="Search in titles"),
    is_pinned: Optional[bool] = Query(None, description="Filter pinned chats"),
    sort_by: str = Query("last_message_at", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List user's chat sessions (paginated)
    
    Supports:
    - Pagination (limit, offset)
    - Filtering (patient_id, is_pinned)
    - Search (in titles)
    - Sorting (by created_at, last_message_at, title)
    """
    try:
        chats, total = await chat_service.get_user_chats(
            db=db,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            patient_id=patient_id,
            search=search,
            is_pinned=is_pinned,
            sort_by=sort_by,
            sort_order=sort_order.value
        )
        
        # Format responses with previews
        chat_responses = []
        for chat in chats:
            # Get last message for preview
            messages = await chat_service.get_chat_messages(db, chat.session_id, limit=1, order="desc")
            preview = messages[0].content_preview if messages else None
            chat_responses.append(format_chat_response(chat, preview=preview))
        
        return ChatListResponse(
            chats=chat_responses,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error listing chats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list chats"
        )


@router.get("/search", response_model=ChatSearchResponse)
async def search_chats(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Search chats by title and message content
    
    Uses PostgreSQL full-text search for relevant results
    """
    try:
        results, total = await chat_service.search_chats(
            db=db,
            user_id=current_user.id,
            query=q,
            limit=limit,
            offset=offset
        )
        
        return ChatSearchResponse(
            results=results,
            total=total,
            query=q
        )
        
    except Exception as e:
        logger.error(f"Error searching chats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search chats"
        )


@router.get("/{session_id}", response_model=ChatDetailResponse)
async def get_chat_details(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get chat session details (metadata only, no messages)
    Use GET /{session_id}/messages to get message history
    """
    chat = await verify_chat_ownership(session_id, current_user, db)
    
    return ChatDetailResponse(
        session_id=chat.session_id,
        title=chat.title,
        is_title_auto_generated=chat.is_title_auto_generated,
        message_count=chat.message_count,
        is_pinned=chat.is_pinned,
        patient_id=chat.patient_id,
        created_at=chat.created_at,
        messages=[]  # Empty, use /messages endpoint for full history
    )


@router.get("/{session_id}/messages", response_model=ChatDetailResponse)
async def get_chat_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=500, description="Max messages to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    order: str = Query("asc", description="Sort order: asc or desc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get chat message history (paginated)
    
    - **limit**: Max messages to return (default: 50, max: 500)
    - **offset**: Pagination offset
    - **order**: Message order (asc for chronological, desc for reverse)
    """
    try:
        chat = await verify_chat_ownership(session_id, current_user, db)
        
        messages = await chat_service.get_chat_messages(
            db=db,
            session_id=session_id,
            limit=limit,
            offset=offset,
            order=order
        )
        
        message_responses = [format_message_response(msg) for msg in messages]
        
        return ChatDetailResponse(
            session_id=chat.session_id,
            title=chat.title,
            is_title_auto_generated=chat.is_title_auto_generated,
            message_count=chat.message_count,
            is_pinned=chat.is_pinned,
            patient_id=chat.patient_id,
            created_at=chat.created_at,
            messages=message_responses
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get messages"
        )


@router.patch("/{session_id}/title", response_model=TitleUpdateResponse)
async def update_chat_title(
    session_id: str,
    request: TitleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update chat title (marks as user-edited)
    """
    try:
        chat = await chat_service.update_chat_title(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            title=request.title,
            is_auto_generated=False
        )
        
        return TitleUpdateResponse(
            session_id=chat.session_id,
            title=chat.title,
            is_title_auto_generated=chat.is_title_auto_generated,
            updated_at=chat.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating title: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update title"
        )


@router.patch("/{session_id}/pin", response_model=ChatSessionResponse)
async def pin_unpin_chat(
    session_id: str,
    request: PinUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Pin or unpin a chat
    """
    try:
        chat = await chat_service.pin_chat(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            is_pinned=request.is_pinned
        )
        
        return format_chat_response(chat)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pinning chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update pin status"
        )


@router.delete("/{session_id}", response_model=ChatDeleteResponse)
async def delete_chat(
    session_id: str,
    permanent: bool = Query(False, description="Permanent delete (true) or soft delete (false)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a chat session
    
    - **permanent=false**: Soft delete (can be recovered)
    - **permanent=true**: Hard delete (cannot be recovered)
    """
    try:
        session_id_result, deleted_at = await chat_service.delete_chat(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            permanent=permanent
        )
        
        return ChatDeleteResponse(
            message="Chat deleted successfully",
            session_id=session_id_result,
            deleted_at=deleted_at,
            permanent=permanent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat"
        )


@router.get("/{session_id}/export")
async def export_chat(
    session_id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Export chat conversation
    
    Supported formats:
    - **json**: Complete data with metadata
    - **txt**: Plain text conversation
    - **markdown**: Formatted markdown with timestamps
    """
    try:
        chat = await verify_chat_ownership(session_id, current_user, db)
        
        # Get all messages
        messages = await chat_service.get_chat_messages(
            db=db,
            session_id=session_id,
            limit=1000,  # Get all messages
            order="asc"
        )
        
        # Export in requested format
        content = chat_export_service.export(chat, messages, format.value)
        
        # Set appropriate content type and filename
        if format == ExportFormat.JSON:
            media_type = "application/json"
            filename = f"{session_id}_export.json"
        elif format == ExportFormat.TEXT:
            media_type = "text/plain"
            filename = f"{session_id}_export.txt"
        else:  # markdown
            media_type = "text/markdown"
            filename = f"{session_id}_export.md"
        
        # Return as downloadable file
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export chat"
        )
