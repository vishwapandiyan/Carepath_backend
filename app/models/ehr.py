from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Date, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base


class PatientEHR(Base):
    """
    Patient Electronic Health Record model (Unified).
    Stores comprehensive patient medical information + administrative profile data.
    MRN and patient_id are auto-generated on creation.
    """
    __tablename__ = "patient_ehr"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, unique=True, index=True, nullable=False)  # PAT_XXXXXXXX format
    mrn = Column(String, unique=True, index=True, nullable=False)  # Auto-generated MRNXXXXXXXX
    
    # Demographics
    name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)  # male, female, other
    bmi = Column(Float, nullable=False)
    insurance_type = Column(String, nullable=False)  # Medicare, Medicaid, Private, etc.
    race = Column(String, nullable=True)
    
    # Chronic Conditions (stored as flags)
    diabetes_flag = Column(Integer, default=0)
    heart_failure_flag = Column(Integer, default=0)
    cardiac_history_flag = Column(Integer, default=0)
    copd_asthma_flag = Column(Integer, default=0)
    ckd_flag = Column(Integer, default=0)
    cancer_flag = Column(Integer, default=0)
    dementia_flag = Column(Integer, default=0)
    hypertension_flag = Column(Integer, default=0)
    immunocompromised_flag = Column(Integer, default=0)
    charlson_comorbidity_index = Column(Integer, default=0)
    
    # Vital Signs (Current)
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    spo2 = Column(Integer, nullable=True)
    pain_score_clinical = Column(Float, nullable=True)
    
    # Lab Values
    hemoglobin = Column(Float, nullable=False)
    creatinine = Column(Float, nullable=False)
    glucose = Column(Integer, nullable=False)
    hba1c = Column(Float, nullable=True)
    wbc_count = Column(Float, nullable=False)
    total_bilirubin = Column(Float, nullable=True)
    platelet_count = Column(Integer, nullable=True)
    sodium = Column(Float, nullable=True)
    potassium = Column(Float, nullable=True)
    troponin = Column(Float, nullable=True)
    bnp = Column(Integer, nullable=True)
    lactate = Column(Float, nullable=True)
    inr = Column(Float, nullable=True)
    
    # Medications
    active_medication_count = Column(Integer, default=0)
    medication_count_at_discharge = Column(Integer, nullable=True)
    polypharmacy_flag = Column(Integer, default=0)
    high_risk_medication_flag = Column(Integer, default=0)
    on_anticoagulants_flag = Column(Integer, default=0)
    on_insulin_flag = Column(Integer, default=0)
    medication_adherence_rate = Column(Float, nullable=True)
    
    # Utilization History
    previous_admissions_12m = Column(Integer, nullable=False)
    previous_er_visits_12m = Column(Integer, nullable=False)
    prior_30_day_readmission_flag = Column(Integer, default=0)
    days_since_last_ed_visit = Column(Integer, nullable=True)
    ed_visits_90d = Column(Integer, nullable=True)
    ed_visits_30d = Column(Integer, nullable=True)
    outpatient_visits_365d = Column(Integer, nullable=True)
    days_since_last_pcp_visit = Column(Integer, nullable=True)
    missed_appointments_6m = Column(Integer, nullable=True)
    
    # Admission Data
    admission_date = Column(Date, nullable=True)
    discharge_date = Column(Date, nullable=True)
    admission_type = Column(String, nullable=True)  # elective, emergency, urgent
    length_of_stay_days = Column(Integer, nullable=True)
    icu_stay_flag = Column(Integer, default=0)
    discharge_destination = Column(String, nullable=True)  # home, rehab, nursing_home, other
    follow_up_within_7_days_flag = Column(Integer, default=0)
    follow_up_appointment_date = Column(Date, nullable=True)
    total_charges_index_stay = Column(Float, nullable=True)
    
    # Clinical Notes
    clinical_notes = Column(Text, nullable=True)
    
    # Additional Administrative Fields (from Care Manager module)
    contact_number = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    insurance_id = Column(String, nullable=True)
    is_active = Column(Integer, default=1)  # 1=active, 0=inactive (soft delete)
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<PatientEHR(patient_id='{self.patient_id}', mrn='{self.mrn}', name='{self.name}')>"
