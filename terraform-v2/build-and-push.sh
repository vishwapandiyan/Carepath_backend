#!/bin/bash
# =============================================================================
# Build and Push Docker Images to ECR
# Builds separate containers for Backend and ML services
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CarePath AI - Docker Build & Push${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if we're in the right directory
if [ ! -f "main.tf" ]; then
    echo -e "${RED}Error: Please run this script from the terraform-v2 directory${NC}"
    exit 1
fi

# Get AWS region
AWS_REGION=${AWS_REGION:-us-east-1}
echo -e "${YELLOW}Using AWS Region: $AWS_REGION${NC}"

# Get ECR repository URLs from Terraform output
echo -e "${YELLOW}Getting ECR repository URLs...${NC}"
BACKEND_ECR=$(terraform output -raw ecr_backend_repository_url 2>/dev/null)
ML_ECR=$(terraform output -raw ecr_ml_repository_url 2>/dev/null)

if [ -z "$BACKEND_ECR" ] || [ -z "$ML_ECR" ]; then
    echo -e "${RED}Error: Could not get ECR URLs. Make sure infrastructure is deployed.${NC}"
    echo -e "${YELLOW}Run 'terraform apply' first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Backend ECR: $BACKEND_ECR${NC}"
echo -e "${GREEN}✓ ML ECR: $ML_ECR${NC}"

# Login to ECR
echo -e "${YELLOW}Logging in to ECR...${NC}"
ECR_DOMAIN=$(echo $BACKEND_ECR | cut -d'/' -f1)
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $ECR_DOMAIN

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to login to ECR${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Logged in to ECR${NC}"

# Go to parent directory (backend root)
cd ..

# =============================================================================
# Build Backend Service
# =============================================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Building Backend Service${NC}"
echo -e "${GREEN}========================================${NC}"

docker build \
    --platform linux/amd64 \
    -t carepath-backend:latest \
    -f terraform-v2/Dockerfile.backend \
    .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to build backend image${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Backend image built successfully${NC}"

# Tag and push backend
echo -e "${YELLOW}Tagging and pushing backend image...${NC}"
docker tag carepath-backend:latest $BACKEND_ECR:latest
docker push $BACKEND_ECR:latest

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to push backend image${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Backend image pushed successfully${NC}"

# =============================================================================
# Build ML Service
# =============================================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Building ML Service${NC}"
echo -e "${GREEN}========================================${NC}"

# Copy ML service file to app directory if not exists
if [ ! -f "app/ml_service.py" ]; then
    echo -e "${YELLOW}Copying ML service file...${NC}"
    cp terraform-v2/ml_service.py app/
fi

docker build \
    --platform linux/amd64 \
    -t carepath-ml:latest \
    -f terraform-v2/Dockerfile.ml \
    .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to build ML image${NC}"
    exit 1
fi
echo -e "${GREEN}✓ ML image built successfully${NC}"

# Tag and push ML
echo -e "${YELLOW}Tagging and pushing ML image...${NC}"
docker tag carepath-ml:latest $ML_ECR:latest
docker push $ML_ECR:latest

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to push ML image${NC}"
    exit 1
fi
echo -e "${GREEN}✓ ML image pushed successfully${NC}"

# =============================================================================
# Update ECS Services
# =============================================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Updating ECS Services${NC}"
echo -e "${GREEN}========================================${NC}"

cd terraform-v2

CLUSTER=$(terraform output -raw ecs_cluster_name)
BACKEND_SERVICE=$(terraform output -raw ecs_backend_service_name)
ML_SERVICE=$(terraform output -raw ecs_ml_service_name)

echo -e "${YELLOW}Updating backend service...${NC}"
aws ecs update-service \
    --cluster $CLUSTER \
    --service $BACKEND_SERVICE \
    --force-new-deployment \
    --region $AWS_REGION \
    --no-cli-pager > /dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to update backend service${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Backend service updated${NC}"

echo -e "${YELLOW}Updating ML service...${NC}"
aws ecs update-service \
    --cluster $CLUSTER \
    --service $ML_SERVICE \
    --force-new-deployment \
    --region $AWS_REGION \
    --no-cli-pager > /dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to update ML service${NC}"
    exit 1
fi
echo -e "${GREEN}✓ ML service updated${NC}"

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}✓ Backend image pushed to ECR${NC}"
echo -e "${GREEN}✓ ML image pushed to ECR${NC}"
echo -e "${GREEN}✓ ECS services updated${NC}"
echo ""
echo -e "${YELLOW}Services are restarting with new images...${NC}"
echo -e "${YELLOW}This may take 2-3 minutes.${NC}"
echo ""
echo -e "Monitor deployment status:"
echo -e "  ${GREEN}Backend:${NC} aws ecs describe-services --cluster $CLUSTER --services $BACKEND_SERVICE"
echo -e "  ${GREEN}ML:${NC}      aws ecs describe-services --cluster $CLUSTER --services $ML_SERVICE"
echo ""
echo -e "View logs:"
echo -e "  ${GREEN}Backend:${NC} aws logs tail /ecs/carepath-ai-backend-prod --follow"
echo -e "  ${GREEN}ML:${NC}      aws logs tail /ecs/carepath-ai-ml-prod --follow"
echo ""
echo -e "Test endpoints:"
BACKEND_URL=$(terraform output -raw backend_api_url)
echo -e "  ${GREEN}Backend:${NC} curl $BACKEND_URL/health"
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Done!${NC}"
echo -e "${GREEN}========================================${NC}"
