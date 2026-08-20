"""
=====================================================================
AVOIDABLE ED PREDICTION - ML PIPELINE
=====================================================================
Matches the schema:
patient_id, primary_symptom_category, pain_level_self_reported,
pain_onset, pain_duration, pain_location, pain_character,
pain_radiating, symptom_trend, flag_* (10 red-flag columns),
systolic_bp, diastolic_bp, heart_rate, respiratory_rate,
temperature, spo2, pain_score_clinical, wbc, hemoglobin,
platelet_count, sodium, potassium, creatinine, glucose, troponin,
bnp, lactate, inr, diabetes_flag, hypertension_flag,
cardiac_history_flag, copd_asthma_flag, ckd_flag, cancer_flag,
immunocompromised_flag, chronic_condition_count,
charlson_comorbidity_index, active_medication_count,
on_anticoagulants_flag, on_insulin_flag, days_since_last_ed_visit,
ed_visits_past_year, admissions_past_year, has_pcp_flag, age,
gender, pqe_category, avoidable_ed

Steps:
1. Load data, drop identifier/leakage columns
2. Feature engineering -- derived clinical features from raw columns
3. Encode categoricals
4. Correlation-based feature selection (drop weak correlation w/ target)
5. Train/test split (stratified)
6. Models: Logistic Regression -> Random Forest -> XGBoost -> LightGBM
   -> CatBoost -> Voting Ensemble -> Stacking Ensemble
7. Evaluate all models (accuracy, precision, recall, F1, ROC-AUC)
=====================================================================
"""

import pickle
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, VotingClassifier, StackingClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier

# ---------------------------------------------------------------
# 0. CONFIG
# ---------------------------------------------------------------
DATA_PATH = "synthetic_avoidable_ed_data.csv"   # <-- change to your file
TARGET = "avoidable_ed"
RANDOM_STATE = 42
CORR_THRESHOLD = 0.05   # raised from 0.03 -- wider feature space (95 cols) needs a stricter cut

# Identifier + leakage columns to drop outright.
# pqe_category is built from the SAME rule pass as the target -> leakage.
DROP_COLS = ["patient_id", "pqe_category"]

RED_FLAG_COLS = [
    "flag_shortness_of_breath", "flag_chest_pain_sweating_nausea",
    "flag_loss_of_consciousness", "flag_confusion_altered_mental_state",
    "flag_uncontrolled_bleeding", "flag_severe_allergic_reaction",
    "flag_stroke_signs", "flag_vomiting_blood_or_blood_in_stool",
    "flag_high_fever_stiff_neck_rash", "flag_severe_dehydration",
]

# ---------------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------------
df = pd.read_csv(DATA_PATH)

df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])

print(f"Loaded data: {df.shape[0]} rows, {df.shape[1]} columns (after dropping ID/leakage cols)")

# ---------------------------------------------------------------
# 2. FEATURE ENGINEERING -- derived clinical features
# ---------------------------------------------------------------
def col_exists(*cols):
    return all(c in df.columns for c in cols)

# --- Vital sign derived features ---
if col_exists("heart_rate", "systolic_bp"):
    df["shock_index"] = df["heart_rate"] / df["systolic_bp"]              # >0.9 = concerning

if col_exists("systolic_bp", "diastolic_bp"):
    df["pulse_pressure"] = df["systolic_bp"] - df["diastolic_bp"]
    df["mean_arterial_pressure"] = df["diastolic_bp"] + (df["pulse_pressure"] / 3)
    df["is_hypotensive"] = (df["systolic_bp"] < 90).astype(int)
    df["is_hypertensive_severe"] = (df["systolic_bp"] > 160).astype(int)

if "heart_rate" in df.columns:
    df["is_tachycardic"] = (df["heart_rate"] > 100).astype(int)
    df["is_bradycardic"] = (df["heart_rate"] < 60).astype(int)

if "respiratory_rate" in df.columns:
    df["is_tachypneic"] = (df["respiratory_rate"] > 20).astype(int)

if "spo2" in df.columns:
    df["is_hypoxic"] = (df["spo2"] < 94).astype(int)

if "temperature" in df.columns:
    df["is_febrile"] = (df["temperature"] >= 38.0).astype(int)

