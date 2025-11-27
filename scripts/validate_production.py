#!/usr/bin/env python3
"""
Karma Marketing + Media - Production Validation
Run this script to verify the production deployment is healthy.

Usage:
    python scripts/validate_production.py
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(name, condition, warning=False):
    """Print check result"""
    if condition:
        print(f"  ✅ {name}")
        return True
    else:
        symbol = "⚠️" if warning else "❌"
        print(f"  {symbol} {name}")
        return False


def validate():
    """Run all validation checks"""
    print("\n" + "="*60)
    print("  KARMA MARKETING + MEDIA - Production Validation")
    print("="*60 + "\n")
    
    errors = 0
    warnings = 0
    
    # ==========================================
    # Environment Variables
    # ==========================================
    print("📋 Environment Variables:")
    
    # Required
    if not check("DATABASE_URL set", os.environ.get('DATABASE_URL')):
        errors += 1
    if not check("SECRET_KEY set", os.environ.get('SECRET_KEY')):
        errors += 1
    if not check("JWT_SECRET_KEY set", os.environ.get('JWT_SECRET_KEY')):
        errors += 1
    
    # CORS check
    cors = os.environ.get('CORS_ORIGINS', '*')
    if cors == '*':
        check("CORS_ORIGINS is restricted (not *)", False, warning=True)
        warnings += 1
    else:
        check(f"CORS_ORIGINS: {cors[:50]}...", True)
    
    # AI Keys
    if not check("OPENAI_API_KEY set", os.environ.get('OPENAI_API_KEY'), warning=True):
        warnings += 1
    
    print()
    
    # ==========================================
    # Database Connection
    # ==========================================
    print("🗄️ Database:")
    
    try:
        from app import create_app
        from app.database import db
        
        app = create_app()
        with app.app_context():
            # Test connection
            result = db.session.execute(db.text("SELECT 1")).fetchone()
            check("Database connection successful", result is not None)
            
            # Check tables
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            check(f"Tables created: {len(tables)}", len(tables) >= 15)
            
    except Exception as e:
        check(f"Database connection failed: {e}", False)
        errors += 1
    
    print()
    
    # ==========================================
    # Models & Data
    # ==========================================
    print("📊 Data:")
    
    try:
        with app.app_context():
            from app.models.db_models import DBUser, DBAgentConfig
            
            # Check admin user
            admin_count = DBUser.query.filter_by(role='admin').count()
            if not check(f"Admin users: {admin_count}", admin_count > 0):
                errors += 1
                print("     → Run: python scripts/create_admin.py")
            
            # Check agents
            agent_count = DBAgentConfig.query.count()
            check(f"AI Agents configured: {agent_count}", agent_count > 0)
            
    except Exception as e:
        check(f"Data check failed: {e}", False)
        errors += 1
    
    print()
    
    # ==========================================
    # Routes & App
    # ==========================================
    print("🌐 Application:")
    
    try:
        with app.app_context():
            rules = list(app.url_map.iter_rules())
            check(f"Routes registered: {len(rules)}", len(rules) > 100)
            check(f"Blueprints loaded: {len(app.blueprints)}", len(app.blueprints) >= 15)
            
    except Exception as e:
        check(f"App check failed: {e}", False)
        errors += 1
    
    print()
    
    # ==========================================
    # Optional Services
    # ==========================================
    print("🔌 Optional Services:")
    
    check("SEMRUSH_API_KEY", os.environ.get('SEMRUSH_API_KEY'), warning=True) or warnings.__add__(1)
    check("SENDGRID_API_KEY", os.environ.get('SENDGRID_API_KEY'), warning=True) or warnings.__add__(1)
    check("TWILIO_ACCOUNT_SID", os.environ.get('TWILIO_ACCOUNT_SID'), warning=True) or warnings.__add__(1)
    
    print()
    
    # ==========================================
    # Summary
    # ==========================================
    print("="*60)
    if errors == 0 and warnings == 0:
        print("  🎉 ALL CHECKS PASSED - Ready for production!")
    elif errors == 0:
        print(f"  ✅ PASSED with {warnings} warning(s)")
        print("     Warnings are optional features not configured.")
    else:
        print(f"  ❌ FAILED: {errors} error(s), {warnings} warning(s)")
        print("     Fix errors before going live.")
    print("="*60 + "\n")
    
    return errors == 0


if __name__ == '__main__':
    success = validate()
    sys.exit(0 if success else 1)
