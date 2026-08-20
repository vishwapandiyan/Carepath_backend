"""
ORM models — all tables defined in one file for SQLAlchemy / Alembic.

Note: Patient profiles have been merged into PatientEHR model (app.models.ehr).
      Use PatientEHR for all patient-related queries.

Active tables:
  patient_ehr             — Unified patient profiles + comprehensive medical records (see app.models.ehr)
  safety_assessments      — Immutable audit log owned by Safety (Seg 2)
  readmission_predictions — Readmission risk prediction scores owned by Care Manager
  post_discharge_statuses — 4-agent post-discharge monitoring states owned by Care Manager
  chat_sessions           — Chat conversation metadata (ChatGPT-style history)
  chat_messages           — Chat messages with JSONB storage for flexible schema
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Enum as SQLEnum, func, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


# ── User & Authentication ───────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    PATIENT = "PATIENT"
    CARE_MANAGER = "CARE_MANAGER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )


# ── Segment 2: Safety — immutable audit log ───────────────────────────────────

class SafetyAssessment(Base):
    """
    One row per evaluate() call — including PENDING and ERROR.
    Never updated after insert.
    """
    __tablename__ = "safety_assessments"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)   # PENDING|YES|NO|ERROR
    next_action: Mapped[str] = mapped_column(String(50), nullable=False)
    triggered_rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_information: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    red_flags_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Care Manager: Readmission Prediction ──────────────────────────────────────

class ReadmissionPrediction(Base):
    __tablename__ = "readmission_predictions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)   # low | medium | high
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Care Manager: Post Discharge Status ───────────────────────────────────────

class PostDischargeStatus(Base):
    __tablename__ = "post_discharge_statuses"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    patient_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    care_plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    follow_up: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_analyser: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    appointment: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Chat History Feature ──────────────────────────────────────────────────────

class ChatSession(Base):
    """
    Chat Session — stores metadata about conversations (ChatGPT-style)
    """
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    
    # Ownership
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("patient_ehr.patient_id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Metadata
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="New Chat")
    is_title_auto_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """
    Chat Message — stores messages as JSONB for flexibility
    """
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    
    # Association
    session_id: Mapped[str] = mapped_column(String(50), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Message Content (JSONB)
    message_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Denormalized fields
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    content_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Versioning (future feature)
    parent_message_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("chat_messages.message_id", ondelete="SET NULL"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current_version: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # Status
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
