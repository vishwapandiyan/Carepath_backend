# Quick Reference Guide - Terraform v2

## 🚀 Quick Start Commands

### Initial Deployment
```bash
cd terraform-v2
terraform init
terraform plan
terraform apply
./build-and-push.sh
```

### Get URLs
```bash
terraform output frontend_url
terraform output backend_api_url
```

## 📦 Docker Commands

### Build Images
```bash
# Backend
docker build -t carepath-backend -f terraform-v2/Dockerfile.backend .

# ML
docker build -t carepath-ml -f terraform-v2/Dockerfile.ml .
```

### Push to ECR
```bash
# Login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin [ACCOUNT].dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag carepath-backend:latest [BACKEND_ECR]:latest
docker push [BACKEND_ECR]:latest

docker tag carepath-ml:latest [ML_ECR]:latest
docker push [ML_ECR]:latest
```

## 🔄 Update Services

### Force New Deployment
```bash
# Backend
aws ecs update-service \
  --cluster [CLUSTER_NAME] \
  --service [BACKEND_SERVICE] \
  --force-new-deployment

# ML
aws ecs update-service \
  --cluster [CLUSTER_NAME] \
  --service [ML_SERVICE] \
  --force-new-deployment
```

### Scale Services
```bash
# Scale backend to 3 instances
aws ecs update-service \
  --cluster [CLUSTER_NAME] \
  --service [BACKEND_SERVICE] \
  --desired-count 3

# Scale ML to 2 instances
aws ecs update-service \
  --cluster [CLUSTER_NAME] \
  --service [ML_SERVICE] \
  --desired-count 2
```

## 📊 Monitoring

### View Logs
```bash
# Backend logs
aws logs tail /ecs/carepath-ai-backend-prod --follow

# ML logs
aws logs tail /ecs/carepath-ai-ml-prod --follow
```

### Check Service Status
```bash
# List all services
aws ecs list-services --cluster [CLUSTER_NAME]

# Describe backend service
aws ecs describe-services \
  --cluster [CLUSTER_NAME] \
  --services [BACKEND_SERVICE]

# Describe ML service
aws ecs describe-services \
  --cluster [CLUSTER_NAME] \
  --services [ML_SERVICE]
```

### Check Task Status
```bash
# List running tasks
aws ecs list-tasks --cluster [CLUSTER_NAME]

# Describe specific task
aws ecs describe-tasks \
  --cluster [CLUSTER_NAME] \
  --tasks [TASK_ARN]
```

## 🗄️ Database Operations

### Connect to RDS
```bash
psql -h [RDS_ENDPOINT] -U dbadmin -d carepath_db
```

### Backup Database
```bash
pg_dump -h [RDS_ENDPOINT] -U dbadmin -d carepath_db > backup.sql
```

### Restore Database
```bash
psql -h [RDS_ENDPOINT] -U dbadmin -d carepath_db < backup.sql
```

## 🌐 Frontend Deployment

### Build and Deploy
```bash
cd CarePath_CTS

# Set API URL
echo "VITE_API_URL=[BACKEND_API_URL]" > .env.production

# Build
npm run build

# Deploy to S3
aws s3 sync dist/ s3://[S3_BUCKET]/ --delete

# Invalidate CloudFront
aws cloudfront create-invalidation \
  --distribution-id [CF_ID] \
  --paths "/*"
```

## 🔍 Troubleshooting

### Check Container Health
```bash
# Get task ARN
TASK_ARN=$(aws ecs list-tasks --cluster [CLUSTER_NAME] --query 'taskArns[0]' --output text)

# Check health status
aws ecs describe-tasks \
  --cluster [CLUSTER_NAME] \
  --tasks $TASK_ARN \
  --query 'tasks[0].healthStatus'
```

### Test Endpoints
```bash
# Backend health
curl https://[CLOUDFRONT_DOMAIN]/health

# Backend API
curl https://[CLOUDFRONT_DOMAIN]/api/v1/health
```

### Check Security Groups
```bash
# List security groups
aws ec2 describe-security-groups \
  --filters "Name=tag:Project,Values=carepath-ai"

# Describe specific security group
aws ec2 describe-security-groups \
  --group-ids [SG_ID]
```

## 🔐 Secrets Management

### Get Secrets
```bash
# Database password
aws secretsmanager get-secret-value \
  --secret-id carepath-ai-db-password-prod

# JWT secret
aws secretsmanager get-secret-value \
  --secret-id carepath-ai-jwt-secret-prod
```

