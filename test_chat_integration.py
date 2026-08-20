"""
Chat History Feature - Integration Test
Tests all chat endpoints and functionality
"""
import asyncio
import json
from datetime import datetime
import httpx

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
TEST_CARE_MANAGER = {
    "username": "test_cm_chat",
    "password": "TestPass123!",
}
TEST_PATIENT = {
    "username": "test_patient_chat",
    "password": "TestPass123!",
    "mrn": "MRN123456789"  # Adjust if needed
}

# Global variables for tokens and IDs
care_manager_token = None
patient_token = None
test_session_id = None


def print_header(text):
    """Print section header"""
    print("\n" + "="*80)
    print(text)
    print("="*80)


def print_success(text):
    """Print success message"""
    print(f"✅ {text}")


def print_error(text):
    """Print error message"""
    print(f"❌ {text}")


def print_info(text):
    """Print info message"""
    print(f"ℹ️  {text}")


async def test_server_connection():
    """Test if server is running"""
    print_header("STEP 0: Checking Server Connection")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL.replace('/api/v1', '')}/health", timeout=5.0)
            if response.status_code == 200:
                print_success("Server is running")
                return True
    except Exception as e:
        print_error(f"Server not running: {e}")
        print_info("Start server with: uvicorn app.main:app --reload")
        return False


async def signup_care_manager():
    """Sign up care manager"""
    global care_manager_token
    print_header("STEP 1: Care Manager Signup")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/auth/signup/care-manager",
                json={
                    "username": TEST_CARE_MANAGER["username"],
                    "password": TEST_CARE_MANAGER["password"],
                    "confirm_password": TEST_CARE_MANAGER["password"]
                },
                timeout=10.0
            )
            
            if response.status_code == 201:
                data = response.json()
                care_manager_token = data["access_token"]
                print_success(f"Care Manager signed up: {TEST_CARE_MANAGER['username']}")
                print_info(f"Token: {care_manager_token[:30]}...")
                return True
            elif response.status_code == 400 and "already exists" in response.text:
                # Try login instead
                print_info("User already exists, logging in...")
                return await login_care_manager()
            else:
                print_error(f"Signup failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Signup error: {e}")
            return False


async def login_care_manager():
    """Login care manager"""
    global care_manager_token
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/auth/login",
                json={
                    "username": TEST_CARE_MANAGER["username"],
                    "password": TEST_CARE_MANAGER["password"]
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                care_manager_token = data["access_token"]
                print_success(f"Care Manager logged in: {TEST_CARE_MANAGER['username']}")
                return True
            else:
                print_error(f"Login failed: {response.status_code}")
                return False
        except Exception as e:
            print_error(f"Login error: {e}")
            return False


async def test_create_chat():
    """Test creating a new chat"""
    global test_session_id
    print_header("STEP 2: Create New Chat")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/chat/new",
                json={
                    "initial_message": "Hello, I need help managing patient care plans"
                },
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=15.0
            )
            
            if response.status_code == 201:
                data = response.json()
                test_session_id = data["session_id"]
                print_success(f"Chat created: {test_session_id}")
                print_info(f"Title: {data['title']}")
                print_info(f"Auto-generated: {data['is_title_auto_generated']}")
                print(json.dumps(data, indent=2))
                return True
            else:
                print_error(f"Create chat failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error creating chat: {e}")
            return False


async def test_send_message():
    """Test sending a message"""
    print_header("STEP 3: Send Message to Chat")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/chat/{test_session_id}/message",
                json={
                    "content": "What are the best practices for post-discharge follow-ups?",
                    "role": "user",
                    "context": {
                        "action": "care_planning"
                    }
                },
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=20.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Message sent successfully")
                print_info(f"User message: {data['user_message']['message_id']}")
                print_info(f"Assistant response: {data['assistant_response']['message_id']}")
                print("\nUser Message:")
                print(data['user_message']['content'][:100] + "...")
                print("\nAssistant Response:")
                print(data['assistant_response']['content'][:200] + "...")
                return True
            else:
                print_error(f"Send message failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error sending message: {e}")
            return False


async def test_list_chats():
    """Test listing chats"""
    print_header("STEP 4: List All Chats")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/chat/list?limit=10",
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Retrieved {len(data['chats'])} chats")
                print_info(f"Total chats: {data['total']}")
                
                for i, chat in enumerate(data['chats'], 1):
                    print(f"\nChat {i}:")
                    print(f"  Session ID: {chat['session_id']}")
                    print(f"  Title: {chat['title']}")
                    print(f"  Messages: {chat['message_count']}")
                    print(f"  Last active: {chat['last_message_at']}")
                
                return True
            else:
                print_error(f"List chats failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error listing chats: {e}")
            return False


