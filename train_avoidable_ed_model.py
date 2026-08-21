"""
Train Avoidable ED Prediction Model (scikit-learn 1.9.0 / 1.6+ Compatible)

Generates realistic clinical dataset combining:
- Chatbot intake features (8 symptoms)
- Safety red flags (10-12 red flags)
- EHR Database records (vitals, labs, chronic conditions, utilization)

Trains Random Forest Classifier with balanced clinical distributions and saves compatible pickle bundle to:
- app/ml_models/best_avoidable_ed_model.pkl
- ML_Complete_Package/best_avoidable_ed_model.pkl
"""

import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score, f1_score

np.random.seed(42)
N_SAMPLES = 3000

print("Generating realistic clinical dataset with 3,000 patient records...")

symptom_categories = ['abdominal_pain', 'back_pain', 'chest_pain', 'headache', 'shortness_of_breath', 'fever', 'injury', 'other']
onsets = ['sudden', 'gradual', 'chronic']
durations = ['1_hour', '2_hours', '1_day', '3_days', '1_week', '1_month']
locations = ['chest', 'abdomen', 'head', 'back', 'arm', 'leg', 'generalized', 'unknown']
characters = ['sharp', 'dull', 'throbbing', 'pressure', 'burning', 'aching', 'unknown']
trends = ['improving', 'stable', 'worsening', 'fluctuating']
genders = ['male', 'female', 'unknown']

data = {
    'patient_id': [f'PAT-{i:05d}' for i in range(1, N_SAMPLES + 1)],
    'primary_symptom_category': np.random.choice(symptom_categories, N_SAMPLES, p=[0.15, 0.15, 0.10, 0.20, 0.10, 0.10, 0.10, 0.10]),
    'pain_level_self_reported': np.random.choice(range(11), N_SAMPLES, p=[0.05, 0.15, 0.20, 0.15, 0.15, 0.10, 0.08, 0.05, 0.04, 0.02, 0.01]),
    'pain_onset': np.random.choice(onsets, N_SAMPLES, p=[0.25, 0.55, 0.20]),
    'pain_duration': np.random.choice(durations, N_SAMPLES),
    'pain_location': np.random.choice(locations, N_SAMPLES),
    'pain_character': np.random.choice(characters, N_SAMPLES),
    'pain_radiating': np.random.choice([0, 1], N_SAMPLES, p=[0.85, 0.15]),
    'symptom_trend': np.random.choice(trends, N_SAMPLES, p=[0.30, 0.40, 0.20, 0.10]),
    
    # Safety Red Flags (majority 0 in outpatient triage)
    'flag_shortness_of_breath': np.random.choice([0, 1], N_SAMPLES, p=[0.92, 0.08]),
    'flag_chest_pain_sweating_nausea': np.random.choice([0, 1], N_SAMPLES, p=[0.94, 0.06]),
    'flag_loss_of_consciousness': np.random.choice([0, 1], N_SAMPLES, p=[0.98, 0.02]),
    'flag_confusion_altered_mental_state': np.random.choice([0, 1], N_SAMPLES, p=[0.97, 0.03]),
    'flag_uncontrolled_bleeding': np.random.choice([0, 1], N_SAMPLES, p=[0.98, 0.02]),
    'flag_severe_allergic_reaction': np.random.choice([0, 1], N_SAMPLES, p=[0.97, 0.03]),
    'flag_stroke_signs': np.random.choice([0, 1], N_SAMPLES, p=[0.99, 0.01]),
    'flag_vomiting_blood_or_blood_in_stool': np.random.choice([0, 1], N_SAMPLES, p=[0.98, 0.02]),
    'flag_high_fever_stiff_neck_rash': np.random.choice([0, 1], N_SAMPLES, p=[0.95, 0.05]),
    'flag_severe_dehydration': np.random.choice([0, 1], N_SAMPLES, p=[0.94, 0.06]),
    
    # Vitals (realistic outpatient distributions: majority normal)
    'systolic_bp': np.random.choice([
        np.random.randint(110, 136), # 85% normal
        np.random.randint(80, 90),   # 5% hypotensive
        np.random.randint(160, 185)  # 10% severe hypertensive
    ], N_SAMPLES, p=[0.85, 0.05, 0.10]),
    'diastolic_bp': np.random.randint(65, 88, N_SAMPLES),
    'heart_rate': np.random.randint(60, 95, N_SAMPLES),
    'respiratory_rate': np.random.randint(12, 20, N_SAMPLES),
    'temperature': np.round(np.random.uniform(97.5, 99.2, N_SAMPLES), 1),
    'spo2': np.random.choice([
        np.random.randint(95, 101),  # 92% normal
        np.random.randint(88, 94)    # 8% hypoxic
    ], N_SAMPLES, p=[0.92, 0.08]),
    'pain_score_clinical': np.random.randint(0, 11, N_SAMPLES),
    
    # Labs (realistic outpatient distributions: majority normal)
    'wbc': np.round(np.random.uniform(4.5, 10.5, N_SAMPLES), 1),
    'hemoglobin': np.round(np.random.uniform(12.0, 16.0, N_SAMPLES), 1),
    'platelet_count': np.random.randint(150000, 350000, N_SAMPLES),
    'sodium': np.round(np.random.uniform(135.0, 144.0, N_SAMPLES), 1),
    'potassium': np.round(np.random.uniform(3.5, 4.8, N_SAMPLES), 1),
    'creatinine': np.round(np.random.uniform(0.7, 1.1, N_SAMPLES), 2),
    'glucose': np.random.randint(80, 140, N_SAMPLES),
    'troponin': np.random.choice([
        np.round(np.random.uniform(0.001, 0.015), 3), # 93% normal
        np.round(np.random.uniform(0.04, 1.2), 3)     # 7% elevated (cardiac emergency)
    ], N_SAMPLES, p=[0.93, 0.07]),
    'bnp': np.random.randint(20, 95, N_SAMPLES),
    'lactate': np.random.choice([
        np.round(np.random.uniform(0.6, 1.4), 1),    # 92% normal
        np.round(np.random.uniform(2.0, 4.5), 1)     # 8% elevated (sepsis/hypoxia emergency)
    ], N_SAMPLES, p=[0.92, 0.08]),
    'inr': np.round(np.random.uniform(0.9, 1.2), 1),
    
    # Chronic conditions
    'diabetes_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.80, 0.20]),
    'hypertension_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.70, 0.30]),
    'cardiac_history_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.85, 0.15]),
    'copd_asthma_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.88, 0.12]),
    'ckd_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.92, 0.08]),
    'cancer_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.95, 0.05]),
    'immunocompromised_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.96, 0.04]),
    
    # Utilization & Demographics
    'chronic_condition_count': np.random.randint(0, 3, N_SAMPLES),
    'charlson_comorbidity_index': np.random.randint(0, 4, N_SAMPLES),
    'active_medication_count': np.random.randint(0, 6, N_SAMPLES),
    'on_anticoagulants_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.90, 0.10]),
    'on_insulin_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.92, 0.08]),
    'days_since_last_ed_visit': np.random.randint(30, 365, N_SAMPLES),
    'ed_visits_past_year': np.random.choice([0, 1, 2, 3], N_SAMPLES, p=[0.70, 0.20, 0.07, 0.03]),
    'admissions_past_year': np.random.choice([0, 1, 2], N_SAMPLES, p=[0.85, 0.12, 0.03]),
    'has_pcp_flag': np.random.choice([0, 1], N_SAMPLES, p=[0.15, 0.85]),
    'age': np.random.randint(18, 80, N_SAMPLES),
    'gender': np.random.choice(genders, N_SAMPLES),
    'pqe_category': 'standard'
}

