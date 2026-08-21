from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime
from enum import Enum


class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class InsuranceTypeEnum(str, Enum):
    Medicare = "Medicare"
    Medicaid = "Medicaid"
    Private = "Private"
    SelfPay = "Self-pay"
    MedicareAdvantage = "Medicare_Advantage"
    Uninsured = "Uninsured"


class AdmissionTypeEnum(str, Enum):
    elective = "elective"
    emergency = "emergency"
    urgent = "urgent"


class DischargeDestinationEnum(str, Enum):
    home = "home"
    rehab = "rehab"
    nursing_home = "nursing_home"
    other = "other"


class DemographicsSchema(BaseModel):
    name: str
    date_of_birth: date
    age: int = Field(..., ge=0, le=120)
    gender: GenderEnum
    bmi: float = Field(..., ge=10.0, le=80.0)
    insurance_type: InsuranceTypeEnum
    race: Optional[str] = None


class ChronicConditionsSchema(BaseModel):
    diabetes_flag: Optional[int] = Field(0, ge=0, le=1)
    heart_failure_flag: Optional[int] = Field(0, ge=0, le=1)
    cardiac_history_flag: Optional[int] = Field(0, ge=0, le=1)
    copd_asthma_flag: Optional[int] = Field(0, ge=0, le=1)
    ckd_flag: Optional[int] = Field(0, ge=0, le=1)
    cancer_flag: Optional[int] = Field(0, ge=0, le=1)
    dementia_flag: Optional[int] = Field(0, ge=0, le=1)
    hypertension_flag: Optional[int] = Field(0, ge=0, le=1)
    immunocompromised_flag: Optional[int] = Field(0, ge=0, le=1)
    charlson_comorbidity_index: Optional[int] = Field(0, ge=0, le=37)


class VitalSignsSchema(BaseModel):
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = Field(None, ge=70, le=100)
    pain_score_clinical: Optional[float] = Field(None, ge=0, le=10)


class LabValuesSchema(BaseModel):
    hemoglobin: float
    creatinine: float
    glucose: int
    hba1c: Optional[float] = None
    wbc_count: float
    total_bilirubin: Optional[float] = None
    platelet_count: Optional[int] = None
    sodium: Optional[float] = None
    potassium: Optional[float] = None
    troponin: Optional[float] = None
    bnp: Optional[int] = None
    lactate: Optional[float] = None
    inr: Optional[float] = None


class MedicationsSchema(BaseModel):
    active_medication_count: Optional[int] = Field(0, ge=0)
    medication_count_at_discharge: Optional[int] = None
    polypharmacy_flag: Optional[int] = Field(0, ge=0, le=1)
    high_risk_medication_flag: Optional[int] = Field(0, ge=0, le=1)
    on_anticoagulants_flag: Optional[int] = Field(0, ge=0, le=1)
    on_insulin_flag: Optional[int] = Field(0, ge=0, le=1)
    medication_adherence_rate: Optional[float] = Field(None, ge=0, le=1)


class UtilizationHistorySchema(BaseModel):
    previous_admissions_12m: int = Field(..., ge=0)
    previous_er_visits_12m: int = Field(..., ge=0)
    prior_30_day_readmission_flag: Optional[int] = Field(0, ge=0, le=1)
    days_since_last_ed_visit: Optional[int] = None
    ed_visits_90d: Optional[int] = None
    ed_visits_30d: Optional[int] = None
    outpatient_visits_365d: Optional[int] = None
    days_since_last_pcp_visit: Optional[int] = None
    missed_appointments_6m: Optional[int] = None


class AdmissionDataSchema(BaseModel):
    admission_date: Optional[date] = None
    discharge_date: Optional[date] = None
    admission_type: Optional[AdmissionTypeEnum] = None
    length_of_stay_days: Optional[int] = None
    icu_stay_flag: Optional[int] = Field(0, ge=0, le=1)
    discharge_destination: Optional[DischargeDestinationEnum] = None
    follow_up_within_7_days_flag: Optional[int] = Field(0, ge=0, le=1)
    follow_up_appointment_date: Optional[date] = None
    total_charges_index_stay: Optional[float] = None


