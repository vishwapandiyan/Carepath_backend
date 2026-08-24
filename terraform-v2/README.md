# CarePath AI - Terraform v2 Infrastructure

## What's New in v2?

This is an improved version of the CarePath AI infrastructure with **separate Docker containers** for Backend and ML services, **optimized for AWS Free Tier**.

### 🆓 Free Tier Optimizations

**Cost: ~$18-22/month** (vs ~$120/month in original production version)

- ✅ **1 × ALB** instead of 2 (saves ~$16/month)
- ✅ **1 × t2.micro** (100% FREE - 750 hours/month)
- ✅ **Path-based routing** for Backend and ML services
- ✅ **Minimal resources** while maintaining separation
- ✅ **db.t3.micro RDS** (100% FREE - 750 hours/month)

**Perfect for:**
- Development and testing
- Learning AWS
- Low-traffic applications
- Budget-conscious startups
- Portfolio projects

### Architecture Changes

#### v1 (Original)
```
┌─────────────────────────┐
│   Single ECS Service    │
│                         │
│  ┌───────────────────┐  │
│  │   Backend + ML    │  │
│  │   (Combined)      │  │
│  │   Port 8000       │  │
│  └───────────────────┘  │
└─────────────────────────┘
```

#### v2 (Current - Free Tier Optimized)
```
┌─────────────────────────────────────────────┐
│  Single t2.micro EC2 (FREE TIER)            │
│                                             │
│  ┌─────────────┐  ┌─────────────┐          │
│  │  Backend    │  │  ML Service │          │
│  │  (FastAPI)  │  │  (Inference)│          │
│  │  Port 8000  │  │  Port 8001  │          │
│  │  256 CPU    │  │  256 CPU    │          │
│  │  512 MB     │  │  512 MB     │          │
│  └──────┬──────┘  └──────┬──────┘          │
│         │                │                 │
│         └────────┬───────┘                 │
│                  │                         │
│     ┌────────────▼─────────────┐           │
│     │   Single ALB             │           │
│     │   Path-based routing:    │           │
│     │   / → Backend            │           │
│     │   /ml/* → ML             │           │
│     └──────────────────────────┘           │
└─────────────────────────────────────────────┘

💰 Cost: ~$18-22/month (vs ~$120/month)
```

## Key Benefits

### 1. **Independent Scaling**
- Scale Backend API separately from ML inference
- ML service can have more CPU/memory for model inference
- Backend can handle more concurrent requests independently

### 2. **Better Resource Management**
- ML models loaded only in ML service (reduced memory footprint)
- Backend service is lighter and faster to start
- More efficient resource utilization

### 3. **Improved Security**
- ML service is **internal-only** (not exposed to internet)
- Backend acts as gateway to ML service
- Reduced attack surface

### 4. **Easier Maintenance**
- Update ML models without redeploying backend
- Update backend logic without restarting ML service
- Independent logging and monitoring

### 5. **Cost Optimization**
- Backend: Can use smaller instances (t3.small)
- ML: Needs more resources only for inference (t3.medium/large)
- Scale down ML service during low-traffic periods

## Quick Comparison

| Feature | v1 (Original) | v2 (Free Tier) |
|---------|---------------|----------------|
| Docker Containers | 1 (Combined) | 2 (Backend + ML) |
| Scaling | Single service | Independent (limited) |
| ML Service Access | Public | Path-based routing |
| Resource Efficiency | Medium | Optimized |
| Deployment Complexity | Simple | Moderate |
| Maintenance | Harder | Easier |
| Cost Control | Limited | Excellent |
| **Monthly Cost** | **~$52** | **~$18-22** ✨ |

## Infrastructure Components

### Network Layer
- **VPC**: 10.0.0.0/16
- **Public Subnets**: 2 (for ALBs and ECS instances)
- **Private Subnets**: 2 (for RDS database)
- **Availability Zones**: us-east-1a, us-east-1b

