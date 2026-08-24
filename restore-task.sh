#!/bin/bash
set -e

echo "Downloading SQL dump from S3..."
aws s3 cp s3://carepath-ai-frontend-prod/db-backup/carepath_data.sql /tmp/

echo "Getting database password from Secrets Manager..."
DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id carepath-ai-db-password-prod --region us-east-1 --query SecretString --output text | jq -r '.password')

echo "Restoring database..."
PGPASSWORD="$DB_PASSWORD" psql -h carepath-ai-db-prod.cu5o4e24iwmf.us-east-1.rds.amazonaws.com -U dbadmin -d carepath_db -f /tmp/carepath_data.sql

echo "Database restored successfully!"
