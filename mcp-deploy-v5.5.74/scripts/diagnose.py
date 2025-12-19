#!/usr/bin/env python3
"""
MCP Framework Diagnostic Script
Run this to see what's working and what's broken
"""
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check(name, condition, fix=""):
    if condition:
        print(f"✅ {name}")
        return True
    else:
        print(f"❌ {name}")
        if fix:
            print(f"   FIX: {fix}")
        return False

def main():
    print("\n" + "="*60)
    print("  MCP FRAMEWORK DIAGNOSTIC")
    print("="*60 + "\n")
    
    all_good = True
    
    # ========================================
    # CRITICAL - Won't work without these
    # ========================================
    print("🔴 CRITICAL (System won't work without these):\n")
    
    # Database
    db_url = os.environ.get('DATABASE_URL', '')
    if not check("DATABASE_URL set", db_url, "Set DATABASE_URL in Render environment"):
        all_good = False
    elif 'postgres' in db_url:
        print(f"   └─ Using PostgreSQL ✓")
    
    # Secret keys
    secret = os.environ.get('SECRET_KEY', '')
    if not check("SECRET_KEY set", secret and secret != 'dev-secret-key-change-in-production', 
                 "Set SECRET_KEY to a random 64-char string"):
        all_good = False
    
    jwt_secret = os.environ.get('JWT_SECRET_KEY', '')
    if not check("JWT_SECRET_KEY set", jwt_secret, 
                 "Set JWT_SECRET_KEY to a random 64-char string"):
        all_good = False
    
    # Admin user
    admin_email = os.environ.get('ADMIN_EMAIL', '')
    admin_pass = os.environ.get('ADMIN_PASSWORD', '')
    if not check("ADMIN_EMAIL set", admin_email, "Set ADMIN_EMAIL for login"):
        all_good = False
    if not check("ADMIN_PASSWORD set", admin_pass, "Set ADMIN_PASSWORD for login"):
        all_good = False
    
    # ========================================
    # HIGH - Content generation won't work
    # ========================================
    print("\n🟠 HIGH PRIORITY (Content generation needs these):\n")
    
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not check("OPENAI_API_KEY set", openai_key, 
                 "Set OPENAI_API_KEY - get from platform.openai.com"):
        all_good = False
    elif openai_key.startswith('sk-'):
        print(f"   └─ Key format looks valid ✓")
    else:
        print(f"   └─ ⚠️  Key should start with 'sk-'")
    
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
    check("ANTHROPIC_API_KEY set (backup)", anthropic_key, 
          "(Optional) Set for fallback AI")
    
    # ========================================
    # MEDIUM - Features won't work
    # ========================================
    print("\n🟡 MEDIUM (Specific features need these):\n")
    
    semrush_key = os.environ.get('SEMRUSH_API_KEY', '')
    check("SEMRUSH_API_KEY set", semrush_key, 
          "(Optional) For keyword research - uses mock data without")
    
    sendgrid_key = os.environ.get('SENDGRID_API_KEY', '')
    check("SENDGRID_API_KEY set", sendgrid_key, 
          "(Optional) For email notifications")
    
    # WordPress
    wp_url = os.environ.get('WP_BASE_URL', '')
    wp_user = os.environ.get('WP_USERNAME', '')
    wp_pass = os.environ.get('WP_APP_PASSWORD', '')
    check("WordPress configured", wp_url and wp_user and wp_pass, 
          "(Optional) For auto-publishing: WP_BASE_URL, WP_USERNAME, WP_APP_PASSWORD")
    
    # ========================================
    # Test Database Connection
    # ========================================
    print("\n📊 DATABASE CONNECTION:\n")
    
    try:
        from app import create_app
        from app.extensions import db
        app = create_app()
        with app.app_context():
            # Try a simple query
            result = db.session.execute(db.text('SELECT 1')).fetchone()
            check("Database connection", result[0] == 1)
            
            # Check tables exist
            from app.models.db_models import DBClient, User
            user_count = User.query.count()
            client_count = DBClient.query.count()
            print(f"   └─ Users in database: {user_count}")
            print(f"   └─ Clients in database: {client_count}")
            
            if user_count == 0:
                print(f"   ⚠️  No admin user! Run: python scripts/create_admin.py")
                all_good = False
                
    except Exception as e:
        check("Database connection", False, f"Error: {e}")
        all_good = False
    
    # ========================================
    # Test AI Service
    # ========================================
    print("\n🤖 AI SERVICE:\n")
    
    try:
        from app.services.ai_service import AIService
        ai = AIService()
        
        check("AI Service initialized", True)
        
        if ai.openai_key:
            print("   └─ OpenAI key loaded ✓")
            # Try a simple completion
            try:
                import requests
                response = requests.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {ai.openai_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4o-mini',
                        'messages': [{'role': 'user', 'content': 'Say "test ok"'}],
                        'max_tokens': 10
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    print("   └─ OpenAI API working ✓")
                else:
                    error = response.json().get('error', {}).get('message', response.text[:100])
                    print(f"   └─ ❌ OpenAI API error: {error}")
                    all_good = False
            except Exception as e:
                print(f"   └─ ❌ OpenAI API test failed: {e}")
                all_good = False
        else:
            print("   └─ ❌ OpenAI key NOT loaded - content generation will fail!")
            all_good = False
            
    except Exception as e:
        check("AI Service", False, f"Error: {e}")
        all_good = False
    
    # ========================================
    # Test Routes
    # ========================================
    print("\n🌐 API ROUTES:\n")
    
    try:
        from app import create_app
        app = create_app()
        routes = [r.rule for r in app.url_map.iter_rules()]
        
        critical_routes = [
            '/api/auth/login',
            '/api/intake/pipeline',
            '/api/clients/',
            '/api/content/blog/generate',
            '/health'
        ]
        
        for route in critical_routes:
            exists = any(route in r for r in routes)
            check(f"Route {route}", exists)
            
        print(f"\n   Total routes: {len(routes)}")
        
    except Exception as e:
        print(f"   ❌ Error checking routes: {e}")
        all_good = False
    
    # ========================================
    # Summary
    # ========================================
    print("\n" + "="*60)
    if all_good:
        print("  ✅ ALL CHECKS PASSED - System should work!")
    else:
        print("  ❌ ISSUES FOUND - Fix the items above")
    print("="*60 + "\n")
    
    return 0 if all_good else 1

if __name__ == '__main__':
    sys.exit(main())
