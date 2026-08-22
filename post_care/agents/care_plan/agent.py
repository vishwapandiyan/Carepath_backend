"""
Care Plan Agent

Orchestrates the care plan generation workflow based on readmission risk prediction.

Workflow:
1. Validate readmission input (MRN, prediction, probability, notes)
2. Retrieve patient context using MRN from readmission dataset
3. Classify risk level based on probability thresholds
4. Check for existing active care plan (agent-generated, separate from EHR notes)
5. Get predefined care pathway based on risk level
6. Determine if existing discharge instructions need augmentation
7. Create or reuse care plan
8. Create pathway tasks
9. Preserve existing EHR notes if provided
10. Return structured CarePlanOutput

Important:
- MRN is now the application-level patient identifier for lookups
- patient_id from the dataset is used for internal tracking only
- Every patient receives post-care (prediction=0 does NOT skip care plan creation)
- Risk level determines intensity of post-care
- EHR notes are separate from agent-generated care plans
- Empty notes means "no existing instructions were provided to our system"
- Notes are PRESERVED in the output, not processed/modified by agent
"""

import logging
from typing import Dict, Any, Optional
from post_care.agents.care_plan.schemas import ReadmissionInput, CareTask, CarePlanOutput
from post_care.agents.care_plan.tools import (
    get_patient_context_tool,
    get_care_pathway,
)
from post_care.llm.doctor_instructions import extract_doctor_instructions, DoctorInstructions
from post_care.llm.task_personalization import map_instructions_to_tasks, personalize_task, get_task_description

# Import PostgreSQL service and repositories
from post_care.services.care_plan_service_postgresql import (
    get_existing_care_plan,
    create_care_plan as create_care_plan_db,
    create_task as create_task_db,
    get_plan_tasks,
)
from post_care.database.repositories import CarePlanTaskRepository

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER: Format DoctorInstructions for output
# ============================================================================

def _format_doctor_instructions(doctor_instructions_obj: DoctorInstructions) -> Optional[str]:
    """
    Format DoctorInstructions object into a readable string for CarePlanOutput.
    
    If all fields are empty/None, returns None.
    
    Args:
        doctor_instructions_obj: DoctorInstructions structured object
    
    Returns:
        Formatted string representation or None if all fields empty
    """
    parts = []
    
    if doctor_instructions_obj.follow_up:
        parts.append(f"Follow-up: {doctor_instructions_obj.follow_up}")
    
    if doctor_instructions_obj.monitoring:
        monitoring_str = "\n  ".join(doctor_instructions_obj.monitoring)
        parts.append(f"Monitoring:\n  {monitoring_str}")
    
    if doctor_instructions_obj.medication:
        medication_str = "\n  ".join(doctor_instructions_obj.medication)
        parts.append(f"Medications:\n  {medication_str}")
    
    if doctor_instructions_obj.escalation:
        escalation_str = "\n  ".join(doctor_instructions_obj.escalation)
        parts.append(f"Escalation/Urgent Care:\n  {escalation_str}")
    
    if doctor_instructions_obj.other_instructions:
        other_str = "\n  ".join(doctor_instructions_obj.other_instructions)
        parts.append(f"Other Instructions:\n  {other_str}")
    
    if not parts:
        return None
    
    return "\n".join(parts)


# ============================================================================
# RISK CLASSIFICATION THRESHOLDS (prototype)
# ============================================================================

RISK_THRESHOLDS = {
    "HIGH": {
        "min_probability": 0.80,
        "intensity": "INTENSIVE"
    },
    "MODERATE": {
        "min_probability": 0.50,
        "intensity": "REGULAR"
    },
    "LOW": {
        "min_probability": 0.0,
        "intensity": "BASIC"
    }
}


# ============================================================================
# HELPER: Classify Risk Level from Probability
# ============================================================================

