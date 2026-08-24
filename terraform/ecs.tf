# =============================================================================
# ECS Cluster, Task Definition, and Service
# =============================================================================

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "disabled" # Enable in production for monitoring
  }

  tags = {
    Name = "${var.project_name}-cluster-${var.environment}"
  }
}

# CloudWatch Log Group for ECS
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}-backend-${var.environment}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-ecs-logs-${var.environment}"
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend-${var.environment}"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "fastapi"
    image     = "${aws_ecr_repository.backend.repository_url}:latest"
    essential = true
    cpu       = var.ecs_task_cpu
    memory    = var.ecs_task_memory

    portMappings = [{
      containerPort = var.container_port
      hostPort      = var.container_port
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "DATABASE_URL"
        value = "postgresql://${var.db_username}:${random_password.db_password.result}@${aws_db_instance.postgres.endpoint}/${var.db_name}"
      },
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
        name  = "ENVIRONMENT"
        value = "production"
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
      }
    ]

    secrets = [
      {
        name      = "JWT_SECRET_KEY"
        valueFrom = aws_secretsmanager_secret.jwt_secret.arn
      },
      {
        name      = "DB_PASSWORD"
        valueFrom = aws_secretsmanager_secret.db_password.arn
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = {
    Name = "${var.project_name}-backend-task-${var.environment}"
  }
}

# EC2 Launch Configuration for ECS
resource "aws_launch_template" "ecs" {
  name_prefix   = "${var.project_name}-ecs-"
  image_id      = data.aws_ami.amazon_linux_2023.id
  instance_type = var.ecs_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.ecs.name
  }

  vpc_security_group_ids = [aws_security_group.ecs_tasks.id]

  user_data = base64encode(<<-EOF
              #!/bin/bash
              echo ECS_CLUSTER=${aws_ecs_cluster.main.name} >> /etc/ecs/ecs.config
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

# Auto Scaling Group for ECS
resource "aws_autoscaling_group" "ecs" {
  name                = "${var.project_name}-ecs-asg-${var.environment}"
  vpc_zone_identifier = [aws_subnet.public.id]
  desired_capacity    = 1
  min_size            = 1
  max_size            = 1 # Keep at 1 for free tier

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

# ECS Service (will be replaced by the one in alb.tf with load balancer)
resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "EC2"

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  # Load balancer configuration
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "fastapi"
    container_port   = 8000
  }

  depends_on = [
    aws_autoscaling_group.ecs,
    aws_db_instance.postgres,
    aws_lb_listener.http
  ]

  tags = {
    Name = "${var.project_name}-backend-service-${var.environment}"
  }

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }
}

# JWT Secret
resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "${var.project_name}-jwt-secret-${var.environment}"
  description             = "JWT secret for ${var.project_name}"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}
