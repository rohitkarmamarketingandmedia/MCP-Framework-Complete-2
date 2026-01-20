#!/bin/bash
# Render Build Script for MCP Framework v4.5
# Karma Marketing + Media
# This runs during deployment on Render

set -e

echo "=============================================="
echo "  KARMA MARKETING + MEDIA"
echo "  MCP Framework Build v4.5"
echo "=============================================="

# Install system fonts for image generation
# CRITICAL: Without these fonts, featured image text will be TINY
echo ""
echo "🔤 Installing system fonts..."
if command -v apt-get &> /dev/null; then
    apt-get update -qq || true
    apt-get install -y --no-install-recommends fonts-dejavu-core fonts-liberation fontconfig || true
    fc-cache -f -v || true
    echo "  ✓ Fonts installed (DejaVu, Liberation)"
else
    echo "  ⚠ apt-get not available, fonts may need manual installation"
fi

# Verify font availability
echo ""
echo "🔍 Checking font availability..."
python -c "
import os
font_paths = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
]
found = False
for p in font_paths:
    if os.path.exists(p):
        print(f'  ✓ Font found: {p}')
        found = True
        break
if not found:
    print('  ⚠ WARNING: No TrueType fonts found!')
    print('    Featured image text may appear very small.')
    print('    The system will attempt to download fonts at runtime.')
"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Run database migrations
echo ""
echo "🗄️ Setting up database..."
python -c "
from app import create_app
from app.database import db
from sqlalchemy import text, inspect

app = create_app('production')
with app.app_context():
    # Create all tables
    db.create_all()
    print('  ✓ Database tables created/verified')
    
    # Check for missing columns and add them
    inspector = inspect(db.engine)
    
    # Get existing columns in clients table
    if 'clients' in inspector.get_table_names():
        existing_cols = [col['name'] for col in inspector.get_columns('clients')]
        
        # Add service_pages column if missing
        if 'service_pages' not in existing_cols:
            db.session.execute(text('ALTER TABLE clients ADD COLUMN service_pages TEXT DEFAULT \"[]\"'))
            db.session.commit()
            print('  ✓ Added service_pages column')
    
    print('  ✓ Database migration complete')
"

# Initialize AI agents
echo ""
echo "🤖 Initializing AI agents..."
python -c "
from app import create_app
from app.services.agent_service import agent_service

app = create_app('production')
with app.app_context():
    created = agent_service.initialize_default_agents()
    if created > 0:
        print(f'  ✓ Initialized {created} AI agents')
    else:
        print('  ✓ AI agents already configured')
"

# Check/create admin user
echo ""
echo "👤 Checking admin user..."
python -c "
import os
import secrets
from app import create_app
from app.database import db
from app.models.db_models import DBUser

app = create_app('production')
with app.app_context():
    # Check if any admin exists
    admin_count = DBUser.query.filter_by(role='admin').count()
    
    if admin_count == 0:
        # Check for ADMIN_EMAIL and ADMIN_PASSWORD env vars
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        
        if admin_email and admin_password:
            admin = DBUser(
                email=admin_email,
                name='Admin',
                role='admin',
                is_active=True,
                can_generate_content=True
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print(f'  ✓ Admin created: {admin_email}')
        else:
            print('  ⚠ No admin user! Set ADMIN_EMAIL and ADMIN_PASSWORD env vars')
            print('    Or run: python scripts/create_admin.py')
    else:
        print(f'  ✓ {admin_count} admin user(s) exist')
"

echo ""
echo "=============================================="
echo "  ✅ BUILD COMPLETE"
echo "=============================================="
echo ""

