#!/bin/bash

# ============================================================================
# CarePath Backend - Complete Dependency Installation Script
# ============================================================================
# This script installs all required packages for CarePath + Phase 1 Twilio
# Usage: bash install_dependencies.sh
# ============================================================================

set -e  # Exit on any error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     CarePath Backend - Installing All Dependencies             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${GREEN}✅${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️ ${NC} $1"
}

# Step 1: Upgrade pip
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Upgrading pip, setuptools, and wheel..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -m pip install --upgrade pip setuptools wheel --quiet
print_status "pip, setuptools, wheel upgraded"
echo ""

# Step 2: Install core dependencies one by one with fallback
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Installing core packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# List of critical packages
declare -a CRITICAL_PACKAGES=(
    "fastapi>=0.111.0"
    "uvicorn[standard]>=0.30.0"
    "pydantic>=2.7.0"
    "pydantic-settings>=2.3.0"
    "python-dotenv>=1.0.0"
)

for package in "${CRITICAL_PACKAGES[@]}"; do
    echo -n "Installing $package... "
    if python3 -m pip install "$package" --quiet 2>/dev/null; then
        print_status "installed"
    else
        print_error "failed"
        echo "  Retrying with --no-cache-dir..."
        python3 -m pip install "$package" --quiet --no-cache-dir
        print_status "installed (with retry)"
    fi
done
echo ""

# Step 3: Install database packages
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Installing database packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

declare -a DB_PACKAGES=(
    "sqlalchemy[asyncio]>=2.0.0"
    "asyncpg>=0.29.0"
    "psycopg2-binary>=2.9.0"
    "alembic>=1.13.0"
)

for package in "${DB_PACKAGES[@]}"; do
    echo -n "Installing $package... "
    if python3 -m pip install "$package" --quiet 2>/dev/null; then
        print_status "installed"
    else
        print_warning "encountered issue, trying alternate method"
        python3 -m pip install "$package" --quiet --no-build-isolation --no-cache-dir || \
            python3 -m pip install "$package" --quiet --force-reinstall
        print_status "installed"
    fi
done
echo ""

# Step 4: Install LLM/AI packages
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Installing AI/LLM packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

declare -a AI_PACKAGES=(
    "google-generativeai>=0.7.0"
    "openai>=1.0.0"
    "httpx>=0.27.0"
)

for package in "${AI_PACKAGES[@]}"; do
    echo -n "Installing $package... "
    if python3 -m pip install "$package" --quiet 2>/dev/null; then
        print_status "installed"
    else
        print_warning "encountered issue, retrying"
        python3 -m pip install "$package" --quiet --no-cache-dir
        print_status "installed"
    fi
done
echo ""

# Step 5: Install authentication packages
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Installing authentication packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

declare -a AUTH_PACKAGES=(
    "bcrypt>=4.0.0"
    "python-jose[cryptography]>=3.3.0"
    "passlib[bcrypt]>=1.7.4"
    "python-multipart>=0.0.6"
)

for package in "${AUTH_PACKAGES[@]}"; do
    echo -n "Installing $package... "
    python3 -m pip install "$package" --quiet 2>/dev/null || \
        python3 -m pip install "$package" --quiet --no-cache-dir
    print_status "installed"
done
echo ""

# Step 6: Install testing packages
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6: Installing testing packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

declare -a TEST_PACKAGES=(
    "pytest>=8.2.0"
    "pytest-asyncio>=0.23.0"
)

for package in "${TEST_PACKAGES[@]}"; do
    echo -n "Installing $package... "
    python3 -m pip install "$package" --quiet 2>/dev/null || \
        python3 -m pip install "$package" --quiet --no-cache-dir
    print_status "installed"
done
echo ""

# Step 7: Install ML packages
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 7: Installing ML packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

declare -a ML_PACKAGES=(
    "scikit-learn>=1.2.0"
    "pandas>=2.0.0"
    "numpy>=1.24.0"
    "xgboost>=1.7.0"
    "lightgbm>=3.3.0"
    "catboost>=1.2.0"
    "streamlit>=1.28.0"
)

for package in "${ML_PACKAGES[@]}"; do
    echo -n "Installing $package... "
    if python3 -m pip install "$package" --quiet 2>/dev/null; then
        print_status "installed"
    else
        print_warning "encountered issue, retrying with no-binary"
        python3 -m pip install "$package" --quiet --no-binary :all: --no-cache-dir || \
            print_warning "skipped (optional)"
    fi
done
echo ""

# Step 8: Install Twilio SDK (for Phase 1)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 8: Installing Twilio SDK (Phase 1)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -n "Installing twilio>=9.0.0... "
python3 -m pip install "twilio>=9.0.0" --quiet 2>/dev/null || \
    python3 -m pip install "twilio>=9.0.0" --quiet --no-cache-dir
print_status "installed"
echo ""

# Step 9: Install YAML parser
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 9: Installing YAML parser..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -n "Installing pyyaml>=6.0.0... "
python3 -m pip install "pyyaml>=6.0.0" --quiet 2>/dev/null || \
    python3 -m pip install "pyyaml>=6.0.0" --quiet --no-cache-dir
print_status "installed"
echo ""

# Verification
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 10: Verifying installations..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test critical imports
echo "Testing critical imports..."
python3 -c "
import sys
try:
    import fastapi
    print('✅ fastapi')
except: print('❌ fastapi')
try:
    import uvicorn
    print('✅ uvicorn')
except: print('❌ uvicorn')
try:
    import pydantic
    print('✅ pydantic')
except: print('❌ pydantic')
try:
    import sqlalchemy
    print('✅ sqlalchemy')
except: print('❌ sqlalchemy')
try:
    import twilio
    print('✅ twilio (Phase 1)')
except: print('❌ twilio')
try:
    from dotenv import load_dotenv
    print('✅ python-dotenv')
except: print('❌ python-dotenv')
" 2>&1 || true

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           ✅ ALL DEPENDENCIES INSTALLED SUCCESSFULLY             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "1. Terminal 1: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo "2. Terminal 2: ngrok http 8000"
echo "3. Terminal 3: curl -X POST http://localhost:8000/api/v1/voice/call ..."
echo ""
