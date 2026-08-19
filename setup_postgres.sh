#!/bin/bash

# PostgreSQL Database Setup Script for CarePath Healthcare Platform
# This script creates the database and applies the schema

echo "========================================="
echo "CarePath PostgreSQL Database Setup"
echo "========================================="
echo ""

# Configuration
DB_NAME="carepath_db"
DB_USER="postgres"
DB_HOST="localhost"
DB_PORT="5432"

echo "Database Configuration:"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo ""

# Check if PostgreSQL is running
echo "Checking PostgreSQL connection..."
if ! psql -U $DB_USER -h $DB_HOST -p $DB_PORT -c '\q' 2>/dev/null; then
    echo "❌ Error: Cannot connect to PostgreSQL"
    echo "Please ensure PostgreSQL is installed and running"
    echo ""
    echo "To start PostgreSQL on macOS:"
    echo "  brew services start postgresql@14"
    echo ""
    echo "To check status:"
    echo "  brew services list"
    exit 1
fi

echo "✅ PostgreSQL is running"
echo ""

# Create database
echo "Creating database '$DB_NAME'..."
psql -U $DB_USER -h $DB_HOST -p $DB_PORT -c "CREATE DATABASE $DB_NAME;" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✅ Database '$DB_NAME' created successfully"
else
    echo "⚠️  Database '$DB_NAME' may already exist"
fi

echo ""

# Apply schema
echo "Applying database schema..."
psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -f database_schema.sql

if [ $? -eq 0 ]; then
    echo "✅ Schema applied successfully"
else
    echo "❌ Error applying schema"
    exit 1
fi

echo ""

# Verify tables
echo "Verifying tables..."
psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -c "\dt"

echo ""
echo "========================================="
echo "✅ Database setup complete!"
echo "========================================="
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "Update your .env file with:"
echo "  DATABASE_URL=postgresql://$DB_USER:YOUR_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
