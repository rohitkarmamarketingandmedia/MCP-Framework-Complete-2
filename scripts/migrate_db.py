#!/usr/bin/env python3
"""
MCP Framework - Database Migration Script
Adds missing columns to existing SQLite databases

Run: python scripts/migrate_db.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db
from sqlalchemy import inspect, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define all columns that should exist in the clients table
CLIENT_COLUMNS = {
    # Social media connections
    'facebook_page_id': 'VARCHAR(100)',
    'facebook_access_token': 'TEXT',
    'facebook_connected_at': 'DATETIME',
    'instagram_account_id': 'VARCHAR(100)',
    'instagram_access_token': 'TEXT',
    'instagram_connected_at': 'DATETIME',
    'linkedin_org_id': 'VARCHAR(100)',
    'linkedin_access_token': 'TEXT',
    'linkedin_connected_at': 'DATETIME',
    
    # Google Business Profile
    'gbp_location_id': 'VARCHAR(100)',
    'gbp_access_token': 'TEXT',
    'gbp_refresh_token': 'TEXT',
    'gbp_connected_at': 'DATETIME',
    
    # WordPress
    'wordpress_url': 'VARCHAR(500)',
    'wordpress_username': 'VARCHAR(100)',
    'wordpress_app_password': 'VARCHAR(100)',
    'wordpress_connected_at': 'DATETIME',
    
    # CallRail
    'callrail_company_id': 'VARCHAR(100)',
    'callrail_account_id': 'VARCHAR(100)',
    
    # Notifications
    'lead_notification_email': 'VARCHAR(255)',
    'lead_notification_phone': 'VARCHAR(20)',
    
    # Health tracking
    'health_score': 'INTEGER DEFAULT 0',
    'health_last_updated': 'DATETIME',
    
    # Service pages
    'service_pages': 'TEXT',  # JSON array
    
    # Additional fields
    'geo_modifier': 'VARCHAR(100)',
    'target_audience': 'TEXT',
    'unique_selling_points': 'TEXT',
    'brand_voice': 'VARCHAR(50)',
    'competitors': 'TEXT',
}

# User table columns
USER_COLUMNS = {
    'phone': 'VARCHAR(20)',
    'last_login_at': 'DATETIME',
    'login_count': 'INTEGER DEFAULT 0',
    'failed_login_count': 'INTEGER DEFAULT 0',
    'locked_until': 'DATETIME',
}

# Content table columns
CONTENT_COLUMNS = {
    'seo_score': 'INTEGER',
    'word_count': 'INTEGER',
    'reading_time': 'INTEGER',
    'internal_links': 'TEXT',
    'external_links': 'TEXT',
    'images': 'TEXT',
    'schema_markup': 'TEXT',
    'faq_content': 'TEXT',
}


def get_existing_columns(table_name):
    """Get list of existing columns in a table"""
    inspector = inspect(db.engine)
    try:
        columns = inspector.get_columns(table_name)
        return [col['name'] for col in columns]
    except Exception:
        return []


def add_column(table_name, column_name, column_type):
    """Add a column to a table if it doesn't exist"""
    try:
        db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'))
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
            return False
        logger.error(f"Error adding {column_name} to {table_name}: {e}")
        return False


def migrate_table(table_name, columns_spec):
    """Migrate a table by adding missing columns"""
    existing = get_existing_columns(table_name)
    
    if not existing:
        logger.warning(f"Table '{table_name}' not found or empty")
        return 0
    
    added = 0
    for col_name, col_type in columns_spec.items():
        if col_name not in existing:
            if add_column(table_name, col_name, col_type):
                logger.info(f"  ✓ Added: {table_name}.{col_name}")
                added += 1
    
    return added


def run_migrations():
    """Run all database migrations"""
    app = create_app()
    
    with app.app_context():
        logger.info("=" * 60)
        logger.info("MCP Framework - Database Migration")
        logger.info("=" * 60)
        
        total_added = 0
        
        # Migrate clients table
        logger.info("\nMigrating 'clients' table...")
        added = migrate_table('clients', CLIENT_COLUMNS)
        total_added += added
        if added == 0:
            logger.info("  (no changes needed)")
        
        # Migrate users table
        logger.info("\nMigrating 'users' table...")
        added = migrate_table('users', USER_COLUMNS)
        total_added += added
        if added == 0:
            logger.info("  (no changes needed)")
        
        # Migrate blog_posts table
        logger.info("\nMigrating 'blog_posts' table...")
        added = migrate_table('blog_posts', CONTENT_COLUMNS)
        total_added += added
        if added == 0:
            logger.info("  (no changes needed)")
        
        logger.info("\n" + "=" * 60)
        if total_added > 0:
            logger.info(f"Migration complete! Added {total_added} columns.")
        else:
            logger.info("Migration complete! Database is up to date.")
        logger.info("=" * 60)
        
        return total_added


if __name__ == '__main__':
    run_migrations()
