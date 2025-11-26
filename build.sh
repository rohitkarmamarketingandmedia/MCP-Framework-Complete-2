#!/bin/bash
# Render Build Script
# This runs during deployment on Render

set -e

echo "=== MCP Framework Build ==="

# Install dependencies
pip install -r requirements.txt

# Run database migrations (create tables)
python -c "
from app import create_app
from app.database import db

app = create_app('production')
with app.app_context():
    db.create_all()
    print('✓ Database tables created')
"

echo "=== Build Complete ==="
