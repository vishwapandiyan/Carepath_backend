"""
ML Model loader - singleton pattern
"""
import pickle
import pandas as pd
from pathlib import Path


class ModelLoader:
    """Singleton model loader"""
    _instance = None
    _model = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load_model(self, model_path: str):
        """Load the trained model"""
        if self._model is None:
            print(f"Loading model from {model_path}...")
            import warnings
            warnings.filterwarnings('ignore')
            
            with open(model_path, 'rb') as f:
                self._model = pickle.load(f)
            print("✓ Model loaded successfully")
        return self._model
    
    def get_model(self):
        """Get loaded model"""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self._model
    
    @property
    def model(self):
        """Property to check if model is loaded"""
        return self._model


# Global instance
model_loader = ModelLoader()

# Auto-load the model on startup
try:
    # For Docker: model is at /app/best_model.pkl
    # For local: model is in backend directory  
    model_paths = [
        Path("/app/best_model.pkl"),  # Docker path
        Path(__file__).parent.parent.parent / "best_model.pkl",  # Backend dir for local dev
    ]
    
    model_path = None
    for path in model_paths:
        print(f"Checking for model at: {path}")
        if path.exists():
            model_path = path
            print(f"✓ Found model at: {path}")
            break
        else:
            print(f"✗ Model not found at: {path}")
    
    if model_path:
        model_loader.load_model(str(model_path))
        print("✓ Model auto-loaded on startup")
    else:
        print(f"⚠ Warning: Model file not found in any of: {model_paths}")
except Exception as e:
    print(f"⚠ Warning: Failed to auto-load model: {e}")
    import traceback
    traceback.print_exc()