class PatientEHRCreate(BaseModel):
    """Schema for creating a new patient EHR record"""
    demographics: DemographicsSchema
    chronic_conditions: ChronicConditionsSchema
    vital_signs_current: Optional[VitalSignsSchema] = None
    lab_values: LabValuesSchema
    medications: MedicationsSchema
    utilization_history: UtilizationHistorySchema
    admission_data: Optional[AdmissionDataSchema] = None
    clinical_notes: Optional[str] = None
    
    # Additional administrative fields
    contact_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    insurance_id: Optional[str] = None


class PatientEHRUpdate(BaseModel):
    """Schema for updating patient EHR record - all fields optional"""
    demographics: Optional[DemographicsSchema] = None
    chronic_conditions: Optional[ChronicConditionsSchema] = None
    vital_signs_current: Optional[VitalSignsSchema] = None
    lab_values: Optional[LabValuesSchema] = None
    medications: Optional[MedicationsSchema] = None
    utilization_history: Optional[UtilizationHistorySchema] = None
    admission_data: Optional[AdmissionDataSchema] = None
    clinical_notes: Optional[str] = None
    
    # Additional administrative fields
    contact_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    insurance_id: Optional[str] = None
    is_active: Optional[int] = None


class PatientEHRResponse(BaseModel):
    """Schema for EHR response"""
    id: int
    patient_id: str
    mrn: str
    
    # Demographics
    name: str
    date_of_birth: Optional[date] = None
    age: Optional[int] = 0
    gender: Optional[str] = "other"
    bmi: Optional[float] = 25.0
    insurance_type: Optional[str] = "Private"
    race: Optional[str] = None
    
    # Chronic Conditions
    diabetes_flag: Optional[int] = 0
    heart_failure_flag: Optional[int] = 0
    cardiac_history_flag: Optional[int] = 0
    copd_asthma_flag: Optional[int] = 0
    ckd_flag: Optional[int] = 0
    cancer_flag: Optional[int] = 0
    dementia_flag: Optional[int] = 0
    hypertension_flag: Optional[int] = 0
    immunocompromised_flag: Optional[int] = 0
    charlson_comorbidity_index: Optional[int] = 0
    
    # Vital Signs
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = None
    pain_score_clinical: Optional[float] = None
    
    # Lab Values
    hemoglobin: Optional[float] = None
    creatinine: Optional[float] = None
    glucose: Optional[int] = None
    hba1c: Optional[float] = None
    wbc_count: Optional[float] = None
    total_bilirubin: Optional[float] = None
    platelet_count: Optional[int] = None
    sodium: Optional[float] = None
    potassium: Optional[float] = None
    troponin: Optional[float] = None
    bnp: Optional[int] = None
    lactate: Optional[float] = None
    inr: Optional[float] = None
    
    # Medications
    active_medication_count: Optional[int] = 0
    medication_count_at_discharge: Optional[int] = None
    polypharmacy_flag: Optional[int] = 0
    high_risk_medication_flag: Optional[int] = 0
    on_anticoagulants_flag: Optional[int] = 0
    on_insulin_flag: Optional[int] = 0
    medication_adherence_rate: Optional[float] = None
    
    # Utilization History
    previous_admissions_12m: Optional[int] = 0
    previous_er_visits_12m: Optional[int] = 0
    prior_30_day_readmission_flag: Optional[int] = 0
    days_since_last_ed_visit: Optional[int] = None
    ed_visits_90d: Optional[int] = None
    ed_visits_30d: Optional[int] = None
    outpatient_visits_365d: Optional[int] = None
    days_since_last_pcp_visit: Optional[int] = None
    missed_appointments_6m: Optional[int] = None
    
    # Admission Data
    admission_date: Optional[date] = None
    discharge_date: Optional[date] = None
    admission_type: Optional[str] = None
    length_of_stay_days: Optional[int] = None
    icu_stay_flag: Optional[int] = 0
    discharge_destination: Optional[str] = None
    follow_up_within_7_days_flag: Optional[int] = 0
    follow_up_appointment_date: Optional[date] = None
    total_charges_index_stay: Optional[float] = None
    
    # Clinical Notes
    clinical_notes: Optional[str] = None
    
    # Additional Administrative Fields
    contact_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    insurance_id: Optional[str] = None
    is_active: Optional[int] = 1
    deleted_at: Optional[datetime] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class PatientEHRListResponse(BaseModel):
    """Simplified schema for listing patients"""
    id: int
    patient_id: str
    mrn: str
    name: str
    date_of_birth: Optional[date] = None
    age: Optional[int] = 0
    gender: Optional[str] = "other"
    contact_number: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[int] = 1
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