async def test_get_messages():
    """Test getting chat messages"""
    print_header("STEP 5: Get Chat Messages")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/chat/{test_session_id}/messages?limit=50",
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Retrieved {len(data['messages'])} messages")
                print_info(f"Chat title: {data['title']}")
                
                for i, msg in enumerate(data['messages'], 1):
                    role_emoji = "👤" if msg['role'] == "user" else "🤖"
                    print(f"\n{role_emoji} Message {i} ({msg['role']}):")
                    print(f"  ID: {msg['message_id']}")
                    print(f"  Content: {msg['content'][:100]}...")
                    print(f"  Time: {msg['created_at']}")
                
                return True
            else:
                print_error(f"Get messages failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error getting messages: {e}")
            return False


async def test_update_title():
    """Test updating chat title"""
    print_header("STEP 6: Update Chat Title")
    
    async with httpx.AsyncClient() as client:
        try:
            new_title = "Post-Discharge Care Planning Discussion"
            response = await client.patch(
                f"{BASE_URL}/chat/{test_session_id}/title",
                json={"title": new_title},
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Title updated successfully")
                print_info(f"New title: {data['title']}")
                print_info(f"Auto-generated: {data['is_title_auto_generated']}")
                return True
            else:
                print_error(f"Update title failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error updating title: {e}")
            return False


async def test_pin_chat():
    """Test pinning a chat"""
    print_header("STEP 7: Pin Chat")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.patch(
                f"{BASE_URL}/chat/{test_session_id}/pin",
                json={"is_pinned": True},
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Chat pinned: {data['is_pinned']}")
                return True
            else:
                print_error(f"Pin chat failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error pinning chat: {e}")
            return False


async def test_search_chats():
    """Test searching chats"""
    print_header("STEP 8: Search Chats")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/chat/search?q=discharge",
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Search found {data['total']} results")
                print_info(f"Query: '{data['query']}'")
                
                for result in data['results']:
                    print(f"\nFound: {result['title']}")
                    print(f"  Session ID: {result['session_id']}")
                    if result['matched_messages']:
                        print(f"  Matched messages: {len(result['matched_messages'])}")
                
                return True
            else:
                print_error(f"Search failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error searching: {e}")
            return False


async def test_export_chat():
    """Test exporting chat"""
    print_header("STEP 9: Export Chat (JSON)")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/chat/{test_session_id}/export?format=json",
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                print_success("Chat exported successfully")
                print_info(f"Content length: {len(response.text)} bytes")
                
                # Try to parse as JSON
                try:
                    export_data = json.loads(response.text)
                    print_info(f"Exported messages: {len(export_data.get('messages', []))}")
                    print_info(f"Exported at: {export_data.get('exported_at', 'N/A')}")
                except:
                    print_info("Export format: Non-JSON (text/markdown)")
                
                return True
            else:
                print_error(f"Export failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error exporting: {e}")
            return False


async def test_delete_chat():
    """Test deleting chat (soft delete)"""
    print_header("STEP 10: Delete Chat (Soft Delete)")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(
                f"{BASE_URL}/chat/{test_session_id}?permanent=false",
                headers={"Authorization": f"Bearer {care_manager_token}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Chat deleted (soft delete)")
                print_info(f"Session ID: {data['session_id']}")
                print_info(f"Deleted at: {data['deleted_at']}")
                print_info(f"Permanent: {data['permanent']}")
                return True
            else:
                print_error(f"Delete failed: {response.status_code}")
                print(response.text)
                return False
        except Exception as e:
            print_error(f"Error deleting: {e}")
            return False


async def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*80)
    print("CHAT HISTORY FEATURE - INTEGRATION TEST")
    print("="*80)
    print(f"Testing against: {BASE_URL}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = []
    
    # Run tests in sequence
    tests = [
        ("Server Connection", test_server_connection),
        ("Care Manager Signup/Login", signup_care_manager),
        ("Create Chat", test_create_chat),
        ("Send Message", test_send_message),
        ("List Chats", test_list_chats),
        ("Get Messages", test_get_messages),
        ("Update Title", test_update_title),
        ("Pin Chat", test_pin_chat),
        ("Search Chats", test_search_chats),
        ("Export Chat", test_export_chat),
        ("Delete Chat", test_delete_chat),
    ]
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            
            # Stop if critical test fails
            if not result and test_name in ["Server Connection", "Care Manager Signup/Login"]:
                print_error(f"Critical test failed: {test_name}. Stopping.")
                break
        except Exception as e:
            print_error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Print summary
    print_header("TEST SUMMARY")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "="*80)
    print(f"Results: {passed}/{total} tests passed")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    if passed == total:
        print_success("🎉 ALL TESTS PASSED!")
    else:
        print_error(f"❌ {total - passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
