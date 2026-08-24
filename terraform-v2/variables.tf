# =============================================================================
# Variables for CarePath AI System AWS Deployment
# Separate ML and Backend Services
# =============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "carepath-ai"
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
  default     = "carepath_db"
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
  description = "EC2 instance type for ECS (t2.micro for free tier)"
  type        = string
  default     = "t2.micro"
}

# Backend Service Configuration
variable "backend_task_cpu" {
  description = "CPU units for Backend ECS task (256 with 2 instances)"
  type        = number
  default     = 256
}

variable "backend_task_memory" {
  description = "Memory (MB) for Backend ECS task (400 to fit with ECS agent overhead)"
  type        = number
  default     = 400
}

variable "backend_container_port" {
  description = "Port exposed by the backend container"
  type        = number
  default     = 8000
}

variable "backend_desired_count" {
  description = "Desired number of backend service instances"
  type        = number
  default     = 1
}

# ML Service Configuration
variable "ml_task_cpu" {
  description = "CPU units for ML ECS task (256 with 2 instances)"
  type        = number
  default     = 256
}

variable "ml_task_memory" {
  description = "Memory (MB) for ML ECS task (400 to fit with ECS agent overhead)"
  type        = number
  default     = 400
}

variable "ml_container_port" {
  description = "Port exposed by the ML container"
  type        = number
  default     = 8001
}

variable "ml_desired_count" {
  description = "Desired number of ML service instances"
  type        = number
  default     = 1
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
    Project     = "CarePath AI System"
    ManagedBy   = "Terraform"
    Environment = "Production"
    Version     = "v2"
  }
}

# API Keys (sensitive - provide via terraform.tfvars or environment variables)
variable "google_api_key" {
  description = "Google API Key for Gemini/AI services"
  type        = string
  sensitive   = true
  default     = ""
}

variable "nvidia_api_key" {
  description = "NVIDIA API Key for Nemotron model"
  type        = string
  sensitive   = true
  default     = ""
}

variable "groq_api_key" {
  description = "Groq API Key for LLM operations"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openrouter_api_key" {
  description = "OpenRouter API Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "app_secret_key" {
  description = "Application secret key"
  type        = string
  sensitive   = true
  default     = ""
}
