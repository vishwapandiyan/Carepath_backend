#!/usr/bin/env python3
"""
Convert pickle model to joblib format for better compatibility
"""
import pickle
import joblib

print("Converting model from pickle to joblib format...")

# Load with pickle
with open('best_model_compatible.pkl', 'rb') as f:
    model = pickle.load(f)

# Save with joblib (better version compatibility)
joblib.dump(model, 'best_model.joblib', compress=3)

print("✓ Model converted successfully!")
print("  Input:  best_model_compatible.pkl")
print("  Output: best_model.joblib")
