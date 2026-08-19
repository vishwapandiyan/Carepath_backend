"""
EHR CRUD Service
Handles business logic for patient EHR records using AsyncSession.
"""
import random
import string
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ehr import PatientEHR
from app.schemas.ehr import PatientEHRCreate, PatientEHRUpdate


class EHRCRUDService:
    """Service class for EHR CRUD operations"""
    
    @staticmethod
    async def generate_mrn(db: AsyncSession) -> str:
        """
        Generate a unique MRN (Medical Record Number).
        Format: MRN followed by 8 digits
        """
        while True:
            number = ''.join(random.choices(string.digits, k=8))
            mrn = f"MRN{number}"
            stmt = select(PatientEHR).where(PatientEHR.mrn == mrn)
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                return mrn
    
    @staticmethod
    async def create_patient_ehr(db: AsyncSession, ehr_data: PatientEHRCreate) -> PatientEHR:
        """Create a new patient EHR record with auto-generated MRN"""
        mrn = await EHRCRUDService.generate_mrn(db)
        
        patient_ehr = PatientEHR(
            mrn=mrn,
            first_name=ehr_data.demographics.first_name,
            last_name=ehr_data.demographics.last_name,
            date_of_birth=ehr_data.demographics.date_of_birth,
            age=ehr_data.demographics.age,
            gender=ehr_data.demographics.gender.value,
            bmi=ehr_data.demographics.bmi,
            insurance_type=ehr_data.demographics.insurance_type.value,
            race=ehr_data.demographics.race,
            
            diabetes_flag=ehr_data.chronic_conditions.diabetes_flag,
            heart_failure_flag=ehr_data.chronic_conditions.heart_failure_flag,
            cardiac_history_flag=ehr_data.chronic_conditions.cardiac_history_flag,
            copd_asthma_flag=ehr_data.chronic_conditions.copd_asthma_flag,
            ckd_flag=ehr_data.chronic_conditions.ckd_flag,
            cancer_flag=ehr_data.chronic_conditions.cancer_flag,
            dementia_flag=ehr_data.chronic_conditions.dementia_flag,
            hypertension_flag=ehr_data.chronic_conditions.hypertension_flag,
            immunocompromised_flag=ehr_data.chronic_conditions.immunocompromised_flag,
            charlson_comorbidity_index=ehr_data.chronic_conditions.charlson_comorbidity_index,
            
            systolic_bp=ehr_data.vital_signs_current.systolic_bp if ehr_data.vital_signs_current else None,
            diastolic_bp=ehr_data.vital_signs_current.diastolic_bp if ehr_data.vital_signs_current else None,
            heart_rate=ehr_data.vital_signs_current.heart_rate if ehr_data.vital_signs_current else None,
            respiratory_rate=ehr_data.vital_signs_current.respiratory_rate if ehr_data.vital_signs_current else None,
            temperature=ehr_data.vital_signs_current.temperature if ehr_data.vital_signs_current else None,
            spo2=ehr_data.vital_signs_current.spo2 if ehr_data.vital_signs_current else None,
            pain_score_clinical=ehr_data.vital_signs_current.pain_score_clinical if ehr_data.vital_signs_current else None,
            
            hemoglobin=ehr_data.lab_values.hemoglobin,
            creatinine=ehr_data.lab_values.creatinine,
            glucose=ehr_data.lab_values.glucose,
            hba1c=ehr_data.lab_values.hba1c,
            wbc_count=ehr_data.lab_values.wbc_count,
            total_bilirubin=ehr_data.lab_values.total_bilirubin,
            platelet_count=ehr_data.lab_values.platelet_count,
            sodium=ehr_data.lab_values.sodium,
            potassium=ehr_data.lab_values.potassium,
            troponin=ehr_data.lab_values.troponin,
            bnp=ehr_data.lab_values.bnp,
            lactate=ehr_data.lab_values.lactate,
            inr=ehr_data.lab_values.inr,
            
            active_medication_count=ehr_data.medications.active_medication_count,
            medication_count_at_discharge=ehr_data.medications.medication_count_at_discharge,
            polypharmacy_flag=ehr_data.medications.polypharmacy_flag,
            high_risk_medication_flag=ehr_data.medications.high_risk_medication_flag,
            on_anticoagulants_flag=ehr_data.medications.on_anticoagulants_flag,
            on_insulin_flag=ehr_data.medications.on_insulin_flag,
            medication_adherence_rate=ehr_data.medications.medication_adherence_rate,
            
            previous_admissions_12m=ehr_data.utilization_history.previous_admissions_12m,
            previous_er_visits_12m=ehr_data.utilization_history.previous_er_visits_12m,
            prior_30_day_readmission_flag=ehr_data.utilization_history.prior_30_day_readmission_flag,
            days_since_last_ed_visit=ehr_data.utilization_history.days_since_last_ed_visit,
            ed_visits_90d=ehr_data.utilization_history.ed_visits_90d,
            ed_visits_30d=ehr_data.utilization_history.ed_visits_30d,
            outpatient_visits_365d=ehr_data.utilization_history.outpatient_visits_365d,
            days_since_last_pcp_visit=ehr_data.utilization_history.days_since_last_pcp_visit,
            missed_appointments_6m=ehr_data.utilization_history.missed_appointments_6m,
            
            admission_date=ehr_data.admission_data.admission_date if ehr_data.admission_data else None,
            discharge_date=ehr_data.admission_data.discharge_date if ehr_data.admission_data else None,
            admission_type=ehr_data.admission_data.admission_type.value if ehr_data.admission_data and ehr_data.admission_data.admission_type else None,
            length_of_stay_days=ehr_data.admission_data.length_of_stay_days if ehr_data.admission_data else None,
            icu_stay_flag=ehr_data.admission_data.icu_stay_flag if ehr_data.admission_data else 0,
            discharge_destination=ehr_data.admission_data.discharge_destination.value if ehr_data.admission_data and ehr_data.admission_data.discharge_destination else None,
            follow_up_within_7_days_flag=ehr_data.admission_data.follow_up_within_7_days_flag if ehr_data.admission_data else 0,
            follow_up_appointment_date=ehr_data.admission_data.follow_up_appointment_date if ehr_data.admission_data else None,
            total_charges_index_stay=ehr_data.admission_data.total_charges_index_stay if ehr_data.admission_data else None,
            
            clinical_notes=ehr_data.clinical_notes
        )
        
        db.add(patient_ehr)
        await db.commit()
        await db.refresh(patient_ehr)
        return patient_ehr
    
    @staticmethod
    async def get_patient_by_id(db: AsyncSession, patient_id: int) -> Optional[PatientEHR]:
        """Get patient EHR by ID"""
        stmt = select(PatientEHR).where(PatientEHR.id == patient_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()
    
    @staticmethod
    async def get_patient_by_mrn(db: AsyncSession, mrn: str) -> Optional[PatientEHR]:
        """Get patient EHR by MRN"""
        stmt = select(PatientEHR).where(PatientEHR.mrn == mrn)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()
    
    @staticmethod
    async def get_all_patients(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[PatientEHR]:
        """Get all patient EHR records with pagination"""
        stmt = select(PatientEHR).offset(skip).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())
    
    @staticmethod
    async def update_patient_ehr(db: AsyncSession, patient_id: int, ehr_update: PatientEHRUpdate) -> Optional[PatientEHR]:
        """Update patient EHR record"""
        patient = await EHRCRUDService.get_patient_by_id(db, patient_id)
        if not patient:
            return None
        
        if ehr_update.demographics:
            patient.first_name = ehr_update.demographics.first_name
            patient.last_name = ehr_update.demographics.last_name
            patient.date_of_birth = ehr_update.demographics.date_of_birth
            patient.age = ehr_update.demographics.age
            patient.gender = ehr_update.demographics.gender.value
            patient.bmi = ehr_update.demographics.bmi
            patient.insurance_type = ehr_update.demographics.insurance_type.value
            patient.race = ehr_update.demographics.race
        
        if ehr_update.chronic_conditions:
            patient.diabetes_flag = ehr_update.chronic_conditions.diabetes_flag
            patient.heart_failure_flag = ehr_update.chronic_conditions.heart_failure_flag
            patient.cardiac_history_flag = ehr_update.chronic_conditions.cardiac_history_flag
            patient.copd_asthma_flag = ehr_update.chronic_conditions.copd_asthma_flag
            patient.ckd_flag = ehr_update.chronic_conditions.ckd_flag
            patient.cancer_flag = ehr_update.chronic_conditions.cancer_flag
            patient.dementia_flag = ehr_update.chronic_conditions.dementia_flag
            patient.hypertension_flag = ehr_update.chronic_conditions.hypertension_flag
            patient.immunocompromised_flag = ehr_update.chronic_conditions.immunocompromised_flag
            patient.charlson_comorbidity_index = ehr_update.chronic_conditions.charlson_comorbidity_index
        
        if ehr_update.vital_signs_current:
            patient.systolic_bp = ehr_update.vital_signs_current.systolic_bp
            patient.diastolic_bp = ehr_update.vital_signs_current.diastolic_bp
            patient.heart_rate = ehr_update.vital_signs_current.heart_rate
            patient.respiratory_rate = ehr_update.vital_signs_current.respiratory_rate
            patient.temperature = ehr_update.vital_signs_current.temperature
            patient.spo2 = ehr_update.vital_signs_current.spo2
            patient.pain_score_clinical = ehr_update.vital_signs_current.pain_score_clinical
        
        if ehr_update.lab_values:
            patient.hemoglobin = ehr_update.lab_values.hemoglobin
            patient.creatinine = ehr_update.lab_values.creatinine
            patient.glucose = ehr_update.lab_values.glucose
            patient.hba1c = ehr_update.lab_values.hba1c
            patient.wbc_count = ehr_update.lab_values.wbc_count
            patient.total_bilirubin = ehr_update.lab_values.total_bilirubin
            patient.platelet_count = ehr_update.lab_values.platelet_count
            patient.sodium = ehr_update.lab_values.sodium
            patient.potassium = ehr_update.lab_values.potassium
            patient.troponin = ehr_update.lab_values.troponin
            patient.bnp = ehr_update.lab_values.bnp
            patient.lactate = ehr_update.lab_values.lactate
            patient.inr = ehr_update.lab_values.inr
        
        if ehr_update.medications:
            patient.active_medication_count = ehr_update.medications.active_medication_count
            patient.medication_count_at_discharge = ehr_update.medications.medication_count_at_discharge
            patient.polypharmacy_flag = ehr_update.medications.polypharmacy_flag
            patient.high_risk_medication_flag = ehr_update.medications.high_risk_medication_flag
            patient.on_anticoagulants_flag = ehr_update.medications.on_anticoagulants_flag
            patient.on_insulin_flag = ehr_update.medications.on_insulin_flag
            patient.medication_adherence_rate = ehr_update.medications.medication_adherence_rate
        
        if ehr_update.utilization_history:
            patient.previous_admissions_12m = ehr_update.utilization_history.previous_admissions_12m
            patient.previous_er_visits_12m = ehr_update.utilization_history.previous_er_visits_12m
            patient.prior_30_day_readmission_flag = ehr_update.utilization_history.prior_30_day_readmission_flag
            patient.days_since_last_ed_visit = ehr_update.utilization_history.days_since_last_ed_visit
            patient.ed_visits_90d = ehr_update.utilization_history.ed_visits_90d
            patient.ed_visits_30d = ehr_update.utilization_history.ed_visits_30d
            patient.outpatient_visits_365d = ehr_update.utilization_history.outpatient_visits_365d
            patient.days_since_last_pcp_visit = ehr_update.utilization_history.days_since_last_pcp_visit
            patient.missed_appointments_6m = ehr_update.utilization_history.missed_appointments_6m
        
        if ehr_update.admission_data:
            patient.admission_date = ehr_update.admission_data.admission_date
            patient.discharge_date = ehr_update.admission_data.discharge_date
            patient.admission_type = ehr_update.admission_data.admission_type.value if ehr_update.admission_data.admission_type else None
            patient.length_of_stay_days = ehr_update.admission_data.length_of_stay_days
            patient.icu_stay_flag = ehr_update.admission_data.icu_stay_flag
            patient.discharge_destination = ehr_update.admission_data.discharge_destination.value if ehr_update.admission_data.discharge_destination else None
            patient.follow_up_within_7_days_flag = ehr_update.admission_data.follow_up_within_7_days_flag
            patient.follow_up_appointment_date = ehr_update.admission_data.follow_up_appointment_date
            patient.total_charges_index_stay = ehr_update.admission_data.total_charges_index_stay
        
        if ehr_update.clinical_notes is not None:
            patient.clinical_notes = ehr_update.clinical_notes
        
        patient.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(patient)
        return patient
    
    @staticmethod
    async def delete_patient_ehr(db: AsyncSession, patient_id: int) -> bool:
        """Delete patient EHR record"""
        patient = await EHRCRUDService.get_patient_by_id(db, patient_id)
        if not patient:
            return False
        
        await db.delete(patient)
        await db.commit()
        return True


ehr_crud_service = EHRCRUDService()
