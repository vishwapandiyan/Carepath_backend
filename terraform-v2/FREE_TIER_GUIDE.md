# 💰 AWS Free Tier Optimized Deployment Guide

## Overview

This Terraform configuration has been optimized for **AWS Free Tier** eligibility, minimizing costs while maintaining separate Backend and ML Docker containers.

## 🎯 Free Tier Optimizations Applied

### ✅ What's FREE (12 months)

| Resource | Free Tier Allowance | Our Usage |
|----------|---------------------|-----------|
| **EC2** | 750 hours/month of t2.micro | 1 × t2.micro (100% FREE) ✅ |
| **RDS** | 750 hours/month of db.t3.micro | 1 × db.t3.micro (100% FREE) ✅ |
| **S3** | 5 GB standard storage | ~100 MB (100% FREE) ✅ |
| **CloudFront** | 50 GB data transfer out | Usage-based (likely FREE) ✅ |
| **Data Transfer** | 100 GB/month out | Usage-based (likely FREE) ✅ |

### ⚠️ What's NOT FREE

| Resource | Why Not Free | Monthly Cost |
|----------|--------------|--------------|
| **ALB** | No free tier | ~$16/month |
| **ECR** | Free <500MB, then $0.10/GB | ~$1-2/month |
| **Secrets Manager** | 30-day trial, then paid | ~$0.80/month |
| **CloudWatch Logs** | Minimal free tier | ~$1/month |

### 📊 Total Estimated Cost

**First 12 months:** ~$18-22/month  
**After 12 months:** ~$35-45/month (when EC2 and RDS free tier expires)

## 🏗️ Architecture (Free Tier Version)

```
┌──────────────────────────────────────────────────────────┐
│              AWS Free Tier Architecture                   │
│                                                            │
│  ┌────────────────┐                                       │
│  │  CloudFront    │ ◄─── HTTPS (FREE: 50GB/month)        │
│  │  (Frontend)    │                                       │
│  └────────┬───────┘                                       │
│           │                                               │
│  ┌────────▼───────┐                                       │
│  │   S3 Bucket    │ ◄─── FREE: 5GB storage               │
│  │  (React App)   │                                       │
│  └────────────────┘                                       │
│                                                            │
│  ┌────────────────┐                                       │
│  │  CloudFront    │ ◄─── HTTPS (FREE: 50GB/month)        │
│  │  (API)         │                                       │
│  └────────┬───────┘                                       │
│           │                                               │
│  ┌────────▼───────────────┐                               │
│  │  Single ALB            │ ◄─── $16/month (NOT FREE)    │
│  │  Path-based Routing    │                               │
│  └────────┬───────────────┘                               │
│           │                                               │
│    ┌──────┴──────────────────────────────┐                │
│    │                                     │                │
│    │  / (root)    /ml/* (ML service)    │                │
│    │                                     │                │
│  ┌─▼──────────────┐      ┌──────────────▼─┐              │
│  │ ECS Cluster    │      │  ECS Cluster   │              │
│  │                │      │                │              │
│  │ ┌────────────┐ │      │ ┌────────────┐ │              │
│  │ │  Backend   │ │      │ │  ML Svc    │ │              │
│  │ │  Port 8000 │ │      │ │  Port 8001 │ │              │
│  │ │  256 CPU   │ │      │ │  256 CPU   │ │              │
│  │ │  512 MB    │ │      │ │  512 MB    │ │              │
│  │ └────────────┘ │      │ └────────────┘ │              │
│  │                │      │                │              │
│  │  Single t2.micro EC2 (750 hrs FREE)   │              │
│  └────────────────┴──────┴────────────────┘              │
│                     │                                     │
│           ┌─────────▼──────────┐                          │
│           │  RDS PostgreSQL    │ ◄─── FREE: 750 hrs/month │
│           │  db.t3.micro       │                          │
│           │  20 GB storage     │                          │
│           └────────────────────┘                          │
│                                                            │
└──────────────────────────────────────────────────────────┘
```

## 🔑 Key Changes from Production Version

### 1. **Single ALB Instead of Two**
- **Before**: 2 ALBs (Public + Internal) = ~$32/month
- **After**: 1 ALB with path-based routing = ~$16/month
- **Savings**: ~$16/month

