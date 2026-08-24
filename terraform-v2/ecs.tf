# =============================================================================
# ECS Cluster, Task Definitions, and Services
# Separate Backend and ML Services
# =============================================================================

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster-${var.environment}"
  }
}

# =============================================================================
# CloudWatch Log Groups
# =============================================================================

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.project_name}-backend-${var.environment}"
  retention_in_days = 7

  tags = {
    Name    = "${var.project_name}-backend-logs-${var.environment}"
    Service = "Backend"
  }
}

resource "aws_cloudwatch_log_group" "ml" {
  name              = "/ecs/${var.project_name}-ml-${var.environment}"
  retention_in_days = 7

  tags = {
    Name    = "${var.project_name}-ml-logs-${var.environment}"
    Service = "ML"
  }
}

# =============================================================================
# Backend Service Task Definition
# =============================================================================

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend-${var.environment}"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  cpu                      = var.backend_task_cpu
  memory                   = var.backend_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "backend"
    image     = "${aws_ecr_repository.backend.repository_url}:latest"
    essential = true
    cpu       = var.backend_task_cpu
    memory    = var.backend_task_memory

    portMappings = [{
      containerPort = var.backend_container_port
      hostPort      = var.backend_container_port # Static port mapping for bridge mode
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "DATABASE_URL"
        value = "postgresql://${var.db_username}:${jsondecode(aws_secretsmanager_secret_version.db_password.secret_string)["password"]}@10.0.4.99:5432/${var.db_name}"
      },
      {
        name  = "DB_HOST"
        value = split(":", aws_db_instance.postgres.endpoint)[0]
      },
      {
        name  = "DB_PORT"
        value = "5432"
      },
      {
        name  = "DB_NAME"
        value = var.db_name
      },
      {
        name  = "DB_USER"
        value = var.db_username
      },
      {
        name  = "ENVIRONMENT"
        value = var.environment
      },
      {
        name  = "DEBUG"
        value = "False"
      },
      {
        name  = "JWT_ALGORITHM"
        value = "HS256"
      },
      {
        name  = "ACCESS_TOKEN_EXPIRE_MINUTES"
        value = "30"
      },
      {
        name  = "ML_SERVICE_URL"
        value = "http://${aws_lb.main.dns_name}/ml"
      },
      {
        name  = "NVIDIA_BASE_URL"
        value = "https://integrate.api.nvidia.com/v1"
      },
      {
        name  = "NVIDIA_MODEL"
        value = "nvidia/nemotron-3.5-lightning-30b-a3b"
      },
      {
        name  = "OPENROUTER_ORCHESTRATOR_MODEL"
        value = "openai/gpt-oss-120b"
      },
      {
        name  = "ALGORITHM"
        value = "HS256"
      }
    ]

    secrets = [
      {
        name      = "JWT_SECRET_KEY"
        valueFrom = "${aws_secretsmanager_secret.jwt_secret.arn}:JWT_SECRET_KEY::"
      },
      {
        name      = "DB_PASSWORD"
        valueFrom = "${aws_secretsmanager_secret.db_password.arn}:password::"
      },
      {
        name      = "GOOGLE_API_KEY"
        valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GOOGLE_API_KEY::"
      },
      {
        name      = "NVIDIA_API_KEY"
        valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:NVIDIA_API_KEY::"
      },
      {
        name      = "GROQ_API_KEY"
        valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GROQ_API_KEY::"
      },
      {
        name      = "OPENROUTER_API_KEY"
        valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:OPENROUTER_API_KEY::"
      },
      {
        name      = "SECRET_KEY"
        valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:SECRET_KEY::"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.backend_container_port}/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = {
    Name    = "${var.project_name}-backend-task-${var.environment}"
    Service = "Backend"
  }
}

# =============================================================================
# ML Service Task Definition
# =============================================================================

