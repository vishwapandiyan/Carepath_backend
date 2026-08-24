#!/bin/bash

echo "🔍 Streaming CarePath AI Backend Logs..."
echo "📍 Log Group: /ecs/carepath-ai-backend-prod"
echo "🌍 Region: us-east-1"
echo ""
echo "Press Ctrl+C to stop"
echo "----------------------------------------"
echo ""

aws logs tail /ecs/carepath-ai-backend-prod --follow --region us-east-1