**How it works:**
- Backend API: `http://alb-domain/` → Backend service
- ML Service: `http://alb-domain/ml/*` → ML service
- Backend calls ML via: `http://alb-domain/ml/predict`

### 2. **Single t2.micro Instance**
- **Before**: 2 × t3.medium = ~$60/month
- **After**: 1 × t2.micro = FREE (750 hours/month)
- **Savings**: ~$60/month

**Trade-offs:**
- ⚠️ Both containers run on same host
- ⚠️ Limited resources (1 vCPU, 1GB RAM total)
- ⚠️ No high availability (single instance)
- ✅ Perfect for development/testing
- ✅ Handles low-moderate traffic

### 3. **Reduced Container Resources**
- **Backend**: 256 CPU units, 512 MB RAM (was 512/1024)
- **ML**: 256 CPU units, 512 MB RAM (was 1024/2048)

**Trade-offs:**
- ⚠️ Slower ML inference
- ⚠️ Lower concurrent request capacity
- ⚠️ May need model optimization
- ✅ Fits in t2.micro limits
- ✅ Still functional for testing

### 4. **db.t3.micro RDS**
- Instance class already optimized for free tier
- 20 GB storage (within free tier limits)
- 750 hours/month = 100% FREE

## 📋 Deployment Instructions

### Prerequisites
- AWS Account (with free tier available)
- Terraform >= 1.5.0
- AWS CLI configured
- Docker installed

### Step 1: Deploy Infrastructure

```bash
cd terraform-v2
terraform init
terraform plan  # Review costs!
terraform apply
```

**Expected time:** 10-15 minutes

### Step 2: Build and Push Docker Images

```bash
./build-and-push.sh
```

This script will:
1. Build backend Docker image
2. Build ML Docker image
3. Push both to ECR
4. Update ECS services

### Step 3: Verify Deployment

```bash
# Get backend URL
BACKEND_URL=$(terraform output -raw backend_api_url)

# Test backend
curl $BACKEND_URL/health

# Test ML service (via backend path)
curl $BACKEND_URL/ml/health
```

### Step 4: Deploy Frontend

```bash
cd ../../CarePath_CTS

# Set backend URL
echo "VITE_API_URL=$BACKEND_URL" > .env.production

# Build and deploy
npm run build
aws s3 sync dist/ s3://$(cd ../CarepathAI_backend/terraform-v2 && terraform output -raw s3_frontend_bucket_name)/ --delete

# Invalidate CloudFront cache
CF_ID=$(cd ../CarepathAI_backend/terraform-v2 && terraform output -raw cloudfront_frontend_id)
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

## 💡 Free Tier Best Practices

### 1. Monitor Your Usage

```bash
# Check EC2 hours used
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY \
  --metrics UsageQuantity \
  --filter file://ec2-filter.json

# Watch for CloudWatch alarms
aws cloudwatch describe-alarms
```

### 2. Optimize Costs

**Stop non-production resources:**
```bash
# Stop ECS services when not in use
aws ecs update-service \
  --cluster carepath-ai-cluster-prod \
  --service carepath-ai-backend-service-prod \
  --desired-count 0

aws ecs update-service \
  --cluster carepath-ai-cluster-prod \
  --service carepath-ai-ml-service-prod \
  --desired-count 0

# Stop RDS (manual in console or via CLI)
aws rds stop-db-instance \
  --db-instance-identifier carepath-ai-db-prod
```

**Resume when needed:**
```bash
# Start services
aws ecs update-service --cluster [CLUSTER] --service [SERVICE] --desired-count 1
aws rds start-db-instance --db-instance-identifier [DB_ID]
```

### 3. Set Up Billing Alerts

```bash
# Create billing alarm for $25/month
aws cloudwatch put-metric-alarm \
  --alarm-name carepath-billing-alarm \
  --alarm-description "Alert when monthly charges exceed $25" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 21600 \
  --evaluation-periods 1 \
  --threshold 25 \
  --comparison-operator GreaterThanThreshold
```

### 4. Clean Up Unused Resources

```bash
# Remove old ECR images
aws ecr batch-delete-image \
  --repository-name carepath-ai-backend-prod \
  --image-ids imageTag=old-tag

