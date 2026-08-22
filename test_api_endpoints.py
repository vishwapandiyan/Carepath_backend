"""
Test API Endpoints for Post-Care Agent with Appointment Integration
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

# Test credentials - Try multiple possibilities
TEST_CREDENTIALS_OPTIONS = [
    {"username": "test_care_manager", "password": "testpass123"},
    {"username": "care_manager", "password": "password"},
    {"username": "admin", "password": "admin"},
]


def print_test_header(title):
    """Print formatted test header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def get_auth_token():
    """Get authentication token - try multiple credential options"""
    print_test_header("Getting Authentication Token")
    
    for credentials in TEST_CREDENTIALS_OPTIONS:
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/auth/login",
                json=credentials
            )
            if response.status_code == 200:
                token = response.json().get("access_token")
                print(f"✅ Authentication successful with {credentials['username']}")
                print(f"   Token: {token[:20]}...")
                return token
            else:
                print(f"   ⚠️  Failed with {credentials['username']}: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️  Error with {credentials['username']}: {e}")
    
    print(f"\n❌ All authentication attempts failed")
    print(f"   Tried usernames: {[c['username'] for c in TEST_CREDENTIALS_OPTIONS]}")
    print(f"\n💡 To create a test user, run:")
    print(f"   python setup_test_user.py")
    return None


def test_health_endpoint():
    """Test health endpoint"""
    print_test_header("TEST 1: Health Endpoint")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed")
            print(f"   Status: {data.get('status')}")
            print(f"   Version: {data.get('version')}")
            print(f"   Environment: {data.get('env')}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_care_manager_health(token):
    """Test care manager health endpoint"""
    print_test_header("TEST 2: Care Manager Health")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/v1/care-manager/health",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Care manager health check passed")
            print(f"   Domain: {data.get('domain')}")
            print(f"   Modules: {data.get('modules')}")
            return True
        else:
            print(f"❌ Care manager health check failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_get_patient_list(token):
    """Test getting patient list"""
    print_test_header("TEST 3: Get Patient List")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/v1/ehr/patients?limit=5",
            headers=headers
        )
        if response.status_code == 200:
            patients = response.json()
            print(f"✅ Retrieved {len(patients)} patients")
            if patients:
                patient = patients[0]
                print(f"   Sample patient:")
                print(f"   - ID: {patient.get('patient_id')}")
                print(f"   - Name: {patient.get('name')}")
                print(f"   - MRN: {patient.get('mrn')}")
                return patient.get('patient_id')
            else:
                print("   ⚠️  No patients found in database")
                return None
        else:
            print(f"❌ Failed to get patients: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_post_discharge_status(token, patient_id):
    """Test post-discharge status endpoint"""
    print_test_header(f"TEST 4: Post-Discharge Status for Patient {patient_id}")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/v1/care-manager/patients/{patient_id}/post-discharge/",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Post-discharge status retrieved")
            print(f"   Patient ID: {data.get('patient_id')}")
            print(f"   Care Plan Status: {data.get('care_plan', {}).get('status')}")
            print(f"   Tasks: {len(data.get('care_plan', {}).get('tasks', []))}")
            print(f"   Follow-up Scheduled: {data.get('follow_up', {}).get('is_scheduled')}")
            print(f"   Appointment: {data.get('appointment', {}).get('is_appointment')}")
            return True
        else:
            print(f"❌ Failed to get post-discharge status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_appointment_context(token, patient_id):
    """Test appointment context endpoint"""
    print_test_header(f"TEST 5: Appointment Context for Patient {patient_id}")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/v1/care-manager/patients/{patient_id}/appointment-context",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Appointment context retrieved")
            print(f"   Requires Appointment: {data.get('requires_appointment')}")
            if data.get('appointment_required'):
                context = data.get('appointment_context', {})
                print(f"   Urgency: {context.get('urgency')}")
                print(f"   Manual Review: {context.get('requires_manual_review')}")
                print(f"   Next Steps: {len(context.get('next_steps', []))}")
            else:
                print(f"   Message: {data.get('message')}")
            return True
        else:
            print(f"❌ Failed to get appointment context: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_care_plan_stream(token, patient_id):
    """Test care plan generation stream endpoint"""
    print_test_header(f"TEST 6: Care Plan Generation Stream for Patient {patient_id}")
    print("⚠️  This will generate a real care plan (takes 10-30 seconds)")
    print("    Streaming SSE events...")
    
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/v1/care-manager/patients/{patient_id}/generate-care-plan-stream",
            headers=headers,
            stream=True,
            timeout=60
        )
        
        if response.status_code == 200:
            print(f"\n✅ Stream started successfully")
            
            event_count = 0
            agent_events = []
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            event_type = data.get('type')
                            event_count += 1
                            
                            if event_type == 'init':
                                print(f"\n   📝 {data.get('message')}")
                            elif event_type == 'agent_start':
                                agent = data.get('agent')
                                agent_events.append(agent)
                                print(f"\n   🤖 Agent: {agent}")
                                print(f"      {data.get('message')}")
                            elif event_type == 'tool_call':
                                print(f"      🔧 Tool: {data.get('tool')}")
                            elif event_type == 'agent_complete':
                                print(f"      ✅ {data.get('message')}")
                            elif event_type == 'complete':
                                print(f"\n   🎉 {data.get('message')}")
                                summary = data.get('summary', {})
                                print(f"\n   Summary:")
                                print(f"   - Total tasks: {summary.get('total_tasks')}")
                                print(f"   - Status: {summary.get('status')}")
                                print(f"   - Appointment: {summary.get('appointment_scheduled')}")
                                
                                # Check for appointment data
                                appointment = data.get('appointment', {})
                                if appointment.get('appointment_required'):
                                    print(f"   ⚕️  Appointment bridge triggered!")
                                
                                break
                            elif event_type == 'error':
                                print(f"\n   ❌ Error: {data.get('message')}")
                                return False
                                
                        except json.JSONDecodeError:
                            pass
            
            print(f"\n✅ Stream completed successfully")
            print(f"   Total events: {event_count}")
            print(f"   Agents executed: {', '.join(agent_events)}")
            return True
            
        else:
            print(f"❌ Stream failed: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all API tests"""
    print("\n" + "="*70)
    print("  POST-CARE AGENT API ENDPOINT TESTS")
    print("="*70)
    
    results = []
    
    # Test 1: Health
    results.append(("Health Endpoint", test_health_endpoint()))
    
    # Get auth token
    token = get_auth_token()
    if not token:
        print("\n❌ Cannot proceed without authentication token")
        print("   Make sure you have a care_manager user in the database")
        return False
    
    # Test 2: Care Manager Health
    results.append(("Care Manager Health", test_care_manager_health(token)))
    
    # Test 3: Get patient
    patient_id = test_get_patient_list(token)
    if not patient_id:
        print("\n⚠️  No patients available for testing")
        print("   Skipping patient-specific tests")
    else:
        # Test 4: Post-discharge status
        results.append(("Post-Discharge Status", test_post_discharge_status(token, patient_id)))
        
        # Test 5: Appointment context
        results.append(("Appointment Context", test_appointment_context(token, patient_id)))
        
        # Test 6: Care plan generation (optional - takes time)
        print("\n" + "="*70)
        user_input = input("Run care plan generation test? (takes 10-30s) [y/N]: ")
        if user_input.lower() == 'y':
            results.append(("Care Plan Stream", test_care_plan_stream(token, patient_id)))
    
    # Summary
    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL API TESTS PASSED! Endpoints are working correctly!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review errors above.")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
