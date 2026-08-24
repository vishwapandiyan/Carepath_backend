"""
QuickSight Dashboard Embedding Endpoint
Generates signed embed URLs for anonymous QuickSight dashboard access
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import os
from typing import List

router = APIRouter()


class EmbedUrlResponse(BaseModel):
    embed_url: str
    dashboard_id: str


@router.get("/embed-url", response_model=EmbedUrlResponse)
async def get_quicksight_embed_url():
    """
    Generate anonymous embed URL for QuickSight dashboard.
    
    The dashboard must have anonymous embedding enabled in QuickSight settings.
    """
    try:
        # AWS Configuration
        aws_account_id = os.getenv("AWS_ACCOUNT_ID", "363401891883")
        region = os.getenv("AWS_REGION", "us-east-1")
        
        # IMPORTANT: Replace this with your actual dashboard ID from QuickSight console
        # You can find it in the dashboard URL after creating it
        dashboard_id = os.getenv("QUICKSIGHT_DASHBOARD_ID", "YOUR_DASHBOARD_ID_HERE")
        
        if dashboard_id == "YOUR_DASHBOARD_ID_HERE":
            raise HTTPException(
                status_code=500,
                detail="QuickSight dashboard ID not configured. Please set QUICKSIGHT_DASHBOARD_ID environment variable."
            )
        
        # Allowed domains for embedding
        allowed_domains: List[str] = [
            "http://localhost:5173",
            "https://d2wdvr99379bz0.cloudfront.net",
        ]
        
        # Create QuickSight client
        quicksight = boto3.client('quicksight', region_name=region)
        
        # Generate anonymous embed URL
        response = quicksight.generate_embed_url_for_anonymous_user(
            AwsAccountId=aws_account_id,
            Namespace='default',
            AuthorizedResourceArns=[
                f'arn:aws:quicksight:{region}:{aws_account_id}:dashboard/{dashboard_id}'
            ],
            ExperienceConfiguration={
                'Dashboard': {
                    'InitialDashboardId': dashboard_id
                }
            },
            AllowedDomains=allowed_domains,
            SessionLifetimeInMinutes=600  # 10 hours
        )
        
        return EmbedUrlResponse(
            embed_url=response['EmbedUrl'],
            dashboard_id=dashboard_id
        )
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'ResourceNotFoundException':
            raise HTTPException(
                status_code=404,
                detail=f"Dashboard not found. Please verify the dashboard ID: {dashboard_id}"
            )
        elif error_code == 'InvalidParameterValueException':
            raise HTTPException(
                status_code=400,
                detail=f"Invalid configuration: {error_message}. Check that anonymous embedding is enabled."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"AWS QuickSight error: {error_message}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate embed URL: {str(e)}"
        )


@router.get("/health")
async def quicksight_health():
    """Health check endpoint for QuickSight integration"""
    dashboard_id = os.getenv("QUICKSIGHT_DASHBOARD_ID", "YOUR_DASHBOARD_ID_HERE")
    is_configured = dashboard_id != "YOUR_DASHBOARD_ID_HERE"
    
    return {
        "status": "configured" if is_configured else "not_configured",
        "dashboard_id": dashboard_id if is_configured else None,
        "message": "QuickSight integration is ready" if is_configured else "Please configure QUICKSIGHT_DASHBOARD_ID"
    }
