# 📊 Amazon QuickSight Setup Guide for CarePath AI

This guide will help you connect Amazon QuickSight to your RDS PostgreSQL database for analytics and dashboards.

## 🎯 Overview

QuickSight will connect to your RDS database through a VPC connection to create interactive dashboards and visualizations for:
- Patient analytics
- Care manager metrics
- Post-discharge tracking
- Financial analytics
- Readmission predictions

---

## 📋 Prerequisites

- AWS Account with QuickSight access
- RDS PostgreSQL database running (✅ Already configured)
- VPC and Security Groups configured (✅ Already configured)

---

## 🔐 Connection Details

| Parameter | Value |
|-----------|-------|
| **RDS Endpoint** | `carepath-ai-db-prod.cu5o4e24iwmf.us-east-1.rds.amazonaws.com` |
| **Port** | `5432` |
| **Database Name** | `carepath_db` |
| **Username** | `dbadmin` |
| **Password** | `E2}=9]P662Qzxx{K)HWv[[K$#hay5$58` |
| **VPC ID** | `vpc-0d2e61a92b4ca0ba3` |
| **Security Group** | `sg-0c16ac81229df3c14` |
| **Subnets** | `subnet-0a02860b167c1d5d3, subnet-05eb90e0b2e352432` |
| **Region** | `us-east-1` |

---

## 📝 Method 1: QuickSight Console (Recommended - Easiest)

### Step 1: Sign Up for QuickSight

