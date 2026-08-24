# =============================================================================
# CloudFront Distribution for Backend API
# Provides HTTPS endpoint with valid SSL certificate
# =============================================================================

resource "aws_cloudfront_distribution" "backend" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.project_name} Backend API - ${var.environment}"
  price_class     = "PriceClass_100"

  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = "ALB-Main"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "ALB-Main"

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Accept", "Content-Type", "Origin"]

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
    Name    = "${var.project_name}-backend-cf-${var.environment}"
    Service = "Backend"
  }
}
