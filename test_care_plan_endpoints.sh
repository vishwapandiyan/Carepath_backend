#!/bin/bash

# Test Care Plan Endpoints
# Run this after starting the backend server

BASE_URL="http://localhost:8000/api/v1"
MRN="MRN000015"
TOKEN="YOUR_TOKEN_HERE"

echo "======================================"
echo "Testing Care Plan Endpoints"
echo "======================================"
echo ""

# Test 1: Get care plan by MRN
echo "1. GET /patients/{mrn}/care-plan"
echo "--------------------------------------"
curl -X GET "$BASE_URL/patients/$MRN/care-plan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || echo "Response not JSON"

echo ""
echo ""

# Test 2: Get care plan by ID (you'll need to replace with actual ID)
CARE_PLAN_ID="CP-xxxxx"
echo "2. GET /care-plans/{id}"
echo "--------------------------------------"
curl -X GET "$BASE_URL/care-plans/$CARE_PLAN_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || echo "Response not JSON"

echo ""
echo ""

# Test 3: Get check-ins
echo "3. GET /care-plans/{id}/checkins"
echo "--------------------------------------"
curl -X GET "$BASE_URL/care-plans/$CARE_PLAN_ID/checkins" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || echo "Response not JSON"

echo ""
echo ""

# Test 4: Get tasks
echo "4. GET /care-plans/{id}/tasks"
echo "--------------------------------------"
curl -X GET "$BASE_URL/care-plans/$CARE_PLAN_ID/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || echo "Response not JSON"

echo ""
echo ""

# Test 5: Submit patient response
echo "5. POST /patients/{id}/care-plan-response"
echo "--------------------------------------"
curl -X POST "$BASE_URL/patients/$MRN/care-plan-response" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"patient_response": "I am feeling much better today"}' \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || echo "Response not JSON"

echo ""
echo "======================================"
echo "Tests Complete"
echo "======================================"