resource "aws_ecs_task_definition" "ml" {
  family                   = "${var.project_name}-ml-${var.environment}"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  cpu                      = var.ml_task_cpu
  memory                   = var.ml_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "ml"
    image     = "${aws_ecr_repository.ml.repository_url}:latest"
    essential = true
    cpu       = var.ml_task_cpu
    memory    = var.ml_task_memory

    portMappings = [{
      containerPort = var.ml_container_port
      hostPort      = var.ml_container_port # Static port mapping for bridge mode
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      },
      {
        name  = "DB_HOST"
        value = split(":", aws_db_instance.postgres.endpoint)[0]
      },
      {
        name  = "DB_PORT"
        value = "5432"
      },
      {
        name  = "DB_NAME"
        value = var.db_name
      },
      {
        name  = "DB_USER"
        value = var.db_username
      },
      {
        name  = "DEBUG"
        value = "False"
      },
      {
        name  = "MODEL_CACHE_DIR"
        value = "/models"
      }
    ]

    secrets = [
      {
        name      = "DB_PASSWORD"
        valueFrom = "${aws_secretsmanager_secret.db_password.arn}:password::"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ml.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.ml_container_port}/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 90
    }
  }])

  tags = {
    Name    = "${var.project_name}-ml-task-${var.environment}"
    Service = "ML"
  }
}

# =============================================================================
# EC2 Launch Configuration for ECS
# =============================================================================

resource "aws_launch_template" "ecs" {
  name_prefix   = "${var.project_name}-ecs-"
  image_id      = data.aws_ami.amazon_linux_2023.id
  instance_type = var.ecs_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.ecs.name
  }

  vpc_security_group_ids = [
    aws_security_group.backend_tasks.id,
    aws_security_group.ml_tasks.id
  ]

  user_data = base64encode(<<-EOF
              #!/bin/bash
              echo ECS_CLUSTER=${aws_ecs_cluster.main.name} >> /etc/ecs/ecs.config
              echo ECS_ENABLE_TASK_IAM_ROLE=true >> /etc/ecs/ecs.config
              echo ECS_ENABLE_TASK_IAM_ROLE_NETWORK_HOST=true >> /etc/ecs/ecs.config
              EOF
  )

  monitoring {
    enabled = true
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-ecs-instance-${var.environment}"
    }
  }
}

# Auto Scaling Group for ECS (in public subnets)
resource "aws_autoscaling_group" "ecs" {
  name                = "${var.project_name}-ecs-asg-${var.environment}"
  vpc_zone_identifier = [aws_subnet.public_1.id, aws_subnet.public_2.id]  # Public subnets
  desired_capacity    = 2  # 2 instances: one for Backend, one for ML
  min_size            = 2
  max_size            = 2  # Stay within free tier (750 hours × 2 = 1500 hours free)

  launch_template {
    id      = aws_launch_template.ecs.id
    version = "$Latest"
  }

  health_check_type         = "EC2"
  health_check_grace_period = 300

  tag {
    key                 = "Name"
    value               = "${var.project_name}-ecs-instance-${var.environment}"
    propagate_at_launch = true
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = true
    propagate_at_launch = true
  }
}

# =============================================================================
# Backend ECS Service
# =============================================================================

resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "EC2"

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = var.backend_container_port
  }

  depends_on = [
    aws_autoscaling_group.ecs,
    aws_db_instance.postgres,
    aws_lb_listener.http
  ]

  tags = {
    Name    = "${var.project_name}-backend-service-${var.environment}"
    Service = "Backend"
  }

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }
}

# =============================================================================
# ML ECS Service
# =============================================================================

resource "aws_ecs_service" "ml" {
  name            = "${var.project_name}-ml-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.ml.arn
  desired_count   = var.ml_desired_count
  launch_type     = "EC2"

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  load_balancer {
    target_group_arn = aws_lb_target_group.ml.arn
    container_name   = "ml"
    container_port   = var.ml_container_port
  }

  depends_on = [
    aws_autoscaling_group.ecs,
    aws_db_instance.postgres,
    aws_lb_listener.http,
    aws_lb_listener_rule.ml
  ]

  tags = {
    Name    = "${var.project_name}-ml-service-${var.environment}"
    Service = "ML"
  }

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }
}
