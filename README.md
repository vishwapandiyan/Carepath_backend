# Healthcare Authentication API

FastAPI backend for healthcare platform authentication with role-based access control.

## Features

### Authentication Flow
- **Single Login Endpoint**: Users login without selecting their role
- **Role-Based Redirect**: Backend automatically determines user role and provides appropriate redirect
- **Secure Password Handling**: Bcrypt hashing, no plaintext storage
- **JWT Tokens**: Stateless authentication with JWT

### User Roles
1. **PATIENT**: Patients with MRN (Medical Record Number) validation
2. **CARE_MANAGER**: Healthcare staff managing patient care

### Signup Flows

#### Care Manager Signup
```
POST /auth/signup/care-manager
{
    "username": "caremanager1",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!"
}
```

**Validation:**
- Username: Required, min 3 characters, must be unique, trimmed
- Password: Required, min 8 characters
- Passwords must match
- No MRN required

#### Patient Signup
```
POST /auth/signup/patient
{
    "username": "patient1",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "mrn": "MRN001"
}
```

**Validation:**
- Username: Required, min 3 characters, must be unique, trimmed
- Password: Required, min 8 characters
- Passwords must match
- MRN: Required, must exist in EHR system, cannot be already registered

### Login Flow
```
POST /auth/login
{
    "username": "patient1",
    "password": "SecurePass123!"
}

Response:
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "token_type": "bearer",
    "role": "PATIENT",
    "redirect_to": "/patient"
}
```

Backend automatically determines role and provides redirect URL:
- PATIENT → `/patient`
- CARE_MANAGER → `/care-manager`

### Protected Routes

#### Care Manager Routes (CARE_MANAGER role required)
- `GET /care-manager/dashboard` - Care manager dashboard
- `GET /care-manager/profile` - Care manager profile

#### Patient Routes (PATIENT role required)
- `GET /patient/dashboard` - Patient dashboard
- `GET /patient/profile` - Patient profile with EHR data

### Security Features
- **Role-Based Authorization**: Automatic enforcement at route level
- **Password Security**: Bcrypt hashing with salt
- **JWT Authentication**: Secure token-based auth
- **MRN Validation**: Integration with mock EHR service
- **Protection Against**:
  - Username enumeration (consistent error messages)
  - Duplicate registrations
  - Cross-role access (patients cannot access care manager routes and vice versa)
  - Plaintext password storage

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure environment (optional):**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Run the application:**
```bash
uvicorn app.main:app --reload
```

The API will be available at: `http://localhost:8000`

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Mock EHR Data

For testing, the following MRNs are available in the mock EHR system:

| MRN | First Name | Last Name | DOB |
|-----|------------|-----------|-----|
| MRN001 | John | Doe | 1980-05-15 |
| MRN002 | Jane | Smith | 1975-08-22 |
| MRN003 | Robert | Johnson | 1990-12-10 |
| MRN004 | Emily | Williams | 1985-03-30 |
| MRN005 | Michael | Brown | 1992-07-18 |

## Testing Examples

### 1. Register a Care Manager
```bash
curl -X POST http://localhost:8000/auth/signup/care-manager \
  -H "Content-Type: application/json" \
  -d '{
    "username": "caremanager1",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!"
  }'
```

### 2. Register a Patient
```bash
curl -X POST http://localhost:8000/auth/signup/patient \
  -H "Content-Type: application/json" \
  -d '{
    "username": "patient1",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "mrn": "MRN001"
  }'
```

### 3. Login
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "patient1",
    "password": "SecurePass123!"
  }'
```

### 4. Access Protected Route
```bash
curl -X GET http://localhost:8000/patient/dashboard \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Error Messages

The API provides clear error messages:

- `"Username already exists"` - Username is taken
- `"Passwords do not match"` - Password confirmation failed
- `"Invalid MRN"` - MRN not found in EHR system
- `"This MRN is already registered"` - MRN already has an account
- `"Please enter all required fields"` - Missing required fields
- `"Invalid username or password"` - Login failed
- `"Access denied. Required role: ..."` - Wrong role for endpoint

## Database Schema

### users
- id (Primary Key)
- username (Unique, Indexed)
- password_hash
- role (PATIENT | CARE_MANAGER)
- patient_id (Foreign Key, nullable)
- created_at

### patients
- id (Primary Key)
- mrn (Unique, Indexed)
- first_name
- last_name
- date_of_birth
- created_at

## Architecture

```
app/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration settings
├── database.py          # Database connection and session
├── models.py            # SQLAlchemy models (User, Patient)
├── schemas.py           # Pydantic schemas for validation
├── security.py          # Authentication and authorization
├── routers/
│   ├── auth.py          # Authentication endpoints
│   ├── care_manager.py  # Care manager endpoints
│   └── patient.py       # Patient endpoints
└── services/
    └── ehr_service.py   # Mock EHR integration
```

## Security Considerations

1. **Production Deployment:**
   - Change `SECRET_KEY` in `.env`
   - Use PostgreSQL or MySQL instead of SQLite
   - Configure CORS appropriately
   - Use HTTPS only
   - Implement rate limiting
   - Add request validation middleware

2. **Password Policy:**
   - Minimum 8 characters (configurable)
   - Consider adding complexity requirements
   - Implement password reset flow

3. **Token Management:**
   - Tokens expire after 30 minutes (configurable)
   - Implement refresh token mechanism
   - Add token blacklisting for logout

## Future Modules

This authentication module is designed to be modular. Future features can be added:
- Patient dashboards with clinical data
- Care manager patient management
- Appointment scheduling
- AI-powered risk prediction
- Care plan management
- Analytics and reporting

## License

Proprietary - Healthcare Platform
