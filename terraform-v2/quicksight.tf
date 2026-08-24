# =============================================================================
# Amazon QuickSight Configuration
# Connects to RDS PostgreSQL for analytics and dashboards
# =============================================================================

# QuickSight needs a security group to access RDS in VPC
resource "aws_security_group" "quicksight" {
  name        = "${var.project_name}-quicksight-${var.environment}"
  description = "Security group for QuickSight VPC connection"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "${var.project_name}-quicksight-sg-${var.environment}"
  }
}

# Allow QuickSight to connect to RDS
resource "aws_security_group_rule" "rds_from_quicksight" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.quicksight.id
  description              = "Allow QuickSight to access RDS"
}

# Note: QuickSight VPC connection must be created manually or through AWS CLI
# because Terraform doesn't fully support QuickSight VPC connections yet.
# Use the outputs below to create the connection manually.

# Output QuickSight connection details
output "quicksight_setup_instructions" {
  value = <<-EOT
  
===================================================================
📊 QuickSight Setup Instructions
===================================================================

STEP 1: Sign up for QuickSight (if not already done)
  - Go to: https://quicksight.aws.amazon.com/
  - Choose "Standard Edition" (or Enterprise if needed)
  - Region: us-east-1
  
STEP 2: Create VPC Connection
  Run this AWS CLI command:

aws quicksight create-vpc-connection \
  --aws-account-id ${data.aws_caller_identity.current.account_id} \
  --vpc-connection-id carepath-rds-vpc \
  --name "CarePath RDS Connection" \
  --role-arn "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/service-role/aws-quicksight-service-role-v0" \
  --security-group-ids ${aws_security_group.quicksight.id} \
  --subnet-ids ${aws_subnet.private_1.id} ${aws_subnet.private_2.id} \
  --region ${data.aws_region.current.name}

STEP 3: Create Data Source
  Run this AWS CLI command:

aws quicksight create-data-source \
  --aws-account-id ${data.aws_caller_identity.current.account_id} \
  --data-source-id carepath-rds-datasource \
  --name "CarePath PostgreSQL" \
  --type POSTGRESQL \
  --data-source-parameters '{
    "RdsParameters": {
      "InstanceId": "${aws_db_instance.postgres.id}",
      "Database": "${var.db_name}"
    }
  }' \
  --credentials '{
    "CredentialPair": {
      "Username": "${var.db_username}",
      "Password": "YOUR_DB_PASSWORD_HERE"
    }
  }' \
  --vpc-connection-properties '{
    "VpcConnectionArn": "arn:aws:quicksight:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:vpcConnection/carepath-rds-vpc"
  }' \
  --ssl-properties '{
    "DisableSsl": false
  }' \
  --region ${data.aws_region.current.name}

===================================================================
📋 Connection Details:
===================================================================
RDS Endpoint:      ${aws_db_instance.postgres.endpoint}
Database Name:     ${var.db_name}
Username:          ${var.db_username}
VPC ID:            ${aws_vpc.main.id}
Security Group ID: ${aws_security_group.quicksight.id}
Subnet IDs:        ${aws_subnet.private_1.id}, ${aws_subnet.private_2.id}
Region:            ${data.aws_region.current.name}
Account ID:        ${data.aws_caller_identity.current.account_id}

===================================================================
🔐 Get Database Password:
===================================================================
aws secretsmanager get-secret-value \
  --secret-id ${aws_secretsmanager_secret.db_password.arn} \
  --query SecretString \
  --output text \
  --region ${data.aws_region.current.name} | jq -r .password

===================================================================
💡 Alternative: Use QuickSight Console (Easier)
===================================================================
1. Go to: https://quicksight.aws.amazon.com/
2. Click "Datasets" → "New dataset"
3. Choose "PostgreSQL"
4. Enter connection details:
   - Connection name: CarePath RDS
   - Database server: ${split(":", aws_db_instance.postgres.endpoint)[0]}
   - Port: 5432
   - Database name: ${var.db_name}
   - Username: ${var.db_username}
   - Password: [Get from secrets manager]
5. Click "Create VPC connection" and select:
   - VPC: ${aws_vpc.main.id}
   - Security Group: ${aws_security_group.quicksight.id}
   - Subnets: ${aws_subnet.private_1.id}, ${aws_subnet.private_2.id}

===================================================================
  EOT
}

output "quicksight_security_group_id" {
  description = "Security group ID for QuickSight VPC connection"
  value       = aws_security_group.quicksight.id
}

output "quicksight_rds_endpoint_clean" {
  description = "RDS endpoint without port (for QuickSight)"
  value       = split(":", aws_db_instance.postgres.endpoint)[0]
}
