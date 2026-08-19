from pydantic import BaseModel, field_validator, Field
from app.models.user import UserRole


class LoginRequest(BaseModel):
    """Login request schema"""
    username: str
    password: str


class Token(BaseModel):
    """JWT token response schema"""
    access_token: str
    token_type: str
    role: UserRole
    redirect_to: str


class CareManagerSignupRequest(BaseModel):
    """Care Manager signup request schema"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        """Trim and validate username"""
        v = v.strip()
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        return v
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        """Validate that passwords match"""
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


class PatientSignupRequest(BaseModel):
    """Patient signup request schema"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    mrn: str = Field(..., min_length=1)
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        """Trim and validate username"""
        v = v.strip()
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        return v
    
    @field_validator('mrn')
    @classmethod
    def validate_mrn(cls, v):
        """Trim and validate MRN"""
        v = v.strip()
        if not v:
            raise ValueError('MRN is required')
        return v
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        """Validate that passwords match"""
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v