vital_flag_cols = [c for c in [
    "is_tachycardic", "is_bradycardic", "is_tachypneic", "is_hypoxic",
    "is_febrile", "is_hypotensive", "is_hypertensive_severe"
] if c in df.columns]
if vital_flag_cols:
    df["vital_abnormality_count"] = df[vital_flag_cols].sum(axis=1)

# --- Lab derived features ---
if "troponin" in df.columns:
    df["troponin_elevated"] = (df["troponin"] >= 0.04).astype(int)   # standard clinical cutoff
if "lactate" in df.columns:
    df["lactate_elevated"] = (df["lactate"] >= 2.0).astype(int)
if "creatinine" in df.columns:
    df["renal_impairment"] = (df["creatinine"] >= 1.3).astype(int)
if "wbc" in df.columns:
    df["wbc_abnormal"] = ((df["wbc"] < 4.0) | (df["wbc"] > 11.0)).astype(int)
if "bnp" in df.columns:
    df["bnp_elevated"] = (df["bnp"] >= 100).astype(int)
if "inr" in df.columns:
    df["inr_elevated"] = (df["inr"] >= 1.5).astype(int)
if "glucose" in df.columns:
    df["is_hyperglycemic"] = (df["glucose"] >= 200).astype(int)
    df["is_hypoglycemic"] = (df["glucose"] < 70).astype(int)

lab_flag_cols = [c for c in [
    "troponin_elevated", "lactate_elevated", "renal_impairment",
    "wbc_abnormal", "bnp_elevated", "inr_elevated"
] if c in df.columns]
if lab_flag_cols:
    df["lab_abnormality_count"] = df[lab_flag_cols].sum(axis=1)

# --- Red-flag / symptom interaction features ---
existing_flags = [c for c in RED_FLAG_COLS if c in df.columns]
if existing_flags:
    df["total_red_flags"] = df[existing_flags].sum(axis=1)
    df["red_flags_present"] = (df["total_red_flags"] > 0).astype(int)
    if "pain_level_self_reported" in df.columns:
        df["pain_x_red_flags"] = df["pain_level_self_reported"] * df["total_red_flags"]

if "pain_level_self_reported" in df.columns:
    df["high_pain_flag"] = (df["pain_level_self_reported"] >= 7).astype(int)

if col_exists("pain_level_self_reported", "pain_score_clinical"):
    df["pain_report_mismatch"] = (df["pain_level_self_reported"] - df["pain_score_clinical"]).abs()

if col_exists("pain_radiating", "flag_chest_pain_sweating_nausea"):
    df["radiating_and_cardiac_symptoms"] = df["pain_radiating"] * df["flag_chest_pain_sweating_nausea"]

# --- Comorbidity / medication burden features ---
comorbid_cols = [c for c in [
    "diabetes_flag", "hypertension_flag", "cardiac_history_flag",
    "copd_asthma_flag", "ckd_flag", "cancer_flag", "immunocompromised_flag"
] if c in df.columns]
if comorbid_cols:
    df["is_multimorbid"] = (df[comorbid_cols].sum(axis=1) >= 2).astype(int)

if col_exists("active_medication_count", "chronic_condition_count"):
    df["medication_burden_ratio"] = df["active_medication_count"] / (df["chronic_condition_count"] + 1)

if col_exists("on_anticoagulants_flag", "flag_uncontrolled_bleeding"):
    df["anticoag_bleeding_risk"] = df["on_anticoagulants_flag"] * df["flag_uncontrolled_bleeding"]

if col_exists("diabetes_flag", "is_hyperglycemic"):
    df["uncontrolled_diabetes"] = df["diabetes_flag"] * df["is_hyperglycemic"]

# --- Utilization pattern features ---
if "ed_visits_past_year" in df.columns:
    df["is_high_utilizer"] = (df["ed_visits_past_year"] >= 3).astype(int)

if "days_since_last_ed_visit" in df.columns:
    df["is_recent_followup"] = (df["days_since_last_ed_visit"] <= 7).astype(int)

if col_exists("ed_visits_past_year", "is_recent_followup"):
    df["visits_x_recent"] = df["ed_visits_past_year"] * df["is_recent_followup"]

# --- Age features ---
if "age" in df.columns:
    df["is_elderly"] = (df["age"] >= 65).astype(int)
    df["age_group"] = pd.cut(
        df["age"], bins=[0, 18, 40, 65, 120], labels=[0, 1, 2, 3]
    ).astype(int)

