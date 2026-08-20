#!/usr/bin/env python3
"""
Retrain the ML model with sklearn 1.5.2 for Docker compatibility
"""
import pickle
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import warnings
warnings.filterwarnings('ignore')

print("=" * 70)
print("🔄 RETRAINING MODEL FOR DOCKER COMPATIBILITY")
print("=" * 70)

# Load existing model to get feature names
print("\n📂 Loading existing model to extract configuration...")
with open('best_model.pkl', 'rb') as f:
    old_model = pickle.load(f)

# Load training data
print("📊 Loading training data...")
df = pd.read_csv('patient_data_final.csv')
print(f"   Loaded {len(df)} patient records")

# Identify target and features
target = 'readmitted_30_days'
features = [col for col in df.columns if col not in [target, 'patient_id']]

print(f"\n🎯 Target: {target}")
print(f"📋 Features: {len(features)} columns")

# Split data
X = df[features]
y = df[target]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"\n✂️  Split:")
print(f"   Training: {len(X_train)} samples")
print(f"   Testing: {len(X_test)} samples")

# Identify numeric and categorical columns
numeric_features = X.select_dtypes(include=['int64', 'float64']).columns.tolist()
categorical_features = X.select_dtypes(include=['object']).columns.tolist()

print(f"\n🔢 Numeric features: {len(numeric_features)}")
print(f"🏷️  Categorical features: {len(categorical_features)}")

# Create preprocessing pipeline
numeric_transformer = StandardScaler()
categorical_transformer = OneHotEncoder(handle_unknown='ignore', sparse_output=False)

preprocessor = ColumnTransformer(
    transformers=[
        ('num', numeric_transformer, numeric_features),
        ('cat', categorical_transformer, categorical_features)
    ]
)

# Create full pipeline with RandomForest
print("\n🌲 Training Random Forest model...")
model = Pipeline([
    ('preprocessor', preprocessor),
    ('classifier', RandomForestClassifier(
        n_estimators=100,
        max_depth=15,
        min_samples_split=10,
        min_samples_leaf=4,
        random_state=42,
        n_jobs=-1
    ))
])

# Train model
model.fit(X_train, y_train)

# Evaluate
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

print(f"\n📈 Model Performance:")
print(f"   Training Accuracy: {train_score:.4f}")
print(f"   Testing Accuracy: {test_score:.4f}")

# Save model
output_path = 'best_model_compatible.pkl'
print(f"\n💾 Saving model to {output_path}...")
with open(output_path, 'wb') as f:
    pickle.dump(model, f)

# Verify it can be loaded
print("✅ Verifying model can be loaded...")
with open(output_path, 'rb') as f:
    loaded_model = pickle.load(f)
    
# Test prediction
print("🧪 Testing prediction on first sample...")
sample = X_test.iloc[:1]
prediction = loaded_model.predict(sample)
probability = loaded_model.predict_proba(sample)

print(f"   Prediction: {prediction[0]}")
print(f"   Probability: {probability[0]}")

print("\n" + "=" * 70)
print("✅ MODEL RETRAINED SUCCESSFULLY!")
print("=" * 70)
print(f"\n📁 New model saved: {output_path}")
print("🔧 Next step: Replace best_model.pkl with best_model_compatible.pkl")
print("")
