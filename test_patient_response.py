#!/usr/bin/env python3
"""
Test script to reproduce the patient response endpoint error.
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# Step 1: Login as patient
print("🔵 Step 1: Logging in as healthy patient...")
login_response = requests.post(
    f"{BASE_URL}/auth/login",
    json={
        "username": "healthy_patient",
        "password": "patient123"
    }
)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)
    exit(1)

token = login_response.json()["access_token"]
print(f"✅ Login successful, token: {token[:20]}...")

# Step 2: Get patient info
print("\n🔵 Step 2: Getting patient info...")
headers = {"Authorization": f"Bearer {token}"}
me_response = requests.get(f"{BASE_URL}/auth/me", headers=headers)

if me_response.status_code != 200:
    print(f"❌ Get user info failed: {me_response.status_code}")
    print(me_response.text)
    exit(1)

patient_data = me_response.json()
patient_id = patient_data["patient_id"]
print(f"✅ Patient ID: {patient_id}")
print(f"   Username: {patient_data['username']}")
print(f"   Role: {patient_data['role']}")

# Step 3: Get follow-up tasks to find checkin_id
print("\n🔵 Step 3: Getting follow-up tasks...")
tasks_response = requests.get(
    f"{BASE_URL}/patients/{patient_id}/follow-up-tasks",
    headers=headers
)

if tasks_response.status_code != 200:
    print(f"❌ Get tasks failed: {tasks_response.status_code}")
    print(tasks_response.text)
    exit(1)

tasks_data = tasks_response.json()
print(f"✅ Tasks retrieved:")
print(json.dumps(tasks_data, indent=2))

if not tasks_data.get("checkins"):
    print("❌ No checkins found for this patient")
    exit(1)

checkin_id = tasks_data["checkins"][0]["checkin_id"]
print(f"\n🔵 Using checkin_id: {checkin_id}")

# Step 4: Submit patient response
print("\n🔵 Step 4: Submitting patient response...")
response_payload = {
    "patient_response": "I'm feeling much better today! No pain or discomfort.",
    "checkin_id": checkin_id
}

print(f"   Payload: {json.dumps(response_payload, indent=2)}")

response = requests.post(
    f"{BASE_URL}/patients/{patient_id}/care-plan-response",
    headers={
        **headers,
        "Content-Type": "application/json"
    },
    json=response_payload
)

print(f"\n📊 Response Status: {response.status_code}")
print(f"📊 Response Headers: {dict(response.headers)}")
print(f"\n📊 Response Body:")
print(response.text)

if response.status_code == 200:
    print("\n✅ SUCCESS! Patient response submitted successfully.")
    result = response.json()
    print(f"   Classification: {result.get('classification')}")
    print(f"   Confidence: {result.get('confidence')}")
    print(f"   Summary: {result.get('summary')}")
else:
    print(f"\n❌ FAILED with status {response.status_code}")