1. Go to [Amazon QuickSight Console](https://quicksight.aws.amazon.com/)
2. If this is your first time:
   - Click **"Sign up for QuickSight"**
   - Choose **"Standard Edition"** (or Enterprise if you need advanced features)
   - Select Region: **us-east-1**
   - Enable VPC connections
   - Create account

### Step 2: Create VPC Connection

1. In QuickSight Console, click your username (top right) → **Manage QuickSight**
2. Click **Manage VPC connections** (left menu under "Security & Permissions")
3. Click **Add VPC connection**
4. Enter details:
   - **VPC connection name**: `CarePath-RDS-Connection`
   - **VPC ID**: `vpc-0d2e61a92b4ca0ba3`
   - **Subnet IDs**: Select both:
     - `subnet-0a02860b167c1d5d3`
     - `subnet-05eb90e0b2e352432`
   - **Security Group ID**: `sg-0c16ac81229df3c14`
5. Click **Create**
6. Wait 2-3 minutes for the connection to become **Available**

### Step 3: Create Data Source

1. Go back to QuickSight home
2. Click **Datasets** (left menu)
3. Click **New dataset**
4. Choose **PostgreSQL**
5. Enter connection details:
   - **Data source name**: `CarePath PostgreSQL`
   - **Connection type**: Select **"VPC connection"**
   - **VPC connection**: Select `CarePath-RDS-Connection`
   - **Database server**: `carepath-ai-db-prod.cu5o4e24iwmf.us-east-1.rds.amazonaws.com`
   - **Port**: `5432`
   - **Database name**: `carepath_db`
   - **Username**: `dbadmin`
   - **Password**: `E2}=9]P662Qzxx{K)HWv[[K$#hay5$58`
6. Click **Validate connection**
7. If successful, click **Create data source**

### Step 4: Select Tables

After creating the data source, you'll see your database tables:
- `patients`
- `care_managers`
- `appointments`
- `post_discharge_tasks`
- `risk_predictions`
- `alternate_care_assessments`
- And more...

Select the tables you want to analyze and click **Select**.

### Step 5: Create Your First Analysis

1. Choose data preparation:
   - **Direct Query**: Real-time data (slower queries)
   - **SPICE**: In-memory cache (faster, but needs refresh)
2. Click **Visualize**
3. Start creating dashboards!

---

## 🖥️ Method 2: AWS CLI

If you prefer automation, use these commands:

### Step 1: Create VPC Connection

```bash
aws quicksight create-vpc-connection \
  --aws-account-id 363401891883 \
  --vpc-connection-id carepath-rds-vpc \
  --name "CarePath RDS Connection" \
  --role-arn "arn:aws:iam::363401891883:role/service-role/aws-quicksight-service-role-v0" \
  --security-group-ids sg-0c16ac81229df3c14 \
  --subnet-ids subnet-0a02860b167c1d5d3 subnet-05eb90e0b2e352432 \
  --region us-east-1
```

### Step 2: Create Data Source

```bash
aws quicksight create-data-source \
  --aws-account-id 363401891883 \
  --data-source-id carepath-rds-datasource \
  --name "CarePath PostgreSQL" \
  --type POSTGRESQL \
  --data-source-parameters '{
    "PostgreSqlParameters": {
      "Host": "carepath-ai-db-prod.cu5o4e24iwmf.us-east-1.rds.amazonaws.com",
      "Port": 5432,
      "Database": "carepath_db"
    }
  }' \
  --credentials '{
    "CredentialPair": {
      "Username": "dbadmin",
      "Password": "E2}=9]P662Qzxx{K)HWv[[K$#hay5$58"
    }
  }' \
  --vpc-connection-properties '{
    "VpcConnectionArn": "arn:aws:quicksight:us-east-1:363401891883:vpcConnection/carepath-rds-vpc"
  }' \
  --ssl-properties '{
    "DisableSsl": false
  }' \
  --region us-east-1
```

---

## 📊 Suggested Dashboards to Create

### 1. **Patient Analytics Dashboard**
- Total patients by risk level
- Age distribution
- Geographic heatmap
- Chronic conditions breakdown

### 2. **Care Manager Performance**
- Patient caseload per care manager
- Appointment completion rates
- Average response time
- Task completion metrics

### 3. **Post-Discharge Monitoring**
- 30-day readmission rates
- Task completion timeline
- Follow-up appointment adherence
- High-risk patient tracking

### 4. **Financial Analytics**
- Cost per patient
- Insurance coverage breakdown
- Revenue by service type
- Cost-saving opportunities

### 5. **Predictive Analytics**
- Readmission risk trends
- Resource utilization forecasting
- Patient outcome predictions
- ED visit probability

---

## 🔍 Sample SQL Queries

### Patient Risk Distribution
```sql
SELECT 
  risk_level,
  COUNT(*) as patient_count,
  ROUND(AVG(risk_score), 2) as avg_risk_score
FROM patients
GROUP BY risk_level
ORDER BY patient_count DESC;
```

### Readmission Rate by Diagnosis
```sql
SELECT 
  p.primary_diagnosis,
  COUNT(DISTINCT p.id) as total_patients,
  SUM(CASE WHEN rp.readmission_risk > 0.7 THEN 1 ELSE 0 END) as high_risk_count,
  ROUND(AVG(rp.readmission_risk) * 100, 2) as avg_readmission_risk_pct
FROM patients p
LEFT JOIN risk_predictions rp ON p.id = rp.patient_id
GROUP BY p.primary_diagnosis
HAVING COUNT(DISTINCT p.id) > 5
ORDER BY avg_readmission_risk_pct DESC;
```

### Care Manager Workload
```sql
SELECT 
  cm.name as care_manager,
  COUNT(DISTINCT p.id) as total_patients,
  COUNT(a.id) as total_appointments,
  SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) as completed_appointments,
  ROUND(SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END)::numeric / 
    NULLIF(COUNT(a.id), 0) * 100, 2) as completion_rate_pct
FROM care_managers cm
LEFT JOIN patients p ON cm.id = p.care_manager_id
LEFT JOIN appointments a ON p.id = a.patient_id
GROUP BY cm.id, cm.name
ORDER BY total_patients DESC;
```

---

## 🛠️ Troubleshooting

### Connection Test Failed

1. **Check Security Group**:
   ```bash
   aws ec2 describe-security-groups \
     --group-ids sg-0c16ac81229df3c14 \
     --region us-east-1
   ```

2. **Verify RDS is accessible**:
   ```bash
   aws rds describe-db-instances \
     --db-instance-identifier carepath-ai-db-prod \
     --region us-east-1
   ```

3. **Test from EC2 instance** (in same VPC):
   ```bash
   psql -h carepath-ai-db-prod.cu5o4e24iwmf.us-east-1.rds.amazonaws.com \
        -U dbadmin -d carepath_db
   ```

### VPC Connection Stuck in "Creating"

- Wait 5-10 minutes (can take time)
- Check subnet availability zones match
- Ensure subnets are in the same VPC
- Verify security group allows outbound traffic

### QuickSight Can't See Tables

- Check username has proper permissions
- Run: `\dt` in psql to list tables
- Verify schema is `public` or specify schema name

---

## 💰 Cost Considerations

### QuickSight Pricing (as of 2024)
- **Standard Edition**: 
  - Author: $24/month per user
  - Reader: $0.30 per session (max $5/month)
  - Includes 10 GB SPICE capacity

- **Free Trial**: 
  - 1 author, 4 readers
  - 30 days free (usually)

- **SPICE Storage**: 
  - First 10 GB free
  - Additional: $0.38/GB/month

### Recommendations
- Use **Direct Query** initially to avoid SPICE costs
- Upgrade to SPICE only for frequently-accessed dashboards
- Start with Standard Edition (Enterprise is $18/user/month more)

---

## 📚 Next Steps

1. ✅ Complete QuickSight setup using Method 1 (Console)
2. Create your first dataset from the `patients` table
3. Build a simple visualization (e.g., patient count by risk level)
4. Share dashboard with your team
5. Explore ML Insights (if using Enterprise Edition)

---

## 🔗 Useful Links

- [QuickSight Console](https://quicksight.aws.amazon.com/)
- [QuickSight Documentation](https://docs.aws.amazon.com/quicksight/)
- [VPC Connection Guide](https://docs.aws.amazon.com/quicksight/latest/user/working-with-aws-vpc.html)
- [PostgreSQL Data Source](https://docs.aws.amazon.com/quicksight/latest/user/create-a-data-source-postgresql.html)

---

## ✅ Security Notes

- ✅ Database password is stored in AWS Secrets Manager
- ✅ QuickSight connects via private VPC (not public internet)
- ✅ Security group restricts access to QuickSight only
- ✅ SSL/TLS encryption enabled
- ⚠️ **Do not share database password in code repositories**
- ⚠️ **Rotate password periodically** (every 90 days recommended)

---

**Need Help?** 
- Check the [troubleshooting section](#-troubleshooting)
- Review AWS QuickSight documentation
- Contact AWS Support if issues persist
