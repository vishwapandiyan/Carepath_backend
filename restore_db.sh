#!/bin/bash
# Database restore script to run from ECS task

set -e

echo "Starting database restore..."

# Get DB password from Secrets Manager
DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id carepath-ai-db-password-prod --region us-east-1 --query SecretString --output text | jq -r '.password')

# Database connection details
DB_HOST="carepath-ai-db-prod.cu5o4e24iwmf.us-east-1.rds.amazonaws.com"
DB_USER="dbadmin"
DB_NAME="carepath_db"

echo "Downloading database dump..."
# You'll need to upload your dump to S3 first
# aws s3 cp s3://your-bucket/carepath_dump.backup /tmp/carepath_dump.backup

echo "Restoring database..."
PGPASSWORD="$DB_PASSWORD" pg_restore -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -v -c /tmp/carepath_dump.backup

echo "Database restore completed!"
