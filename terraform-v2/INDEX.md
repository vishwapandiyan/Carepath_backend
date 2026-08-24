# Terraform v2 - Complete File Index

## 📁 Overview

This directory contains the complete Terraform infrastructure for CarePath AI with **separate Docker containers** for Backend and ML services.

## 📋 File Structure

```
terraform-v2/
├── 🔧 Terraform Configuration Files
│   ├── main.tf                          # Main Terraform configuration
│   ├── variables.tf                     # Input variables and defaults
│   ├── outputs.tf                       # Output values and deployment info
│   ├── vpc.tf                           # VPC, subnets, security groups
│   ├── ecr.tf                           # ECR repositories for Docker images
│   ├── ecs.tf                           # ECS cluster, services, tasks
│   ├── alb.tf                           # Application Load Balancers
│   ├── rds.tf                           # PostgreSQL database
│   ├── iam.tf                           # IAM roles and policies
│   ├── s3-cloudfront.tf                 # Frontend static hosting
│   └── cloudfront-api.tf                # API CDN configuration
│
├── 🐳 Docker Configuration Files
│   ├── Dockerfile.backend               # Backend service container
│   ├── Dockerfile.ml                    # ML service container
│   └── ml_service.py                    # ML service application
│
├── 📚 Documentation Files
│   ├── README.md                        # Main documentation
│   ├── DEPLOYMENT.md                    # Detailed deployment guide
│   ├── ARCHITECTURE_COMPARISON.md       # v1 vs v2 comparison
│   ├── QUICK_REFERENCE.md              # Command reference guide
│   └── INDEX.md                         # This file
│
└── 🛠️ Helper Scripts
    └── build-and-push.sh                # Build and deploy script
```

## 📄 File Descriptions

### Terraform Configuration Files

#### `main.tf`
**Purpose**: Main Terraform configuration with providers and core resources  
**Contains**:
- Terraform and provider version requirements
- AWS provider configuration
- Random password generators for RDS and JWT
- Secrets Manager resources for secure credential storage
- Data sources for AWS account and region info

#### `variables.tf`
**Purpose**: Input variables for customizing deployment  
**Contains**:
- Project configuration (name, environment, region)
- VPC and networking settings
- Database configuration (instance class, storage, credentials)
- ECS configuration (instance types, task sizes)
- Backend service settings (CPU, memory, ports)
- ML service settings (CPU, memory, ports)
- Common tags for resource management

#### `outputs.tf`
**Purpose**: Output values displayed after deployment  
**Contains**:
- Database connection information
- ECR repository URLs for Docker images
- ECS cluster and service names
- Load balancer DNS names and URLs
- CloudFront distribution IDs and domains
- S3 bucket names
- Security group IDs
- Deployment instructions and next steps

#### `vpc.tf`
**Purpose**: Network infrastructure configuration  
**Contains**:
- VPC with DNS support
- Public subnets (2 AZs) for ALBs and ECS
- Private subnets (2 AZs) for RDS
- Internet Gateway
- Route tables and associations
- Security groups for:
  - Backend ECS tasks
  - ML ECS tasks
  - Application Load Balancers
  - RDS database
- DB subnet group

#### `ecr.tf`
**Purpose**: Docker container registries  
**Contains**:
- Backend ECR repository with encryption
- ML ECR repository with encryption
- Image scanning on push
- Lifecycle policies (keep last 5 images)

#### `ecs.tf`
**Purpose**: Container orchestration setup  
**Contains**:
- ECS cluster with Container Insights
- CloudWatch log groups for Backend and ML
- Backend task definition with:
  - Container configuration
  - Environment variables
  - Secrets integration
  - Health checks
  - Log configuration
- ML task definition with similar setup
- EC2 launch template for ECS hosts
- Auto Scaling Group
- ECS services for Backend and ML

#### `alb.tf`
**Purpose**: Load balancing configuration  
**Contains**:
- Public ALB for Backend API (internet-facing)
- Internal ALB for ML Service (private only)
- Target groups with health checks
- HTTP listeners for routing
- Port 80 and 443 configuration

#### `rds.tf`
**Purpose**: PostgreSQL database configuration  
**Contains**:
- RDS PostgreSQL 15.8 instance
- Storage configuration (gp3, encryption)
- Network configuration (private subnets)
- Backup settings (7-day retention)
- Maintenance windows
- Monitoring and logging

#### `iam.tf`
**Purpose**: Permission and access control  
**Contains**:
- ECS task execution role (for pulling images, writing logs)
- ECS task role (for application permissions)
- EC2 instance role for ECS hosts
- Policies for:
  - Secrets Manager access
  - ECR image pulling
  - CloudWatch Logs
  - S3 access for ML models
- Instance profile for EC2

