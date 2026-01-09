#!/usr/bin/env python3
"""
Migration: Add GBP refresh token and connected_at fields

This fixes the issue where GBP tokens expire after 1 hour and cannot be
refreshed because the refresh_token field doesn't exist.

Run with: python scripts/migrations/add_gbp_refresh_token.py
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app
from app.database import db
from sqlalchemy import inspect, text

def run_migration():
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("Migration: Add GBP Refresh Token Fields")
        print("=" * 60)
        
        # Get current columns
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('clients')]
        
        print(f"\nCurrent columns in 'clients' table: {len(columns)}")
        
        migrations_run = 0
        
        # Add gbp_refresh_token
        if 'gbp_refresh_token' not in columns:
            print("\n→ Adding 'gbp_refresh_token' column...")
            db.session.execute(text('ALTER TABLE clients ADD COLUMN gbp_refresh_token TEXT'))
            migrations_run += 1
            print("  ✓ Added gbp_refresh_token")
        else:
            print("\n✓ gbp_refresh_token already exists")
        
        # Add gbp_connected_at
        if 'gbp_connected_at' not in columns:
            print("\n→ Adding 'gbp_connected_at' column...")
            db.session.execute(text('ALTER TABLE clients ADD COLUMN gbp_connected_at TIMESTAMP'))
            migrations_run += 1
            print("  ✓ Added gbp_connected_at")
        else:
            print("✓ gbp_connected_at already exists")
        
        # Commit changes
        if migrations_run > 0:
            db.session.commit()
            print(f"\n{'=' * 60}")
            print(f"Migration complete! {migrations_run} column(s) added.")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Update app/models/db_models.py to add the new fields")
            print("2. Reconnect GBP for affected clients")
            print("3. The refresh token will be saved during OAuth flow")
        else:
            print(f"\n{'=' * 60}")
            print("No migrations needed - all columns already exist.")
            print("=" * 60)
        
        # Verify
        print("\nVerifying columns...")
        new_columns = [col['name'] for col in inspector.get_columns('clients')]
        gbp_cols = [c for c in new_columns if 'gbp' in c.lower()]
        print(f"GBP-related columns: {gbp_cols}")
        
        return migrations_run


if __name__ == '__main__':
    try:
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
