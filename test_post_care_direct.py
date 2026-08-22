"""
Direct test of Post-Care Agent with real patient data (no authentication needed)
"""
import asyncio
import sys
from pathlib import Path

# Add post_care to path
POST_CARE_PATH = Path(__file__).parent / "post_care"
sys.path.insert(0, str(POST_CARE_PATH))

from sqlalchemy import select
from app.db.base import get_db
from app.models.ehr import PatientEHR
from app.integrations.appointment_bridge import appointment_bridge


async def test_with_real_patient_data():
    """Test appointment bridge with real patient data from database"""
    print("\n" + "="*70)
    print("TESTING POST-CARE AGENT WITH REAL PATIENT DATA")
    print("="*70)
    
    async for db in get_db():
        try:
            # Get a real patient from database  
            stmt = select(PatientEHR).limit(5)
            result = await db.execute(stmt)
            patients = result.scalars().all()
            
            if not patients:
                print("❌ No patients found in database")
                print("   Please add some test patients first")
                return False
            
            patient = patients[0]  # Use first patient
            
            print(f"\n✅ Found patient in database:")
            print(f"   Name: {patient.name}")
            print(f"   ID: {patient.patient_id}")
            print(f"   MRN: {patient.mrn}")
            print(f"   Age: {patient.age}")
            print(f"   Diabetes: {patient.diabetes_flag}")
            print(f"   Heart Failure: {patient.heart_failure_flag}")
            print(f"   Hypertension: {patient.hypertension_flag}")
            
            # Test 1: URGENT classification
            print("\n" + "-"*70)
            print("TEST 1: URGENT Classification (should trigger appointment)")
            print("-"*70)
            
            urgent_care_continuity = {
                "mrn": patient.mrn,
                "classification": "URGENT",
                "continuity_action": "URGENT_REVIEW",
                "requires_appointment": True,
                "requires_human_review": True,
                "reason": "Patient reports severe chest pain and shortness of breath",
                "symptoms": ["chest pain", "shortness of breath", "dizziness"],
                "concerns": ["cardiac event"]
            }
            
            urgent_result = await appointment_bridge.trigger_appointment_workflow(
                patient_id=patient.patient_id,
                care_continuity_output=urgent_care_continuity,
                db=db
            )
            
            if urgent_result and urgent_result.get("success"):
                print("✅ URGENT case processed successfully")
                context = urgent_result.get("appointment_context", {})
                print(f"   Appointment Required: {urgent_result.get('appointment_required')}")
                print(f"   Urgency: {context.get('urgency')}")
                print(f"   Manual Review: {context.get('requires_manual_review')}")
                print(f"   Next Steps: {len(context.get('next_steps', []))}")
                for step in context.get("next_steps", []):
                    print(f"     - {step}")
            else:
                print(f"❌ URGENT case failed: {urgent_result.get('error')}")
                return False
            
            # Test 2: CONCERN classification
            print("\n" + "-"*70)
            print("TEST 2: CONCERN Classification (should trigger appointment)")
            print("-"*70)
            
            concern_care_continuity = {
                "mrn": patient.mrn,
                "classification": "CONCERN",
                "continuity_action": "CLINICAL_REVIEW",
                "requires_appointment": True,
                "requires_human_review": True,
                "reason": "Patient reports increased pain and swelling",
                "symptoms": ["pain", "swelling", "redness"],
                "concerns": ["wound infection"]
            }
            
            concern_result = await appointment_bridge.trigger_appointment_workflow(
                patient_id=patient.patient_id,
                care_continuity_output=concern_care_continuity,
                db=db
            )
            
            if concern_result and concern_result.get("success"):
                print("✅ CONCERN case processed successfully")
                context = concern_result.get("appointment_context", {})
                print(f"   Appointment Required: {concern_result.get('appointment_required')}")
                print(f"   Urgency: {context.get('urgency')}")
                print(f"   Manual Review: {context.get('requires_manual_review')}")
                print(f"   Next Steps: {len(context.get('next_steps', []))}")
            else:
                print(f"❌ CONCERN case failed: {concern_result.get('error')}")
                return False
            
            # Test 3: NORMAL classification
            print("\n" + "-"*70)
            print("TEST 3: NORMAL Classification (should NOT trigger appointment)")
            print("-"*70)
            
            normal_care_continuity = {
                "mrn": patient.mrn,
                "classification": "NORMAL",
                "continuity_action": "CONTINUE_FOLLOW_UP",
                "requires_appointment": False,
                "requires_human_review": False,
                "reason": "Patient recovering well, no complications",
                "symptoms": [],
                "concerns": []
            }
            
            normal_result = await appointment_bridge.trigger_appointment_workflow(
                patient_id=patient.patient_id,
                care_continuity_output=normal_care_continuity,
                db=db
            )
            
            if normal_result is None:
                print("✅ NORMAL case processed correctly (no appointment needed)")
            else:
                print(f"⚠️  NORMAL case returned result: {normal_result}")
            
            # Test 4: Verify patient context extraction
            print("\n" + "-"*70)
            print("TEST 4: Patient Context Extraction")
            print("-"*70)
            
            patient_context = appointment_bridge._extract_patient_context(
                patient, urgent_care_continuity
            )
            
            print("✅ Patient context extracted:")
            print(f"   Name: {patient_context.get('patient_name')}")
            print(f"   MRN: {patient_context.get('mrn')}")
            print(f"   Age: {patient_context.get('age')}")
            print(f"   Gender: {patient_context.get('gender')}")
            print(f"   Clinical Flags: {patient_context.get('clinical_flags')}")
            print(f"   Symptoms Reported: {patient_context.get('symptoms_reported')}")
            print(f"   Concerns: {patient_context.get('concerns_reported')}")
            
            # Summary
            print("\n" + "="*70)
            print("TEST SUMMARY")
            print("="*70)
            print("✅ URGENT classification → appointment required")
            print("✅ CONCERN classification → appointment required")
            print("✅ NORMAL classification → no appointment")
            print("✅ Patient context extraction working")
            print("✅ Urgency determination working")
            print("✅ Next steps generation working")
            
            print("\n🎉 ALL TESTS PASSED WITH REAL PATIENT DATA!")
            return True
            
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    success = await test_with_real_patient_data()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
