# QuickSight Dashboard - Final Setup Steps

## ✅ Configuration Complete

Your dashboard ID has been configured:
- **Dashboard ID**: `abcbf9d1-c35d-4b45-9e28-b7cdc7e964f3`
- **Dashboard URL**: https://us-east-1.quicksight.aws.amazon.com/sn/account/Vishwapandiyan/dashboards/abcbf9d1-c35d-4b45-9e28-b7cdc7e964f3

---

## 🚀 Required Steps (In Order)

### Step 1: Enable Anonymous Embedding in QuickSight

1. **Go to QuickSight Settings**
   - Click your profile icon (top right)
   - Select "Manage QuickSight"
   - Navigate to "Domains and embedding" under "Security & permissions"

2. **Add Allowed Domains**
   ```
   http://localhost:5173
   https://d2wdvr99379bz0.cloudfront.net
   ```
   - Click "Add domains"
   - Paste each domain (one at a time)
   - Click "Add"

3. **Enable Anonymous Embedding**
   - Toggle "Enable" for anonymous embedding
   - Save changes

### Step 2: Configure Dashboard for Public Access

1. **Open Your Dashboard**
   - Go to: https://us-east-1.quicksight.aws.amazon.com/sn/account/Vishwapandiyan/dashboards/abcbf9d1-c35d-4b45-9e28-b7cdc7e964f3

2. **Share Settings**
   - Click "Share" button (top right)
   - Select "Manage dashboard access"
   - Enable "Public access" or configure anonymous user settings
   - Save

### Step 3: Setup Auto-Refresh for Dataset

1. **Go to Datasets**
   - In QuickSight, navigate to "Datasets"
   - Find your dataset (ml_predictions dataset)

2. **Schedule Refresh**
   - Click on the dataset
   - Go to "Refresh" tab
   - Click "Add schedule"
   - Recommended settings:
     - **Frequency**: Hourly (or every 15 minutes if available)
     - **Time zone**: Your local timezone
     - **Starting**: Now
   - Click "Create"

### Step 4: Deploy Backend to Production

```bash
# Navigate to backend directory
cd /Users/vishwa/Desktop/CarepathAI_backend

# Commit the .env changes (but add .env to .gitignore first!)
# Instead, add environment variables to ECS Task Definition

# Login to AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 363401891883.dkr.ecr.us-east-1.amazonaws.com

# Build Docker image
cd terraform-v2
docker build -f Dockerfile.backend -t carepath-backend:latest ..

# Tag for ECR
docker tag carepath-backend:latest 363401891883.dkr.ecr.us-east-1.amazonaws.com/carepath-backend:latest

# Push to ECR
docker push 363401891883.dkr.ecr.us-east-1.amazonaws.com/carepath-backend:latest

# Update ECS Task Definition with environment variables
aws ecs describe-task-definition \
  --task-definition carepath-backend-prod \
  --region us-east-1 > task-def.json

# Edit task-def.json to add these environment variables:
# {
#   "name": "QUICKSIGHT_DASHBOARD_ID",
#   "value": "abcbf9d1-c35d-4b45-9e28-b7cdc7e964f3"
# },
# {
#   "name": "AWS_ACCOUNT_ID",
#   "value": "363401891883"
# },
# {
#   "name": "AWS_REGION",
#   "value": "us-east-1"
# }

# Register updated task definition
aws ecs register-task-definition --cli-input-json file://task-def.json

# Force new deployment
aws ecs update-service \
  --cluster carepath-ecs-prod \
  --service carepath-backend-prod \
  --force-new-deployment \
  --region us-east-1

# Monitor deployment (wait until it shows RUNNING)
aws ecs describe-services \
  --cluster carepath-ecs-prod \
  --services carepath-backend-prod \
  --region us-east-1 \
  --query 'services[0].deployments'
```

### Step 5: Deploy Frontend to Production

