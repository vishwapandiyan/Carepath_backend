# =============================================================================
# CloudFront Distribution for API (HTTPS termination)
# =============================================================================

resource "aws_cloudfront_distribution" "api" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CloudFront distribution for readmission API"
  price_class         = "PriceClass_100" # US, Canada, Europe

  origin {
    domain_name = aws_lb.backend.dns_name
    origin_id   = "alb-backend"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "alb-backend"

    forwarded_values {
      query_string = true
      headers      = ["*"]

      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_name}-api-cloudfront-${var.environment}"
  }
}

# Output the API CloudFront URL
output "api_cloudfront_url" {
  description = "HTTPS URL for API via CloudFront"
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "api_cloudfront_domain" {
  description = "CloudFront domain name for API"
  value       = aws_cloudfront_distribution.api.domain_name
}