### Compute Layer
- **ECS Cluster**: Single cluster running both services
- **EC2 Instance**: 1 × t2.micro (FREE TIER - 750 hours/month)
- **Backend Service**: 
  - CPU: 256 units (reduced for free tier)
  - Memory: 512 MB (reduced for free tier)
  - Desired Count: 1
  - Port: 8000
- **ML Service**:
  - CPU: 256 units (reduced for free tier)
  - Memory: 512 MB (reduced for free tier)
  - Desired Count: 1
  - Port: 8001

### Load Balancers
- **Single ALB**: Routes traffic to both services via path-based routing
  - `/` → Backend service
  - `/ml/*` → ML service
  - **Cost**: ~$16/month (only paid component)

### Storage Layer
- **RDS PostgreSQL**: 
  - Instance: db.t3.micro
  - Storage: 20 GB (auto-scaling to 100 GB)
  - Backup: 7 days retention
  - Multi-AZ: Disabled (enable for production)

### Container Registry
- **Backend ECR**: `carepath-ai-backend-prod`
- **ML ECR**: `carepath-ai-ml-prod`

### CDN & Static Hosting
- **CloudFront (Frontend)**: Serves React application from S3
- **CloudFront (API)**: HTTPS endpoint for Backend API
- **S3 Bucket**: Static frontend files

### Security
- **Secrets Manager**: Database password, JWT secret
- **Security Groups**: 
  - Backend tasks: Allow from public ALB
  - ML tasks: Allow from backend tasks only
  - RDS: Allow from backend and ML tasks
  - ALBs: Allow HTTP/HTTPS from internet
- **IAM Roles**: Task execution and task roles with least privilege

## Files Structure

```
terraform-v2/
├── main.tf                 # Main Terraform configuration
├── variables.tf            # Input variables
├── outputs.tf             # Output values
├── vpc.tf                 # VPC, subnets, security groups
├── ecr.tf                 # Docker image repositories
├── ecs.tf                 # ECS cluster, services, tasks
├── alb.tf                 # Application Load Balancers
├── rds.tf                 # PostgreSQL database
├── iam.tf                 # IAM roles and policies
├── s3-cloudfront.tf       # Frontend hosting
├── cloudfront-api.tf      # API CDN
├── Dockerfile.backend     # Backend service container
├── Dockerfile.ml          # ML service container
├── ml_service.py          # ML service application
├── DEPLOYMENT.md          # Detailed deployment guide
└── README.md             # This file
```

## Prerequisites

- Terraform >= 1.5.0
- AWS CLI >= 2.0
- Docker >= 20.0
- AWS Account with appropriate permissions

## Quick Start

1. **Initialize Terraform:**
   ```bash
   cd terraform-v2
   terraform init
   ```

2. **Review Variables:**
   ```bash
   # Edit variables.tf or create terraform.tfvars
   vim terraform.tfvars
   ```

3. **Deploy Infrastructure:**
   ```bash
   terraform plan
   terraform apply
   ```

4. **Build and Push Images:**
   ```bash
   # See DEPLOYMENT.md for detailed instructions
   ./build-and-push.sh
   ```

5. **Access Your Application:**
   ```bash
   terraform output frontend_url
   terraform output backend_api_url
   ```

For detailed deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## Cost Estimate

**Monthly costs** (us-east-1 region, with AWS Free Tier):

| Service | Configuration | Free Tier | Monthly Cost |
|---------|--------------|-----------|--------------|
| ECS (t2.micro × 1) | 750 hours | ✅ FREE | $0 |
| RDS (db.t3.micro) | 750 hours | ✅ FREE | $0 |
| ALB × 1 | Load Balancer | ❌ Paid | ~$16 |
| CloudFront | CDN + Data Transfer | ✅ 50GB FREE | ~$0 |
| S3 | 5GB storage | ✅ FREE | ~$0 |
| ECR | Container storage | ❌ >500MB | ~$1-2 |
| Secrets Manager | 2 secrets | ❌ Paid | ~$0.80 |
| CloudWatch | Logs | ❌ Exceeds limits | ~$1 |
| **Total (First 12 months)** | | | **~$18-22/month** |
| **Total (After free tier)** | | | **~$35-45/month** |

