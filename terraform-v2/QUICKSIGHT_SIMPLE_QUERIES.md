# 📊 QuickSight Simple Queries - Based on Actual Schema

These queries work with your actual database schema and won't timeout.

---

## ✅ Query 1: Basic Patient Overview (START WITH THIS)

```sql
-- Test this first - simplest query
SELECT 
    patient_id,
    name,
    age,
    gender,
    discharge_date,
    length_of_stay,
    charlson_comorbidity_index as risk_score,
    CASE 
        WHEN charlson_comorbidity_index >= 4 THEN 'high'
        WHEN charlson_comorbidity_index >= 2 THEN 'medium'
        ELSE 'low'
    END as risk_level,
    is_active,
    created_at
FROM patient_ehr
WHERE is_active = 1
LIMIT 100;
```

---

## ✅ Query 2: Patient Count by Risk Level

```sql
-- Simple aggregation
SELECT 
    CASE 
        WHEN charlson_comorbidity_index >= 4 THEN 'high'
        WHEN charlson_comorbidity_index >= 2 THEN 'medium'
        ELSE 'low'
    END as risk_level,
    COUNT(*) as patient_count,
    ROUND(AVG(age), 1) as avg_age,
    ROUND(AVG(length_of_stay), 1) as avg_los
FROM patient_ehr
WHERE is_active = 1
GROUP BY 
    CASE 
        WHEN charlson_comorbidity_index >= 4 THEN 'high'
        WHEN charlson_comorbidity_index >= 2 THEN 'medium'
        ELSE 'low'
    END;
```

---

## ✅ Query 3: Readmission Risk Dashboard

```sql
-- Readmission predictions
SELECT 
    rp.patient_id,
    pe.name as patient_name,
    pe.age,
    pe.gender,
    rp.risk_score,
    rp.risk_level,
    rp.predicted_at,
    pe.discharge_date,
    pe.length_of_stay,
    pe.previous_admissions_12m,
    pe.charlson_comorbidity_index,
    pe.follow_up_within_7_days_flag,
    EXTRACT(DAY FROM (CURRENT_DATE - pe.discharge_date)) as days_since_discharge
FROM readmission_predictions rp
INNER JOIN patient_ehr pe ON rp.patient_id = pe.patient_id
WHERE pe.is_active = 1
  AND pe.discharge_date IS NOT NULL
ORDER BY rp.risk_score DESC
LIMIT 500;
```

---

## ✅ Query 4: Condition Flags Summary

```sql
-- Health conditions overview
SELECT 
    COUNT(*) as total_patients,
    SUM(diabetes_flag) as diabetes_count,
    SUM(hypertension_flag) as hypertension_count,
    SUM(heart_failure_flag) as heart_failure_count,
    SUM(copd_asthma_flag) as copd_asthma_count,
    SUM(ckd_flag) as ckd_count,
    SUM(icu_stay_flag) as icu_stay_count,
    ROUND(AVG(age), 1) as avg_age,
    ROUND(AVG(length_of_stay), 1) as avg_length_of_stay
FROM patient_ehr
WHERE is_active = 1;
```

---

## ✅ Query 5: Patients Needing Follow-up

```sql
-- Post-discharge follow-up tracking
SELECT 
    patient_id,
    name,
    age,
    discharge_date,
    follow_up_appointment_date,
    follow_up_within_7_days_flag,
    EXTRACT(DAY FROM (CURRENT_DATE - discharge_date)) as days_since_discharge,
    CASE 
        WHEN follow_up_within_7_days_flag = 1 THEN 'Completed'
        WHEN follow_up_appointment_date < CURRENT_DATE THEN 'Missed'
        WHEN follow_up_appointment_date IS NULL THEN 'Not Scheduled'
        ELSE 'Scheduled'
    END as followup_status,
    CASE 
        WHEN charlson_comorbidity_index >= 4 THEN 'high'
        WHEN charlson_comorbidity_index >= 2 THEN 'medium'
        ELSE 'low'
    END as risk_level
FROM patient_ehr
WHERE discharge_date IS NOT NULL
  AND discharge_date >= CURRENT_DATE - INTERVAL '30 days'
  AND is_active = 1
ORDER BY discharge_date DESC
LIMIT 200;
```

---

## ✅ Query 6: Monthly Patient Trend

```sql
-- Patient enrollment over time
SELECT 
    TO_CHAR(created_at, 'YYYY-MM') as enrollment_month,
    COUNT(*) as new_patients,
    ROUND(AVG(age), 1) as avg_age,
    SUM(CASE WHEN charlson_comorbidity_index >= 4 THEN 1 ELSE 0 END) as high_risk_count
FROM patient_ehr
WHERE created_at >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY TO_CHAR(created_at, 'YYYY-MM')
ORDER BY enrollment_month;
```

---

## ✅ Query 7: Vital Signs Overview

```sql
-- Current vital signs for active patients
SELECT 
    patient_id,
    name,
    age,
    systolic_bp,
    diastolic_bp,
    heart_rate,
    temperature,
    spo2,
    pain_score_clinical,
    CASE 
        WHEN systolic_bp > 140 OR diastolic_bp > 90 THEN 'High BP'
        WHEN heart_rate > 100 THEN 'Elevated HR'
        WHEN spo2 < 95 THEN 'Low O2'
        ELSE 'Normal'
    END as vital_alert,
    updated_at as last_measurement
FROM patient_ehr
WHERE is_active = 1
  AND (systolic_bp IS NOT NULL OR heart_rate IS NOT NULL)
ORDER BY updated_at DESC
LIMIT 100;
```

