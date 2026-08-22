"""
Populate clinical_notes for all patients based on their EHR data.
This will provide meaningful context for AI-generated care plans.
"""

import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Database connection
DATABASE_URL = "postgresql+asyncpg://vishwa:@localhost:5432/carepath_db"


def generate_clinical_notes(patient_data: dict) -> str:
    """Generate realistic clinical notes based on patient EHR data."""
    
    notes = []
    
    # Basic demographics and admission info
    notes.append(f"Patient: {patient_data['name']}, {patient_data['age']}yo {patient_data['gender']}")
    
    if patient_data['admission_date']:
        notes.append(f"Admitted: {patient_data['admission_date']} ({patient_data['admission_type']} admission)")
    
    if patient_data['discharge_date']:
        notes.append(f"Discharged: {patient_data['discharge_date']}")
    
    if patient_data['length_of_stay_days']:
        notes.append(f"LOS: {patient_data['length_of_stay_days']} days")
    
    # Primary conditions/diagnoses
    conditions = []
    if patient_data['diabetes_flag']:
        hba1c = patient_data.get('hba1c')
        glucose = patient_data.get('glucose')
        conditions.append(f"Type 2 Diabetes Mellitus (HbA1c: {hba1c}%, Glucose: {glucose}mg/dL)" if hba1c else "Type 2 Diabetes Mellitus")
    
    if patient_data['heart_failure_flag']:
        bnp = patient_data.get('bnp')
        conditions.append(f"Congestive Heart Failure (BNP: {bnp}pg/mL)" if bnp else "Congestive Heart Failure (CHF)")
    
    if patient_data['hypertension_flag']:
        sbp = patient_data.get('systolic_bp')
        dbp = patient_data.get('diastolic_bp')
        conditions.append(f"Hypertension (BP: {sbp}/{dbp}mmHg)" if sbp else "Hypertension")
    
    if patient_data['copd_asthma_flag']:
        spo2 = patient_data.get('spo2')
        conditions.append(f"COPD/Asthma (SpO2: {spo2}%)" if spo2 else "COPD/Asthma")
    
    if patient_data['ckd_flag']:
        creat = patient_data.get('creatinine')
        conditions.append(f"Chronic Kidney Disease (Creatinine: {creat}mg/dL)" if creat else "Chronic Kidney Disease (CKD)")
    
    if patient_data['cancer_flag']:
        conditions.append("Cancer (active)")
    
    if patient_data['cardiac_history_flag']:
        troponin = patient_data.get('troponin')
        if troponin and troponin > 0.04:
            conditions.append(f"Cardiac history - Elevated troponin ({troponin}ng/mL)")
        else:
            conditions.append("Cardiac history (MI/CAD)")
    
    if patient_data['dementia_flag']:
        conditions.append("Dementia")
    
    if conditions:
        notes.append("\nDIAGNOSES:")
        for idx, cond in enumerate(conditions, 1):
            notes.append(f"  {idx}. {cond}")
    
    # Comorbidity score
    cci = patient_data.get('charlson_comorbidity_index', 0)
    if cci > 0:
        notes.append(f"\nCharlson Comorbidity Index: {cci}")
    
    # Vital signs and labs
    vitals = []
    if patient_data.get('systolic_bp') and patient_data.get('diastolic_bp'):
        vitals.append(f"BP: {patient_data['systolic_bp']}/{patient_data['diastolic_bp']}mmHg")
    if patient_data.get('heart_rate'):
        vitals.append(f"HR: {patient_data['heart_rate']}bpm")
    if patient_data.get('respiratory_rate'):
        vitals.append(f"RR: {patient_data['respiratory_rate']}/min")
    if patient_data.get('temperature'):
        vitals.append(f"Temp: {patient_data['temperature']}°F")
    if patient_data.get('spo2'):
        vitals.append(f"SpO2: {patient_data['spo2']}%")
    
    if vitals:
        notes.append(f"\nVITALS: {', '.join(vitals)}")
    
    # Key lab values
    labs = []
    if patient_data.get('hemoglobin'):
        labs.append(f"Hgb: {patient_data['hemoglobin']}g/dL")
    if patient_data.get('creatinine'):
        labs.append(f"Cr: {patient_data['creatinine']}mg/dL")
    if patient_data.get('glucose'):
        labs.append(f"Glucose: {patient_data['glucose']}mg/dL")
    if patient_data.get('hba1c'):
        labs.append(f"HbA1c: {patient_data['hba1c']}%")
    if patient_data.get('sodium'):
        labs.append(f"Na: {patient_data['sodium']}mEq/L")
    if patient_data.get('potassium'):
        labs.append(f"K: {patient_data['potassium']}mEq/L")
    
    if labs:
        notes.append(f"\nLABS: {', '.join(labs)}")
    
    # Medications
    med_count = patient_data.get('medication_count_at_discharge') or 0
    if med_count > 0:
        notes.append(f"\nMEDICATIONS: {med_count} medications at discharge")
        
        if patient_data.get('polypharmacy_flag'):
            notes.append("  ⚠️ POLYPHARMACY - Patient on ≥5 medications")
        
        if patient_data.get('on_anticoagulants_flag'):
            if patient_data.get('inr'):
                notes.append(f"  • Anticoagulation therapy (INR: {patient_data['inr']})")
            else:
                notes.append("  • Anticoagulation therapy - Monitor INR closely")
        
        if patient_data.get('on_insulin_flag'):
            notes.append("  • Insulin therapy - Blood glucose monitoring required")
        
        if patient_data.get('high_risk_medication_flag'):
            notes.append("  ⚠️ HIGH-RISK MEDICATIONS - Close monitoring needed")
        
        adherence = patient_data.get('medication_adherence_rate')
        if adherence and adherence < 0.8:
            notes.append(f"  ⚠️ Poor med adherence ({int(adherence*100)}%) - Increased monitoring")
    
    # Hospital utilization history
    prev_admits = patient_data.get('previous_admissions_12m', 0)
    prev_er = patient_data.get('previous_er_visits_12m', 0)
    
    if prev_admits > 0 or prev_er > 0:
        notes.append(f"\nUTILIZATION (past 12mo): {prev_admits} admissions, {prev_er} ED visits")
        
        if patient_data.get('prior_30_day_readmission_flag'):
            notes.append("  ⚠️ READMISSION within 30 days of prior discharge - HIGH RISK")
    
    # ICU stay
    if patient_data.get('icu_stay_flag'):
        notes.append("\n⚠️ ICU stay during this admission - Complex case")
    
    # Discharge planning
    dest = patient_data.get('discharge_destination')
    if dest:
        notes.append(f"\nDISCHARGE TO: {dest.upper()}")
    
    follow_up = patient_data.get('follow_up_within_7_days_flag')
    follow_up_date = patient_data.get('follow_up_appointment_date')
    
    if follow_up:
        if follow_up_date:
            notes.append(f"Follow-up scheduled: {follow_up_date}")
        else:
            notes.append("Follow-up within 7 days recommended")
    
    # Risk flags and recommendations
    notes.append("\nCLINICAL RECOMMENDATIONS:")
    
    if patient_data.get('diabetes_flag'):
        notes.append("  • Monitor blood glucose 2-3x daily")
        hba1c = patient_data.get('hba1c')
        if hba1c and hba1c > 8.0:
            notes.append("  • Diabetes poorly controlled - Consider medication adjustment")
    
    if patient_data.get('heart_failure_flag'):
        notes.append("  • Daily weight monitoring (report gain >2lbs/day or 5lbs/week)")
        notes.append("  • Fluid restriction: 1.5-2L per day")
        notes.append("  • Low sodium diet (<2g/day)")
    
    if patient_data.get('hypertension_flag'):
        notes.append("  • BP monitoring 2x daily (target <140/90)")
    
    if patient_data.get('copd_asthma_flag'):
        notes.append("  • Monitor respiratory symptoms and O2 saturation")
        notes.append("  • Ensure inhaler technique correct")
    
    if patient_data.get('ckd_flag'):
        notes.append("  • Monitor fluid intake/output")
        notes.append("  • Renal diet compliance")
    
    if patient_data.get('on_anticoagulants_flag'):
        notes.append("  • INR monitoring per protocol")
        notes.append("  • Watch for bleeding signs")
    
    # Risk assessment
    if cci >= 7:
        notes.append("\n⚠️⚠️ VERY HIGH RISK: Multiple complex comorbidities - Intensive monitoring required")
    elif cci >= 5:
        notes.append("\n⚠️ HIGH RISK: Significant comorbidities - Close follow-up needed")
    elif cci >= 3:
        notes.append("\nMODERATE RISK: Standard post-discharge monitoring")
    else:
        notes.append("\nLOW RISK: Routine follow-up care")
    
    return "\n".join(notes)


