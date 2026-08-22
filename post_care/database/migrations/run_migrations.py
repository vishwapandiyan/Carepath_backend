"""
Database Migration Runner

Executes pending migrations to set up the database schema.

Usage:
    python -m post_care.database.migrations.run_migrations [up|down]
    
Examples:
    python -m post_care.database.migrations.run_migrations up     # Run all migrations
    python -m post_care.database.migrations.run_migrations down   # Revert all migrations
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.migrations import migration_001_create_follow_up_checkins


def run_migrations(direction="up"):
    """
    Run all database migrations.
    
    Args:
        direction: "up" to apply, "down" to revert
    """
    migrations = [
        ("001_create_follow_up_checkins", migration_001_create_follow_up_checkins),
    ]
    
    print(f"\n{'='*60}")
    print(f"Running database migrations: {direction.upper()}")
    print(f"{'='*60}\n")
    
    if direction == "up":
        for name, migration in migrations:
            try:
                print(f"Running migration: {name}...")
                migration.up()
                print()
            except Exception as e:
                print(f"❌ Migration failed: {name}")
                print(f"   Error: {str(e)}")
                sys.exit(1)
    
    elif direction == "down":
        for name, migration in reversed(migrations):
            try:
                print(f"Reverting migration: {name}...")
                migration.down()
                print()
            except Exception as e:
                print(f"❌ Migration revert failed: {name}")
                print(f"   Error: {str(e)}")
                sys.exit(1)
    
    else:
        print(f"❌ Invalid direction: {direction}")
        print("   Use 'up' or 'down'")
        sys.exit(1)
    
    print(f"{'='*60}")
    print(f"✅ All migrations completed: {direction.upper()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    direction = sys.argv[1] if len(sys.argv) > 1 else "up"
    run_migrations(direction)