#### `s3-cloudfront.tf`
**Purpose**: Frontend static site hosting  
**Contains**:
- S3 bucket for React application
- Bucket policies for CloudFront OAC
- Website configuration
- CloudFront distribution with:
  - Origin Access Control
  - HTTPS redirect
  - Custom error pages for SPA routing
  - Caching configuration

#### `cloudfront-api.tf`
**Purpose**: API CDN and HTTPS endpoint  
**Contains**:
- CloudFront distribution for Backend API
- Custom origin configuration (ALB)
- Cache behavior settings
- HTTPS enforcement
- Header forwarding for API requests

### Docker Configuration Files

#### `Dockerfile.backend`
**Purpose**: Backend API service container  
**Contains**:
- Python 3.11 slim base image
- System dependencies (curl, gcc, postgresql-client)
- Python dependencies (FastAPI, SQLAlchemy, etc.)
- Application code (app/, migrations/)
- Non-root user for security
- Health check configuration
- Uvicorn server with 2 workers on port 8000

**Key Features**:
- Lightweight (excludes heavy ML libraries)
- Fast startup time
- Optimized for API serving

#### `Dockerfile.ml`
**Purpose**: ML inference service container  
**Contains**:
- Python 3.11 slim base image
- System dependencies including ML build tools
- Full Python dependencies (including ML libraries)
- Application code + ML packages
- Model cache directory
- Non-root user for security
- Health check with longer startup period
- Uvicorn server with 1 worker on port 8001

**Key Features**:
- Includes ML libraries (scikit-learn, xgboost, etc.)
- More CPU/memory allocation
- Optimized for inference

#### `ml_service.py`
**Purpose**: Standalone ML inference application  
**Contains**:
- FastAPI application for ML predictions
- Endpoints for:
  - `/health` - Health check
  - `/predict/readmission` - Readmission risk prediction
  - `/predict/post-discharge` - Post-discharge prediction
  - `/models` - List available models
- Request/response models
- Error handling
- Logging configuration

### Documentation Files

#### `README.md`
**Purpose**: Main project documentation  
**Contains**:
- Overview of v2 architecture
- Key benefits and improvements
- Quick comparison with v1
- Infrastructure components description
- File structure overview
- Prerequisites and quick start
- Cost estimates
- Monitoring and scaling guides
- Security considerations
- Troubleshooting tips

**Target Audience**: Developers, DevOps engineers, new team members

#### `DEPLOYMENT.md`
**Purpose**: Comprehensive deployment guide  
**Contains**:
- Detailed architecture diagrams
- Step-by-step deployment instructions
- Docker build and push commands
- Service update procedures
- Frontend deployment process
- Monitoring and logging setup
- Scaling strategies
- Cost optimization tips
- Troubleshooting procedures
- Backup and recovery procedures
- Security best practices

**Target Audience**: DevOps engineers, System administrators

#### `ARCHITECTURE_COMPARISON.md`
**Purpose**: Compare v1 and v2 architectures  
**Contains**:
- Side-by-side architecture diagrams
- Detailed feature comparison tables
- Resource allocation comparison
- Security analysis
- Cost analysis
- Performance benchmarks
- Real-world scenarios
- Migration guide from v1 to v2
- Use case recommendations

**Target Audience**: Technical leads, Architects, Decision makers

#### `QUICK_REFERENCE.md`
**Purpose**: Command cheat sheet  
**Contains**:
- Quick start commands
- Docker commands
- Service update commands
- Monitoring commands
- Database operations
- Frontend deployment
- Troubleshooting commands
- Terraform operations
- Emergency procedures
- Variable reference

**Target Audience**: All team members for daily operations

#### `INDEX.md`
**Purpose**: File navigation and reference  
**Contains**:
- Complete file structure
- File descriptions
- Use cases for each file
- Relationships between files
- When to modify each file

**Target Audience**: New team members, Documentation reference

### Helper Scripts

#### `build-and-push.sh`
**Purpose**: Automated Docker build and deployment  
**Contains**:
- Color-coded output for readability
- ECR repository URL extraction from Terraform
- ECR login automation
- Backend image build and push
- ML image build and push
- ECS service update
- Deployment status monitoring
- Error handling and validation

**Usage**:
```bash
cd terraform-v2
./build-and-push.sh
```

**Features**:
- Automated entire deployment process
- Error checking at each step
- Clear status messages
- Deployment verification

## 🎯 Common Use Cases

### 1. Initial Deployment
**Files to use**:
1. `variables.tf` - Review and customize settings
2. `main.tf`, `*.tf` - Infrastructure definition
3. Run: `terraform init && terraform apply`
4. `build-and-push.sh` - Build and deploy containers
5. `DEPLOYMENT.md` - Follow step-by-step guide