# Clean up old CloudWatch logs
aws logs delete-log-group \
  --log-group-name /ecs/old-service
```

## ⚠️ Limitations of Free Tier Setup

### Performance
- **Single instance**: No redundancy or load distribution
- **Limited CPU/Memory**: May struggle with high load
- **Slower ML inference**: Reduced resources affect model performance

### Availability
- **No auto-scaling**: Fixed at 1 instance
- **Single point of failure**: If EC2 instance fails, entire app is down
- **No Multi-AZ RDS**: Database in single availability zone

### Capacity
- **Concurrent requests**: Limited by single t2.micro
- **ML model size**: Large models may not fit in 512 MB
- **Response time**: May be slower under load

## 🚀 Upgrade Path (When You Outgrow Free Tier)

### Option 1: Keep Architecture, Upgrade Resources
```hcl
# In variables.tf
ecs_instance_type     = "t3.small"    # $15/month
backend_task_cpu      = 512
backend_task_memory   = 1024
ml_task_cpu           = 512
ml_task_memory        = 1024
```
**Cost:** ~$35-40/month

### Option 2: Add Auto-Scaling
```hcl
# In ecs.tf ASG
desired_capacity = 2
min_size         = 1
max_size         = 3
```
**Cost:** ~$50-70/month (variable)

### Option 3: Production-Grade (Separate ALBs)
- Use the original v2 architecture
- 2 ALBs (Public + Internal)
- t3.medium instances
- Multi-AZ RDS
**Cost:** ~$120-150/month

## 📊 Cost Breakdown (First 12 Months)

```
Monthly Recurring Costs:
├─ ALB                    $16.00  ⚠️ NOT FREE
├─ ECR Storage            $ 1.50  ⚠️ NOT FREE (if >500MB)
├─ Secrets Manager        $ 0.80  ⚠️ NOT FREE (after 30 days)
├─ CloudWatch Logs        $ 1.00  ⚠️ NOT FREE (exceeds limits)
├─ EC2 (t2.micro)         $ 0.00  ✅ FREE (750 hrs)
├─ RDS (db.t3.micro)      $ 0.00  ✅ FREE (750 hrs)
├─ S3 Storage             $ 0.00  ✅ FREE (<5GB)
├─ CloudFront             $ 0.00  ✅ FREE (<50GB)
└─ Data Transfer          $ 0.00  ✅ FREE (<100GB)
                         --------
TOTAL:                    ~$19.30/month
```

## 🎓 When to Use This Setup

### ✅ Good For:
- Development and testing
- Learning AWS and containers
- Low-traffic applications (<1000 requests/day)
- Proof of concept
- Side projects
- Portfolio projects
- Budget-conscious startups

### ❌ Not Good For:
- Production applications with SLA requirements
- High-traffic applications
- Mission-critical systems
- Applications requiring 99.9% uptime
- Heavy ML inference workloads
- Multiple concurrent users (>10)

## 🔧 Troubleshooting Free Tier Issues

### Issue 1: Out of Memory
**Symptom**: Containers keep restarting  
**Solution**: Reduce container memory or optimize application
```bash
# Check container memory usage
aws ecs describe-tasks --cluster [CLUSTER] --tasks [TASK_ARN]
```

### Issue 2: Slow Performance
**Symptom**: High response times  
**Solution**: Optimize code, reduce ML model size, or upgrade instance
```bash
# Monitor CPU usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=carepath-ai-cluster-prod
```

### Issue 3: Exceeded Free Tier
**Symptom**: Unexpected charges  
**Solution**: Check AWS Cost Explorer and reduce usage
```bash
# View cost breakdown
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity DAILY \
  --metrics BlendedCost
```

## 📚 Additional Resources

- [AWS Free Tier Details](https://aws.amazon.com/free/)
- [ECS Pricing Calculator](https://aws.amazon.com/ecs/pricing/)
- [Cost Optimization Guide](https://aws.amazon.com/pricing/cost-optimization/)
- [Billing Dashboard](https://console.aws.amazon.com/billing/)

---

**Free Tier Version**: 2.1.0  
**Last Updated**: 2026-08-23  
**Estimated Monthly Cost**: $18-22 (with free tier)
