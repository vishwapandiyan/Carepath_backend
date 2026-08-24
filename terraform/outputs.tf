# =============================================================================
# Outputs - Important values needed after deployment
# =============================================================================

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
}

output "rds_password_secret_arn" {
  description = "ARN of secret containing database password"
  value       = aws_secretsmanager_secret.db_password.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for backend"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.backend.name
}

output "ecs_task_definition" {
  description = "ECS task definition ARN"
  value       = aws_ecs_task_definition.backend.arn
}

output "s3_bucket_name" {
  description = "S3 bucket name for frontend"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_url" {
  description = "Frontend URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_backend_distribution_id" {
  description = "CloudFront distribution ID for backend API"
  value       = aws_cloudfront_distribution.backend.id
}

output "cloudfront_backend_domain_name" {
  description = "CloudFront domain name for backend API"
  value       = aws_cloudfront_distribution.backend.domain_name
}

output "backend_api_url" {
  description = "HTTPS URL for backend API via CloudFront (no certificate warnings)"
  value       = "https://${aws_cloudfront_distribution.backend.domain_name}"
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "Private subnet ID"
  value       = aws_subnet.private.id
}

output "ecs_security_group_id" {
  description = "ECS security group ID"
  value       = aws_security_group.ecs_tasks.id
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

# Instructions for connecting to resources
output "deployment_instructions" {
  description = "Next steps after infrastructure deployment"
  value = <<-EOT
  
  ===================================================================
  🎉 Infrastructure Deployed Successfully!
  ===================================================================
  
  Frontend URL: https://${aws_cloudfront_distribution.frontend.domain_name}
  Backend API URL: https://${aws_cloudfront_distribution.backend.domain_name}
  ECR Repository: ${aws_ecr_repository.backend.repository_url}
  RDS Endpoint: ${aws_db_instance.postgres.endpoint}
  
  ✅ SSL/TLS: All endpoints use valid CloudFront certificates
  ✅ No certificate warnings for users
  
  NEXT STEPS:
  
  1. Build and Push Docker Image:
     cd ..
     ./scripts/03-build-and-push.sh
  
  2. Update ECS Service:
     ./scripts/04-update-ecs-service.sh
  
  3. Deploy Frontend with new API URL:
     Update .env.production with: VITE_API_URL=https://${aws_cloudfront_distribution.backend.domain_name}
     npm run build && aws s3 sync dist/ s3://${aws_s3_bucket.frontend.id}/ --delete
     aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.frontend.id} --paths "/*"
  
  4. Test the deployment:
     curl https://${aws_cloudfront_distribution.backend.domain_name}/health
  
  ===================================================================
  EOT
}
