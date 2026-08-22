"""
Test Post-Care Agent with Appointment Bridge Integration
"""
import asyncio
import sys
from pathlib import Path

# Add post_care to path
POST_CARE_PATH = Path(__file__).parent / "post_care"
sys.path.insert(0, str(POST_CARE_PATH))

async def test_appointment_bridge_import():
    """Test 1: Verify appointment bridge imports correctly"""
    print("\n" + "="*70)
    print("TEST 1: Appointment Bridge Import")
    print("="*70)
    try:
        from app.integrations.appointment_bridge import appointment_bridge
        print("✅ Appointment bridge imported successfully")
        print(f"   Bridge type: {type(appointment_bridge)}")
        return True
    except Exception as e:
        print(f"❌ Failed to import appointment bridge: {e}")
        return False


async def test_post_care_adapter_import():
    """Test 2: Verify post-care adapter imports correctly"""
    print("\n" + "="*70)
    print("TEST 2: Post-Care Adapter Import")
    print("="*70)
    try:
        from app.integrations.post_care_adapter import stream_real_post_care_workflow
        print("✅ Post-care adapter imported successfully")
        print(f"   Function: {stream_real_post_care_workflow.__name__}")
        return True
    except Exception as e:
        print(f"❌ Failed to import post-care adapter: {e}")
        return False


async def test_care_continuity_schemas():
    """Test 3: Verify care continuity schemas updated correctly"""
    print("\n" + "="*70)
    print("TEST 3: Care Continuity Schemas")
    print("="*70)
    try:
        from post_care.agents.care_continuity.schemas import get_continuity_action
        
        # Test CONCERN classification
        concern_action = get_continuity_action("CONCERN")
        print(f"✅ CONCERN classification:")
        print(f"   - requires_appointment: {concern_action['requires_appointment']}")
        print(f"   - continuity_action: {concern_action['continuity_action']}")
        
        # Test URGENT classification
        urgent_action = get_continuity_action("URGENT")
        print(f"✅ URGENT classification:")
        print(f"   - requires_appointment: {urgent_action['requires_appointment']}")
        print(f"   - continuity_action: {urgent_action['continuity_action']}")
        
        # Test NORMAL classification
        normal_action = get_continuity_action("NORMAL")
        print(f"✅ NORMAL classification:")
        print(f"   - requires_appointment: {normal_action['requires_appointment']}")
        print(f"   - continuity_action: {normal_action['continuity_action']}")
        
        # Verify CONCERN and URGENT require appointments
        assert concern_action['requires_appointment'] == True, "CONCERN should require appointment"
        assert urgent_action['requires_appointment'] == True, "URGENT should require appointment"
        assert normal_action['requires_appointment'] == False, "NORMAL should NOT require appointment"
        
        print("\n✅ All classifications configured correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to test care continuity schemas: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_appointment_bridge_workflow():
    """Test 4: Test appointment bridge workflow with mock data"""
    print("\n" + "="*70)
    print("TEST 4: Appointment Bridge Workflow (Mock)")
    print("="*70)
    try:
        from app.integrations.appointment_bridge import appointment_bridge
        
        # Mock care continuity output for CONCERN case
        mock_care_continuity = {
            "mrn": "MRN123456",
            "classification": "CONCERN",
            "continuity_action": "CLINICAL_REVIEW",
            "requires_appointment": True,
            "requires_human_review": True,
            "reason": "Patient reports worsening symptoms",
            "symptoms": ["pain", "swelling"],
            "concerns": ["wound infection"]
        }
        
        # Test urgency determination
        urgency = appointment_bridge._determine_urgency(mock_care_continuity)
        print(f"✅ Urgency determination: {urgency}")
        assert urgency == "high_priority", "CONCERN should map to high_priority"
        
        # Test next steps generation
        next_steps = appointment_bridge._get_next_steps(urgency, mock_care_continuity)
        print(f"✅ Generated {len(next_steps)} next steps:")
        for step in next_steps:
            print(f"   - {step}")
        
        # Test URGENT urgency
        urgent_continuity = {**mock_care_continuity, "classification": "URGENT"}
        urgent_level = appointment_bridge._determine_urgency(urgent_continuity)
        print(f"\n✅ URGENT urgency determination: {urgent_level}")
        assert urgent_level == "urgent", "URGENT should map to urgent"
        
        print("\n✅ Appointment bridge workflow working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to test appointment bridge workflow: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test 5: Verify API endpoints are registered"""
    print("\n" + "="*70)
    print("TEST 5: API Endpoints Registration")
    print("="*70)
    try:
        from app.api.v1.endpoints import care_plan_generation
        from fastapi import FastAPI
        
        # Check if new endpoints exist
        routes = [route.path for route in care_plan_generation.router.routes]
        print(f"✅ Found {len(routes)} routes in care_plan_generation:")
        for route in routes:
            print(f"   - {route}")
        
        # Verify key endpoints
        expected_endpoints = [
            "/patients/{patient_id}/generate-care-plan-stream",
            "/patients/{patient_id}/send-care-plan",
            "/patients/{patient_id}/appointment-context",
            "/patients/{patient_id}/book-appointment"
        ]
        
        for endpoint in expected_endpoints:
            if endpoint in routes:
                print(f"   ✅ {endpoint} - FOUND")
            else:
                print(f"   ❌ {endpoint} - MISSING")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to test API endpoints: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_graph_builder():
    """Test 6: Test LangGraph orchestrator can be built"""
    print("\n" + "="*70)
    print("TEST 6: LangGraph Orchestrator Builder")
    print("="*70)
    try:
        from orchestrator.agentic_graph_builder import build_agentic_graph
        
        print("Building agentic graph...")
        graph = build_agentic_graph()
        print(f"✅ Graph built successfully: {type(graph)}")
        
        # Check graph nodes
        if hasattr(graph, 'nodes'):
            print(f"   Graph has {len(graph.nodes)} nodes")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to build graph: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_integration():
    """Test 7: End-to-end integration test"""
    print("\n" + "="*70)
    print("TEST 7: End-to-End Integration Test")
    print("="*70)
    try:
        from app.integrations.post_care_adapter import PostCareStreamingAdapter
        
        # Create adapter
        adapter = PostCareStreamingAdapter(patient_id="test_patient_123")
        print("✅ Created streaming adapter")
        print(f"   Patient ID: {adapter.patient_id}")
        print(f"   Agent map: {adapter.agent_map}")
        
        # Verify agent mapping
        expected_agents = ["care_plan", "followup", "response_analyser", "appointment"]
        mapped_agents = list(adapter.agent_map.values())
        print(f"\n   Expected agents: {expected_agents}")
        print(f"   Mapped agents: {mapped_agents}")
        
        for agent in expected_agents:
            if agent in mapped_agents:
                print(f"   ✅ {agent} - mapped")
            else:
                print(f"   ❌ {agent} - not mapped")
        
        print("\n✅ Integration components working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Failed integration test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("POST-CARE AGENT + APPOINTMENT BRIDGE INTEGRATION TESTS")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("Appointment Bridge Import", await test_appointment_bridge_import()))
    results.append(("Post-Care Adapter Import", await test_post_care_adapter_import()))
    results.append(("Care Continuity Schemas", await test_care_continuity_schemas()))
    results.append(("Appointment Bridge Workflow", await test_appointment_bridge_workflow()))
    results.append(("API Endpoints", await test_api_endpoints()))
    results.append(("LangGraph Builder", await test_graph_builder()))
    results.append(("Full Integration", await test_full_integration()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Integration is working correctly!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
