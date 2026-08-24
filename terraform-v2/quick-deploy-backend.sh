#!/bin/bash

# Quick Backend Deployment Script
# Updates ECS task definition with new environment variables and forces redeployment
# No Docker rebuild needed - just updates environment configuration

set -e

echo "🚀 Quick Backend Deployment to ECS"
echo "===================================="

# Configuration
CLUSTER_NAME="carepath-ecs-prod"
SERVICE_NAME="carepath-backend-prod"
TASK_FAMILY="carepath-ai-backend-prod"
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="363401891883"

echo "📥 Fetching current task definition..."
aws ecs describe-task-definition \
  --task-definition $TASK_FAMILY \
  --region $AWS_REGION \
  --query 'taskDefinition' > task-def-temp.json

echo "✏️  Adding QuickSight environment variables..."

# Extract and modify the task definition
cat task-def-temp.json | jq '.containerDefinitions[0].environment += [
  {"name": "QUICKSIGHT_DASHBOARD_ID", "value": "abcbf9d1-c35d-4b45-9e28-b7cdc7e964f3"},
  {"name": "AWS_ACCOUNT_ID", "value": "363401891883"},
  {"name": "AWS_REGION", "value": "us-east-1"}
] | {
  family: .family,
  taskRoleArn: .taskRoleArn,
  executionRoleArn: .executionRoleArn,
  networkMode: .networkMode,
  containerDefinitions: .containerDefinitions,
  requiresCompatibilities: .requiresCompatibilities,
  cpu: .cpu,
  memory: .memory
}' > task-def-new.json

echo "📝 Registering new task definition..."
NEW_TASK_DEF=$(aws ecs register-task-definition \
  --cli-input-json file://task-def-new.json \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "✅ New task definition: $NEW_TASK_DEF"

echo "🔄 Updating ECS service..."
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --task-definition $NEW_TASK_DEF \
  --force-new-deployment \
  --region $AWS_REGION \
  --query 'service.serviceName' \
  --output text

echo "🧹 Cleaning up temp files..."
rm task-def-temp.json task-def-new.json

echo ""
echo "✅ Deployment initiated!"
echo "===================================="
echo ""
echo "📊 Monitor deployment status:"
echo "aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION --query 'services[0].deployments'"
echo ""
echo "📝 View logs:"
echo "aws logs tail /ecs/carepath-backend-prod --follow --region $AWS_REGION"
echo ""
echo "⏱️  Deployment typically takes 2-3 minutes"
