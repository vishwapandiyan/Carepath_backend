from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.db.models import User, UserRole
from app.models.ehr import PatientEHR
from app.db.session import get_db
from app.schemas import (
    CareManagerSignupRequest,
    LoginRequest,
    PatientSignupRequest,
    Token,
    UserResponse,
)
from app.services.ehr_service import ehr_service

router = APIRouter()


@router.post("/signup/care-manager", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup_care_manager(
    request: CareManagerSignupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new Care Manager.
    
    - **username**: Unique username (min 3 characters)
    - **password**: Password (min 8 characters)
    - **confirm_password**: Must match password
    """
    username = request.username.strip()
    
    # Check if username already exists
    stmt = select(User).where(User.username == username)
    res = await db.execute(stmt)
    existing_user = res.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Hash password
    password_hash = get_password_hash(request.password)
    
    # Create Care Manager account
    new_user = User(
        username=username,
        password_hash=password_hash,
        role=UserRole.CARE_MANAGER,
        patient_id=None
    )
    
    db.add(new_user)
    await db.commit()

    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.username, "role": new_user.role.value},
        expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=new_user.role,
        redirect_to="/care-manager"
    )


@router.post("/signup/patient", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup_patient(
    request: PatientSignupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new Patient.
    
    - **username**: Unique username (min 3 characters)
    - **password**: Password (min 8 characters)
    - **confirm_password**: Must match password
    - **mrn**: Medical Record Number
    """
    username = request.username.strip()
    mrn = request.mrn.strip()
    
    # Check if username already exists
    stmt = select(User).where(User.username == username)
    res = await db.execute(stmt)
    existing_user = res.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Check if MRN is already registered
    stmt_patient = select(PatientEHR).where(PatientEHR.mrn == mrn)
    res_patient = await db.execute(stmt_patient)
    existing_patient = res_patient.scalar_one_or_none()
    
    if existing_patient:
        patient = existing_patient
    else:
        patient_data = await ehr_service.get_patient_data(db, mrn)
        patient_name = f"{patient_data.get('first_name', '')} {patient_data.get('last_name', '')}".strip() or "Patient"
        patient = Patient(
            mrn=mrn,
            name=patient_name,
            full_name=patient_name,
            dob=patient_data.get("date_of_birth")
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)
    
    # Hash password
    password_hash = get_password_hash(request.password)
    
    # Create Patient user account
    patient_id_val = str(getattr(patient, "patient_id", getattr(patient, "id", None)))
    new_user = User(
        username=username,
        password_hash=password_hash,
        role=UserRole.PATIENT,
        patient_id=patient_id_val
    )
    
    db.add(new_user)
    await db.commit()

    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.username, "role": new_user.role.value},
        expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=new_user.role,
        redirect_to="/patient"
    )


@router.post("/login", response_model=Token)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT token.
    Backend determines user role and provides appropriate redirect.
    """
    stmt = select(User).where(User.username == request.username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    redirect_to = "/care-manager" if user.role == UserRole.CARE_MANAGER else "/patient"
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        redirect_to=redirect_to
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.
    """
    return current_user


@router.post("/logout")
async def logout(response: Response):
    """
    Logout endpoint.
    Clears authentication cookies if present.
    """
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}

