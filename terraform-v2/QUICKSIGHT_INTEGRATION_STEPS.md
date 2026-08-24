# QuickSight Dashboard Integration - Complete Setup Guide

## ✅ What We've Done

### Backend Setup
1. ✅ Created `/app/api/v1/endpoints/quicksight.py` - API endpoint for generating signed embed URLs
2. ✅ Registered QuickSight router in `/app/api/v1/api.py`
3. ✅ Configured anonymous embedding with allowed domains

### Frontend Setup
1. ✅ Created `QuickSightDashboard.tsx` component for embedding
2. ✅ Added QuickSight styles to `care-manager.css`
3. ✅ Integrated dashboard into Analytics page (`/care-manager/analytics`)

---

## 🎯 What You Need To Do Next

### Step 1: Publish Your QuickSight Dashboard

1. **Go to QuickSight Console**
   - Navigate to: https://us-east-1.quicksight.aws.amazon.com/
   - Go to "Dashboards" section

2. **Publish Your Dashboard**
   - Open your dashboard in QuickSight
   - Click "Share" → "Publish dashboard"
   - Give it a name (e.g., "CarePath Analytics Dashboard")
   - Click "Publish"

3. **Get the Dashboard ID**
   - After publishing, look at the URL in your browser
   - It will look like: `https://...quicksight.aws.amazon.com/.../dashboards/YOUR_DASHBOARD_ID`
   - Copy the Dashboard ID (it's a UUID like `12345678-1234-1234-1234-123456789abc`)

### Step 2: Enable Anonymous Embedding

1. **In QuickSight Console**
   - Click your profile icon (top right)
   - Select "Manage QuickSight"
   - Go to "Domains and embedding" (left menu under "Security & permissions")

2. **Add Allowed Domains**
   - Click "Add domains"
   - Add these two domains:
     ```
     http://localhost:5173
     https://d2wdvr99379bz0.cloudfront.net
     ```
   - Click "Add"

3. **Enable Anonymous Embedding**
   - In the same "Domains and embedding" section
   - Toggle "Enable" for anonymous embedding
   - Confirm the action

### Step 3: Configure Dashboard Settings

1. **Open Your Dashboard**
   - Go to your published dashboard
   - Click "Share" → "Embed"

2. **Enable Anonymous Access**
   - Select "Enable public access"
   - Or configure anonymous user embedding settings
   - Save the settings

### Step 4: Setup Scheduled Refresh

1. **In QuickSight**
   - Go to "Datasets"
   - Find your dataset (the one using custom SQL queries)
   - Click on it

2. **Configure SPICE Refresh**
   - Click "Refresh" tab
   - Click "Add schedule"
   - Choose refresh frequency:
     - **Hourly** - For near real-time updates
     - **Every 15 minutes** - For frequent updates (requires QuickSight Enterprise)
     - **Daily** - For less frequent updates
   - Set the timezone
   - Click "Create"

### Step 5: Update Backend Configuration

1. **Add Environment Variables**
   
   Add to `/Users/vishwa/Desktop/CarepathAI_backend/.env`:
   ```bash
   # QuickSight Configuration
   QUICKSIGHT_DASHBOARD_ID=YOUR_DASHBOARD_ID_HERE
   AWS_ACCOUNT_ID=363401891883
   AWS_REGION=us-east-1
   ```

2. **Replace Dashboard ID**
   - Open `.env` file
   - Replace `YOUR_DASHBOARD_ID_HERE` with the actual Dashboard ID from Step 1

### Step 6: Deploy Backend Changes

1. **Commit and Push Changes**
   ```bash
   cd /Users/vishwa/Desktop/CarepathAI_backend
   git add .
   git commit -m "Add QuickSight dashboard integration"
   git push origin main
   ```

2. **Rebuild and Deploy Docker Image**
   ```bash
   cd terraform-v2
   
   # Build new image
   docker build -f Dockerfile.backend -t carepath-backend:latest ..
   
   # Tag for ECR
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 363401891883.dkr.ecr.us-east-1.amazonaws.com
   docker tag carepath-backend:latest 363401891883.dkr.ecr.us-east-1.amazonaws.com/carepath-backend:latest
   
   # Push to ECR
   docker push 363401891883.dkr.ecr.us-east-1.amazonaws.com/carepath-backend:latest
   ```

3. **Update ECS Service**
   ```bash
   # Force new deployment
   aws ecs update-service \
     --cluster carepath-ecs-prod \
     --service carepath-backend-prod \
     --force-new-deployment \
     --region us-east-1
   ```

4. **Monitor Deployment**
   ```bash
   # Watch service status
   aws ecs describe-services \
     --cluster carepath-ecs-prod \
     --services carepath-backend-prod \
     --region us-east-1 \
     --query 'services[0].deployments'
   ```

### Step 7: Deploy Frontend Changes

1. **Commit and Push Frontend**
   ```bash
   cd /Users/vishwa/Desktop/CarePath_CTS
   git add .
   git commit -m "Add QuickSight dashboard to analytics page"
   git push origin main
   ```

2. **Build and Deploy**
   ```bash
   # Build production bundle
   npm run build
   
   # Deploy to S3
   aws s3 sync dist/ s3://carepath-frontend-prod --delete
   
   # Invalidate CloudFront cache
   aws cloudfront create-invalidation \
     --distribution-id E2XXXXXXXXXX \
     --paths "/*"
   ```

### Step 8: Test the Integration

1. **Test Backend Endpoint**
   ```bash
   # Health check
   curl https://d1i62cubxntt9j.cloudfront.net/api/v1/quicksight/health
   
   # Should return:
   # {
   #   "status": "configured",
   #   "dashboard_id": "your-dashboard-id",
   #   "message": "QuickSight integration is ready"
   # }
   ```

2. **Test Embed URL Generation**
   ```bash
   curl https://d1i62cubxntt9j.cloudfront.net/api/v1/quicksight/embed-url
   
   # Should return:
   # {
   #   "embed_url": "https://...quicksight.aws.amazon.com/...",
   #   "dashboard_id": "your-dashboard-id"
   # }
   ```

3. **Test Frontend**
   - Navigate to: https://d2wdvr99379bz0.cloudfront.net/care-manager/analytics
   - The QuickSight dashboard should load in the "Live Analytics Dashboard" section
   - You should see your visualizations and data

---

## 🔍 Troubleshooting

### Error: "Dashboard not configured"
- **Cause**: Environment variable `QUICKSIGHT_DASHBOARD_ID` is not set
- **Fix**: Add the dashboard ID to `.env` and redeploy

### Error: "Dashboard not found"
- **Cause**: Invalid dashboard ID or dashboard not published
- **Fix**: Verify the dashboard ID and ensure the dashboard is published

### Error: "Invalid configuration"
- **Cause**: Anonymous embedding is not enabled
- **Fix**: Enable anonymous embedding in QuickSight settings (Step 2)

### Error: "Domain not allowed"
- **Cause**: Frontend domain not in allowed domains list
- **Fix**: Add your frontend domain to QuickSight allowed domains (Step 2)

### Dashboard Loads But Shows Old Data
- **Cause**: SPICE refresh not scheduled
- **Fix**: Setup scheduled refresh in QuickSight (Step 4)

### CORS Errors
- **Cause**: Backend not properly configured
- **Fix**: Ensure allowed domains match exactly (no trailing slashes)

---

## 📊 Dashboard Features Available

Once setup is complete, your analytics page will show:

1. **Real-time Metrics** from `ml_predictions` table
2. **Auto-refreshing Data** based on your SPICE schedule
3. **Interactive Filters** in the QuickSight dashboard
4. **Drill-down Capabilities** if configured in QuickSight
5. **Export Options** (if enabled in dashboard settings)

---

## 🎉 Success Indicators

You'll know it's working when:

1. ✅ Backend health endpoint returns "configured"
2. ✅ Backend embed-url endpoint returns a valid URL
3. ✅ Frontend analytics page loads without errors
4. ✅ QuickSight dashboard appears in the iframe
5. ✅ Dashboard shows your prediction data
6. ✅ Dashboard refreshes with new data automatically

---

## 📝 Next Steps After Integration

1. **Customize Dashboard**
   - Add more visualizations in QuickSight
   - Create calculated fields for advanced metrics
   - Add filters for care managers to explore data

2. **Performance Optimization**
   - Monitor SPICE refresh times
   - Optimize SQL queries if needed
   - Consider incremental refresh for large datasets

3. **User Training**
   - Document dashboard features for care managers
   - Create guides for interpreting the analytics
   - Share best practices for using filters

---

## 🆘 Need Help?

If you encounter any issues:

1. Check CloudWatch logs for backend errors:
   ```bash
   aws logs tail /ecs/carepath-backend-prod --follow
   ```

2. Check browser console for frontend errors

3. Verify QuickSight dashboard permissions and settings

4. Test the API endpoints directly with curl/Postman

5. Review this guide's troubleshooting section
