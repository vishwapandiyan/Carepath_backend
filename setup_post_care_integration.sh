#!/bin/bash

# Post-Care Integration Setup Script
# Run this script to set up the complete post-care agentic flow integration
# Usage: bash setup_post_care_integration.sh

set -e  # Exit on error

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║   CarePath Post-Care Agentic Flow Integration Setup          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
DB_NAME="carepath_db"
DB_USER="vishwa"
DB_HOST="localhost"
DB_PORT="5432"

# Step 1: Check Prerequisites
echo -e "${BLUE}Step 1: Checking Prerequisites...${NC}"

# Check PostgreSQL - try Homebrew path first
if [ -f "/opt/homebrew/opt/postgresql@14/bin/psql" ]; then
    export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"
    PSQL="/opt/homebrew/opt/postgresql@14/bin/psql"
    echo -e "${GREEN}✅ PostgreSQL installed (Homebrew)${NC}"
elif command -v psql &> /dev/null; then
    PSQL="psql"
    echo -e "${GREEN}✅ PostgreSQL installed${NC}"
else
    echo -e "${RED}❌ PostgreSQL is not installed. Please install PostgreSQL first.${NC}"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 3 installed${NC}"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js is not installed.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Node.js installed${NC}"

echo ""

# Step 2: Test Database Connection
echo -e "${BLUE}Step 2: Testing Database Connection...${NC}"

if $PSQL -U $DB_USER -d $DB_NAME -c "SELECT 1;" &> /dev/null; then
    echo -e "${GREEN}✅ Database connection successful${NC}"
else
    echo -e "${RED}❌ Cannot connect to database ${DB_NAME}${NC}"
    echo -e "${YELLOW}Please ensure PostgreSQL is running and the database exists.${NC}"
    echo -e "Create database: ${YELLOW}$PSQL -U $DB_USER -d postgres -c 'CREATE DATABASE $DB_NAME;'${NC}"
    exit 1
fi

echo ""

# Step 3: Run Migrations
echo -e "${BLUE}Step 3: Running Database Migrations...${NC}"

MIGRATION_DIR="/Users/vishwa/Desktop/CarepathAI_backend/migrations"

# Main schema
echo "  → Running 001_create_main_schema.sql..."
$PSQL -U $DB_USER -d $DB_NAME -f "$MIGRATION_DIR/001_create_main_schema.sql" > /dev/null 2>&1
echo -e "${GREEN}  ✅ Main schema created${NC}"

# Care plan tables
echo "  → Running create_care_plan_tables.sql..."
$PSQL -U $DB_USER -d $DB_NAME -f "$MIGRATION_DIR/create_care_plan_tables.sql" > /dev/null 2>&1
echo -e "${GREEN}  ✅ Care plan tables created${NC}"

# Appointment tables
echo "  → Running create_appointment_tables.sql..."
$PSQL -U $DB_USER -d $DB_NAME -f "$MIGRATION_DIR/create_appointment_tables.sql" > /dev/null 2>&1
echo -e "${GREEN}  ✅ Appointment tables created${NC}"

echo ""

# Step 4: Verify Tables
echo -e "${BLUE}Step 4: Verifying Tables...${NC}"

