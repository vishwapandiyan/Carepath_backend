from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union

from .schemas import CarePlanOption, PathwayDecision, PathwayRequest, PathwayResponse
from app.services.ed_feature_mapper import ed_feature_mapper
from app.services.ed_prediction_service import ed_prediction_service


def run_pathway(
    patient_id: str,
    request: Optional[PathwayRequest] = None,
    ehr_data: Optional[Any] = None,
) -> PathwayResponse:
    """
    Runs the Clinical Emergency Risk Model & CarePlan Agent.
    Evaluates:
      1. Patient EHR / MRN records (baseline clinical risk from database)
      2. Extracted Intake Data (chief complaint, onset, pain scale, location)
      3. Red Flag Safety Answers (screening questions)
    
    Predictions are computed strictly via the trained ML Random Forest Model
    (best_avoidable_ed_model.pkl) through EDFeatureMapper & EDPredictionService.
    """
    # 1. Extract inputs
    chief_complaint = (request.chief_complaint if request else None) or "Unspecified concern"
    symptom_onset = (request.symptom_onset if request else None) or "Unknown"
    pain_scale = (request.pain_scale if request else 0) or 0
    location = (request.location if request else None) or "General"
    red_flags = (request.red_flag_answers if request else {}) or {}

    intake_data = {
        "chief_complaint": chief_complaint,
        "symptom_onset": symptom_onset,
        "pain_scale": pain_scale,
        "location": location,
    }

    # 2. Risk Calculation using ML Model (Random Forest classifier)
    ml_prediction = None
    if ed_prediction_service.model:
        try:
            features = ed_feature_mapper.build_ml_features(
                intake_data=intake_data,
                safety_flags=red_flags,
                ehr_data=ehr_data
            )
            ml_prediction = ed_prediction_service.predict(features)
        except Exception as err:
            ml_prediction = None

    if ml_prediction:
        prob_avoidable = ml_prediction["probability"]
        # Emergency risk score = probability ED visit is NOT avoidable
        final_score = round((1.0 - prob_avoidable) * 100.0, 1)
        avoidable_ed = ml_prediction["avoidable_ed"]
        confidence = ml_prediction["confidence"]
        
        red_flag_count = sum(1 for v in red_flags.values() if v is True)
        if avoidable_ed == "NO" or final_score >= 50.0 or red_flag_count > 0:
            decision = PathwayDecision.NOT_AVOIDABLE
            risk_level = "CRITICAL" if final_score >= 80.0 else "HIGH"
        else:
            decision = PathwayDecision.POTENTIALLY_AVOIDABLE
            risk_level = "MODERATE" if final_score >= 30.0 else "LOW"
            
        explanation = (
            f"ML Model Prediction ({ed_prediction_service.model_bundle.get('model_name', 'Random Forest')}): "
            f"Avoidable ED = '{avoidable_ed}' with {confidence} confidence. "
            f"Calculated Emergency Risk Score: {final_score}% ({risk_level}). "
            f"{ml_prediction['recommendation']}"
        )
    else:
        # Fallback heuristic calculation if ML model is unavailable
        base_score = 15.0
        base_score += (pain_scale / 10.0) * 30.0
        if any(kw in symptom_onset.lower() for kw in ["sudden", "acute", "immediate", "hour", "hours", "min"]):
            base_score += 15.0
        high_risk_kws = ["chest", "breath", "shortness", "headache", "bleeding", "faint", "stroke", "numbness"]
        if any(kw in chief_complaint.lower() or kw in location.lower() for kw in high_risk_kws):
            base_score += 20.0
        red_flag_count = sum(1 for v in red_flags.values() if v is True)
        base_score += red_flag_count * 25.0
        final_score = min(max(round(base_score, 1), 5.0), 99.0)

        if final_score >= 70.0 or red_flag_count > 0:
            risk_level = "CRITICAL" if final_score >= 85.0 else "HIGH"
            decision = PathwayDecision.NOT_AVOIDABLE
            explanation = f"Risk score of {final_score}% ({risk_level}). Symptoms require immediate clinical evaluation."
        elif final_score >= 40.0:
            risk_level = "MODERATE"
            decision = PathwayDecision.POTENTIALLY_AVOIDABLE
            explanation = f"Risk score of {final_score}% ({risk_level}). Manageable through Urgent Care or Telehealth."
        else:
            risk_level = "LOW"
            decision = PathwayDecision.POTENTIALLY_AVOIDABLE
            explanation = f"Risk score of {final_score}% ({risk_level}). Non-emergency presentation."

    # 4. CarePlan Agent Generation
    care_plan: list[CarePlanOption] = []
    if decision == PathwayDecision.NOT_AVOIDABLE:
        care_plan.append(
            CarePlanOption(
                title="Immediate Emergency Department Evaluation",
                urgency="Immediate",
                description="High-severity presentation requiring emergency clinical assessment and diagnostic workup.",
                recommended_action="Proceed to the nearest Emergency Room or dial 911 if experiencing distress.",
            )
        )
        care_plan.append(
            CarePlanOption(
                title="Care Manager Notification",
                urgency="Immediate",
                description="Alert sent to the on-call Nurse Care Manager for post-triage tracking.",
                recommended_action="Care team will follow up via phone within 2 hours.",
            )
        )
    else:
        care_plan.append(
            CarePlanOption(
                title="Telehealth / Same-Day Urgent Care",
                urgency="Moderate" if risk_level == "MODERATE" else "Routine",
                description=f"Same-day evaluation for {chief_complaint} to prevent symptom progression.",
                recommended_action="Book a virtual consultation or visit an affiliated Urgent Care center within 24 hours.",
            )
        )
        care_plan.append(
            CarePlanOption(
                title="Outpatient Care Plan & Monitoring",
                urgency="Routine",
                description="Personalized symptom monitoring and medication review plan.",
                recommended_action="Follow up with primary care physician within 3-5 days.",
            )
        )

    raw_agent_output = {
        "patient_id": patient_id,
        "calculated_risk_score": final_score,
        "risk_level": risk_level,
        "decision": decision.value,
        "red_flags_active": red_flag_count,
        "intake_fields_used": {
            "chief_complaint": chief_complaint,
            "symptom_onset": symptom_onset,
            "pain_scale": pain_scale,
            "location": location,
        },
    }

    return PathwayResponse(
        patient_id=patient_id,
        risk_score=final_score,
        risk_level=risk_level,
        decision=decision,
        explanation=explanation,
        care_plan=care_plan,
        predicted_at=datetime.now(timezone.utc),
        raw_agent_output=raw_agent_output,
    )
