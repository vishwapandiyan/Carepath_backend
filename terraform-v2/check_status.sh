#!/bin/bash
echo "=========================================="
echo "CarePath AI Deployment Status"
echo "=========================================="
echo ""

# ECS Services
echo "📦 ECS Services:"
echo "----------------"
aws ecs describe-services \
  --cluster carepath-ai-cluster-prod \
  --services carepath-ai-backend-service-prod carepath-ai-ml-service-prod \
  --query 'services[*].{Service:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Health:deployments[0].rolloutState}' \
  --output table

echo ""
echo "🖥️  ECS Tasks:"
echo "----------------"
aws ecs list-tasks --cluster carepath-ai-cluster-prod --query 'taskArns[*]' --output text | while read task; do
  if [ ! -z "$task" ]; then
    aws ecs describe-tasks --cluster carepath-ai-cluster-prod --tasks $task \
      --query 'tasks[0].{TaskID:taskArn,Status:lastStatus,Health:healthStatus,Container:containers[0].name}' \
      --output table
  fi
done

echo ""
echo "🏥 RDS Database:"
echo "----------------"
aws rds describe-db-instances \
  --db-instance-identifier carepath-ai-db-prod \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Port:Endpoint.Port,Storage:AllocatedStorage,Class:DBInstanceClass}' \
  --output table

echo ""
echo "⚖️  Load Balancer:"
echo "----------------"
aws elbv2 describe-load-balancers \
  --names carepath-ai-alb-prod \
  --query 'LoadBalancers[0].{State:State.Code,DNS:DNSName,Type:Type}' \
  --output table

echo ""
echo "🎯 Target Groups Health:"
echo "----------------"
# Backend target group
TG_ARN=$(aws elbv2 describe-target-groups --names carepath-ai-backend-tg-prod --query 'TargetGroups[0].TargetGroupArn' --output text)
echo "Backend Target Group:"
aws elbv2 describe-target-health --target-group-arn $TG_ARN --query 'TargetHealthDescriptions[*].{Target:Target.Id,Port:Target.Port,Health:TargetHealth.State}' --output table

echo ""
# ML target group
TG_ARN=$(aws elbv2 describe-target-groups --names carepath-ai-ml-tg-prod --query 'TargetGroups[0].TargetGroupArn' --output text)
echo "ML Target Group:"
aws elbv2 describe-target-health --target-group-arn $TG_ARN --query 'TargetHealthDescriptions[*].{Target:Target.Id,Port:Target.Port,Health:TargetHealth.State}' --output table

echo ""
echo "🔗 URLs:"
echo "----------------"
cd terraform-v2 2>/dev/null || true
echo "Frontend:     $(terraform output -raw frontend_url 2>/dev/null || echo 'Not available')"
echo "Backend API:  $(terraform output -raw backend_api_url 2>/dev/null || echo 'Not available')"
echo "ALB Direct:   $(terraform output -raw alb_url 2>/dev/null || echo 'Not available')"
echo ""
echo "=========================================="