```bash
# Navigate to frontend directory
cd /Users/vishwa/Desktop/CarePath_CTS

# Commit changes
git add .
git commit -m "Add QuickSight dashboard integration to analytics page"
git push origin main

# Build production bundle
npm run build

# Get your CloudFront distribution ID
aws cloudfront list-distributions --query 'DistributionList.Items[?Comment==`CarePath Frontend`].Id' --output text

# Deploy to S3
aws s3 sync dist/ s3://carepath-frontend-prod --delete

# Invalidate CloudFront cache (replace DISTRIBUTION_ID with actual ID)
aws cloudfront create-invalidation \
  --distribution-id YOUR_DISTRIBUTION_ID \
  --paths "/*"
```

### Step 6: Verify Integration

1. **Test Backend Health**
   ```bash
   curl https://d1i62cubxntt9j.cloudfront.net/api/v1/quicksight/health
   ```
   Expected response:
   ```json
   {
     "status": "configured",
     "dashboard_id": "abcbf9d1-c35d-4b45-9e28-b7cdc7e964f3",
     "message": "QuickSight integration is ready"
   }
   ```

2. **Test Embed URL Generation**
   ```bash
   curl https://d1i62cubxntt9j.cloudfront.net/api/v1/quicksight/embed-url
   ```
   Should return a valid embed URL

3. **Test Frontend**
   - Navigate to: https://d2wdvr99379bz0.cloudfront.net/care-manager/analytics
   - The QuickSight dashboard should load in the "Live Analytics Dashboard" section

---

## 🔧 Quick Test Locally First

Before deploying to production, test locally:

```bash
# Start backend locally
cd /Users/vishwa/Desktop/CarepathAI_backend
uvicorn main:app --reload

# In another terminal, start frontend
cd /Users/vishwa/Desktop/CarePath_CTS
npm run dev

# Test in browser
# Go to: http://localhost:5173/care-manager/analytics
# The dashboard should load (after Step 1 & 2 are done)
```

---

## 📋 Checklist

- [ ] Step 1: Add domains to QuickSight allowed list
- [ ] Step 1: Enable anonymous embedding in QuickSight
- [ ] Step 2: Configure dashboard for public/anonymous access
- [ ] Step 3: Setup auto-refresh schedule for dataset
- [ ] Step 4: Test locally first (http://localhost:5173)
- [ ] Step 5: Deploy backend to production
- [ ] Step 6: Deploy frontend to production
- [ ] Step 7: Test production URLs
- [ ] Step 8: Verify dashboard loads and refreshes

---

## 🎯 Expected Result

Once complete, your care managers will see:

1. **Analytics Page** at `/care-manager/analytics`
2. **KPI Cards** showing risk distribution
3. **Live Analytics Dashboard** section with embedded QuickSight
4. **Interactive Charts** from your ml_predictions data
5. **Auto-refreshing Data** based on your schedule
6. **Filters and Controls** you configured in QuickSight

---

## 🆘 Common Issues

### Issue: "Dashboard not configured"
- **Solution**: Make sure environment variables are set in ECS Task Definition

### Issue: "Domain not allowed"
- **Solution**: Add exact domains (no trailing slash) in QuickSight settings

### Issue: Dashboard shows but says "Access Denied"
- **Solution**: Enable anonymous embedding in QuickSight dashboard settings

### Issue: Dashboard shows old data
- **Solution**: Trigger manual refresh or setup scheduled refresh

### Issue: CORS errors
- **Solution**: Verify allowed domains match frontend URL exactly

---

## 📞 Support

If you encounter issues:

1. Check CloudWatch logs:
   ```bash
   aws logs tail /ecs/carepath-backend-prod --follow
   ```

2. Check browser console for errors (F12)

3. Test API endpoints directly with curl

4. Verify QuickSight permissions and settings

---

## 🎉 Success!

You'll know it's working when you can:
- Navigate to the analytics page
- See the QuickSight dashboard embedded
- Interact with the charts and filters
- See your prediction data visualized
- Dashboard refreshes automatically with new data
