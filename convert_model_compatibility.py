#!/usr/bin/env python3
"""
Model Compatibility Converter

This script attempts to load the old pickle file and re-save it
with the current scikit-learn version to fix compatibility issues.
"""

import pickle
import sys
from pathlib import Path

def convert_model(input_path, output_path):
    """Load model with compatibility fixes and re-save"""
    
    print(f"Loading model from: {input_path}")
    
    try:
        # Try loading with different protocols
        with open(input_path, "rb") as f:
            # Load the entire bundle
            model_bundle = pickle.load(f)
        
        print("✓ Model loaded successfully!")
        print(f"  Model type: {model_bundle.get('model_name', 'Unknown')}")
        print(f"  Features: {len(model_bundle.get('feature_columns', []))}")
        
        # The model object itself
        model = model_bundle['model']
        print(f"  Sklearn model: {type(model).__name__}")
        
        # Re-save with current Python/sklearn version
        print(f"\nRe-saving to: {output_path}")
        with open(output_path, "wb") as f:
            pickle.dump(model_bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        print("✓ Model converted and saved successfully!")
        
        # Test loading the new file
        print("\nTesting new model file...")
        with open(output_path, "rb") as f:
            test_bundle = pickle.load(f)
        
        print("✓ New model loads correctly!")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    input_file = Path("ML_Complete_Package/best_avoidable_ed_model.pkl")
    output_file = Path("app/ml_models/best_avoidable_ed_model.pkl")
    
    if not input_file.exists():
        print(f"✗ Input file not found: {input_file}")
        sys.exit(1)
    
    # Create output directory if needed
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    success = convert_model(input_file, output_file)
    sys.exit(0 if success else 1)
