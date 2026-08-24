# 📊 QuickSight Analytics Dashboard for Care Manager

Complete guide to create a live, interactive analytics dashboard with filters for care managers.

---

## 🎯 Dashboard Overview

This dashboard will provide real-time insights for care managers with:
- **Live Updates**: Refresh data automatically
- **Interactive Filters**: Filter by date, care manager, risk level, etc.
- **Key Metrics**: Patient stats, readmission rates, task completion, etc.
- **Visualizations**: Charts, graphs, heatmaps, and trend analysis

---

## 📋 Step 1: Create Custom SQL Datasets

After connecting QuickSight to your RDS database, create these custom SQL datasets:

### Dataset 1: Patient Overview Dashboard

```sql
-- Name: patient_overview_dashboard
SELECT 
    p.id as patient_id,
    p.name as patient_name,
    p.age,
    p.gender,
    p.primary_diagnosis,
    p.risk_level,
    p.risk_score,
    p.insurance_type,
    p.admission_date,
    p.discharge_date,
    p.created_at as enrollment_date,
    
    -- Care Manager Info
    cm.id as care_manager_id,
    cm.name as care_manager_name,
    cm.email as care_manager_email,
    cm.specialization,
    
    -- Risk Predictions
    rp.readmission_risk,
    rp.readmission_probability,
    rp.ed_visit_risk,
    rp.predicted_los_days,
    rp.prediction_date,
    
    -- Appointment Stats
    COUNT(DISTINCT a.id) as total_appointments,
    SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) as completed_appointments,
    SUM(CASE WHEN a.status = 'scheduled' THEN 1 ELSE 0 END) as scheduled_appointments,
    SUM(CASE WHEN a.status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_appointments,
    
    -- Task Completion
    COUNT(DISTINCT pdt.id) as total_tasks,
    SUM(CASE WHEN pdt.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
    SUM(CASE WHEN pdt.status = 'pending' THEN 1 ELSE 0 END) as pending_tasks,
    
    -- Days Since Last Contact
    EXTRACT(DAY FROM (CURRENT_DATE - MAX(a.appointment_date))) as days_since_last_contact,
    
    -- Length of Stay
    CASE 
        WHEN p.discharge_date IS NOT NULL 
        THEN EXTRACT(DAY FROM (p.discharge_date - p.admission_date))
        ELSE NULL 
    END as length_of_stay_days

FROM patients p
LEFT JOIN care_managers cm ON p.care_manager_id = cm.id
LEFT JOIN risk_predictions rp ON p.id = rp.patient_id
LEFT JOIN appointments a ON p.id = a.patient_id
LEFT JOIN post_discharge_tasks pdt ON p.id = pdt.patient_id

GROUP BY 
    p.id, p.name, p.age, p.gender, p.primary_diagnosis, p.risk_level, 
    p.risk_score, p.insurance_type, p.admission_date, p.discharge_date, 
    p.created_at, cm.id, cm.name, cm.email, cm.specialization,
    rp.readmission_risk, rp.readmission_probability, rp.ed_visit_risk,
    rp.predicted_los_days, rp.prediction_date;
```

### Dataset 2: Care Manager Performance

