# Schemas module
from app.schemas.auth import (
    LoginRequest,
    Token,
    CareManagerSignupRequest,
    PatientSignupRequest
)
from app.schemas.user import UserResponse
from app.schemas.patient import PatientResponse
from app.schemas.ehr import (
    PatientEHRCreate,
    PatientEHRUpdate,
    PatientEHRResponse,
    PatientEHRListResponse
)
from app.schemas.chat import (
    # Request schemas
    ChatCreateRequest,
    MessageSendRequest,
    TitleUpdateRequest,
    PinUpdateRequest,
    # Response schemas
    ChatSessionResponse,
    MessageResponse,
    ChatDetailResponse,
    MessageSendResponse,
    ChatListResponse,
    ChatSearchResponse,
    ChatSearchResult,
    ChatDeleteResponse,
    TitleUpdateResponse,
    ExportResponse,
    # Enums
    MessageRole,
    ExportFormat,
    SortOrder,
    # Supporting schemas
    MessageMetadata,
    MessageAttachment,
    MessageContext,
)

__all__ = [
    # Auth
    "LoginRequest",
    "Token",
    "CareManagerSignupRequest",
    "PatientSignupRequest",
    # User
    "UserResponse",
    "PatientResponse",
    # EHR
    "PatientEHRCreate",
    "PatientEHRUpdate",
    "PatientEHRResponse",
    "PatientEHRListResponse",
    # Chat - Requests
    "ChatCreateRequest",
    "MessageSendRequest",
    "TitleUpdateRequest",
    "PinUpdateRequest",
    # Chat - Responses
    "ChatSessionResponse",
    "MessageResponse",
    "ChatDetailResponse",
    "MessageSendResponse",
    "ChatListResponse",
    "ChatSearchResponse",
    "ChatSearchResult",
    "ChatDeleteResponse",
    "TitleUpdateResponse",
    "ExportResponse",
    # Chat - Enums
    "MessageRole",
    "ExportFormat",
    "SortOrder",
    # Chat - Supporting
    "MessageMetadata",
    "MessageAttachment",
    "MessageContext",
]