*Estimates exclude data transfer costs which vary by usage.*

### 💡 Cost Optimization Tips
1. **Stop when not in use**: ECS services can be scaled to 0
2. **Use spot instances**: After free tier expires (not in this config)
3. **Optimize images**: Smaller Docker images = less ECR costs
4. **Monitor usage**: Set up billing alarms at $25/month

**See [FREE_TIER_GUIDE.md](./FREE_TIER_GUIDE.md) for detailed cost breakdown and optimization strategies.**

## Monitoring

### CloudWatch Logs
- `/ecs/carepath-ai-backend-prod`
- `/ecs/carepath-ai-ml-prod`

### Metrics
- ECS Container Insights (enabled)
- ALB health checks
- RDS performance metrics
- CloudFront access logs

## Scaling Guide

### Backend Service
```bash
aws ecs update-service \
  --cluster carepath-ai-cluster-prod \
  --service carepath-ai-backend-service-prod \
  --desired-count 3
```

### ML Service
```bash
aws ecs update-service \
  --cluster carepath-ai-cluster-prod \
  --service carepath-ai-ml-service-prod \
  --desired-count 2
```

### Database
```hcl
# In terraform.tfvars
db_instance_class = "db.t3.small"  # Upgrade instance
```

## Security Considerations

✅ **Implemented:**
- Secrets stored in AWS Secrets Manager
- RDS in private subnet (no public access)
- ML service internal-only (not exposed to internet)
- HTTPS via CloudFront (valid SSL certificates)
- Security groups with least privilege access
- IAM roles with minimal permissions
- Encryption at rest for RDS and S3

⚠️ **Production Recommendations:**
- Enable RDS Multi-AZ for high availability
- Enable RDS encryption with KMS
- Implement WAF rules for CloudFront
- Enable MFA for AWS accounts
- Set up CloudTrail for audit logging
- Enable GuardDuty for threat detection
- Implement VPC Flow Logs
- Use AWS Certificate Manager for custom domains

## Troubleshooting

### Common Issues

**1. ECS Tasks Not Starting**
- Check CloudWatch logs
- Verify Docker images are pushed to ECR
- Confirm IAM roles have correct permissions
- Check security group rules

**2. Backend Can't Reach ML Service**
- Verify internal ALB DNS is correct in backend environment
- Check security group allows backend → ML traffic
- Confirm ML service is healthy

**3. Database Connection Failed**
- Verify RDS security group allows ECS task access
- Check database credentials in Secrets Manager
- Confirm RDS is in running state

**4. Frontend Not Loading**
- Check S3 bucket has files
- Verify CloudFront distribution is deployed
- Confirm CORS settings in backend

For detailed troubleshooting, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## Migrating from v1 to v2

If you have existing v1 infrastructure:

1. **Export Current Data:**
   ```bash
   pg_dump -h [old-rds-endpoint] -U dbadmin carepath_db > backup.sql
   ```

2. **Deploy v2 Infrastructure:**
   ```bash
   cd terraform-v2
   terraform apply
   ```

3. **Import Data:**
   ```bash
   psql -h [new-rds-endpoint] -U dbadmin carepath_db < backup.sql
   ```

4. **Update DNS/Domain:**
   - Point domain to new CloudFront distribution
   - Update API endpoint in frontend

5. **Destroy v1 Infrastructure:**
   ```bash
   cd terraform
   terraform destroy
   ```

## Contributing

When making changes to infrastructure:

1. Create a new branch
2. Make changes to `.tf` files
3. Run `terraform fmt` to format code
4. Run `terraform validate` to validate syntax
5. Test in dev environment first
6. Create pull request with detailed description

## License

This infrastructure code is part of the CarePath AI project.

## Support

For questions or issues:
- Check [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed guides
- Review CloudWatch logs for runtime errors
- Check AWS Console for service status
- Contact infrastructure team

---

**Version**: 2.0.0  
**Created**: 2026-08-23  
**Author**: CarePath AI Infrastructure Team