```sql
-- Name: care_manager_performance
SELECT 
    cm.id as care_manager_id,
    cm.name as care_manager_name,
    cm.email,
    cm.phone,
    cm.specialization,
    cm.department,
    
    -- Patient Load
    COUNT(DISTINCT p.id) as total_patients,
    SUM(CASE WHEN p.risk_level = 'high' THEN 1 ELSE 0 END) as high_risk_patients,
    SUM(CASE WHEN p.risk_level = 'medium' THEN 1 ELSE 0 END) as medium_risk_patients,
    SUM(CASE WHEN p.risk_level = 'low' THEN 1 ELSE 0 END) as low_risk_patients,
    
    -- Appointment Metrics
    COUNT(DISTINCT a.id) as total_appointments,
    SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) as completed_appointments,
    ROUND(
        SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END)::numeric / 
        NULLIF(COUNT(DISTINCT a.id), 0) * 100, 
        2
    ) as appointment_completion_rate,
    
    -- Task Management
    COUNT(DISTINCT pdt.id) as total_tasks,
    SUM(CASE WHEN pdt.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
    ROUND(
        SUM(CASE WHEN pdt.status = 'completed' THEN 1 ELSE 0 END)::numeric / 
        NULLIF(COUNT(DISTINCT pdt.id), 0) * 100, 
        2
    ) as task_completion_rate,
    
    -- Average Response Time (in days)
    ROUND(
        AVG(EXTRACT(DAY FROM (a.appointment_date - a.created_at))),
        1
    ) as avg_response_time_days,
    
    -- Readmission Prevention
    COUNT(DISTINCT CASE 
        WHEN rp.readmission_probability < 0.3 
        THEN p.id 
    END) as low_readmission_risk_count,
    
    -- Active vs Discharged
    SUM(CASE WHEN p.discharge_date IS NULL THEN 1 ELSE 0 END) as active_patients,
    SUM(CASE WHEN p.discharge_date IS NOT NULL THEN 1 ELSE 0 END) as discharged_patients,
    
    -- Last Activity
    MAX(a.appointment_date) as last_appointment_date

FROM care_managers cm
LEFT JOIN patients p ON cm.id = p.care_manager_id
LEFT JOIN appointments a ON p.id = a.patient_id
LEFT JOIN post_discharge_tasks pdt ON p.id = pdt.patient_id
LEFT JOIN risk_predictions rp ON p.id = rp.patient_id

GROUP BY 
    cm.id, cm.name, cm.email, cm.phone, cm.specialization, cm.department;
```

### Dataset 3: Readmission Risk Analysis

```sql
-- Name: readmission_risk_analysis
SELECT 
    p.id as patient_id,
    p.name as patient_name,
    p.age,
    p.gender,
    p.primary_diagnosis,
    p.admission_date,
    p.discharge_date,
    
    -- Risk Metrics
    rp.readmission_risk,
    rp.readmission_probability * 100 as readmission_probability_pct,
    rp.ed_visit_risk,
    rp.predicted_los_days,
    
    -- Risk Factors
    rp.risk_factors,
    
    -- Categorize Risk Level
    CASE 
        WHEN rp.readmission_probability >= 0.7 THEN 'Very High'
        WHEN rp.readmission_probability >= 0.5 THEN 'High'
        WHEN rp.readmission_probability >= 0.3 THEN 'Medium'
        ELSE 'Low'
    END as readmission_category,
    
    -- Days Since Discharge
    CASE 
        WHEN p.discharge_date IS NOT NULL 
        THEN EXTRACT(DAY FROM (CURRENT_DATE - p.discharge_date))
        ELSE 0 
    END as days_since_discharge,
    
    -- Care Manager
    cm.name as care_manager_name,
    
    -- Follow-up Status
    COUNT(DISTINCT a.id) FILTER (
        WHERE a.appointment_date >= p.discharge_date
    ) as post_discharge_appointments,
    
    -- Task Completion
    COUNT(DISTINCT pdt.id) as assigned_tasks,
    SUM(CASE WHEN pdt.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks

FROM patients p
LEFT JOIN risk_predictions rp ON p.id = rp.patient_id
LEFT JOIN care_managers cm ON p.care_manager_id = cm.id
LEFT JOIN appointments a ON p.id = a.patient_id
LEFT JOIN post_discharge_tasks pdt ON p.id = pdt.patient_id

WHERE rp.readmission_probability IS NOT NULL

GROUP BY 
    p.id, p.name, p.age, p.gender, p.primary_diagnosis, 
    p.admission_date, p.discharge_date, 
    rp.readmission_risk, rp.readmission_probability, rp.ed_visit_risk,
    rp.predicted_los_days, rp.risk_factors, cm.name;
```

### Dataset 4: Financial Metrics

