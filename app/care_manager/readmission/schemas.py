from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ReadmissionPredictionOut(BaseModel):
    patient_id: str
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Risk probability score (0.0 to 1.0)")
    risk_level: str = Field(..., description="Risk category: low | medium | high")
    predicted_at: datetime

    model_config = ConfigDict(from_attributes=True)
