# =============================================================================
# Variables for Hospital Readmission System AWS Deployment
# =============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "readmission"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "availability_zone" {
  description = "Availability zone for resources"
  type        = string
  default     = "us-east-1a"
}

variable "availability_zone_2" {
  description = "Second availability zone for RDS"
  type        = string
  default     = "us-east-1b"
}

# Database Configuration
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "readmission_db"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "dbadmin"
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automated backups"
  type        = number
  default     = 7
}

# ECS Configuration
variable "ecs_instance_type" {
  description = "EC2 instance type for ECS"
  type        = string
  default     = "t2.micro"
}

variable "ecs_task_cpu" {
  description = "CPU units for ECS task"
  type        = number
  default     = 512
}

variable "ecs_task_memory" {
  description = "Memory (MB) for ECS task"
  type        = number
  default     = 768
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 8000
}

# Frontend Configuration
variable "frontend_domain_name" {
  description = "Custom domain name for frontend (optional)"
  type        = string
  default     = ""
}

# Tags
variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "Hospital Readmission System"
    ManagedBy   = "Terraform"
    Environment = "Production"
  }
}
