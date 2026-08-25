"""
Structured logging for CONCERN → Care Plan Modification flow
Provides detailed logs for debugging and verification of the voice response
pipeline when CONCERN classification triggers care plan updates.
"""

import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class ConcernFlowLogger:
    """Structured logging for CONCERN classification → care plan modification"""
    
    @staticmethod
    def log_patient_response(
        checkin_id: str,
        patient_response: str,
        call_sid: str,
        turn_number: int
    ) -> None:
        """Log initial patient response"""
        logger.info(f"\n{'='*100}")
        logger.info(f"🔵 PATIENT RESPONSE (Turn {turn_number})")
        logger.info(f"{'='*100}")
        logger.info(f"  checkin_id:        {checkin_id}")
        logger.info(f"  patient_response:  {patient_response}")
        logger.info(f"  call_sid:          {call_sid}")
        logger.info(f"  turn_number:       {turn_number}")
    
    @staticmethod
    def log_response_analyzer(
        classification: str,
        confidence: float,
        symptoms: List[str],
        summary: str,
        concerns: List[str]
    ) -> None:
        """Log Response Analyzer output"""
        logger.info(f"\n{'='*100}")
        logger.info(f"🟢 RESPONSE ANALYZER OUTPUT")
        logger.info(f"{'='*100}")
        logger.info(f"  classification:    {classification}")
        logger.info(f"  confidence:        {confidence}")
        logger.info(f"  symptoms:          {symptoms}")
        logger.info(f"  summary:           {summary}")
        logger.info(f"  concerns:          {concerns}")
    
    @staticmethod
    def log_care_continuity(
        continuity_action: str,
        reason: str,
        care_plan_modifications: Optional[List[str]] = None,
        requires_appointment: bool = False
    ) -> None:
        """Log Care Continuity output"""
        logger.info(f"\n{'='*100}")
        logger.info(f"🟣 CARE CONTINUITY OUTPUT")
        logger.info(f"{'='*100}")
        logger.info(f"  continuity_action:        {continuity_action}")
        logger.info(f"  reason:                   {reason}")
        logger.info(f"  care_plan_modifications:  {care_plan_modifications or []}")
        logger.info(f"  requires_appointment:     {requires_appointment}")
    
    @staticmethod
    def log_before_database_update(
        care_plan_id: str,
        existing_task_id: str,
        current_status: str,
        active_task_count: int,
        checkin_id: str
    ) -> None:
        """Log database state BEFORE modification"""
        logger.info(f"\n{'='*100}")
        logger.info(f"📊 BEFORE: DATABASE STATE")
        logger.info(f"{'='*100}")
        logger.info(f"  care_plan_id:          {care_plan_id}")
        logger.info(f"  existing_task_id:      {existing_task_id}")
        logger.info(f"  current_status:        {current_status}")
        logger.info(f"  active_task_count:     {active_task_count}")
        logger.info(f"  checkin_id:            {checkin_id}")
    
    @staticmethod
    def log_care_plan_modification_triggered(
        reason: str,
        modifications: List[str]
    ) -> None:
        """Log care plan modification trigger"""
        logger.info(f"\n{'='*100}")
        logger.info(f"⚙️  CARE PLAN MODIFICATION TRIGGERED")
        logger.info(f"{'='*100}")
        logger.info(f"  Reason: {reason}")
        logger.info(f"  Modifications:")
        for mod in modifications:
            logger.info(f"    • {mod}")
    
    @staticmethod
    def log_task_insertion(
        task_id: str,
        care_plan_id: str,
        task_type: str,
        description: str,
        priority: str,
        status: str,
        created_by: str,
        frequency: Optional[str] = None
    ) -> None:
        """Log individual task insertion"""
        logger.info(f"\n  ✅ INSERTING TASK: {task_id}")
        logger.info(f"     task_id:        {task_id}")
        logger.info(f"     care_plan_id:   {care_plan_id}")
        logger.info(f"     task_type:      {task_type}")
        logger.info(f"     description:    {description}")
        logger.info(f"     priority:       {priority}")
        logger.info(f"     status:         {status}")
        logger.info(f"     created_by:     {created_by}")
        if frequency:
            logger.info(f"     frequency:      {frequency}")
    
    @staticmethod
    def log_database_insert_batch(
        new_tasks: List[Dict[str, Any]],
        total_count: int
    ) -> None:
        """Log batch database insertions"""
        logger.info(f"\n{'='*100}")
        logger.info(f"💾 DATABASE INSERT: NEW TASKS")
        logger.info(f"{'='*100}")
        logger.info(f"  Total tasks to insert: {total_count}")
        
        for i, task in enumerate(new_tasks, 1):
            logger.info(f"\n  Task {i}:")
            logger.info(f"    task_id:        {task.get('task_id')}")
            logger.info(f"    care_plan_id:   {task.get('care_plan_id')}")
            logger.info(f"    task_type:      {task.get('task_type')}")
            logger.info(f"    description:    {task.get('description')}")
            logger.info(f"    priority:       {task.get('priority')}")
            logger.info(f"    status:         {task.get('status')}")
            logger.info(f"    created_by:     {task.get('created_by')}")
            if task.get('frequency'):
                logger.info(f"    frequency:      {task.get('frequency')}")
    
    @staticmethod
    def log_database_update_followup_checkins(
        checkin_id: str,
        new_status: str,
        response: str,
        care_plan_modified: bool,
        tasks_added: int,
        response_received_at: str
    ) -> None:
        """Log follow_up_checkins table update"""
        logger.info(f"\n{'='*100}")
        logger.info(f"🔄 DATABASE UPDATE: follow_up_checkins")
        logger.info(f"{'='*100}")
        logger.info(f"  checkin_id:           {checkin_id}")
        logger.info(f"  status:               {new_status}")
        logger.info(f"  response:             {response}")
        logger.info(f"  care_plan_modified:   {care_plan_modified}")
        logger.info(f"  tasks_added:          {tasks_added}")
        logger.info(f"  response_received_at: {response_received_at}")
    
    @staticmethod
    def log_after_database_update(
        care_plan_id: str,
        final_status: str,
        modification_count: int,
        total_active_tasks: int,
        newly_added_task_ids: List[str]
    ) -> None:
        """Log database state AFTER modification"""
        logger.info(f"\n{'='*100}")
        logger.info(f"📊 AFTER: DATABASE STATE")
        logger.info(f"{'='*100}")
        logger.info(f"  care_plan_id:          {care_plan_id}")
        logger.info(f"  final_status:          {final_status}")
        logger.info(f"  modification_count:    {modification_count}")
        logger.info(f"  total_active_tasks:    {total_active_tasks}")
        logger.info(f"  newly_added_task_ids:  {newly_added_task_ids}")
    
    @staticmethod
    def log_final_voice_response(
        message: str,
        classification: str,
        continuity_action: str,
        requires_followup: bool,
        care_plan_modified: bool
    ) -> None:
        """Log final voice response sent to patient"""
        logger.info(f"\n{'='*100}")
        logger.info(f"🎙️  FINAL VOICE RESPONSE")
        logger.info(f"{'='*100}")
        logger.info(f"  message:")
        logger.info(f"    {message}")
        logger.info(f"  classification:       {classification}")
        logger.info(f"  continuity_action:    {continuity_action}")
        logger.info(f"  requires_followup:    {requires_followup}")
        logger.info(f"  care_plan_modified:   {care_plan_modified}")
    
    @staticmethod
    def log_flow_summary(
        classification: str,
        care_plan_modified: bool,
        existing_task_id: str,
        new_tasks_added: int,
        new_task_ids: List[str],
        database_updated: bool,
        final_message_sent: bool
    ) -> None:
        """Log complete flow summary"""
        logger.info(f"\n{'='*100}")
        logger.info(f"✅ CONCERN FLOW COMPLETE")
        logger.info(f"{'='*100}")
        logger.info(f"  Classification:        {classification}")
        logger.info(f"  Care Plan Modified:    {care_plan_modified}")
        logger.info(f"  Existing Task:         {existing_task_id}")
        logger.info(f"  New Tasks Added:       {new_tasks_added}")
        logger.info(f"  New Task IDs:          {new_task_ids}")
        logger.info(f"  Database Updated:      {database_updated}")
        logger.info(f"  Final Message Sent:    {final_message_sent}")
        logger.info(f"{'='*100}\n")
