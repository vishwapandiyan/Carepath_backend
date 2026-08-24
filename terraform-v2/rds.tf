# =============================================================================
# RDS PostgreSQL Database
# Shared by both Backend and ML Services
# =============================================================================

resource "aws_db_instance" "postgres" {
  identifier = "${var.project_name}-db-${var.environment}"

  # Engine
  engine         = "postgres"
  engine_version = "15.8"
  instance_class = var.db_instance_class

  # Storage
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  # Database
  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result
  port     = 5432

  # Network
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false  # Secure: RDS in private subnet

  # Backup
  backup_retention_period   = var.db_backup_retention_days
  backup_window             = "03:00-04:00" # UTC
  maintenance_window        = "Mon:04:00-Mon:05:00"
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-db-final-snapshot-${var.environment}-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  # High Availability
  multi_az = false # Set to true for production

  # Performance Insights
  performance_insights_enabled = false # Enable for production monitoring

  # Monitoring
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # Deletion protection
  deletion_protection = false # Set to true for production

  tags = {
    Name = "${var.project_name}-db-${var.environment}"
  }
}