```sql
-- Name: financial_metrics
SELECT 
    p.id as patient_id,
    p.name as patient_name,
    p.insurance_type,
    p.primary_diagnosis,
    
    -- Length of Stay Cost Impact
    CASE 
        WHEN p.discharge_date IS NOT NULL 
        THEN EXTRACT(DAY FROM (p.discharge_date - p.admission_date))
        ELSE EXTRACT(DAY FROM (CURRENT_DATE - p.admission_date))
    END as length_of_stay_days,
    
    -- Estimated Cost (assuming $2000/day average)
    CASE 
        WHEN p.discharge_date IS NOT NULL 
        THEN EXTRACT(DAY FROM (p.discharge_date - p.admission_date)) * 2000
        ELSE EXTRACT(DAY FROM (CURRENT_DATE - p.admission_date)) * 2000
    END as estimated_cost,
    
    -- Care Manager
    cm.name as care_manager_name,
    cm.department,
    
    -- Risk Level
    p.risk_level,
    rp.readmission_probability,
    
    -- Potential Savings (if readmission prevented)
    CASE 
        WHEN rp.readmission_probability >= 0.7 THEN 30000
        WHEN rp.readmission_probability >= 0.5 THEN 20000
        WHEN rp.readmission_probability >= 0.3 THEN 10000
        ELSE 0
    END as potential_savings,
    
    -- Admission Type
    CASE 
        WHEN p.admission_date IS NOT NULL THEN 'Inpatient'
        ELSE 'Outpatient'
    END as admission_type,
    
    -- Quarter and Year for Trend Analysis
    EXTRACT(QUARTER FROM p.admission_date) as admission_quarter,
    EXTRACT(YEAR FROM p.admission_date) as admission_year,
    TO_CHAR(p.admission_date, 'YYYY-MM') as admission_month

FROM patients p
LEFT JOIN care_managers cm ON p.care_manager_id = cm.id
LEFT JOIN risk_predictions rp ON p.id = rp.patient_id

WHERE p.admission_date IS NOT NULL;
```

### Dataset 5: Post-Discharge Follow-up

```sql
-- Name: post_discharge_followup
SELECT 
    p.id as patient_id,
    p.name as patient_name,
    p.discharge_date,
    
    -- Days Since Discharge
    EXTRACT(DAY FROM (CURRENT_DATE - p.discharge_date)) as days_since_discharge,
    
    -- 30-Day Window Status
    CASE 
        WHEN EXTRACT(DAY FROM (CURRENT_DATE - p.discharge_date)) <= 30 THEN 'Within 30 Days'
        ELSE 'Beyond 30 Days'
    END as followup_window,
    
    -- Care Manager
    cm.name as care_manager_name,
    
    -- Tasks
    pdt.task_type,
    pdt.title as task_title,
    pdt.status as task_status,
    pdt.due_date,
    pdt.completed_date,
    
    -- Task Overdue Status
    CASE 
        WHEN pdt.status != 'completed' AND pdt.due_date < CURRENT_DATE THEN 'Overdue'
        WHEN pdt.status = 'completed' THEN 'Completed'
        ELSE 'On Track'
    END as task_timeline_status,
    
    -- Appointments
    COUNT(DISTINCT a.id) FILTER (
        WHERE a.appointment_date >= p.discharge_date
    ) as post_discharge_appointments,
    
    -- Next Appointment
    MIN(a.appointment_date) FILTER (
        WHERE a.appointment_date > CURRENT_DATE AND a.status = 'scheduled'
    ) as next_appointment_date,
    
    -- Risk Level
    p.risk_level,
    rp.readmission_probability * 100 as readmission_probability_pct

FROM patients p
LEFT JOIN care_managers cm ON p.care_manager_id = cm.id
LEFT JOIN post_discharge_tasks pdt ON p.id = pdt.patient_id
LEFT JOIN appointments a ON p.id = a.patient_id
LEFT JOIN risk_predictions rp ON p.id = rp.patient_id

WHERE p.discharge_date IS NOT NULL
  AND p.discharge_date >= CURRENT_DATE - INTERVAL '90 days'

GROUP BY 
    p.id, p.name, p.discharge_date, p.risk_level,
    cm.name, pdt.id, pdt.task_type, pdt.title, pdt.status, 
    pdt.due_date, pdt.completed_date, rp.readmission_probability;
```

---

## 🎨 Step 2: Build Dashboard Visualizations

### Dashboard Layout: "Care Manager Analytics"

Create a new **Analysis** in QuickSight with these visuals:

#### **Section 1: Key Performance Indicators (KPIs)** - Top Row

1. **Total Active Patients** (KPI)
   - Dataset: `patient_overview_dashboard`
   - Value: `COUNT(DISTINCT patient_id)` WHERE `discharge_date IS NULL`
   - Comparison: Previous period

2. **High Risk Patients** (KPI)
   - Dataset: `patient_overview_dashboard`
   - Value: `COUNT(DISTINCT patient_id)` WHERE `risk_level = 'high'`
   - Color: Red if >30, Yellow if >15, Green otherwise

3. **Readmission Rate** (KPI)
   - Dataset: `readmission_risk_analysis`
   - Value: `AVG(readmission_probability_pct)`
   - Format: Percentage

