# =============================================================================
# IAM Roles and Policies for ECS Tasks
# =============================================================================

# ECS Task Execution Role (for pulling images and writing logs)
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-ecs-task-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.project_name}-ecs-task-execution-role-${var.environment}"
  }
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom policy for accessing Secrets Manager
resource "aws_iam_role_policy" "ecs_secrets" {
  name = "${var.project_name}-ecs-secrets-${var.environment}"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = [
        aws_secretsmanager_secret.db_password.arn,
        aws_secretsmanager_secret.jwt_secret.arn,
        aws_secretsmanager_secret.api_keys.arn
      ]
    }]
  })
}

# Policy for ECR access
resource "aws_iam_role_policy" "ecs_ecr_access" {
  name = "${var.project_name}-ecs-ecr-access-${var.environment}"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ]
      Resource = "*"
    }]
  })
}

# ECS Task Role (for application permissions)
resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.project_name}-ecs-task-role-${var.environment}"
  }
}

# Policy for ECS task to access CloudWatch Logs
resource "aws_iam_role_policy" "ecs_task_cloudwatch" {
  name = "${var.project_name}-ecs-task-cloudwatch-${var.environment}"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:CreateLogGroup"
      ]
      Resource = [
        "${aws_cloudwatch_log_group.backend.arn}:*",
        "${aws_cloudwatch_log_group.ml.arn}:*"
      ]
    }]
  })
}

# Policy for ML tasks to access S3 for model storage (optional)
resource "aws_iam_role_policy" "ml_s3_access" {
  name = "${var.project_name}-ml-s3-access-${var.environment}"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ]
      Resource = [
        "arn:aws:s3:::${var.project_name}-ml-models-${var.environment}",
        "arn:aws:s3:::${var.project_name}-ml-models-${var.environment}/*"
      ]
    }]
  })
}

# EC2 Instance Role for ECS
resource "aws_iam_role" "ecs_instance" {
  name = "${var.project_name}-ecs-instance-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.project_name}-ecs-instance-role-${var.environment}"
  }
}

# Attach AWS managed policy for ECS instance
resource "aws_iam_role_policy_attachment" "ecs_instance" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

# Additional policy for ECS instance to pull from ECR
resource "aws_iam_role_policy" "ecs_instance_ecr" {
  name = "${var.project_name}-ecs-instance-ecr-${var.environment}"
  role = aws_iam_role.ecs_instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ]
      Resource = "*"
    }]
  })
}

# Instance profile for EC2
resource "aws_iam_instance_profile" "ecs" {
  name = "${var.project_name}-ecs-instance-profile-${var.environment}"
  role = aws_iam_role.ecs_instance.name
}
