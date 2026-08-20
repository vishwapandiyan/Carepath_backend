from fastapi import APIRouter, Depends

from app.patient.safety import schemas, service
from app.core.security import get_current_patient
from app.db.base import get_db
from app.models.user import User

router = APIRouter(
    prefix="/safety",
    tags=["Patient - Module 2: Safety"],
)


@router.post(
    "/sessions/{session_id}/red-flags",
    response_model=schemas.RedFlagsOut,
    status_code=201,
    summary="Submit red-flag checklist",
    description=(
        "Submit the 10-field red-flag checklist for a session. "
        "Use True/False/null per field. Null fields are treated as unanswered (→ PENDING on evaluate)."
    ),
)
async def submit_red_flags(
    session_id: str,
    payload: schemas.RedFlagsIn,
    current_user: User = Depends(get_current_patient),
) -> schemas.RedFlagsOut:
    return await service.save_red_flags(session_id, payload)


@router.post(
    "/sessions/{session_id}/evaluate",
    response_model=schemas.SafetyResult,
    summary="Run safety evaluation",
    description=(
        "Run the deterministic Safety Rule Engine against submitted red flags. "
        "Result: YES (emergency) | NO (continue to Pathway) | PENDING (more info needed) | ERROR (engine failure). "
        "Every call writes an immutable audit row to safety_assessments."
    ),
)
async def evaluate(
    session_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_patient),
) -> schemas.SafetyResult:
    return await service.run_safety_engine(session_id, db)


@router.get(
    "/sessions/{session_id}/assessment",
    response_model=schemas.SafetyResult,
    summary="Get latest safety assessment",
    description="Return the most recent audit record from safety_assessments for this session.",
)
async def get_assessment(
    session_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_patient),
) -> schemas.SafetyResult:
    return await service.get_latest_assessment(session_id, db)
