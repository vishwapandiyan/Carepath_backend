"""
Database Migration: Create Voice Conversation Turns Table

This migration creates the voice_conversation_turns table for storing
multi-turn voice conversation context between the voice-service and backend.

Table: voice_conversation_turns
- Stores each turn of a voice conversation
- Links turns to check-ins and calls via foreign key
- Tracks patient responses, classifications, and symptoms
- Enables contextual analysis for multi-turn conversations

SQL Schema:
    CREATE TABLE voice_conversation_turns (
        turn_id BIGSERIAL PRIMARY KEY,
        checkin_id VARCHAR(255) NOT NULL,
        call_sid VARCHAR(255) NOT NULL,
        turn_number INT NOT NULL,
        patient_response TEXT NOT NULL,
        classification VARCHAR(50),
        symptoms TEXT[],
        concerns TEXT[],
        followup_question TEXT,
        response_received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (checkin_id) REFERENCES follow_up_checkins(checkin_id) ON DELETE CASCADE
    );

Run this migration:
    python -m post_care.database.migrations.run 006_create_voice_conversation_turns
"""

from post_care.database.connection import get_db_connection, close_db_connection


def up():
    """Execute the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Create voice_conversation_turns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voice_conversation_turns (
                turn_id BIGSERIAL PRIMARY KEY,
                checkin_id VARCHAR(255) NOT NULL,
                call_sid VARCHAR(255) NOT NULL,
                turn_number INT NOT NULL,
                patient_response TEXT NOT NULL,
                classification VARCHAR(50),
                symptoms TEXT[],
                concerns TEXT[],
                followup_question TEXT,
                response_received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (checkin_id) REFERENCES follow_up_checkins(checkin_id) ON DELETE CASCADE
            );
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_voice_turns_checkin_id
            ON voice_conversation_turns(checkin_id);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_voice_turns_call_sid
            ON voice_conversation_turns(call_sid);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_voice_turns_checkin_call
            ON voice_conversation_turns(checkin_id, call_sid);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_voice_turns_turn_number
            ON voice_conversation_turns(checkin_id, call_sid, turn_number);
        """)
        
        conn.commit()
        print("✅ Migration 006_create_voice_conversation_turns: SUCCESS")
        print("   Table voice_conversation_turns created successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 006_create_voice_conversation_turns: FAILED")
        print(f"   Error: {str(e)}")
        raise
    
    finally:
        close_db_connection(conn)


def down():
    """Revert the migration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS voice_conversation_turns CASCADE;")
        
        conn.commit()
        print("✅ Migration 006_create_voice_conversation_turns reverted: SUCCESS")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 006_create_voice_conversation_turns revert: FAILED")
        print(f"   Error: {str(e)}")
        raise
    
    finally:
        close_db_connection(conn)
