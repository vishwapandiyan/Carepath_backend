from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    mrn: str | None = Field(
        default=None,
        description="Optional custom MRN (e.g., MRN001 or MRN040001). If omitted, auto-generated sequentially.",
    )
    name: str | None = Field(default=None, description="Full patient name")
    dob: str | None = Field(default=None, description="Date of birth (YYYY-MM-DD)")
    gender: str | None = Field(default=None, description="Gender (e.g., Male, Female, Other)")
    contact_number: str | None = Field(default=None, description="Phone number")
    email: str | None = Field(default=None, description="Email address")
    address: str | None = Field(default=None, description="Residential address")
    insurance_id: str | None = Field(default=None, description="Insurance policy or member ID")
    admission_date: str | None = Field(default=None, description="Admission date/time")
    discharge_date: str | None = Field(default=None, description="Discharge date/time")


class PatientUpdate(BaseModel):
    name: str | None = None
    dob: str | None = None
    gender: str | None = None
    contact_number: str | None = None
    email: str | None = None
    address: str | None = None
    insurance_id: str | None = None
    admission_date: str | None = None
    discharge_date: str | None = None


class PatientOut(BaseModel):
    id: str
    mrn: str
    name: str | None = None
    dob: str | None = None
    gender: str | None = None
    contact_number: str | None = None
    email: str | None = None
    address: str | None = None
    insurance_id: str | None = None
    admission_date: str | None = None
    discharge_date: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PatientListOut(BaseModel):
    total: int
    skip: int
    limit: int
    patients: list[PatientOut]
