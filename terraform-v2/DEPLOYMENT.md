# CarePath AI - Terraform v2 Deployment Guide

## Overview

This Terraform configuration deploys the CarePath AI system on AWS with **separate Docker containers** for Backend and ML services, providing improved scalability, isolation, and resource management.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│                                                                   │
│  ┌─────────────────────┐     ┌─────────────────────┐            │
│  │   CloudFront (CDN)  │     │  CloudFront (API)   │            │
│  │   Frontend Static   │     │   HTTPS Endpoint    │            │
│  └──────────┬──────────┘     └──────────┬──────────┘            │
│             │                           │                        │
│  ┌──────────▼──────────┐     ┌──────────▼──────────┐            │
│  │   S3 Bucket         │     │   Public ALB        │            │
│  │   React App         │     │   Backend API       │            │
│  └─────────────────────┘     └──────────┬──────────┘            │
│                                          │                        │
│                              ┌───────────▼───────────┐            │
│                              │   ECS Cluster         │            │
│                              │                       │            │
│                              │  ┌─────────────────┐  │            │
│                              │  │ Backend Service │  │            │
│                              │  │ (Port 8000)     │  │            │
│                              │  │ - FastAPI       │  │            │
│                              │  │ - Business Logic│  │            │
│                              │  │ - Auth          │◄─┼───┐        │
│                              │  └─────────┬───────┘  │   │        │
│                              │            │          │   │        │
│                              │  ┌─────────▼───────┐  │   │        │
│                              │  │  ML Service     │  │   │        │
│                              │  │  (Port 8001)    │  │   │        │
│                              │  │  - Predictions  │  │   │        │
│                              │  │  - ML Models    │  │   │        │
│                              │  │  - Inference    │  │   │        │
│                              │  └─────────┬───────┘  │   │        │
│                              └────────────┼──────────┘   │        │
│                                           │              │        │
│                              ┌────────────▼──────────┐   │        │
│                              │  RDS PostgreSQL       │   │        │
│                              │  Shared Database      │   │        │
│                              └───────────────────────┘   │        │
│                                                           │        │
│                              ┌────────────────────────────┘        │
│                              │  Internal ALB (ML)                 │
│                              │  Private Communication Only        │
│                              └────────────────────────────────────┘
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Features

1. **Separate Services**
   - Backend Service: Handles API requests, authentication, business logic
   - ML Service: Dedicated to machine learning inference and predictions
   - Internal communication via private ALB

2. **Security**
   - Backend: Public access via CloudFront + ALB
   - ML Service: Internal-only access, not exposed to internet
   - RDS: Private subnet, accessible only by ECS tasks
   - Secrets managed via AWS Secrets Manager

3. **Scalability**
   - Independent scaling for Backend and ML services
   - Auto-scaling groups for ECS instances
   - Load balancing for both services

4. **High Availability**
   - Multi-AZ deployment
   - Health checks for all services
   - Automatic failover capabilities

## Prerequisites

### Required Tools

1. **Terraform** (>= 1.5.0)
   ```bash
   brew install terraform  # macOS
   ```

2. **AWS CLI** (>= 2.0)
   ```bash
   brew install awscli  # macOS
   aws configure
   ```

3. **Docker**
   ```bash
   brew install docker  # macOS
   ```

### AWS Configuration

Ensure your AWS credentials are configured:
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Default region: us-east-1
# Default output format: json
```

## Deployment Steps

### Step 1: Initialize Terraform

```bash
cd terraform-v2
terraform init
```

### Step 2: Review and Customize Variables

Edit `variables.tf` or create `terraform.tfvars`:

```hcl
# terraform.tfvars
project_name = "carepath-ai"
environment  = "prod"
aws_region   = "us-east-1"

# Backend Service
backend_task_cpu      = 512
backend_task_memory   = 1024
backend_desired_count = 2

# ML Service
ml_task_cpu      = 1024
ml_task_memory   = 2048
ml_desired_count = 1

# Database
db_instance_class        = "db.t3.small"
db_allocated_storage     = 20
db_backup_retention_days = 7

# ECS
ecs_instance_type = "t3.medium"
```

### Step 3: Plan Infrastructure

```bash
terraform plan -out=tfplan
```

Review the planned changes carefully.

### Step 4: Deploy Infrastructure

```bash
terraform apply tfplan
```

This will create:
- VPC with public and private subnets
- RDS PostgreSQL database
- ECS cluster
- ECR repositories (backend and ML)
- Application Load Balancers (public and internal)
- CloudFront distributions
- S3 bucket for frontend
- IAM roles and security groups

**Expected deployment time**: 10-15 minutes

### Step 5: Build and Push Docker Images

#### Backend Service

```bash
cd /path/to/CarepathAI_backend

