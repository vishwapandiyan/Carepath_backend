# =============================================================================
# Application Load Balancer (FREE TIER OPTIMIZED - Single ALB)
# Uses path-based routing to serve both Backend and ML services
# =============================================================================

# Single Application Load Balancer for both services
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_1.id, aws_subnet.public_2.id]

  enable_deletion_protection = false
  enable_http2               = true

  tags = {
    Name = "${var.project_name}-alb-${var.environment}"
  }
}

# Target Group for Backend Service
resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-backend-tg-${var.environment}"
  port        = var.backend_container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = {
    Name    = "${var.project_name}-backend-tg-${var.environment}"
    Service = "Backend"
  }
}

# Target Group for ML Service (internal access via path routing)
resource "aws_lb_target_group" "ml" {
  name        = "${var.project_name}-ml-tg-${var.environment}"
  port        = var.ml_container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = {
    Name    = "${var.project_name}-ml-tg-${var.environment}"
    Service = "ML"
  }
}

# HTTP Listener with path-based routing
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # Default action forwards to backend
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# Listener Rule for ML Service (path-based routing)
# Routes /ml/* to ML service for internal backend-to-ML communication
resource "aws_lb_listener_rule" "ml" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ml.arn
  }

  condition {
    path_pattern {
      values = ["/ml/*"]
    }
  }
}
