# Post-Care Integration - Quick Start

## 🚀 Start Everything

### 1. Start Backend (Terminal 1)
```bash
cd /Users/vishwa/Desktop/CarepathAI_backend
uvicorn app.main:app --reload --port 8000
```

### 2. Start Frontend (Terminal 2)
```bash
cd /Users/vishwa/Desktop/CarePath_CTS
npm run dev
```

### 3. Test the Integration
Open browser: `http://localhost:5173/patient/care-plan`

---

## 🧪 Test API Directly

### Create Care Plan
```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/post-care/generate \
  -H "Content-Type: application/json"
```

### Submit NORMAL Response
```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/care-plan-response \
  -H "Content-Type: application/json" \
  -d '{"patient_response": "I am feeling much better today"}'
```

### Submit URGENT Response (Triggers Appointment)
```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/care-plan-response \
  -H "Content-Type: application/json" \
  -d '{"patient_response": "I have severe chest pain and shortness of breath"}'
```

---

## 📖 Full Documentation

- **Complete Guide:** `POST_CARE_INTEGRATION_GUIDE.md`
- **Architecture Details:** `POST_CARE_AGENTIC_FLOW_CHANGES.md`
- **Status:** `POST_CARE_INTEGRATION_STATUS.md`

---

## ✅ Integration Complete!

All backend endpoints are ready.  
All frontend components are created.  
Database tables are in place.

**Next:** Start the servers and test!
