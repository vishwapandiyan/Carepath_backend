# =============================================================================
# IAM Role for QuickSight VPC Connection
# =============================================================================

# IAM Role for QuickSight
resource "aws_iam_role" "quicksight_vpc" {
  name = "aws-quicksight-vpc-connection-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "quicksight.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-quicksight-vpc-role-${var.environment}"
  }
}

# Policy for VPC access
resource "aws_iam_role_policy" "quicksight_vpc_access" {
  name = "quicksight-vpc-access-policy"
  role = aws_iam_role.quicksight_vpc.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:ModifyNetworkInterfaceAttribute",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

# Output the role ARN
output "quicksight_vpc_role_arn" {
  description = "IAM Role ARN for QuickSight VPC connection"
  value       = aws_iam_role.quicksight_vpc.arn
}