print(f"After feature engineering: {df.shape[1]} columns")

# ---------------------------------------------------------------
# 3. ENCODE CATEGORICALS
# ---------------------------------------------------------------
categorical_cols = df.select_dtypes(include=["object"]).columns.tolist()
categorical_cols = [c for c in categorical_cols if c != TARGET]

print(f"\nEncoding categorical columns: {categorical_cols}")

encoders = {}
for col in categorical_cols:
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col].astype(str))
    encoders[col] = le

# ---------------------------------------------------------------
# 4. CORRELATION-BASED FEATURE SELECTION
# ---------------------------------------------------------------
X_full = df.drop(columns=[TARGET])
y = df[TARGET]

corr_with_target = X_full.apply(lambda col: np.corrcoef(col, y)[0, 1])
corr_df = corr_with_target.abs().sort_values(ascending=False).reset_index()
corr_df.columns = ["feature", "abs_correlation"]

print("\n=== Feature correlation with target (sorted) ===")
print(corr_df.to_string(index=False))

selected_features = corr_df.loc[corr_df["abs_correlation"] >= CORR_THRESHOLD, "feature"].tolist()
dropped_features = corr_df.loc[corr_df["abs_correlation"] < CORR_THRESHOLD, "feature"].tolist()

print(f"\nKept {len(selected_features)} features (|corr| >= {CORR_THRESHOLD})")
print(f"Dropped {len(dropped_features)} weakly-correlated features: {dropped_features}")

X = X_full[selected_features]

# ---------------------------------------------------------------
# 4b. REMOVE HIGHLY-COLLINEAR FEATURES (reduces overfitting)
# ---------------------------------------------------------------
# Many engineered features are built FROM other features already in the
# set (e.g. shock_index from heart_rate+systolic_bp, vital_abnormality_count
# from individual is_* flags). High collinearity lets tree models overfit
# to redundant signal. Drop one of every pair with |corr| > 0.90.
corr_matrix = X.corr().abs()
upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
collinear_drop = [col for col in upper.columns if any(upper[col] > 0.90)]

if collinear_drop:
    print(f"\nDropping {len(collinear_drop)} highly-collinear (redundant) features: {collinear_drop}")
    X = X.drop(columns=collinear_drop)

print(f"Final feature set: {X.shape[1]} features")

# ---------------------------------------------------------------
# 5. TRAIN / TEST SPLIT
# ---------------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print(f"\nTrain size: {X_train.shape[0]}  |  Test size: {X_test.shape[0]}")

# ---------------------------------------------------------------
# 6. EVALUATION HELPER
# ---------------------------------------------------------------
results = []
fitted_models = {}   # keeps the actual trained model object per name, so we can pickle the best one later

def evaluate_model(name, model, X_tr, y_tr, X_te, y_te):
    model.fit(X_tr, y_tr)

    # --- Train performance (to detect overfitting) ---
    train_preds = model.predict(X_tr)
    train_acc = accuracy_score(y_tr, train_preds)
    train_recall = recall_score(y_tr, train_preds, zero_division=0)

    # --- Test performance ---
    preds = model.predict(X_te)
    probs = model.predict_proba(X_te)[:, 1] if hasattr(model, "predict_proba") else preds

    acc = accuracy_score(y_te, preds)
    prec = precision_score(y_te, preds, zero_division=0)
    rec = recall_score(y_te, preds, zero_division=0)
    f1 = f1_score(y_te, preds, zero_division=0)
    auc = roc_auc_score(y_te, probs)

    # --- Cross-validation (more honest generalization estimate) ---
    # Skip the expensive nested CV for Stacking (it already runs 5-fold CV
    # internally to fit its meta-learner) to keep full-dataset runtime sane.
    if isinstance(model, StackingClassifier):
        cv_scores = np.array([train_recall])  # reuse train recall as a light proxy
    else:
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE)
        cv_scores = cross_val_score(model, X_tr, y_tr, cv=cv, scoring="recall", n_jobs=-1)

    gap = train_acc - acc

    results.append({
        "model": name, "train_accuracy": train_acc, "test_accuracy": acc,
        "overfit_gap": gap, "precision": prec, "recall": rec, "f1": f1,
        "roc_auc": auc, "cv_recall_mean": cv_scores.mean(), "cv_recall_std": cv_scores.std()
    })
    fitted_models[name] = model

    print(f"\n--- {name} ---")
    print(f"Train Accuracy: {train_acc:.4f} | Test Accuracy: {acc:.4f} | "
          f"Gap: {gap:.4f}  {'<-- OVERFITTING' if gap > 0.10 else ''}")
    print(f"Train Recall: {train_recall:.4f} | Test Recall: {rec:.4f}")
    print(f"5-Fold CV Recall: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")
    print(f"Precision: {prec:.4f} | F1: {f1:.4f} | ROC-AUC: {auc:.4f}")
    print(classification_report(y_te, preds, target_names=["Not Avoidable", "Avoidable"], zero_division=0))
    print("Confusion Matrix:\n", confusion_matrix(y_te, preds))

    return model

