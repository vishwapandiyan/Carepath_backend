from fastapi import APIRouter, Depends

from app.patient.intake import schemas, service
from app.core.security import get_current_patient
from app.models.user import User

router = APIRouter(
    prefix="/intake",
    tags=["Patient - Module 1: Intake"],
)


@router.post(
    "/sessions",
    response_model=schemas.SessionOut,
    status_code=201,
    summary="Create intake session",
    description="Start a new intake session for a patient. Returns the session ID and the first question to ask.",
)
async def create_session(
    payload: schemas.SessionCreate,
    current_user: User = Depends(get_current_patient),
) -> schemas.SessionOut:
    return await service.create_intake_session(payload)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=schemas.MessageResponse,
    summary="Send patient message",
    description=(
        "Submit the patient's free-text message. "
        "The LLM extracts structured fields; the question policy returns the next question. "
        "When all required fields are collected, status transitions to COMPLETE."
    ),
)
async def send_message(
    session_id: str,
    payload: schemas.MessageIn,
    current_user: User = Depends(get_current_patient),
) -> schemas.MessageResponse:
    return await service.handle_message(session_id, payload)


@router.get(
    "/sessions/{session_id}",
    response_model=schemas.SessionOut,
    summary="Get intake session",
    description="Return the current state of an intake session including all extracted features.",
)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_patient),
) -> schemas.SessionOut:
    return await service.get_intake_session(session_id)
