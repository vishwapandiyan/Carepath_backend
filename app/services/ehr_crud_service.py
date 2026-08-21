"""
EHR CRUD Service
Handles business logic for patient EHR records using AsyncSession.
Auto-triggers ML predictions (readmission) when patient EHR is created.
"""
import random
import string
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ehr import PatientEHR
from app.schemas.ehr import PatientEHRCreate, PatientEHRUpdate
from app.schemas.ml_predictions import MLPredictionCreate
from app.services.readmission_prediction_service import readmission_prediction_service
from app.services.ml_predictions_service import ml_predictions_service

logger = logging.getLogger(__name__)


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
    async def generate_patient_id(db: AsyncSession) -> str:
        """
        Generate a unique patient_id.
        Format: PAT_ followed by 8 uppercase hex characters
        """
        while True:
            hex_part = ''.join(random.choices(string.hexdigits.upper(), k=8))
            patient_id = f"PAT_{hex_part}"
            stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                return patient_id
    
    @staticmethod
    async def create_patient_ehr(db: AsyncSession, ehr_data: PatientEHRCreate) -> PatientEHR:
        """Create a new patient EHR record with auto-generated MRN and patient_id"""
        mrn = await EHRCRUDService.generate_mrn(db)
        patient_id = await EHRCRUDService.generate_patient_id(db)
        
        patient_ehr = PatientEHR(
            patient_id=patient_id,
            mrn=mrn,
            name=ehr_data.demographics.name,
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
            
            clinical_notes=ehr_data.clinical_notes,
            
            # Additional administrative fields
            contact_number=ehr_data.contact_number,
            email=ehr_data.email,
            address=ehr_data.address,
            insurance_id=ehr_data.insurance_id,
            is_active=1  # New records are active by default
        )
        
        db.add(patient_ehr)
        await db.commit()
        await db.refresh(patient_ehr)
        
        # Auto-trigger readmission prediction after patient creation
        await EHRCRUDService._auto_trigger_readmission_prediction(db, patient_ehr)
        
        return patient_ehr
    
    @staticmethod
    async def _auto_trigger_readmission_prediction(db: AsyncSession, patient_ehr: PatientEHR) -> None:
        """
        Automatically trigger readmission prediction after patient EHR is created.
        Stores the prediction in ml_predictions table.
        """
        try:
            logger.info(f"Auto-triggering readmission prediction for patient {patient_ehr.patient_id}")
            
            # Make readmission prediction
            prediction_result = readmission_prediction_service.predict(patient_ehr)
            
            # Store prediction in database
            prediction_data = MLPredictionCreate(
                patient_id=patient_ehr.patient_id,
                mrn=patient_ehr.mrn,
                model_type=prediction_result["model_type"],
                model_version=prediction_result["model_version"],
                risk_score=prediction_result["risk_score"],
                prediction_result=prediction_result["prediction_details"],
                created_by="system_auto"  # Automatic prediction
            )
            
            await ml_predictions_service.create_prediction(db, prediction_data)
            
            logger.info(
                f"✓ Readmission prediction stored for patient {patient_ehr.patient_id}: "
                f"risk_score={prediction_result['risk_score']:.4f}"
            )
            
        except Exception as e:
            # Log error but don't fail patient creation
            logger.error(f"Failed to auto-trigger readmission prediction for patient {patient_ehr.patient_id}: {str(e)}")
            logger.error("Patient creation succeeded, but prediction failed")
    
    @staticmethod
    async def get_patient_by_patient_id(db: AsyncSession, patient_id: str) -> Optional[PatientEHR]:
        """Get patient EHR by patient_id (PAT_XXXXXXXX format)"""
        stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()
    
    @staticmethod
    async def get_patient_by_id(db: AsyncSession, patient_id: str | int, include_inactive: bool = False) -> Optional[PatientEHR]:
        """Get patient EHR by ID (int), patient_id (PAT_XXXXXXXX), or MRN"""
        from sqlalchemy import or_
        target_str = str(patient_id)
        conds = [
            PatientEHR.patient_id == target_str,
            PatientEHR.mrn == target_str,
        ]
        if target_str.isdigit():
            conds.append(PatientEHR.id == int(target_str))
        stmt = select(PatientEHR).where(or_(*conds))
        if not include_inactive:
            stmt = stmt.where(or_(PatientEHR.is_active != 0, PatientEHR.is_active.is_(None)))
        res = await db.execute(stmt)
        return res.scalars().first()
    
    @staticmethod
    async def get_patient_by_mrn(db: AsyncSession, mrn: str) -> Optional[PatientEHR]:
        """Get patient EHR by MRN"""
        from sqlalchemy import or_
        stmt = select(PatientEHR).where(
            (PatientEHR.mrn == mrn) & or_(PatientEHR.is_active != 0, PatientEHR.is_active.is_(None))
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()
    
    @staticmethod
    async def get_all_patients(db: AsyncSession, skip: int = 0, limit: int = 100, include_inactive: bool = False) -> List[PatientEHR]:
        """Get all patient EHR records with pagination, filtering out soft-deleted records by default"""
        from sqlalchemy import or_
        stmt = select(PatientEHR)
        if not include_inactive:
            stmt = stmt.where(or_(PatientEHR.is_active != 0, PatientEHR.is_active.is_(None)))
        stmt = stmt.offset(skip).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())
    
    @staticmethod
    async def update_patient_ehr(db: AsyncSession, patient_id: int, ehr_update: PatientEHRUpdate) -> Optional[PatientEHR]:
        """Update patient EHR record"""
        patient = await EHRCRUDService.get_patient_by_id(db, patient_id)
        if not patient:
            return None
        
        if ehr_update.demographics:
            patient.name = ehr_update.demographics.name
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
        
        # Update additional administrative fields
        if ehr_update.contact_number is not None:
            patient.contact_number = ehr_update.contact_number
        if ehr_update.email is not None:
            patient.email = ehr_update.email
        if ehr_update.address is not None:
            patient.address = ehr_update.address
        if ehr_update.insurance_id is not None:
            patient.insurance_id = ehr_update.insurance_id
        if ehr_update.is_active is not None:
            patient.is_active = ehr_update.is_active
        
        patient.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(patient)
        return patient
    
    @staticmethod
    async def delete_patient_ehr(db: AsyncSession, patient_id: int) -> bool:
        """Soft delete patient EHR record (set is_active=0)"""
        patient = await EHRCRUDService.get_patient_by_id(db, patient_id)
        if not patient:
            return False
        
        # Soft delete: set is_active to 0 instead of hard delete
        patient.is_active = 0
        patient.updated_at = datetime.utcnow()
        await db.commit()
        return True


ehr_crud_service = EHRCRUDService()