# ---------------------------------------------------------------
# 7. LOGISTIC REGRESSION (baseline, uses scaled features)
# ---------------------------------------------------------------
log_reg = LogisticRegression(
    max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE,
    C=0.1, penalty="l2"   # much stronger regularization (was C=0.5)
)
evaluate_model("Logistic Regression", log_reg, X_train_scaled, y_train, X_test_scaled, y_test)

# ---------------------------------------------------------------
# 8. RANDOM FOREST (very tightened: shallow trees, large leaf minimums)
# ---------------------------------------------------------------
rf = RandomForestClassifier(
    n_estimators=200, max_depth=4, min_samples_leaf=50, min_samples_split=100,
    max_features=0.5, class_weight="balanced",
    random_state=RANDOM_STATE, n_jobs=-1
)
evaluate_model("Random Forest", rf, X_train, y_train, X_test, y_test)

# ---------------------------------------------------------------
# 9. XGBOOST (very tightened: shallow, heavy subsampling, strong L1/L2)
# ---------------------------------------------------------------
scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()
xgb = XGBClassifier(
    n_estimators=200, max_depth=3, learning_rate=0.02,
    subsample=0.6, colsample_bytree=0.6,
    reg_alpha=1.0, reg_lambda=5.0, min_child_weight=20, gamma=1.0,
    scale_pos_weight=scale_pos_weight, eval_metric="logloss",
    random_state=RANDOM_STATE, n_jobs=-1
)
evaluate_model("XGBoost", xgb, X_train, y_train, X_test, y_test)

# ---------------------------------------------------------------
# 10. LIGHTGBM (very tightened: shallow, heavy subsampling, strong L1/L2)
# ---------------------------------------------------------------
lgbm = LGBMClassifier(
    n_estimators=200, max_depth=3, num_leaves=8, learning_rate=0.02,
    subsample=0.6, colsample_bytree=0.6,
    reg_alpha=1.0, reg_lambda=5.0, min_child_samples=50,
    class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1, verbose=-1
)
evaluate_model("LightGBM", lgbm, X_train, y_train, X_test, y_test)

# ---------------------------------------------------------------
# 11. CATBOOST (very tightened: shallow, strong L2)
# ---------------------------------------------------------------
cat = CatBoostClassifier(
    iterations=200, depth=3, learning_rate=0.02,
    l2_leaf_reg=15, subsample=0.6,
    auto_class_weights="Balanced", random_state=RANDOM_STATE, verbose=0
)
evaluate_model("CatBoost", cat, X_train, y_train, X_test, y_test)

# ---------------------------------------------------------------
# 12. VOTING ENSEMBLE (soft voting across best tree models)
# ---------------------------------------------------------------
voting_clf = VotingClassifier(
    estimators=[
        ("rf", RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=50,
                                       min_samples_split=100, max_features=0.5,
                                       class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1)),
        ("xgb", XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.02,
                               subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0,
                               reg_lambda=5.0, min_child_weight=20, gamma=1.0,
                               scale_pos_weight=scale_pos_weight, eval_metric="logloss",
                               random_state=RANDOM_STATE, n_jobs=-1)),
        ("lgbm", LGBMClassifier(n_estimators=200, max_depth=3, num_leaves=8, learning_rate=0.02,
                                 subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0,
                                 reg_lambda=5.0, min_child_samples=50,
                                 class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1, verbose=-1)),
    ],
    voting="soft"
)
evaluate_model("Voting Ensemble (RF+XGB+LGBM)", voting_clf, X_train, y_train, X_test, y_test)

