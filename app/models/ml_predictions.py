from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Index
from datetime import datetime
from app.db.base import Base


class MLPrediction(Base):
    """
    ML Predictions model - stores predictions from all ML models.
    Supports multiple model types: readmission, ed_avoidable, etc.
    """
    __tablename__ = "ml_predictions"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, nullable=False, index=True)  # PAT_XXXXXXXX format
    mrn = Column(String, nullable=False, index=True)  # MRNXXXXXXXX format
    
    # Model information
    model_type = Column(String, nullable=False, index=True)  # 'readmission', 'ed_avoidable', etc.
    model_version = Column(String, nullable=True)  # Optional: track model version
    
    # Prediction results
    risk_score = Column(Float, nullable=False)  # Probability score (0.0 to 1.0)
    prediction_result = Column(JSON, nullable=True)  # Optional: store detailed results as JSON
    
    # Metadata
    predicted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String, nullable=True)  # User who triggered prediction (if manual)
    
    # Create composite index for efficient queries
    __table_args__ = (
        Index('idx_patient_model_time', 'patient_id', 'model_type', 'predicted_at'),
        Index('idx_mrn_model_time', 'mrn', 'model_type', 'predicted_at'),
    )
    
    def __repr__(self):
        return f"<MLPrediction(id={self.id}, patient_id='{self.patient_id}', model_type='{self.model_type}', risk_score={self.risk_score})>"