### 2. Update Backend Code
**Files to modify**:
1. Backend application code (in `/app`)
2. `Dockerfile.backend` - If dependencies changed
3. Run: `./build-and-push.sh` or manual docker commands

### 3. Update ML Models
**Files to modify**:
1. ML code or models
2. `Dockerfile.ml` - If dependencies changed
3. `ml_service.py` - If API endpoints changed
4. Run: `./build-and-push.sh`

### 4. Scale Services
**Files to modify**:
1. `variables.tf` - Update `backend_desired_count` or `ml_desired_count`
2. Run: `terraform apply`
3. Or use AWS CLI commands from `QUICK_REFERENCE.md`

### 5. Add Environment Variable
**Files to modify**:
1. `ecs.tf` - Add to `environment` block in task definition
2. Run: `terraform apply`
3. Force new deployment with AWS CLI

### 6. Modify Security Rules
**Files to modify**:
1. `vpc.tf` - Update security group rules
2. Run: `terraform plan` then `terraform apply`

### 7. Change Database Size
**Files to modify**:
1. `variables.tf` - Update `db_instance_class` or `db_allocated_storage`
2. Run: `terraform apply`
3. Note: This may cause downtime

### 8. Troubleshooting
**Files to reference**:
1. `QUICK_REFERENCE.md` - Common commands
2. `DEPLOYMENT.md` - Troubleshooting section
3. `outputs.tf` - Get resource names and URLs

## 🔄 Relationships Between Files

```
main.tf
  ├─→ variables.tf (reads input variables)
  ├─→ vpc.tf (uses VPC resources)
  ├─→ ecr.tf (references ECR URLs)
  ├─→ ecs.tf (uses cluster and services)
  ├─→ rds.tf (uses database endpoint)
  ├─→ iam.tf (uses IAM roles)
  └─→ outputs.tf (exports resource info)

ecs.tf
  ├─→ ecr.tf (ECR repository URLs for images)
  ├─→ vpc.tf (security groups, subnets)
  ├─→ alb.tf (target groups)
  ├─→ rds.tf (database endpoint)
  └─→ iam.tf (task execution and task roles)

Dockerfile.backend
  └─→ build-and-push.sh (automated build)

Dockerfile.ml
  ├─→ ml_service.py (ML application)
  └─→ build-and-push.sh (automated build)

DEPLOYMENT.md
  ├─→ Dockerfile.backend (build instructions)
  ├─→ Dockerfile.ml (build instructions)
  ├─→ build-and-push.sh (automation reference)
  └─→ QUICK_REFERENCE.md (command reference)
```

## 📝 When to Modify Each File

| File | Modify When... |
|------|----------------|
| `main.tf` | Changing providers, adding core resources |
| `variables.tf` | Adding new configuration options |
| `outputs.tf` | Need to expose new resource information |
| `vpc.tf` | Changing network topology, security rules |
| `ecr.tf` | Adding new container repositories |
| `ecs.tf` | Changing service configuration, resource allocation |
| `alb.tf` | Modifying load balancer rules, health checks |
| `rds.tf` | Changing database configuration |
| `iam.tf` | Adding new permissions or roles |
| `s3-cloudfront.tf` | Changing frontend hosting configuration |
| `cloudfront-api.tf` | Modifying API CDN settings |
| `Dockerfile.backend` | Updating backend dependencies or setup |
| `Dockerfile.ml` | Updating ML dependencies or models |
| `ml_service.py` | Adding new ML endpoints or models |
| `build-and-push.sh` | Changing build/deploy process |

## 🚀 Getting Started

1. **First Time Setup**:
   - Read `README.md` for overview
   - Review `ARCHITECTURE_COMPARISON.md` to understand v2 benefits
   - Follow `DEPLOYMENT.md` for deployment

2. **Daily Operations**:
   - Use `QUICK_REFERENCE.md` for common commands
   - Use `build-and-push.sh` for deployments

3. **Troubleshooting**:
   - Check `QUICK_REFERENCE.md` for quick commands
   - Refer to `DEPLOYMENT.md` troubleshooting section

4. **Making Changes**:
   - Modify appropriate `.tf` files
   - Run `terraform plan` to preview
   - Run `terraform apply` to deploy

## 📞 Support

For questions about specific files:
- **Infrastructure**: Check Terraform `.tf` files
- **Containers**: Check `Dockerfile.*` files
- **Deployment**: Check `DEPLOYMENT.md`
- **Commands**: Check `QUICK_REFERENCE.md`
- **Architecture**: Check `ARCHITECTURE_COMPARISON.md`

---

**Index Version**: 1.0  
**Last Updated**: 2026-08-23  
**Total Files**: 22 (11 Terraform, 3 Docker, 5 Documentation, 1 Script, 2 Metadata)
