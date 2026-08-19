"""
ORM models — all tables defined in one file for SQLAlchemy / Alembic.

Active tables:
  patients                — Patient profiles with patient_id primary key and MRN
  safety_assessments      — Immutable audit log owned by Safety (Seg 2)
  readmission_predictions — Readmission risk prediction scores owned by Care Manager
  post_discharge_statuses — 4-agent post-discharge monitoring states owned by Care Manager
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Enum as SQLEnum, func
from sqlalchemy.orm import Mapped, mapped_column

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


# ── Patient Profile ───────────────────────────────────────────────────────────


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: f"PAT_{uuid.uuid4().hex[:8].upper()}"
    )
    id: Mapped[str | None] = mapped_column(String, nullable=True)
    mrn: Mapped[str | None] = mapped_column(
        String(50), index=True, nullable=True
    )  # e.g., MRN00001, MRN040001
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dob: Mapped[str | None] = mapped_column(String(10), nullable=True)         # YYYY-MM-DD
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    insurance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admission_date: Mapped[str | None] = mapped_column(String(25), nullable=True)  # YYYY-MM-DD or ISO timestamp
    discharge_date: Mapped[str | None] = mapped_column(String(25), nullable=True)  # YYYY-MM-DD or ISO timestamp
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
