#!/bin/bash

echo "=================================================="
echo "QUICK FIX: Restart Backend with Clean Cache"
echo "=================================================="
echo ""

# Navigate to backend directory
cd /Users/vishwa/Desktop/CarepathAI_backend

echo "Step 1: Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Cache cleared"
echo ""

echo "Step 2: Verifying configuration..."
echo "Main .env GROQ_API_KEY:"
grep "GROQ_API_KEY" .env
echo ""
echo "Post-care .env DB_USER:"
grep "DB_USER" post_care/.env
echo ""

echo "Step 3: Instructions to restart server:"
echo "=================================================="
echo "1. Go to your terminal where backend is running"
echo "2. Press Ctrl+C to stop the server"
echo "3. Run this command to restart:"
echo ""
echo "   python -m uvicorn app.main:app --reload --port 8000"
echo ""
echo "=================================================="
echo ""
echo "After restart, the 'role subitsha' error should be gone!"
echo "Then test by generating a care plan in the frontend."