def classify_risk_level(probability: float) -> tuple[str, str]:
    """
    Classify risk level and intensity from readmission probability.
    
    Uses prototype thresholds:
    - probability >= 0.80 → HIGH → INTENSIVE
    - 0.50 <= probability < 0.80 → MODERATE → REGULAR
    - probability < 0.50 → LOW → BASIC
    
    Args:
        probability: Readmission probability between 0 and 1
    
    Returns:
        Tuple of (risk_level, intensity) where:
        - risk_level: One of "HIGH", "MODERATE", "LOW"
        - intensity: One of "INTENSIVE", "REGULAR", "BASIC"
    
    Raises:
        ValueError: If probability is outside valid range
    """
    if not isinstance(probability, (int, float)):
        raise ValueError(
            f"Probability must be a number, got {type(probability).__name__}"
        )
    
    if probability < 0.0 or probability > 1.0:
        raise ValueError(
            f"Probability must be between 0 and 1, got {probability}"
        )
    
    # Classify from HIGH to LOW based on thresholds
    if probability >= RISK_THRESHOLDS["HIGH"]["min_probability"]:
        risk_level = "HIGH"
        intensity = RISK_THRESHOLDS["HIGH"]["intensity"]
    elif probability >= RISK_THRESHOLDS["MODERATE"]["min_probability"]:
        risk_level = "MODERATE"
        intensity = RISK_THRESHOLDS["MODERATE"]["intensity"]
    else:
        risk_level = "LOW"
        intensity = RISK_THRESHOLDS["LOW"]["intensity"]
    
    return risk_level, intensity


# ============================================================================
# HELPER: Check if notes are meaningful
# ============================================================================

def has_meaningful_notes(notes: Optional[str]) -> bool:
    """
    Determine if the notes contain meaningful content.
    
    Args:
        notes: Notes string or None
    
    Returns:
        True if notes contain meaningful text, False if None/empty/whitespace-only
    
    Examples:
        has_meaningful_notes(None) → False
        has_meaningful_notes("") → False
        has_meaningful_notes("   ") → False
        has_meaningful_notes("Meet Dr. X after 7 days") → True
    """
    if notes is None:
        return False
    if isinstance(notes, str) and notes.strip():
        return True
    return False


# ============================================================================
# MAIN AGENT FUNCTION
# ============================================================================

