#!/bin/bash
# Render Build Script
# This runs during deployment on Render

set -e

echo "=== MCP Framework Build ==="

# Install dependencies
pip install -r requirements.txt

# Run database migrations (create tables + add new columns)
python -c "
from app import create_app
from app.database import db
from sqlalchemy import text, inspect

app = create_app('production')
with app.app_context():
    # Create all tables
    db.create_all()
    print('✓ Database tables created/verified')
    
    # Check for missing columns and add them
    inspector = inspect(db.engine)
    
    # Get existing columns in clients table
    if 'clients' in inspector.get_table_names():
        existing_cols = [col['name'] for col in inspector.get_columns('clients')]
        
        # Add service_pages column if missing
        if 'service_pages' not in existing_cols:
            db.session.execute(text('ALTER TABLE clients ADD COLUMN service_pages TEXT DEFAULT \"[]\"'))
            db.session.commit()
            print('✓ Added service_pages column to clients table')
        else:
            print('✓ service_pages column already exists')
    
    print('✓ Database migration complete')
"

# Create default admin if needed
python -c "
from app import create_app
from app.database import db
from app.models.db_models import DBUser, UserRole

app = create_app('production')
with app.app_context():
    existing = DBUser.query.filter_by(email='admin@mcp.local').first()
    if not existing:
        admin = DBUser(
            email='admin@mcp.local',
            name='Admin',
            password='admin123',
            role=UserRole.ADMIN
        )
        db.session.add(admin)
        db.session.commit()
        print('✓ Default admin created: admin@mcp.local / admin123')
    else:
        print('✓ Admin user exists')
"

echo "=== Build Complete ==="