df = pd.DataFrame(data)

# Calculate clinical target (1 = Avoidable ED, 0 = ED Needed)
# ED is NEEDED (avoidable = 0) if:
# 1. Any major red flag is active
# 2. Critical vitals (hypotension <90, hypoxia < 94)
# 3. Elevated troponin (>= 0.04) or high lactate (>= 2.0)
# 4. Severe pain (>= 8) with chest/head/cardiac symptoms
red_flag_cols = [c for c in df.columns if c.startswith('flag_')]
df['total_red_flags'] = df[red_flag_cols].sum(axis=1)

is_emergency = (
    (df['total_red_flags'] >= 1) |
    (df['systolic_bp'] < 90) |
    (df['spo2'] < 94) |
    (df['troponin'] >= 0.04) |
    (df['lactate'] >= 2.0) |
    ((df['pain_level_self_reported'] >= 8) & (df['primary_symptom_category'].isin(['chest_pain', 'shortness_of_breath'])))
)

df['avoidable_ed'] = np.where(is_emergency, 0, 1)

print(f"Avoidable ED distribution:\n{df['avoidable_ed'].value_counts(normalize=True)}")

# Save synthetic dataset for reference
Path("ML_Complete_Package/data").mkdir(parents=True, exist_ok=True)
df.to_csv('ML_Complete_Package/data/synthetic_avoidable_ed_data.csv', index=False)

# Feature Engineering (matches EDFeatureMapper)
df['shock_index'] = df['heart_rate'] / df['systolic_bp']
df['pulse_pressure'] = df['systolic_bp'] - df['diastolic_bp']
df['mean_arterial_pressure'] = df['diastolic_bp'] + (df['pulse_pressure'] / 3)
df['is_hypotensive'] = (df['systolic_bp'] < 90).astype(int)
df['is_hypertensive_severe'] = (df['systolic_bp'] > 160).astype(int)
df['is_tachycardic'] = (df['heart_rate'] > 100).astype(int)
df['is_bradycardic'] = (df['heart_rate'] < 60).astype(int)
df['is_tachypneic'] = (df['respiratory_rate'] > 20).astype(int)
df['is_hypoxic'] = (df['spo2'] < 94).astype(int)
df['is_febrile'] = (df['temperature'] >= 38.0).astype(int)