---

## ✅ Query 8: Lab Results Summary

```sql
-- Recent lab results
SELECT 
    patient_id,
    name,
    age,
    hba1c,
    creatinine,
    egfr,
    sodium,
    potassium,
    hemoglobin,
    CASE 
        WHEN hba1c > 7.0 THEN 'Uncontrolled Diabetes'
        WHEN egfr < 60 THEN 'Kidney Disease'
        WHEN hemoglobin < 12.0 THEN 'Anemia'
        ELSE 'Normal'
    END as lab_alert,
    diabetes_flag,
    ckd_flag
FROM patient_ehr
WHERE is_active = 1
  AND (hba1c IS NOT NULL OR creatinine IS NOT NULL)
ORDER BY updated_at DESC
LIMIT 100;
```

---

## ✅ Query 9: Medication Adherence

```sql
-- Medication adherence tracking
SELECT 
    CASE 
        WHEN medication_adherence_rate >= 80 THEN 'Good'
        WHEN medication_adherence_rate >= 50 THEN 'Fair'
        ELSE 'Poor'
    END as adherence_category,
    COUNT(*) as patient_count,
    ROUND(AVG(medication_adherence_rate), 2) as avg_adherence,
    ROUND(AVG(active_medication_count), 1) as avg_medication_count,
    SUM(CASE WHEN charlson_comorbidity_index >= 4 THEN 1 ELSE 0 END) as high_risk_count
FROM patient_ehr
WHERE medication_adherence_rate IS NOT NULL
  AND is_active = 1
GROUP BY 
    CASE 
        WHEN medication_adherence_rate >= 80 THEN 'Good'
        WHEN medication_adherence_rate >= 50 THEN 'Fair'
        ELSE 'Poor'
    END;
```

---

## ✅ Query 10: Notifications Dashboard

```sql
-- Recent notifications
SELECT 
    notification_type,
    status,
    priority,
    COUNT(*) as notification_count,
    COUNT(CASE WHEN status = 'unread' THEN 1 END) as unread_count,
    MIN(created_at) as oldest_notification,
    MAX(created_at) as newest_notification
FROM notifications
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY notification_type, status, priority
ORDER BY 
    CASE priority
        WHEN 'urgent' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        ELSE 4
    END,
    notification_count DESC;
```

---

## 🎨 How to Use in QuickSight

### Step 1: Test Query First
1. Copy Query 1 (Basic Patient Overview)
2. In QuickSight, click **"New dataset"** → **"PostgreSQL"**
3. Use your VPC connection
4. Click **"Custom SQL"**
5. Paste the query
6. Click **"Confirm query"**
7. If it works, click **"Select"**

### Step 2: Create Visualizations

**For Query 1 (Patient Overview):**
- KPI: Count of `patient_id` (Total Patients)
- Donut Chart: `risk_level` vs COUNT(*)
- Bar Chart: `age` (bins) vs COUNT(*)
- Line Chart: `created_at` (by month) vs COUNT(*)

**For Query 2 (Risk Level):**
- Vertical Bar Chart: `risk_level` vs `patient_count`
- KPI Cards: One for each risk level

**For Query 3 (Readmission Risk):**
- Table: Top 20 high-risk patients
- Scatter Plot: `days_since_discharge` vs `risk_score`
- Heatmap: `risk_level` vs `length_of_stay`

**For Query 5 (Follow-up):**
- Pie Chart: `followup_status` distribution
- Table: Missed follow-ups (filter where status = 'Missed')
- KPI: Count of patients needing follow-up

**For Query 10 (Notifications):**
- Stacked Bar: `notification_type` by `status`
- KPI: `unread_count`
- Line Chart: Daily notification trend

### Step 3: Add Filters

Add these parameter controls:
- **Date Range**: Last 7/30/90 days
- **Risk Level**: High/Medium/Low
- **Active Status**: Active/All

### Step 4: Refresh Schedule

- Go to **Datasets** → Your dataset → **Schedule refresh**
- Set to refresh every **1 hour** (or 15 minutes if needed)
- Enable **automatic refresh**

---

## 🚨 Troubleshooting

### If query still times out:

1. **Add LIMIT**: Always use `LIMIT 500` or less for initial testing
2. **Add WHERE clause**: Filter by date range (last 30 days)
3. **Remove JOINs**: Start with single table queries
4. **Use indexes**: Our schema has indexes on key fields

### Example minimal query:

```sql
-- Absolute minimum - just to test connection
SELECT 
    patient_id,
    name,
    age,
    is_active
FROM patient_ehr
LIMIT 10;
```

### Check database performance:

```sql
-- See if there's data
SELECT COUNT(*) FROM patient_ehr;
SELECT COUNT(*) FROM readmission_predictions;
SELECT COUNT(*) FROM notifications;
```

---

## ✅ Quick Wins - Build These First

1. **Patient Count KPI** - Query 1
2. **Risk Distribution Donut** - Query 2  
3. **Readmission List Table** - Query 3
4. **Follow-up Status Pie** - Query 5
5. **Notification Alert Count** - Query 10

These 5 visualizations will give you a functional dashboard in under 30 minutes!

---

Need help? Start with the absolute minimum query and build up from there.