async def populate_all_patients():
    """Populate clinical notes for all patients."""
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Get all patients
        query = text("""
            SELECT 
                patient_id, mrn, name, age, gender, bmi,
                date_of_birth, admission_date, discharge_date, 
                admission_type, length_of_stay_days, icu_stay_flag,
                discharge_destination, follow_up_within_7_days_flag,
                follow_up_appointment_date,
                diabetes_flag, heart_failure_flag, cardiac_history_flag,
                copd_asthma_flag, ckd_flag, cancer_flag, dementia_flag,
                hypertension_flag, immunocompromised_flag,
                charlson_comorbidity_index,
                systolic_bp, diastolic_bp, heart_rate, respiratory_rate,
                temperature, spo2, pain_score_clinical,
                hemoglobin, creatinine, glucose, hba1c, wbc_count,
                sodium, potassium, troponin, bnp, lactate, inr,
                active_medication_count, medication_count_at_discharge,
                polypharmacy_flag, high_risk_medication_flag,
                on_anticoagulants_flag, on_insulin_flag,
                medication_adherence_rate,
                previous_admissions_12m, previous_er_visits_12m,
                prior_30_day_readmission_flag,
                clinical_notes
            FROM patient_ehr
            ORDER BY charlson_comorbidity_index DESC, patient_id
        """)
        
        result = await session.execute(query)
        patients = result.mappings().all()
        
        print(f"Found {len(patients)} patients")
        print("=" * 80)
        
        updated_count = 0
        
        for patient in patients:
            patient_dict = dict(patient)
            patient_id = patient_dict['patient_id']
            mrn = patient_dict['mrn']
            name = patient_dict['name']
            
            # Generate clinical notes
            clinical_notes = generate_clinical_notes(patient_dict)
            
            print(f"\n{'='*80}")
            print(f"Patient: {name} ({patient_id}, {mrn})")
            print(f"{'='*80}")
            print(clinical_notes)
            print(f"{'='*80}\n")
            
            # Update the patient record
            update_query = text("""
                UPDATE patient_ehr 
                SET clinical_notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE patient_id = :patient_id
            """)
            
            await session.execute(
                update_query,
                {"notes": clinical_notes, "patient_id": patient_id}
            )
            updated_count += 1
        
        await session.commit()
        
        print(f"\n{'='*80}")
        print(f"✅ Successfully updated clinical notes for {updated_count} patients")
        print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(populate_all_patients())