4. **Task Completion Rate** (KPI)
   - Dataset: `care_manager_performance`
   - Value: `AVG(task_completion_rate)`
   - Format: Percentage

5. **Appointment Adherence** (KPI)
   - Dataset: `care_manager_performance`
   - Value: `AVG(appointment_completion_rate)`
   - Format: Percentage

#### **Section 2: Patient Distribution** - Second Row

6. **Patients by Risk Level** (Donut Chart)
   - Dataset: `patient_overview_dashboard`
   - Group by: `risk_level`
   - Value: `COUNT(DISTINCT patient_id)`
   - Colors: Red (High), Orange (Medium), Green (Low)

7. **Patients by Care Manager** (Horizontal Bar Chart)
   - Dataset: `care_manager_performance`
   - Y-axis: `care_manager_name`
   - X-axis: `total_patients`
   - Color by: `avg_task_completion_rate`

8. **Age Distribution** (Histogram)
   - Dataset: `patient_overview_dashboard`
   - X-axis: `age` (bins of 10)
   - Y-axis: `COUNT(patient_id)`

#### **Section 3: Trends & Analytics** - Third Row

9. **Patient Enrollment Trend** (Line Chart)
   - Dataset: `patient_overview_dashboard`
   - X-axis: `enrollment_date` (by month)
   - Y-axis: `COUNT(patient_id)`
   - Line color by: `risk_level`

10. **Readmission Risk Distribution** (Box Plot)
    - Dataset: `readmission_risk_analysis`
    - Y-axis: `readmission_probability_pct`
    - Group by: `primary_diagnosis`

11. **Appointment Completion Over Time** (Area Chart)
    - Dataset: Use appointments table
    - X-axis: Date (by week)
    - Y-axis: Appointment count
    - Stack by: Status (completed, scheduled, cancelled)

#### **Section 4: Financial Insights** - Fourth Row

12. **Cost by Insurance Type** (Vertical Bar Chart)
    - Dataset: `financial_metrics`
    - X-axis: `insurance_type`
    - Y-axis: `SUM(estimated_cost)`

13. **Potential Savings** (Gauge Chart)
    - Dataset: `financial_metrics`
    - Value: `SUM(potential_savings)`
    - Target: $500,000

14. **Length of Stay Analysis** (Scatter Plot)
    - Dataset: `financial_metrics`
    - X-axis: `length_of_stay_days`
    - Y-axis: `estimated_cost`
    - Color by: `risk_level`
    - Size by: `readmission_probability`

#### **Section 5: Follow-up Tracking** - Fifth Row

15. **Post-Discharge Task Status** (Stacked Bar Chart)
    - Dataset: `post_discharge_followup`
    - X-axis: `care_manager_name`
    - Y-axis: `COUNT(tasks)`
    - Stack by: `task_timeline_status`

16. **30-Day Follow-up Heatmap** (Pivot Table/Heatmap)
    - Dataset: `post_discharge_followup`
    - Rows: `patient_name`
    - Columns: `task_type`
    - Values: `task_status`
    - Color code: Green (Completed), Yellow (On Track), Red (Overdue)

17. **Overdue Tasks Alert** (Table)
    - Dataset: `post_discharge_followup`
    - Columns: Patient Name, Task Title, Due Date, Days Overdue, Care Manager
    - Filter: `task_timeline_status = 'Overdue'`
    - Sorted by: Days Overdue (DESC)

---

## 🔄 Step 3: Add Interactive Filters

Add these **Parameter Controls** at the top of the dashboard:

### Filter 1: Date Range
```
Type: Date Range
Parameter: date_range_start, date_range_end
Apply to: All datasets
Default: Last 30 days
```

### Filter 2: Care Manager
```
Type: Multi-select Dropdown
Dataset Field: care_manager_name
Apply to: All datasets
Default: All
```

### Filter 3: Risk Level
```
Type: Multi-select Dropdown
Options: High, Medium, Low
Apply to: patient_overview_dashboard, readmission_risk_analysis
Default: All
```

### Filter 4: Patient Status
```
Type: Single-select Dropdown
Options: Active, Discharged, All
Apply to: patient_overview_dashboard
Default: Active
```

### Filter 5: Department
```
Type: Multi-select Dropdown
Dataset Field: department
Apply to: care_manager_performance
Default: All
```

---

