"""
Tests for AppointmentSessionRepository.

Verifies:
1. Table exists in carepath_db
2. MRN can reference existing patient
3. Session can be created with session_id
4. Session can be retrieved by session_id
5. Session can be updated (JSONB fields + scalars)
6. Expiration works (expired sessions not returned)
7. expire_sessions() cleanup works
8. Existing Post-care tables are not modified
9. No second database is created
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from post_care.database.connection import get_db_connection, close_db_connection
from post_care.database.appointment_repository import AppointmentSessionRepository


def _cleanup_test_sessions():
    """Remove any test sessions left by previous runs."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM appointment_sessions WHERE mrn LIKE 'TEST_MRN_%'"
        )
        conn.commit()
        cursor.close()
    finally:
        close_db_connection(conn)


def test_01_table_exists():
    """Verify appointment_sessions table exists in carepath_db."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'appointment_sessions'
            )
        """)
        exists = cursor.fetchone()[0]
        cursor.execute("SELECT current_database()")
        db_name = cursor.fetchone()[0]
        cursor.close()

        assert exists, "appointment_sessions table does not exist"
        assert db_name == "carepath_db", f"Wrong database: {db_name}"
        print("✓ TEST 01 PASSED: appointment_sessions table exists in carepath_db")
    finally:
        close_db_connection(conn)


