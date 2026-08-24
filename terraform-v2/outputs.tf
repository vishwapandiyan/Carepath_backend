# =============================================================================
# Terraform Outputs - Important values after deployment
# =============================================================================

# Database Outputs
output "rds_endpoint" {
  description = "RDS database endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_database_name" {
  description = "RDS database name"
  value       = aws_db_instance.postgres.db_name
}

output "rds_username" {
  description = "RDS database username"
  value       = var.db_username
  sensitive   = true
}

output "rds_password_secret_arn" {
  description = "ARN of secret containing database password"
  value       = aws_secretsmanager_secret.db_password.arn
}

# ECR Outputs
output "ecr_backend_repository_url" {
  description = "ECR repository URL for backend service"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_ml_repository_url" {
  description = "ECR repository URL for ML service"
  value       = aws_ecr_repository.ml.repository_url
}

# ECS Outputs
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_backend_service_name" {
  description = "ECS backend service name"
  value       = aws_ecs_service.backend.name
}

output "ecs_ml_service_name" {
  description = "ECS ML service name"
  value       = aws_ecs_service.ml.name
}

# Load Balancer Outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_url" {
  description = "HTTP URL for ALB (serves both Backend and ML)"
  value       = "http://${aws_lb.main.dns_name}"
}

output "backend_url" {
  description = "Backend API URL via ALB"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ml_internal_url" {
  description = "ML service URL (internal access via /ml path)"
  value       = "http://${aws_lb.main.dns_name}/ml"
}

# CloudFront Outputs
output "cloudfront_frontend_id" {
  description = "CloudFront distribution ID for frontend"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_frontend_domain" {
  description = "CloudFront domain name for frontend"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_url" {
  description = "HTTPS URL for frontend application"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_backend_id" {
  description = "CloudFront distribution ID for backend API"
  value       = aws_cloudfront_distribution.backend.id
}

output "cloudfront_backend_domain" {
  description = "CloudFront domain name for backend API"
  value       = aws_cloudfront_distribution.backend.domain_name
}

output "backend_api_url" {
  description = "HTTPS URL for backend API via CloudFront"
  value       = "https://${aws_cloudfront_distribution.backend.domain_name}"
}

# S3 Outputs
output "s3_frontend_bucket_name" {
  description = "S3 bucket name for frontend static files"
  value       = aws_s3_bucket.frontend.id
}

# VPC Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = [aws_subnet.public_1.id, aws_subnet.public_2.id]
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = [aws_subnet.private_1.id, aws_subnet.private_2.id]
}

# Security Group Outputs
output "backend_security_group_id" {
  description = "Backend ECS tasks security group ID"
  value       = aws_security_group.backend_tasks.id
}

output "ml_security_group_id" {
  description = "ML ECS tasks security group ID"
  value       = aws_security_group.ml_tasks.id
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

# Deployment Instructions
output "deployment_instructions" {
  description = "Next steps after infrastructure deployment"
  value = <<-EOT
  
  ===================================================================
  🎉 CarePath AI Infrastructure Deployed Successfully! (v2)
  ===================================================================
  
  🌐 URLS:
  Frontend:    https://${aws_cloudfront_distribution.frontend.domain_name}
  Backend API: https://${aws_cloudfront_distribution.backend.domain_name}
  
  🐳 DOCKER REPOSITORIES:
  Backend ECR: ${aws_ecr_repository.backend.repository_url}
  ML ECR:      ${aws_ecr_repository.ml.repository_url}
  
  🗄️ DATABASE:
  RDS Endpoint: ${aws_db_instance.postgres.endpoint}
  DB Name:      ${aws_db_instance.postgres.db_name}
  
  ✅ ARCHITECTURE (FREE TIER OPTIMIZED):
  - Single ALB with path-based routing (saves ~$16/month)
  - 1 × t2.micro EC2 instance (750 hours/month FREE)
  - Separate Docker containers for Backend and ML services
  - Backend service: Public-facing via CloudFront + ALB
  - ML service: Path-based routing via /ml path
  - Backend communicates with ML via: ${aws_lb.main.dns_name}/ml
  
  💰 MONTHLY COST: ~$18-22 (mostly ALB + minor fees)
  
  📋 NEXT STEPS:
  
  1. Build and Push Backend Docker Image:
     cd /path/to/backend
     docker build -t backend -f Dockerfile.backend .
     aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.backend.repository_url}
     docker tag backend:latest ${aws_ecr_repository.backend.repository_url}:latest
     docker push ${aws_ecr_repository.backend.repository_url}:latest
  
  2. Build and Push ML Docker Image:
     cd /path/to/ml
     docker build -t ml -f Dockerfile.ml .
     aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.ml.repository_url}
     docker tag ml:latest ${aws_ecr_repository.ml.repository_url}:latest
     docker push ${aws_ecr_repository.ml.repository_url}:latest
  
  3. Update ECS Services:
     aws ecs update-service --cluster ${aws_ecs_cluster.main.name} --service ${aws_ecs_service.backend.name} --force-new-deployment --region ${var.aws_region}
     aws ecs update-service --cluster ${aws_ecs_cluster.main.name} --service ${aws_ecs_service.ml.name} --force-new-deployment --region ${var.aws_region}
  
  4. Deploy Frontend:
     Update .env.production with: VITE_API_URL=https://${aws_cloudfront_distribution.backend.domain_name}
     npm run build
     aws s3 sync dist/ s3://${aws_s3_bucket.frontend.id}/ --delete
     aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.frontend.id} --paths "/*"
  
  5. Test Deployment:
     Backend:  curl https://${aws_cloudfront_distribution.backend.domain_name}/health
     Frontend: https://${aws_cloudfront_distribution.frontend.domain_name}
  
  ===================================================================
  📚 For detailed Dockerfile examples, see terraform-v2/DEPLOYMENT.md
  ===================================================================
  EOT
}
