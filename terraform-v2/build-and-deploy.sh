#!/bin/bash

# Streamlined Build and Deploy Script
# Docker will cache unchanged layers - only new code is rebuilt
# Push is incremental - only changed layers are uploaded

set -e

echo "🚀 CarePath Backend - Build & Deploy"
echo "====================================="

# Configuration
ECR_REPO="363401891883.dkr.ecr.us-east-1.amazonaws.com/carepath-backend"
AWS_REGION="us-east-1"
CLUSTER_NAME="carepath-ecs-prod"
SERVICE_NAME="carepath-backend-prod"

echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin 363401891883.dkr.ecr.us-east-1.amazonaws.com

echo ""
echo "🏗️  Building Docker image (cached layers will be reused)..."
cd ..
docker build \
  -f terraform-v2/Dockerfile.backend \
  -t carepath-backend:latest \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  .
cd terraform-v2

echo ""
echo "🏷️  Tagging image for ECR..."
docker tag carepath-backend:latest $ECR_REPO:latest

echo ""
echo "📤 Pushing to ECR (only changed layers will upload)..."
docker push $ECR_REPO:latest

echo ""
echo "🔄 Forcing ECS service deployment..."
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --force-new-deployment \
  --region $AWS_REGION \
  --no-cli-pager

echo ""
echo "✅ Deployment Complete!"
echo "====================================="
echo ""
echo "📊 Monitor status:"
echo "aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION"
echo ""
echo "📝 View logs:"
echo "aws logs tail /ecs/carepath-backend-prod --follow"
