"""
Setup test care manager user and patient data for testing
"""
import asyncio
import sys
from sqlalchemy import select
from app.db.base import get_db
from app.models.user import User, UserRole
from app.models.ehr import PatientEHR
from app.core.security import get_password_hash
from datetime import datetime, date


async def create_care_manager_user():
    """Create a test care manager user"""
    print("\n" + "="*70)
    print("Creating Test Care Manager User")
    print("="*70)
    
    async for db in get_db():
        try:
            # Check if user already exists
            stmt = select(User).where(User.username == "care_manager_test")
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"✅ Care manager user already exists")
                print(f"   Username: care_manager_test")
                print(f"   Role: {existing.role}")
                return existing
            
            # Create new user
            hashed_password = get_password_hash("test123")
            
            new_user = User(
                username="care_manager_test",
                email="care_manager@test.com",
                hashed_password=hashed_password,
                password_hash=hashed_password,
                role=UserRole.CARE_MANAGER,
                is_active=True,
                is_superuser=False,
                full_name="Test Care Manager",
                first_name="Test",
                last_name="Manager",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            print(f"✅ Created care manager user")
            print(f"   Username: care_manager_test")
            print(f"   Password: test123")
            print(f"   Role: {new_user.role}")
            
            return new_user
            
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            import traceback
            traceback.print_exc()
            return None


async def create_test_patients():
    """Create test patients with various risk levels"""
    print("\n" + "="*70)
    print("Creating Test Patients")
    print("="*70)
    
    patients_data = [
        {
            "name": "John Urgent",
            "mrn": "MRN-URGENT-001",
            "age": 68,
            "gender": "Male",
            "diabetes_flag": True,
            "heart_failure_flag": True,
            "hypertension_flag": True,
            "prior_30_day_readmission_flag": 1,
            "clinical_notes": "Recent discharge. Patient reports severe chest pain and shortness of breath.",
            "risk_level": "URGENT"
        },
        {
            "name": "Sarah Concern",
            "mrn": "MRN-CONCERN-002",
            "age": 55,
            "gender": "Female",
            "diabetes_flag": True,
            "hypertension_flag": True,
            "copd_asthma_flag": True,
            "clinical_notes": "Discharged 3 days ago. Reports increased pain and swelling at surgical site.",
            "risk_level": "CONCERN"
        },
        {
            "name": "Mike Normal",
            "mrn": "MRN-NORMAL-003",
            "age": 45,
            "gender": "Male",
            "diabetes_flag": False,
            "heart_failure_flag": False,
            "hypertension_flag": False,
            "clinical_notes": "Routine follow-up. Patient recovering well, no complications.",
            "risk_level": "NORMAL"
        }
    ]
    
    created_patients = []
    
    async for db in get_db():
        try:
            for patient_data in patients_data:
                # Check if patient exists
                stmt = select(PatientEHR).where(PatientEHR.mrn == patient_data["mrn"])
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    print(f"✅ Patient already exists: {patient_data['name']} ({patient_data['mrn']})")
                    created_patients.append(existing)
                    continue
                
                # Create new patient
                patient = PatientEHR(
                    patient_id=f"PT-{patient_data['mrn'].split('-')[-1]}",
                    name=patient_data["name"],
                    mrn=patient_data["mrn"],
                    age=patient_data["age"],
                    gender=patient_data["gender"],
                    diabetes_flag=patient_data.get("diabetes_flag", False),
                    heart_failure_flag=patient_data.get("heart_failure_flag", False),
                    hypertension_flag=patient_data.get("hypertension_flag", False),
                    copd_asthma_flag=patient_data.get("copd_asthma_flag", False),
                    prior_30_day_readmission_flag=patient_data.get("prior_30_day_readmission_flag", 0),
                    clinical_notes=patient_data["clinical_notes"],
                    discharge_date=date.today(),
                    admission_date=date.today(),
                    is_active=True,
                    address="123 Test St, Test City, TC 12345",
                    contact_number="555-0100",
                    email=f"{patient_data['name'].lower().replace(' ', '.')}@test.com",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.add(patient)
                created_patients.append(patient)
                
                print(f"✅ Created patient: {patient_data['name']} ({patient_data['mrn']})")
                print(f"   Risk Level: {patient_data['risk_level']}")
            
            await db.commit()
            
            # Refresh all patients
            for patient in created_patients:
                await db.refresh(patient)
            
            print(f"\n✅ Total patients ready: {len(created_patients)}")
            return created_patients
            
        except Exception as e:
            print(f"❌ Error creating patients: {e}")
            import traceback
            traceback.print_exc()
            return []


async def main():
    """Setup test data"""
    print("\n" + "="*70)
    print("POST-CARE AGENT TEST DATA SETUP")
    print("="*70)
    
    # Create care manager user
    user = await create_care_manager_user()
    if not user:
        print("\n❌ Failed to create care manager user")
        return False
    
    # Create test patients
    patients = await create_test_patients()
    if not patients:
        print("\n❌ Failed to create test patients")
        return False
    
    # Summary
    print("\n" + "="*70)
    print("SETUP COMPLETE")
    print("="*70)
    print(f"\n✅ Test care manager user created:")
    print(f"   Username: care_manager_test")
    print(f"   Password: test123")
    print(f"\n✅ Test patients created:")
    for patient in patients:
        print(f"   - {patient.name} (MRN: {patient.mrn}, ID: {patient.patient_id})")
    
    print(f"\n🎯 Ready to run tests with:")
    print(f"   python test_api_endpoints.py")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