vital_flags = ['is_tachycardic', 'is_bradycardic', 'is_tachypneic', 'is_hypoxic', 'is_febrile', 'is_hypotensive', 'is_hypertensive_severe']
df['vital_abnormality_count'] = df[vital_flags].sum(axis=1)

df['troponin_elevated'] = (df['troponin'] >= 0.04).astype(int)
df['lactate_elevated'] = (df['lactate'] >= 2.0).astype(int)
df['renal_impairment'] = (df['creatinine'] >= 1.3).astype(int)
df['wbc_abnormal'] = ((df['wbc'] < 4.0) | (df['wbc'] > 11.0)).astype(int)
df['bnp_elevated'] = (df['bnp'] >= 100).astype(int)
df['inr_elevated'] = (df['inr'] >= 1.5).astype(int)

lab_flags = ['troponin_elevated', 'lactate_elevated', 'renal_impairment', 'wbc_abnormal', 'bnp_elevated', 'inr_elevated']
df['lab_abnormality_count'] = df[lab_flags].sum(axis=1)

df['red_flags_present'] = (df['total_red_flags'] > 0).astype(int)
df['pain_x_red_flags'] = df['pain_level_self_reported'] * df['total_red_flags']
df['high_pain_flag'] = (df['pain_level_self_reported'] >= 7).astype(int)
df['pain_report_mismatch'] = (df['pain_level_self_reported'] - df['pain_score_clinical']).abs()
df['radiating_and_cardiac_symptoms'] = df['pain_radiating'] * df['flag_chest_pain_sweating_nausea']

comorbids = ['diabetes_flag', 'hypertension_flag', 'cardiac_history_flag', 'copd_asthma_flag', 'ckd_flag', 'cancer_flag', 'immunocompromised_flag']
df['is_multimorbid'] = (df[comorbids].sum(axis=1) >= 2).astype(int)
df['medication_burden_ratio'] = df['active_medication_count'] / (df['chronic_condition_count'] + 1)
df['anticoag_bleeding_risk'] = df['on_anticoagulants_flag'] * df['flag_uncontrolled_bleeding']

df['is_high_utilizer'] = (df['ed_visits_past_year'] >= 3).astype(int)
df['is_recent_followup'] = (df['days_since_last_ed_visit'] <= 7).astype(int)
df['visits_x_recent'] = df['ed_visits_past_year'] * df['is_recent_followup']

df['is_elderly'] = (df['age'] >= 65).astype(int)
df['age_group'] = pd.cut(df['age'], bins=[-1, 18, 40, 65, 120], labels=[0, 1, 2, 3]).astype(int)

# Categorical Encoders
X_full = df.drop(columns=['patient_id', 'pqe_category', 'avoidable_ed'])
y = df['avoidable_ed']

categorical_cols = X_full.select_dtypes(include=['object']).columns.tolist()
encoders = {}
for col in categorical_cols:
    le = LabelEncoder()
    X_full[col] = le.fit_transform(X_full[col].astype(str))
    encoders[col] = le

X_train, X_test, y_train, y_test = train_test_split(X_full, y, test_size=0.2, random_state=42, stratify=y)

print(f"\nTraining Random Forest model on {len(X_train)} samples with {X_train.shape[1]} features...")
rf = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_split=4,
    min_samples_leaf=2,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1
)

rf.fit(X_train, y_train)

y_pred = rf.predict(X_test)
y_prob = rf.predict_proba(X_test)[:, 1]

acc = accuracy_score(y_test, y_pred)
rec = recall_score(y_test, y_pred)
auc = roc_auc_score(y_test, y_prob)
f1 = f1_score(y_test, y_pred)

print(f"\nModel Evaluation:")
print(f"   Accuracy : {acc:.4f}")
print(f"   Recall   : {rec:.4f}")
print(f"   F1-Score : {f1:.4f}")
print(f"   ROC-AUC  : {auc:.4f}")

# Package into bundle
model_bundle = {
    'model': rf,
    'model_name': 'Random Forest Classifier',
    'needs_scaling': False,
    'scaler': None,
    'feature_columns': list(X_full.columns),
    'categorical_encoders': encoders,
    'target_column': 'avoidable_ed',
    'test_metrics': {
        'accuracy': acc,
        'recall': rec,
        'f1': f1,
        'roc_auc': auc
    }
}

paths = [
    Path("app/ml_models/best_avoidable_ed_model.pkl"),
    Path("ML_Complete_Package/best_avoidable_ed_model.pkl")
]

for p in paths:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        pickle.dump(model_bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[SUCCESS] Saved trained model bundle to {p}")

print("\nModel retraining completed successfully!")
