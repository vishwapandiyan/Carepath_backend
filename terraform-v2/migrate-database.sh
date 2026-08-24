#!/bin/bash
# =============================================================================
# Migrate Local PostgreSQL to AWS RDS
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Database Migration: Local → AWS RDS${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if in terraform-v2 directory
if [ ! -f "main.tf" ]; then
    echo -e "${RED}Error: Run this script from terraform-v2 directory${NC}"
    exit 1
fi

# Step 1: Create local backup
echo -e "${YELLOW}Step 1: Creating local database backup...${NC}"
cd ..
echo "Enter your local PostgreSQL database name (default: readmission_db):"
read -r LOCAL_DB_NAME
LOCAL_DB_NAME=${LOCAL_DB_NAME:-readmission_db}

echo "Enter your local PostgreSQL username (default: postgres):"
read -r LOCAL_DB_USER
LOCAL_DB_USER=${LOCAL_DB_USER:-postgres}

BACKUP_FILE="database_backup_$(date +%Y%m%d_%H%M%S).sql"

pg_dump -U $LOCAL_DB_USER -d $LOCAL_DB_NAME > $BACKUP_FILE

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to create database backup${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
FILE_SIZE=$(du -h $BACKUP_FILE | cut -f1)
echo -e "${GREEN}✓ Backup size: $FILE_SIZE${NC}"

# Step 2: Get RDS connection details
echo ""
echo -e "${YELLOW}Step 2: Getting RDS connection details...${NC}"
cd terraform-v2

# Check if infrastructure is deployed
if [ ! -f "terraform.tfstate" ]; then
    echo -e "${RED}Error: Infrastructure not deployed. Run 'terraform apply' first.${NC}"
    exit 1
fi

RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null)
DB_NAME=$(terraform output -raw rds_database_name 2>/dev/null)
RDS_HOST=$(echo $RDS_ENDPOINT | cut -d':' -f1)

if [ -z "$RDS_ENDPOINT" ]; then
    echo -e "${RED}Error: Could not get RDS endpoint. Infrastructure may not be deployed.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ RDS Host: $RDS_HOST${NC}"
echo -e "${GREEN}✓ Database: $DB_NAME${NC}"

# Get password from Secrets Manager
echo -e "${YELLOW}Getting database password from Secrets Manager...${NC}"
SECRET_ARN=$(terraform output -raw rds_password_secret_arn 2>/dev/null)
DB_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id $SECRET_ARN \
    --query 'SecretString' \
    --output text | jq -r '.password')

if [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}Error: Could not retrieve database password${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Password retrieved${NC}"

# Step 3: Test RDS connection
echo ""
echo -e "${YELLOW}Step 3: Testing RDS connection...${NC}"

PGPASSWORD=$DB_PASSWORD psql -h $RDS_HOST -U dbadmin -d $DB_NAME -c "SELECT version();" > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Cannot connect to RDS. Check security groups!${NC}"
    echo -e "${YELLOW}RDS might not be publicly accessible. Try Option B (via EC2)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Connection successful${NC}"

# Step 4: Import data
echo ""
echo -e "${YELLOW}Step 4: Importing data to RDS...${NC}"
echo -e "${YELLOW}This may take a few minutes...${NC}"

cd ..
PGPASSWORD=$DB_PASSWORD psql -h $RDS_HOST -U dbadmin -d $DB_NAME -f $BACKUP_FILE

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Data import failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Data imported successfully${NC}"

# Step 5: Verify import
echo ""
echo -e "${YELLOW}Step 5: Verifying import...${NC}"

TABLE_COUNT=$(PGPASSWORD=$DB_PASSWORD psql -h $RDS_HOST -U dbadmin -d $DB_NAME -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")

echo -e "${GREEN}✓ Tables found: $(echo $TABLE_COUNT | xargs)${NC}"

# Count records in main tables
for table in users patients patient_ehr; do
    COUNT=$(PGPASSWORD=$DB_PASSWORD psql -h $RDS_HOST -U dbadmin -d $DB_NAME -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓ $table: $(echo $COUNT | xargs) records${NC}"
done

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Migration Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Backup file: $BACKUP_FILE"
echo -e "RDS Endpoint: $RDS_HOST"
echo -e "Database: $DB_NAME"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Deploy containers: cd terraform-v2 && ./build-and-push.sh"
echo -e "2. Test backend: curl \$(terraform output -raw backend_api_url)/health"
echo -e "3. Keep backup file safe for rollback if needed"
echo ""
echo -e "${GREEN}Done!${NC}"