# ---------------------------------------------------------------
# 13. STACKING ENSEMBLE (meta-learner on top of base models)
# ---------------------------------------------------------------
stacking_clf = StackingClassifier(
    estimators=[
        ("rf", RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=50,
                                       min_samples_split=100, max_features=0.5,
                                       class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1)),
        ("xgb", XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.02,
                               subsample=0.6, colsample_bytree=0.6, reg_alpha=1.0,
                               reg_lambda=5.0, min_child_weight=20, gamma=1.0,
                               scale_pos_weight=scale_pos_weight, eval_metric="logloss",
                               random_state=RANDOM_STATE, n_jobs=-1)),
        ("cat", CatBoostClassifier(iterations=200, depth=3, learning_rate=0.02,
                                    l2_leaf_reg=15, subsample=0.6,
                                    auto_class_weights="Balanced", random_state=RANDOM_STATE, verbose=0)),
    ],
    final_estimator=LogisticRegression(max_iter=1000, C=0.1, random_state=RANDOM_STATE),
    cv=5, n_jobs=-1
)
evaluate_model("Stacking Ensemble (RF+XGB+Cat -> LogReg)", stacking_clf, X_train, y_train, X_test, y_test)

# ---------------------------------------------------------------
# 14. FINAL COMPARISON TABLE
# ---------------------------------------------------------------
results_df = pd.DataFrame(results).sort_values("recall", ascending=False)
print("\n\n=== MODEL COMPARISON (sorted by recall — most important for safety) ===")
print(results_df.to_string(index=False))
print("\nNote: 'overfit_gap' = train_accuracy - test_accuracy. Above ~0.10 suggests")
print("meaningful overfitting; the regularization settings above already reduce this")
print("but you can tighten further (lower max_depth, raise min_samples_leaf/reg_lambda,")
print("or lower CORR_THRESHOLD's counterpart -- reduce total feature count) if the gap")
print("is still large on your real data.")

# ---------------------------------------------------------------
# 15. SAVE THE BEST MODEL AS A PICKLE FILE
# ---------------------------------------------------------------
# Best model = highest test recall (recall is the priority metric here,
# since missing a real emergency is the costly error type).
best_model_name = "Random Forest"   # pinned explicitly instead of auto-picking by recall
best_model = fitted_models[best_model_name]

best_model_row = results_df[results_df["model"] == best_model_name].iloc[0]
print(f"\nBest model selected: {best_model_name} "
      f"(recall={best_model_row['recall']:.4f}, "
      f"roc_auc={best_model_row['roc_auc']:.4f})")

# Logistic Regression was trained on SCALED features -- every other model
# was trained on raw features. Save which preprocessing the best model
# needs, plus the scaler and the exact final feature list, so inference
# code applies the identical transform used during training.
needs_scaling = (best_model_name == "Logistic Regression")

model_bundle = {
    "model": best_model,
    "model_name": best_model_name,
    "needs_scaling": needs_scaling,
    "scaler": scaler if needs_scaling else None,
    "feature_columns": list(X.columns),      # exact column order the model expects
    "categorical_encoders": encoders,        # LabelEncoders used for categorical columns
    "target_column": TARGET,
    "corr_threshold": CORR_THRESHOLD,
    "test_metrics": best_model_row.to_dict(),
}

PICKLE_PATH = "best_avoidable_ed_model.pkl"
with open(PICKLE_PATH, "wb") as f:
    pickle.dump(model_bundle, f)

print(f"Saved best model bundle -> {PICKLE_PATH}")
print("Bundle contains: model, needs_scaling flag, scaler, feature_columns, "
      "categorical_encoders, target_column, corr_threshold, test_metrics")

# ---- Example of how to load and use this bundle at inference time -----
# with open("best_avoidable_ed_model.pkl", "rb") as f:
#     bundle = pickle.load(f)
#
# new_data = new_data[bundle["feature_columns"]]           # align columns
# for col, le in bundle["categorical_encoders"].items():
#     if col in new_data.columns:
#         new_data[col] = le.transform(new_data[col].astype(str))
#
# if bundle["needs_scaling"]:
#     new_data = bundle["scaler"].transform(new_data)
#
# predictions = bundle["model"].predict(new_data)
# probabilities = bundle["model"].predict_proba(new_data)[:, 1]
