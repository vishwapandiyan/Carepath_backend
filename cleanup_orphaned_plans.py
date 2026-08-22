#!/usr/bin/env python3
"""
Cleanup orphaned care plans (plans created without tasks from failed runs)
"""

import sys
import os

# Add post_care to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'post_care'))

from database.connection import get_db_connection, close_db_connection

def cleanup_orphaned_plans():
    """Delete care plans that have no associated tasks"""
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Find orphaned plans
        cursor.execute("""
            SELECT cp.id, cp.mrn, cp.risk_level, cp.created_at
            FROM care_plans cp
            LEFT JOIN care_plan_tasks t ON t.care_plan_id = cp.id
            WHERE cp.status = 'ACTIVE'
            GROUP BY cp.id, cp.mrn, cp.risk_level, cp.created_at
            HAVING COUNT(t.id) = 0
        """)
        
        orphaned = cursor.fetchall()
        
        if not orphaned:
            print("✅ No orphaned care plans found")
            return
        
        print(f"\n🔍 Found {len(orphaned)} orphaned care plan(s):")
        for plan in orphaned:
            print(f"  - {plan[0]} (MRN: {plan[1]}, Risk: {plan[2]}, Created: {plan[3]})")
        
        # Delete orphaned plans
        cursor.execute("""
            DELETE FROM care_plans 
            WHERE id IN (
                SELECT cp.id
                FROM care_plans cp
                LEFT JOIN care_plan_tasks t ON t.care_plan_id = cp.id
                WHERE cp.status = 'ACTIVE'
                GROUP BY cp.id
                HAVING COUNT(t.id) = 0
            )
        """)
        
        deleted_count = cursor.rowcount
        conn.commit()
        
        print(f"\n✅ Deleted {deleted_count} orphaned care plan(s)")
        print("\nYou can now retry care plan generation.")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    
    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    print("=" * 70)
    print("Cleanup Orphaned Care Plans")
    print("=" * 70)
    cleanup_orphaned_plans()