# Build backend image
docker build -t carepath-backend -f terraform-v2/Dockerfile.backend .

# Get ECR login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(terraform -chdir=terraform-v2 output -raw ecr_backend_repository_url | cut -d'/' -f1)

# Tag and push
BACKEND_ECR=$(cd terraform-v2 && terraform output -raw ecr_backend_repository_url)
docker tag carepath-backend:latest $BACKEND_ECR:latest
docker push $BACKEND_ECR:latest
```

#### ML Service

First, copy the ML service file to the app directory:
```bash
cp terraform-v2/ml_service.py app/
```

Then build and push:
```bash
# Build ML image
docker build -t carepath-ml -f terraform-v2/Dockerfile.ml .

# Get ECR login (same as above)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(terraform -chdir=terraform-v2 output -raw ecr_ml_repository_url | cut -d'/' -f1)

# Tag and push
ML_ECR=$(cd terraform-v2 && terraform output -raw ecr_ml_repository_url)
docker tag carepath-ml:latest $ML_ECR:latest
docker push $ML_ECR:latest
```

### Step 6: Update ECS Services

```bash
cd terraform-v2

# Get cluster and service names
CLUSTER=$(terraform output -raw ecs_cluster_name)
BACKEND_SERVICE=$(terraform output -raw ecs_backend_service_name)
ML_SERVICE=$(terraform output -raw ecs_ml_service_name)

# Force new deployment
aws ecs update-service \
  --cluster $CLUSTER \
  --service $BACKEND_SERVICE \
  --force-new-deployment \
  --region us-east-1

aws ecs update-service \
  --cluster $CLUSTER \
  --service $ML_SERVICE \
  --force-new-deployment \
  --region us-east-1
```

### Step 7: Deploy Frontend

```bash
cd /path/to/CarePath_CTS

# Update environment file with backend API URL
BACKEND_URL=$(cd ../CarepathAI_backend/terraform-v2 && terraform output -raw backend_api_url)
echo "VITE_API_URL=$BACKEND_URL" > .env.production

# Build frontend
npm run build

# Get S3 bucket name
S3_BUCKET=$(cd ../CarepathAI_backend/terraform-v2 && terraform output -raw s3_frontend_bucket_name)

# Upload to S3
aws s3 sync dist/ s3://$S3_BUCKET/ --delete

# Invalidate CloudFront cache
CF_ID=$(cd ../CarepathAI_backend/terraform-v2 && terraform output -raw cloudfront_frontend_id)
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

### Step 8: Verify Deployment

```bash
cd terraform-v2

# Get URLs
FRONTEND_URL=$(terraform output -raw frontend_url)
BACKEND_URL=$(terraform output -raw backend_api_url)

# Test backend health
curl $BACKEND_URL/health

# Test ML service (internal - must be from within VPC or via backend)
# The ML service is not directly accessible from internet

# Open frontend
open $FRONTEND_URL  # macOS
```

## Service Communication

### Backend → ML Communication

The backend service communicates with the ML service using the internal ALB:

```python
# In backend code
import httpx

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL")  # Set by Terraform

async def get_prediction(features: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ML_SERVICE_URL}/predict/readmission",
            json={"features": features}
        )
        return response.json()
```

### Environment Variables

Both services receive these environment variables:

**Backend Service:**
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`
- `ML_SERVICE_URL` (internal ALB URL)
- `ENVIRONMENT`

**ML Service:**
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `MODEL_CACHE_DIR`
- `ENVIRONMENT`

## Monitoring and Logs

### CloudWatch Logs

View logs for each service:

```bash
# Backend logs
aws logs tail /ecs/carepath-ai-backend-prod --follow

# ML logs
aws logs tail /ecs/carepath-ai-ml-prod --follow
```

### ECS Service Status

```bash
cd terraform-v2
CLUSTER=$(terraform output -raw ecs_cluster_name)

# Check backend service
aws ecs describe-services \
  --cluster $CLUSTER \
  --services carepath-ai-backend-service-prod

# Check ML service
aws ecs describe-services \
  --cluster $CLUSTER \
  --services carepath-ai-ml-service-prod
```

### Health Checks

Both services expose `/health` endpoints:

```bash
# Backend (public)
curl https://[cloudfront-domain]/health

# ML (internal only - accessible via backend)
# The ML service health is monitored by ALB
```

## Scaling

### Manual Scaling

```bash
cd terraform-v2
CLUSTER=$(terraform output -raw ecs_cluster_name)

# Scale backend service
aws ecs update-service \
  --cluster $CLUSTER \
  --service carepath-ai-backend-service-prod \
  --desired-count 3

# Scale ML service
aws ecs update-service \
  --cluster $CLUSTER \
  --service carepath-ai-ml-service-prod \
  --desired-count 2
