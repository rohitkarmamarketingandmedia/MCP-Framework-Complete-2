"""
Migration: Add trigger behavior and guided flow columns to chatbot_configs table
Run this once after deploying the new db_models.py

Usage: python scripts/migrate_chatbot_triggers.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db

def migrate():
    app = create_app()
    
    with app.app_context():
        # Add columns that don't exist yet
        columns_to_add = [
            ("trigger_mode", "VARCHAR(30) DEFAULT 'disabled'"),
            ("trigger_delay_seconds", "INTEGER DEFAULT 60"),
            ("trigger_page_views", "INTEGER DEFAULT 2"),
            ("reopen_after_close", "BOOLEAN DEFAULT FALSE"),
            ("guided_flow_enabled", "BOOLEAN DEFAULT FALSE"),
            ("guided_flow_json", "TEXT"),
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                db.session.execute(
                    db.text(f"ALTER TABLE chatbot_configs ADD COLUMN {col_name} {col_type}")
                )
                db.session.commit()
                print(f"  ✓ Added column: {col_name}")
            except Exception as e:
                db.session.rollback()
                if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower():
                    print(f"  - Column already exists: {col_name}")
                else:
                    print(f"  ✗ Error adding {col_name}: {e}")
        
        print("\nDone! Chatbot trigger columns migrated.")

if __name__ == '__main__':
    migrate()
