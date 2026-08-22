#!/usr/bin/env python3
"""
Run database migration to fix task_type constraint
"""

import sys
import os

# Add post_care to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'post_care'))

from database.connection import get_db_connection, close_db_connection

def run_migration():
    """Apply the task_type constraint fix"""
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        print("🔄 Dropping old task_type constraint...")
        cursor.execute("""
            ALTER TABLE care_plan_tasks 
            DROP CONSTRAINT IF EXISTS care_plan_tasks_task_type_check
        """)
        
        print("✅ Old constraint dropped")
        
        print("\n🔄 Adding new task_type constraint with all agent task types...")
        cursor.execute("""
            ALTER TABLE care_plan_tasks
            ADD CONSTRAINT care_plan_tasks_task_type_check
            CHECK (task_type IN (
                -- LOW risk tasks (3 tasks - BASIC pathway)
                'BASIC_CHECKIN',
                'FOLLOW_UP_REMINDER',
                'PATIENT_SUPPORT',
                
                -- MODERATE risk tasks (4 tasks - REGULAR pathway)
                'CHECKIN',
                'FOLLOW_UP_APPOINTMENT',
                'APPOINTMENT_REMINDER',
                'RESPONSE_MONITORING',
                
                -- HIGH risk tasks (5 tasks - INTENSIVE pathway)
                'EARLY_CHECKIN',
                'FREQUENT_CHECKINS',
                'APPOINTMENT_MONITORING',
                'CONCERN_ESCALATION',
                'MEDICATION_REVIEW',
                
                -- Legacy/additional task types (keep for backwards compatibility)
                'VITALS_MONITORING',
                'LABS_MONITORING',
                'EDUCATION',
                'LIFESTYLE',
                'FOLLOWUP_APPOINTMENT',
                'WOUND_CARE',
                'DIET_COUNSELING',
                'PHYSICAL_THERAPY'
            ))
        """)
        
        conn.commit()
        
        print("✅ New constraint added successfully")
        print("\n" + "=" * 70)
        print("Migration Complete!")
        print("=" * 70)
        print("\nSupported task types:")
        print("  LOW risk: BASIC_CHECKIN, FOLLOW_UP_REMINDER, PATIENT_SUPPORT")
        print("  MODERATE risk: CHECKIN, FOLLOW_UP_APPOINTMENT, APPOINTMENT_REMINDER, RESPONSE_MONITORING")
        print("  HIGH risk: EARLY_CHECKIN, FREQUENT_CHECKINS, APPOINTMENT_MONITORING, CONCERN_ESCALATION, MEDICATION_REVIEW")
        print("\nYou can now generate care plans successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    
    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    print("=" * 70)
    print("Fix Task Type Constraint Migration")
    print("=" * 70)
    print()
    run_migration()