TABLES=$($PSQL -U $DB_USER -d $DB_NAME -t -c "
SELECT COUNT(*) FROM information_schema.tables 
WHERE table_schema='public' 
AND (table_name LIKE 'care_%' OR table_name LIKE 'appointment_%');
")

if [ "$TABLES" -ge 7 ]; then
    echo -e "${GREEN}✅ All required tables verified${NC}"
else
    echo -e "${RED}❌ Some tables are missing (found: $TABLES, expected: ≥7)${NC}"
fi

# List tables
echo "  Tables created:"
$PSQL -U $DB_USER -d $DB_NAME -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema='public' 
AND (table_name LIKE 'care_%' OR table_name LIKE 'appointment_%')
ORDER BY table_name;
" -t | sed 's/^/    • /'

echo ""

# Step 5: Seed Test Data
echo -e "${BLUE}Step 5: Seeding Test Data...${NC}"

$PSQL -U $DB_USER -d $DB_NAME << 'EOF' > /dev/null 2>&1
-- Insert test cardiology provider (Chennai area)
INSERT INTO appointment_providers (provider_id, provider_name, destination, specialty, address, latitude, longitude, phone)
VALUES 
('TEST-CARDIO-001', 'Test Cardiology Center', 'SPECIALIST', 'CARDIOLOGY', 
 'Test Medical Center, 100 Health Ave, Chennai', 13.085, 80.275, '+91-44-TEST-001')
ON CONFLICT (provider_id) DO NOTHING;

-- Insert test slots for next 7 days
INSERT INTO provider_slots (slot_id, provider_id, start_time, end_time, status)
SELECT 
    'slot_test_cardio_' || to_char(slot_time, 'YYYYMMDDHH24'),
    'TEST-CARDIO-001',
    slot_time,
    slot_time + INTERVAL '30 minutes',
    'AVAILABLE'
FROM generate_series(
    NOW() + INTERVAL '1 day',
    NOW() + INTERVAL '7 days',
    INTERVAL '1 hour'
) AS slot_time
WHERE EXTRACT(HOUR FROM slot_time) BETWEEN 9 AND 17
ON CONFLICT (slot_id) DO NOTHING;
EOF

echo -e "${GREEN}✅ Test data seeded${NC}"

# Verify test data
PROVIDER_COUNT=$($PSQL -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM appointment_providers WHERE provider_id = 'TEST-CARDIO-001';")
SLOT_COUNT=$($PSQL -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM provider_slots WHERE provider_id = 'TEST-CARDIO-001';")

echo "  • Providers: $PROVIDER_COUNT"
echo "  • Available slots: $SLOT_COUNT"

echo ""

# Step 6: Check Backend Configuration
echo -e "${BLUE}Step 6: Checking Backend Configuration...${NC}"

BACKEND_DIR="/Users/vishwa/Desktop/CarepathAI_backend"
ENV_FILE="$BACKEND_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}✅ Backend .env file exists${NC}"
    
    # Check for required variables
    if grep -q "DATABASE_URL" "$ENV_FILE"; then
        echo -e "${GREEN}  ✓ DATABASE_URL configured${NC}"
    else
        echo -e "${YELLOW}  ⚠ DATABASE_URL not found in .env${NC}"
    fi
    
    if grep -q "NVIDIA_API_KEY" "$ENV_FILE"; then
        echo -e "${GREEN}  ✓ NVIDIA_API_KEY configured${NC}"
    else
        echo -e "${YELLOW}  ⚠ NVIDIA_API_KEY not found in .env${NC}"
    fi
    
    if grep -q "GROQ_API_KEY" "$ENV_FILE"; then
        echo -e "${GREEN}  ✓ GROQ_API_KEY configured${NC}"
    else
        echo -e "${YELLOW}  ⚠ GROQ_API_KEY not found in .env${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Backend .env file not found${NC}"
    echo -e "${YELLOW}  Create $ENV_FILE with required variables${NC}"
fi

echo ""

# Step 7: Check Frontend Configuration
echo -e "${BLUE}Step 7: Checking Frontend Configuration...${NC}"

FRONTEND_DIR="/Users/vishwa/Desktop/CarePath_CTS"
FRONTEND_ENV="$FRONTEND_DIR/.env"

if [ -f "$FRONTEND_ENV" ]; then
    echo -e "${GREEN}✅ Frontend .env file exists${NC}"
    
    if grep -q "VITE_API" "$FRONTEND_ENV"; then
        echo -e "${GREEN}  ✓ API URL configured${NC}"
    else
        echo -e "${YELLOW}  ⚠ VITE_API_BASE_URL not found in .env${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Frontend .env file not found${NC}"
fi

# Check if careService.ts was created
if [ -f "$FRONTEND_DIR/src/services/careService.ts" ]; then
    echo -e "${GREEN}✅ careService.ts created${NC}"
else
    echo -e "${YELLOW}⚠ careService.ts not found (should be created by integration script)${NC}"
fi

echo ""

# Step 8: Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Integration Setup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next Steps:"
echo ""
echo "1. Start the Backend:"
echo "   ${YELLOW}cd $BACKEND_DIR${NC}"
echo "   ${YELLOW}uvicorn app.main:app --reload --port 8000${NC}"
echo ""
echo "2. Start the Frontend:"
echo "   ${YELLOW}cd $FRONTEND_DIR${NC}"
echo "   ${YELLOW}npm run dev${NC}"
echo ""
echo "3. Test the Integration:"
echo "   • Visit: ${YELLOW}http://localhost:5173/patient/care-plan${NC}"
echo "   • Or use curl (see POST_CARE_INTEGRATION_GUIDE.md)"
echo ""
echo "4. Read Full Documentation:"
echo "   ${YELLOW}$BACKEND_DIR/POST_CARE_INTEGRATION_GUIDE.md${NC}"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