## ⚡ Step 4: Enable Live Updates

### Option 1: SPICE with Scheduled Refresh
1. In QuickSight, go to **Datasets**
2. Select your dataset → **Schedule refresh**
3. Set frequency:
   - **Real-time critical data**: Every 15 minutes
   - **Standard analytics**: Every hour
   - **Historical trends**: Daily at midnight

### Option 2: Direct Query (Real-time)
1. When creating dataset, choose **"Direct Query"** instead of SPICE
2. Data will always be live from RDS
3. Note: Slower query performance but always current

### Recommended Hybrid Approach:
- **SPICE**: Historical trends, aggregated metrics (refresh hourly)
- **Direct Query**: Critical alerts, overdue tasks, active patients (real-time)

---

## 📱 Step 5: Embed Dashboard in Your Frontend

### Create Embedded Dashboard URL

1. In QuickSight, publish your analysis as a **Dashboard**
2. Go to Dashboard → Share → **Manage dashboard embedding**
3. Enable embedding and copy the embed URL

### Add to Your React Frontend

```typescript
// src/pages/care_manager/Analytics.tsx
import React, { useEffect, useState } from 'react';
import { embedDashboard } from 'amazon-quicksight-embedding-sdk';

const Analytics: React.FC = () => {
  const [dashboardUrl, setDashboardUrl] = useState('');

  useEffect(() => {
    // Fetch signed URL from your backend
    fetch('/api/v1/quicksight/dashboard-url')
      .then(res => res.json())
      .then(data => setDashboardUrl(data.embedUrl));
  }, []);

  useEffect(() => {
    if (dashboardUrl) {
      const containerDiv = document.getElementById('quicksight-container');
      
      const options = {
        url: dashboardUrl,
        container: containerDiv,
        height: '100%',
        width: '100%',
        scrolling: 'no',
        parameters: {
          // Pass filters from your app
          careManagerId: localStorage.getItem('careManagerId'),
          dateRange: 'last30days'
        },
        footerPaddingEnabled: true
      };

      embedDashboard(options);
    }
  }, [dashboardUrl]);

  return (
    <div style={{ height: '100vh', width: '100%' }}>
      <div id="quicksight-container" style={{ height: '100%', width: '100%' }} />
    </div>
  );
};

export default Analytics;
```

---

## 🔐 Step 6: Create Backend Endpoint for Signed URLs

```python
# app/api/v1/endpoints/quicksight.py
from fastapi import APIRouter, Depends, HTTPException
from boto3 import client
from app.core.config import settings

router = APIRouter()

@router.get("/quicksight/dashboard-url")
async def get_quicksight_dashboard_url(current_user: dict = Depends(get_current_user)):
    """
    Generate a signed URL for QuickSight dashboard embedding
    """
    try:
        quicksight = client('quicksight', region_name='us-east-1')
        
        response = quicksight.generate_embed_url_for_registered_user(
            AwsAccountId='363401891883',
            ExperienceConfiguration={
                'Dashboard': {
                    'InitialDashboardId': 'your-dashboard-id'
                }
            },
            UserArn=f'arn:aws:quicksight:us-east-1:363401891883:user/default/{current_user["email"]}',
            SessionLifetimeInMinutes=60
        )
        
        return {"embedUrl": response['EmbedUrl']}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 📊 Dashboard Features Summary

✅ **Live Data**: Auto-refresh every 15 minutes (or real-time with Direct Query)
✅ **Interactive Filters**: Date range, care manager, risk level, department, status
✅ **17 Visualizations**: KPIs, charts, graphs, heatmaps, tables
✅ **5 Custom Datasets**: Optimized SQL queries for different views
✅ **Drill-down Capability**: Click any chart to see details
✅ **Export Options**: PDF, CSV, Excel
✅ **Mobile Responsive**: Works on tablets and phones
✅ **Embedded in App**: Seamless integration with your React frontend

---

## 🎯 Next Steps

1. ✅ Complete VPC connection setup
2. ✅ Create datasets using the SQL queries above
3. ✅ Build visualizations in QuickSight
4. ✅ Add filters and parameters
5. ✅ Publish as dashboard
6. ✅ Enable embedding
7. ✅ Integrate into your frontend

**Estimated Setup Time**: 2-3 hours
**Monthly Cost**: ~$24/month (1 author) + $5/month per viewer

---

Need help with any specific step? Let me know!
