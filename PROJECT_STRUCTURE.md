# Healthcare Platform - Project Structure

## Overview
Professional, scalable FastAPI backend with modular architecture designed for future expansion.

## Directory Structure

```
CarepathAI_backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   │
│   ├── core/                      # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py              # Application settings & configuration
│   │   └── security.py            # Authentication, authorization, JWT
│   │
│   ├── api/                       # API endpoints
│   │   ├── __init__.py
│   │   └── v1/                    # API version 1
│   │       ├── __init__.py
│   │       ├── api.py             # API router aggregation
│   │       └── endpoints/         # Endpoint modules
│   │           ├── __init__.py
│   │           ├── auth.py        # Authentication endpoints
│   │           ├── patient.py     # Patient endpoints
│   │           └── care_manager.py # Care Manager endpoints
│   │
│   ├── db/                        # Database configuration
│   │   ├── __init__.py
│   │   ├── base.py                # Base model and imports
│   │   └── session.py             # Database session and engine
│   │
│   ├── models/                    # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py                # User model with roles
│   │   └── patient.py             # Patient model
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── auth.py                # Auth request/response schemas
│   │   ├── user.py                # User schemas
│   │   └── patient.py             # Patient schemas
│   │
│   └── services/                  # Business logic services
│       ├── __init__.py
│       └── ehr_service.py         # EHR integration (mock)
│
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variables template
├── .gitignore                     # Git ignore rules
├── README.md                      # Project documentation
└── PROJECT_STRUCTURE.md           # This file

```

## Module Descriptions

### Core (`app/core/`)
Contains core functionality used across the application:
- **config.py**: Application settings, environment variables, global configuration
- **security.py**: JWT authentication, password hashing, role-based authorization

### API (`app/api/`)
REST API endpoints organized by version:
- **v1/**: Version 1 of the API
  - **api.py**: Aggregates all endpoint routers
  - **endpoints/**: Individual endpoint modules grouped by domain
    - **auth.py**: Login, signup, logout endpoints
    - **patient.py**: Patient-specific endpoints
    - **care_manager.py**: Care manager-specific endpoints

### Database (`app/db/`)
Database configuration and session management:
- **base.py**: SQLAlchemy Base and model imports for migrations
- **session.py**: Database engine and session factory

### Models (`app/models/`)
SQLAlchemy ORM models representing database tables:
- **user.py**: User authentication model with role enum
- **patient.py**: Patient records from EHR

### Schemas (`app/schemas/`)
Pydantic schemas for request validation and response serialization:
- **auth.py**: Login, signup, token schemas
- **user.py**: User response schemas
- **patient.py**: Patient response schemas

### Services (`app/services/`)
Business logic and external integrations:
- **ehr_service.py**: Mock EHR system integration for MRN validation

## Future Expansion

The architecture is designed to easily accommodate new modules:

### Machine Learning Module
```
app/
├── ml/
│   ├── __init__.py
│   ├── models/           # ML model files
│   ├── predictors/       # Prediction logic
│   └── training/         # Training scripts
```

### Appointments Module
```
app/
├── api/v1/endpoints/
│   └── appointments.py
├── models/
│   └── appointment.py
├── schemas/
│   └── appointment.py
└── services/
    └── appointment_service.py
```

### Analytics Module
```
app/
├── api/v1/endpoints/
│   └── analytics.py
├── models/
│   └── analytics.py
└── services/
    └── analytics_service.py
```

### Chatbot Module
```
app/
├── api/v1/endpoints/
│   └── chatbot.py
├── services/
│   └── chatbot_service.py
└── ml/
    └── nlp/
```

## Key Design Principles

1. **Separation of Concerns**: Each module has a clear responsibility
2. **Scalability**: Easy to add new features without affecting existing code
3. **Versioning**: API versioned for backward compatibility
4. **Security**: Authentication and authorization at the core level
5. **Maintainability**: Consistent structure and naming conventions

## API Versioning

All endpoints are prefixed with `/api/v1/`:
- `/api/v1/auth/login`
- `/api/v1/patient/dashboard`
- `/api/v1/care-manager/dashboard`

Future versions can be added without breaking existing clients:
- `/api/v2/...` (when needed)

## Adding New Features

### Example: Adding an Appointments Module

1. **Create model**: `app/models/appointment.py`
2. **Create schemas**: `app/schemas/appointment.py`
3. **Create service**: `app/services/appointment_service.py`
4. **Create endpoints**: `app/api/v1/endpoints/appointment.py`
5. **Register router**: Import in `app/api/v1/api.py`

### Example: Adding ML Predictions

1. **Create ML directory**: `app/ml/`
2. **Add predictor**: `app/ml/predictors/readmission_predictor.py`
3. **Create endpoint**: `app/api/v1/endpoints/predictions.py`
4. **Add schema**: `app/schemas/prediction.py`

## Database Migrations

For production use, add Alembic for database migrations:

```bash
pip install alembic
alembic init alembic
```

Configure `alembic/env.py` to use `app.db.base.Base.metadata`

## Testing Structure (Future)

```
tests/
├── __init__.py
├── conftest.py          # Pytest fixtures
├── test_auth.py
├── test_patient.py
└── test_care_manager.py
```

## Environment Variables

See `.env.example` for required configuration:
- DATABASE_URL
- SECRET_KEY
- CORS settings
- Token expiration

## Getting Started

1. Install dependencies: `pip install -r requirements.txt`
2. Configure environment: `cp .env.example .env`
3. Run server: `uvicorn app.main:app --reload`
4. Visit docs: `http://localhost:8000/docs`

## Architecture Benefits

✅ **Clean separation** of concerns  
✅ **Easy to test** each component independently  
✅ **Scalable** for large teams  
✅ **Maintainable** with clear structure  
✅ **Extensible** for new features  
✅ **Production-ready** architecture  