```

### Auto Scaling (via Terraform)

Update `terraform.tfvars`:

```hcl
backend_desired_count = 3
ml_desired_count = 2
```

Then apply:

```bash
terraform apply
```

## Cost Optimization

### Current Configuration Costs (Estimated)

- **ECS EC2 Instances** (t3.medium × 2): ~$60/month
- **RDS PostgreSQL** (db.t3.micro): ~$15/month
- **ALB** (2 × Load Balancers): ~$32/month
- **CloudFront**: $0.085/GB (first 10TB)
- **S3**: $0.023/GB
- **Data Transfer**: Variable

**Total**: ~$110-150/month (excluding data transfer)

### Cost Reduction Tips

1. **Use Fargate Spot** for non-production environments
2. **Enable RDS Multi-AZ** only for production
3. **Use S3 Intelligent-Tiering** for infrequent access
4. **Set up CloudWatch alarms** to monitor costs
5. **Schedule ECS services** to scale down during off-hours

## Troubleshooting

### Service Not Starting

1. **Check ECS Task Logs:**
   ```bash
   aws logs tail /ecs/carepath-ai-backend-prod --follow
   aws logs tail /ecs/carepath-ai-ml-prod --follow
   ```

2. **Check Task Definition:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition carepath-ai-backend-prod
   ```

3. **Check Security Groups:**
   - Ensure backend can reach RDS (port 5432)
   - Ensure backend can reach ML internal ALB
   - Ensure ALB can reach ECS tasks

### Database Connection Issues

1. **Verify RDS is running:**
   ```bash
   aws rds describe-db-instances \
     --db-instance-identifier carepath-ai-db-prod
   ```

2. **Check security group rules:**
   ```bash
   cd terraform-v2
   terraform show | grep security_group
   ```

3. **Test connection from ECS task:**
   ```bash
   # SSH into ECS instance and test
   psql -h [rds-endpoint] -U dbadmin -d carepath_db
   ```

### ML Service Not Reachable

1. **Verify internal ALB:**
   ```bash
   cd terraform-v2
   terraform output ml_internal_url
   ```

2. **Check ML service logs:**
   ```bash
   aws logs tail /ecs/carepath-ai-ml-prod --follow
   ```

3. **Ensure backend has correct ML_SERVICE_URL:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition carepath-ai-backend-prod | \
     grep ML_SERVICE_URL
   ```

## Updating Services

### Update Backend Code

```bash
# Make code changes
# Build and push new image
docker build -t carepath-backend -f terraform-v2/Dockerfile.backend .
docker tag carepath-backend:latest $BACKEND_ECR:latest
docker push $BACKEND_ECR:latest

# Force new deployment
aws ecs update-service \
  --cluster $CLUSTER \
  --service $BACKEND_SERVICE \
  --force-new-deployment
```

### Update ML Models

```bash
# Update ML code or models
# Build and push new image
docker build -t carepath-ml -f terraform-v2/Dockerfile.ml .
docker tag carepath-ml:latest $ML_ECR:latest
docker push $ML_ECR:latest

# Force new deployment
aws ecs update-service \
  --cluster $CLUSTER \
  --service $ML_SERVICE \
  --force-new-deployment
```

### Update Infrastructure

```bash
cd terraform-v2
terraform plan
terraform apply
```

## Cleanup

To destroy all resources:

```bash
cd terraform-v2

# Remove all objects from S3 bucket first
S3_BUCKET=$(terraform output -raw s3_frontend_bucket_name)
aws s3 rm s3://$S3_BUCKET --recursive

# Destroy infrastructure
terraform destroy
```

**Warning**: This will delete all data including the database. Make sure to backup if needed.

## Security Best Practices

1. **Enable MFA** for AWS root account
2. **Use IAM roles** instead of access keys
3. **Enable CloudTrail** for audit logging
4. **Enable GuardDuty** for threat detection
5. **Regular security updates** for Docker images
6. **Use AWS Secrets Manager** for sensitive data
7. **Enable encryption** for RDS and S3
8. **Implement WAF** for CloudFront (additional cost)

## Backup and Recovery

### Database Backups

Automated backups are configured for 7 days. To create manual backup:

```bash
aws rds create-db-snapshot \
  --db-instance-identifier carepath-ai-db-prod \
  --db-snapshot-identifier carepath-manual-backup-$(date +%Y%m%d)
```

### Restore from Backup

```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier carepath-ai-db-restored \
  --db-snapshot-identifier carepath-manual-backup-20260823
```

## Additional Resources

- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/intro.html)
- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)

## Support

For issues or questions:
1. Check CloudWatch Logs
2. Review ECS task definitions
3. Verify security group rules
4. Check IAM permissions
5. Review this documentation

---

**Version**: 2.0.0  
**Last Updated**: 2026-08-23  
**Maintained By**: CarePath AI Team
