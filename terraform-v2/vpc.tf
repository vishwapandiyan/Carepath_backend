# =============================================================================
# VPC and Networking Configuration
# =============================================================================

# VPC
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc-${var.environment}"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw-${var.environment}"
  }
}

# Public Subnet 1
resource "aws_subnet" "public_1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet-1-${var.environment}"
  }
}

# Public Subnet 2 (for ALB - needs 2 AZs)
resource "aws_subnet" "public_2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.4.0/24"
  availability_zone       = var.availability_zone_2
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet-2-${var.environment}"
  }
}

# Private Subnet 1
resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = var.availability_zone

  tags = {
    Name = "${var.project_name}-private-subnet-1-${var.environment}"
  }
}

# Private Subnet 2 (for RDS - needs 2 AZs)
resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = var.availability_zone_2

  tags = {
    Name = "${var.project_name}-private-subnet-2-${var.environment}"
  }
}

# Route Table for Public Subnets
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt-${var.environment}"
  }
}

# Associate Public Subnets with Route Table
resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}

# =============================================================================
# Security Groups
# =============================================================================

# Security Group for Backend ECS Tasks
resource "aws_security_group" "backend_tasks" {
  name        = "${var.project_name}-backend-tasks-${var.environment}"
  description = "Security group for Backend API ECS tasks"
  vpc_id      = aws_vpc.main.id

  # Allow inbound from ALB on all ports (ECS uses dynamic port mapping)
  ingress {
    description     = "All TCP from ALB (ECS dynamic ports)"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Allow all outbound traffic
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-backend-tasks-sg-${var.environment}"
  }
}

# Security Group for ML ECS Tasks
resource "aws_security_group" "ml_tasks" {
  name        = "${var.project_name}-ml-tasks-${var.environment}"
  description = "Security group for ML Service ECS tasks"
  vpc_id      = aws_vpc.main.id

  # Allow inbound from Backend tasks (internal communication, ECS dynamic ports)
  ingress {
    description     = "All TCP from Backend (ECS dynamic ports)"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.backend_tasks.id]
  }

  # Allow inbound from ALB for direct ML API access (ECS dynamic ports)
  ingress {
    description     = "All TCP from ALB (ECS dynamic ports)"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Allow all outbound traffic
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ml-tasks-sg-${var.environment}"
  }
}

# Security Group for Application Load Balancer
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg-${var.environment}"
  description = "Security group for Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  # Allow HTTP from anywhere
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP from anywhere"
  }

  # Allow HTTPS from anywhere
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS from anywhere"
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic"
  }

  tags = {
    Name = "${var.project_name}-alb-sg-${var.environment}"
  }
}

# Security Group for RDS
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-${var.environment}"
  description = "Security group for RDS database"
  vpc_id      = aws_vpc.main.id

  # Allow PostgreSQL from Backend tasks
  ingress {
    description     = "PostgreSQL from Backend"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.backend_tasks.id]
  }

  # Allow PostgreSQL from ML tasks
  ingress {
    description     = "PostgreSQL from ML"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ml_tasks.id]
  }

  tags = {
    Name = "${var.project_name}-rds-sg-${var.environment}"
  }
}

# DB Subnet Group (keeping in public subnets - RDS cannot change subnets while running)
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group-${var.environment}"
  subnet_ids = [aws_subnet.public_1.id, aws_subnet.public_2.id]

  tags = {
    Name = "${var.project_name}-db-subnet-group-${var.environment}"
  }

  lifecycle {
    create_before_destroy = true
  }
}