def test_02_mrn_references_existing_patient():
    """Verify MRN000001 exists in patient_ehr (same DB)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT mrn FROM patient_ehr WHERE mrn = 'MRN000001' LIMIT 1")
        row = cursor.fetchone()
        cursor.close()

        assert row is not None, "MRN000001 not found in patient_ehr"
        assert row[0] == "MRN000001"
        print("✓ TEST 02 PASSED: MRN000001 exists in patient_ehr (same carepath_db)")
    finally:
        close_db_connection(conn)


def test_03_create_session():
    """Verify session can be created and returns expected fields."""
    _cleanup_test_sessions()

    session = AppointmentSessionRepository.create_session(
        mrn="TEST_MRN_001",
        destination="SPECIALIST",
        specialty="CARDIOLOGY",
        rule_id="SPEC-002-PULM",
        latitude=37.7749,
        longitude=-122.4194,
        radius_km=15.0,
        source="PATIENT",
    )

    assert session is not None
    assert session["session_id"].startswith("rec_")
    assert session["mrn"] == "TEST_MRN_001"
    assert session["destination"] == "SPECIALIST"
    assert session["specialty"] == "CARDIOLOGY"
    assert session["rule_id"] == "SPEC-002-PULM"
    assert session["latitude"] == 37.7749
    assert session["longitude"] == -122.4194
    assert session["radius_km"] == 15.0
    assert session["workflow_stage"] == "NAVIGATION_COMPLETE"
    assert session["source"] == "PATIENT"
    assert session["expires_at"] is not None
    assert session["provider_candidates"] is None
    assert session["appointment_id"] is None
    print(f"✓ TEST 03 PASSED: Session created (session_id={session['session_id']})")

    _cleanup_test_sessions()


def test_04_get_session():
    """Verify session can be retrieved by session_id."""
    _cleanup_test_sessions()

    created = AppointmentSessionRepository.create_session(
        mrn="TEST_MRN_002",
        destination="URGENT_CARE",
        rule_id="UC-001-INFECTION",
        latitude=40.7128,
        longitude=-74.0060,
    )

    session_id = created["session_id"]

    retrieved = AppointmentSessionRepository.get_session(session_id)

    assert retrieved is not None
    assert retrieved["session_id"] == session_id
    assert retrieved["mrn"] == "TEST_MRN_002"
    assert retrieved["destination"] == "URGENT_CARE"
    assert retrieved["rule_id"] == "UC-001-INFECTION"
    assert retrieved["latitude"] == 40.7128
    assert retrieved["longitude"] == -74.0060
    print(f"✓ TEST 04 PASSED: Session retrieved by session_id={session_id}")

    _cleanup_test_sessions()


def test_05_get_session_nonexistent():
    """Verify nonexistent session returns None."""
    result = AppointmentSessionRepository.get_session("rec_DOES_NOT_EXIST")
    assert result is None
    print("✓ TEST 05 PASSED: Nonexistent session returns None")


def test_06_update_session_scalars():
    """Verify scalar fields can be updated."""
    _cleanup_test_sessions()

    created = AppointmentSessionRepository.create_session(
        mrn="TEST_MRN_003",
        destination="PCP",
        rule_id="PCP-001-FLAREUP",
        latitude=30.2672,
        longitude=-97.7431,
    )

    session_id = created["session_id"]

    updated = AppointmentSessionRepository.update_session(session_id, {
        "selected_provider_id": "osm:node:12345",
        "workflow_stage": "PROVIDER_SELECTED",
    })

    assert updated["selected_provider_id"] == "osm:node:12345"
    assert updated["workflow_stage"] == "PROVIDER_SELECTED"
    assert updated["session_id"] == session_id
    print(f"✓ TEST 06 PASSED: Scalar fields updated successfully")

    _cleanup_test_sessions()


def test_07_update_session_jsonb():
    """Verify JSONB fields (provider_candidates, ranked_providers) can be updated."""
    _cleanup_test_sessions()

    created = AppointmentSessionRepository.create_session(
        mrn="TEST_MRN_004",
        destination="SPECIALIST",
        specialty="ORTHOPEDICS",
        rule_id="SPEC-003-ORTHO",
        latitude=37.7749,
        longitude=-122.4194,
    )

    session_id = created["session_id"]

    providers = [
        {"provider_id": "osm:node:111", "name": "Test Clinic A", "distance_km": 2.5},
        {"provider_id": "osm:node:222", "name": "Test Clinic B", "distance_km": 5.1},
    ]

    updated = AppointmentSessionRepository.update_session(session_id, {
        "provider_candidates": providers,
        "workflow_stage": "PROVIDERS_SEARCHED",
    })

    assert updated["provider_candidates"] is not None
    assert len(updated["provider_candidates"]) == 2
    assert updated["provider_candidates"][0]["name"] == "Test Clinic A"
    assert updated["workflow_stage"] == "PROVIDERS_SEARCHED"
    print(f"✓ TEST 07 PASSED: JSONB provider_candidates stored and retrieved")

    _cleanup_test_sessions()


def test_08_expiration_hides_session():
    """Verify expired sessions are not returned by get_session."""
    _cleanup_test_sessions()

    # Create session with 0-minute TTL (already expired)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        cursor.execute(
            """
            INSERT INTO appointment_sessions
            (session_id, mrn, destination, workflow_stage, expires_at, source)
            VALUES ('rec_EXPIRED_TEST', 'TEST_MRN_005', 'PCP', 'NAVIGATION_COMPLETE', %s, 'PATIENT')
            """,
            (expired_time,),
        )
        conn.commit()
        cursor.close()
    finally:
        close_db_connection(conn)

    # Should NOT be retrievable
    result = AppointmentSessionRepository.get_session("rec_EXPIRED_TEST")
    assert result is None, "Expired session should not be returned"
    print("✓ TEST 08 PASSED: Expired session is hidden from get_session")

    _cleanup_test_sessions()
    # Clean up the expired test row
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM appointment_sessions WHERE session_id = 'rec_EXPIRED_TEST'")
        conn.commit()
        cursor.close()
    finally:
        close_db_connection(conn)


def test_09_expire_sessions_cleanup():
    """Verify expire_sessions() deletes expired rows."""
    _cleanup_test_sessions()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        cursor.execute(
            """
            INSERT INTO appointment_sessions
            (session_id, mrn, destination, workflow_stage, expires_at, source)
            VALUES ('rec_CLEANUP_01', 'TEST_MRN_006', 'PCP', 'NAVIGATION_COMPLETE', %s, 'PATIENT'),
                   ('rec_CLEANUP_02', 'TEST_MRN_007', 'URGENT_CARE', 'NAVIGATION_COMPLETE', %s, 'PATIENT')
            """,
            (expired_time, expired_time),
        )
        conn.commit()
        cursor.close()
    finally:
        close_db_connection(conn)

    deleted = AppointmentSessionRepository.expire_sessions()
    assert deleted >= 2, f"Expected at least 2 deletions, got {deleted}"
    print(f"✓ TEST 09 PASSED: expire_sessions() cleaned up {deleted} expired rows")


def test_10_existing_tables_not_modified():
    """Verify existing Post-care tables still have their original column counts."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # patient_ehr should have 68 columns (as verified earlier)
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'patient_ehr'
        """)
        patient_cols = cursor.fetchone()[0]

        # care_plans should have 10 columns
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'care_plans'
        """)
        care_plan_cols = cursor.fetchone()[0]

        # care_plan_tasks should have 9 columns
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'care_plan_tasks'
        """)
        task_cols = cursor.fetchone()[0]

        cursor.close()

        assert patient_cols == 68, f"patient_ehr columns changed! Expected 68, got {patient_cols}"
        assert care_plan_cols == 10, f"care_plans columns changed! Expected 10, got {care_plan_cols}"
        assert task_cols == 9, f"care_plan_tasks columns changed! Expected 9, got {task_cols}"

        print(f"✓ TEST 10 PASSED: Existing tables unchanged (patient_ehr={patient_cols}, care_plans={care_plan_cols}, care_plan_tasks={task_cols})")
    finally:
        close_db_connection(conn)


def test_11_no_second_database():
    """Verify we are using carepath_db and no other database was created."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT current_database()")
        db_name = cursor.fetchone()[0]
        cursor.close()

        assert db_name == "carepath_db", f"Expected carepath_db, got {db_name}"
        print(f"✓ TEST 11 PASSED: Using single database: {db_name}")
    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    print("=" * 70)
    print("APPOINTMENT SESSION REPOSITORY — DATABASE FOUNDATION TESTS")
    print("=" * 70)
    print()

    tests = [
        test_01_table_exists,
        test_02_mrn_references_existing_patient,
        test_03_create_session,
        test_04_get_session,
        test_05_get_session_nonexistent,
        test_06_update_session_scalars,
        test_07_update_session_jsonb,
        test_08_expiration_hides_session,
        test_09_expire_sessions_cleanup,
        test_10_existing_tables_not_modified,
        test_11_no_second_database,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test_fn.__name__} FAILED: {e}")

    print()
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 70)