def run_care_plan_agent(input_data: ReadmissionInput) -> CarePlanOutput:
    """
    Generate or retrieve a care plan based on readmission risk.
    
    Workflow:
    1. Validate input using ReadmissionInput schema (MRN, prediction, probability, notes)
    2. Retrieve patient context from readmission dataset using MRN
    3. Check for existing ACTIVE care plan
    4. If ACTIVE plan exists:
       - Retrieve the existing care plan
       - Retrieve its existing tasks (preserve their current statuses)
       - Return the existing plan WITH preserved tasks (NO duplicates)
    5. If no ACTIVE plan exists:
       - Classify risk level from probability
       - Create new care plan
       - Get predefined care pathway based on risk level
       - Create pathway tasks
    6. Preserve existing EHR discharge notes if provided
    7. Build and return CarePlanOutput
    
    Important:
    - MRN is the application-level patient identifier for lookups
    - patient_id is used for internal tracking only
    - ACTIVE care plans are REUSED, not duplicated
    - Existing tasks are PRESERVED with their current statuses
    - Risk classification is ONLY done when creating new plans
    - EHR notes are separate from agent-generated plans
    - Empty/None notes means "no existing instructions were provided to our system"
    
    Args:
        input_data: ReadmissionInput with MRN, prediction, probability, notes
    
    Returns:
        CarePlanOutput with complete care plan, tasks (existing or new), and preserved notes
    
    Raises:
        ValueError: If input invalid, patient not found, or care plan retrieval fails
    """
    
    # ========================================================================
    # STEP 1: VALIDATE INPUT
    # ========================================================================
    
    try:
        # Pydantic validation
        validated_input = ReadmissionInput(
            mrn=input_data.mrn,
            prediction=input_data.prediction,
            probability=input_data.probability,
            notes=input_data.notes
        )
    except ValueError as e:
        raise ValueError(f"Invalid input: {e}")
    
    mrn = validated_input.mrn
    probability = validated_input.probability
    notes = validated_input.notes
    
    # ========================================================================
    # STEP 2: RETRIEVE PATIENT CONTEXT USING MRN
    # ========================================================================
    
    try:
        patient_context, patient_id = get_patient_context_tool(mrn)
    except ValueError as e:
        raise ValueError(f"Patient with MRN '{mrn}' not found: {e}")
    except Exception as e:
        raise ValueError(f"Failed to retrieve patient context for MRN '{mrn}': {e}")
    
    # Extract EHR clinical notes (preserved as-is from PostgreSQL, may be None)
    ehr_clinical_notes = patient_context.get("clinical_notes")
    
    # Extract doctor instructions from EHR clinical notes using Groq LLM
    try:
        doctor_instructions_obj = extract_doctor_instructions(ehr_clinical_notes)
    except Exception as e:
        logger.error(f"Failed to extract doctor instructions: {e}")
        doctor_instructions_obj = DoctorInstructions()
    
    # Convert DoctorInstructions object to formatted string for output
    doctor_instructions_str = _format_doctor_instructions(doctor_instructions_obj)
    
    # ========================================================================
    # STEP 3: CHECK FOR EXISTING ACTIVE CARE PLAN
    # ========================================================================
    
    existing_plan = get_existing_care_plan(mrn)
    
    if existing_plan:
        # ====================================================================
        # STEP 3A: REUSE EXISTING ACTIVE CARE PLAN
        # ====================================================================
        # DO NOT create a new plan
        # DO NOT create duplicate tasks
        # Retrieve existing tasks from PostgreSQL and preserve their statuses
        
        try:
            existing_tasks = get_plan_tasks(existing_plan["care_plan_id"])
        except ValueError as e:
            raise ValueError(f"Failed to retrieve tasks for existing care plan '{existing_plan['care_plan_id']}': {e}")
        
        # Convert task dicts to CareTask objects, preserving their current statuses
        care_tasks = []
        for task in existing_tasks:
            care_task = CareTask(
                task_id=task["task_id"],
                task_type=task["task_type"],
                status=task["status"],
                description=task.get("description"),
                doctor_instruction=task.get("doctor_instruction")
                # Note: No personalization for existing tasks in reused plans
                # Personalization only happens during new plan creation
            )
            care_tasks.append(care_task)
        
        # Check if notes are meaningful
        notes_to_preserve = notes if has_meaningful_notes(notes) else None
        
        # Build output using EXISTING plan (no risk classification needed)
        care_plan_output = CarePlanOutput(
            mrn=mrn,
            patient_id=str(patient_id),
            care_plan_id=existing_plan["care_plan_id"],
            risk_level=existing_plan["risk_level"],  # Use existing risk level
            intensity=existing_plan["intensity"],    # Use existing intensity
            status=existing_plan["status"],          # Use existing status
            notes=notes_to_preserve,
            doctor_instructions=existing_plan.get("doctor_instructions"),
            tasks=care_tasks
        )
        
        return care_plan_output
    
    # ====================================================================
    # STEP 3B: NO EXISTING PLAN - CREATE NEW CARE PLAN
    # ====================================================================
    
    # ========================================================================
    # STEP 4: CLASSIFY RISK LEVEL FROM PROBABILITY (new plan only)
    # ========================================================================
    
    try:
        risk_level, intensity = classify_risk_level(probability)
    except ValueError as e:
        raise ValueError(f"Risk classification failed: {e}")
    
    # ========================================================================
    # STEP 5: GET CARE PATHWAY BASED ON RISK LEVEL
    # ========================================================================
    
    try:
        pathway_tasks = get_care_pathway(risk_level)
    except ValueError as e:
        raise ValueError(f"Failed to get care pathway for risk level '{risk_level}': {e}")
    
    # ========================================================================
    # STEP 6: CREATE NEW CARE PLAN
    # ========================================================================
    
    try:
        care_plan = create_care_plan_db(
            mrn=mrn,
            patient_id=patient_id,
            risk_level=risk_level,
            intensity=intensity,
            doctor_instructions=doctor_instructions_str
        )
        care_plan_id = care_plan["care_plan_id"]
    except ValueError as e:
        raise ValueError(f"Failed to create care plan for MRN '{mrn}': {e}")
    
    # ========================================================================
    # STEP 7: CREATE PATHWAY TASKS FOR NEW PLAN (with personalization)
    # ========================================================================
    
    tasks_created = []
    
    for task_type in pathway_tasks:
        try:
            # Get personalization data for this task (will be populated later)
            task = create_task_db(care_plan_id, task_type)
            tasks_created.append(task)
        except ValueError as e:
            raise ValueError(f"Failed to create task '{task_type}' for care plan '{care_plan_id}': {e}")
    
    # ========================================================================
    # STEP 8: MAP DOCTOR INSTRUCTIONS TO TASKS (Personalization)
    # ========================================================================
    # Create mapping from extracted doctor instructions to task personalization data
    
    instruction_mapping = map_instructions_to_tasks(risk_level, doctor_instructions_obj)
    
    # ========================================================================
    # STEP 9: PERSONALIZE TASKS (Update in PostgreSQL)
    # ========================================================================
    
    # Convert task dicts to CareTask objects with personalization
    care_tasks = []
    for task in tasks_created:
        task_type = task["task_type"]
        
        # Get personalization data for this task
        personalized_description, doctor_instruction = personalize_task(task_type, instruction_mapping)
        
        # Use personalized description if available, otherwise generic
        final_description = get_task_description(task_type, personalized_description)
        
        # Update task in PostgreSQL with personalization
        if personalized_description or doctor_instruction:
            updated_task = CarePlanTaskRepository.update_task(
                task["task_id"],
                {
                    "description": final_description,
                    "doctor_instruction": doctor_instruction
                }
            )
        else:
            # Still set description even if not personalized
            updated_task = CarePlanTaskRepository.update_task(
                task["task_id"],
                {
                    "description": final_description,
                    "doctor_instruction": None
                }
            )
        
        care_task = CareTask(
            task_id=updated_task["task_id"],
            task_type=updated_task["task_type"],
            status=updated_task["status"],
            description=updated_task.get("description"),
            doctor_instruction=updated_task.get("doctor_instruction")
        )
        care_tasks.append(care_task)
    
    # ========================================================================
    # STEP 10: BUILD CARE PLAN OUTPUT
    # ========================================================================
    
    # Check if notes are meaningful
    notes_to_preserve = notes if has_meaningful_notes(notes) else None
    
    # Build output
    care_plan_output = CarePlanOutput(
        mrn=mrn,
        patient_id=str(patient_id),
        care_plan_id=care_plan_id,
        risk_level=risk_level,
        intensity=intensity,
        status="ACTIVE",
        notes=notes_to_preserve,
        doctor_instructions=doctor_instructions_str,
        tasks=care_tasks
    )
    
    return care_plan_output


# ============================================================================
# CONVENIENCE: Convert dict input to ReadmissionInput (for testing)
# ============================================================================

def run_care_plan_agent_from_dict(input_dict: Dict[str, Any]) -> CarePlanOutput:
    """
    Run care plan agent with dictionary input.
    
    Convenience function for testing that converts dict to ReadmissionInput schema.
    
    Args:
        input_dict: Dictionary with keys: mrn, prediction, probability, notes (optional)
    
    Returns:
        CarePlanOutput with complete care plan and tasks
    """
    try:
        input_data = ReadmissionInput(**input_dict)
    except Exception as e:
        raise ValueError(f"Invalid input dictionary: {e}")
    
    return run_care_plan_agent(input_data)