### Update Secrets
```bash
# Update database password
aws secretsmanager update-secret \
  --secret-id carepath-ai-db-password-prod \
  --secret-string '{"password":"new_password"}'
```

## 🧹 Cleanup

### Delete Specific Resources
```bash
# Stop all tasks
aws ecs update-service \
  --cluster [CLUSTER_NAME] \
  --service [SERVICE_NAME] \
  --desired-count 0

# Delete service
aws ecs delete-service \
  --cluster [CLUSTER_NAME] \
  --service [SERVICE_NAME] \
  --force
```

### Destroy All Infrastructure
```bash
# Empty S3 bucket first
aws s3 rm s3://[S3_BUCKET] --recursive

# Destroy with Terraform
terraform destroy
```

## 📈 Common Tasks

### Update Backend Code
```bash
# 1. Make code changes
# 2. Build new image
docker build -t carepath-backend -f terraform-v2/Dockerfile.backend .

# 3. Push to ECR
docker tag carepath-backend:latest [BACKEND_ECR]:latest
docker push [BACKEND_ECR]:latest

# 4. Update service
aws ecs update-service --cluster [CLUSTER_NAME] --service [BACKEND_SERVICE] --force-new-deployment
```

### Update ML Models
```bash
# 1. Update ML code/models
# 2. Build new image
docker build -t carepath-ml -f terraform-v2/Dockerfile.ml .

# 3. Push to ECR
docker tag carepath-ml:latest [ML_ECR]:latest
docker push [ML_ECR]:latest

# 4. Update service
aws ecs update-service --cluster [CLUSTER_NAME] --service [ML_SERVICE] --force-new-deployment
```

### Add Environment Variable
```bash
# 1. Update ECS task definition in terraform-v2/ecs.tf
# 2. Apply changes
terraform apply

# 3. Force new deployment
aws ecs update-service --cluster [CLUSTER_NAME] --service [SERVICE] --force-new-deployment
```

## 🎯 Terraform Commands

### Common Operations
```bash
# Format code
terraform fmt

# Validate configuration
terraform validate

# Plan changes
terraform plan

# Apply changes
terraform apply

# Show current state
terraform show

# List resources
terraform state list

# Get specific output
terraform output [OUTPUT_NAME]

# Get all outputs
terraform output
```

### State Management
```bash
# Refresh state
terraform refresh

# Import existing resource
terraform import [RESOURCE_TYPE].[NAME] [RESOURCE_ID]

# Remove resource from state
terraform state rm [RESOURCE_ADDRESS]
```

## 🔗 Useful Links

- **AWS Console**: https://console.aws.amazon.com
- **CloudWatch Logs**: https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups
- **ECS Dashboard**: https://console.aws.amazon.com/ecs/home
- **RDS Dashboard**: https://console.aws.amazon.com/rds/home
- **ECR Repositories**: https://console.aws.amazon.com/ecr/repositories

## 📝 Variables Quick Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `project_name` | carepath-ai | Project name prefix |
| `environment` | prod | Environment name |
| `aws_region` | us-east-1 | AWS region |
| `backend_task_cpu` | 512 | Backend CPU units |
| `backend_task_memory` | 1024 | Backend memory (MB) |
| `ml_task_cpu` | 1024 | ML CPU units |
| `ml_task_memory` | 2048 | ML memory (MB) |
| `db_instance_class` | db.t3.micro | RDS instance type |
| `ecs_instance_type` | t3.medium | ECS instance type |

## 🚨 Emergency Procedures

### Service Down
```bash
# 1. Check logs
aws logs tail /ecs/carepath-ai-backend-prod --follow

# 2. Check task status
aws ecs describe-services --cluster [CLUSTER] --services [SERVICE]

# 3. Restart service
aws ecs update-service --cluster [CLUSTER] --service [SERVICE] --force-new-deployment
```

### High Memory Usage
```bash
# 1. Check current resource usage in CloudWatch
# 2. Scale up memory in terraform-v2/variables.tf
backend_task_memory = 2048

# 3. Apply changes
terraform apply
```

### Database Connection Issues
```bash
# 1. Check RDS status
aws rds describe-db-instances --db-instance-identifier [DB_ID]

# 2. Check security group rules
aws ec2 describe-security-groups --group-ids [SG_ID]

# 3. Test connectivity from ECS task
# SSH to ECS instance and run:
telnet [RDS_ENDPOINT] 5432
```

---

**Quick Reference Version**: 1.0  
**Last Updated**: 2026-08-23
