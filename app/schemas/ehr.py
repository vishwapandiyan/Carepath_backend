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
    first_name: str
    last_name: str
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


class PatientEHRResponse(BaseModel):
    """Schema for EHR response"""
    id: int
    mrn: str
    
    # Demographics
    first_name: str
    last_name: str
    date_of_birth: date
    age: int
    gender: str
    bmi: float
    insurance_type: str
    race: Optional[str]
    
    # Chronic Conditions
    diabetes_flag: int
    heart_failure_flag: int
    cardiac_history_flag: int
    copd_asthma_flag: int
    ckd_flag: int
    cancer_flag: int
    dementia_flag: int
    hypertension_flag: int
    immunocompromised_flag: int
    charlson_comorbidity_index: int
    
    # Vital Signs
    systolic_bp: Optional[int]
    diastolic_bp: Optional[int]
    heart_rate: Optional[int]
    respiratory_rate: Optional[int]
    temperature: Optional[float]
    spo2: Optional[int]
    pain_score_clinical: Optional[float]
    
    # Lab Values
    hemoglobin: float
    creatinine: float
    glucose: int
    hba1c: Optional[float]
    wbc_count: float
    total_bilirubin: Optional[float]
    platelet_count: Optional[int]
    sodium: Optional[float]
    potassium: Optional[float]
    troponin: Optional[float]
    bnp: Optional[int]
    lactate: Optional[float]
    inr: Optional[float]
    
    # Medications
    active_medication_count: int
    medication_count_at_discharge: Optional[int]
    polypharmacy_flag: int
    high_risk_medication_flag: int
    on_anticoagulants_flag: int
    on_insulin_flag: int
    medication_adherence_rate: Optional[float]
    
    # Utilization History
    previous_admissions_12m: int
    previous_er_visits_12m: int
    prior_30_day_readmission_flag: int
    days_since_last_ed_visit: Optional[int]
    ed_visits_90d: Optional[int]
    ed_visits_30d: Optional[int]
    outpatient_visits_365d: Optional[int]
    days_since_last_pcp_visit: Optional[int]
    missed_appointments_6m: Optional[int]
    
    # Admission Data
    admission_date: Optional[date]
    discharge_date: Optional[date]
    admission_type: Optional[str]
    length_of_stay_days: Optional[int]
    icu_stay_flag: int
    discharge_destination: Optional[str]
    follow_up_within_7_days_flag: int
    follow_up_appointment_date: Optional[date]
    total_charges_index_stay: Optional[float]
    
    # Clinical Notes
    clinical_notes: Optional[str]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PatientEHRListResponse(BaseModel):
    """Simplified schema for listing patients"""
    id: int
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: date
    age: int
    gender: str
    created_at: datetime
    
    class Config:
        from_attributes = True
