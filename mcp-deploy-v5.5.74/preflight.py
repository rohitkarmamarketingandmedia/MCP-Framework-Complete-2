#!/usr/bin/env python3
"""
MCP Framework - Pre-Flight Checklist
Run this BEFORE deploying to verify everything works.

Usage:
    python preflight.py
"""
import os
import sys
import time
import shutil
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def green(text): return f"\033[92m  ✓ {text}\033[0m"
def red(text): return f"\033[91m  ✗ {text}\033[0m"
def yellow(text): return f"\033[93m  ⚠ {text}\033[0m"
def header(text): return f"\033[94m\n▶ {text}\033[0m"

class PreflightChecker:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []
        
    def check(self, name, condition, error_msg=""):
        if condition:
            print(green(name))
            self.passed += 1
            return True
        else:
            msg = f"{name}: {error_msg}" if error_msg else name
            print(red(msg))
            self.failed += 1
            self.failures.append(name)
            return False
    
    def run_all(self):
        start = time.time()
        
        print("\n" + "╔" + "═"*62 + "╗")
        print("║         MCP Framework - Pre-Flight Checklist                 ║")
        print("║                                                              ║")
        print("║  This verifies everything works before deployment.           ║")
        print("╚" + "═"*62 + "╝")
        
        # Phase 1: Environment
        print(header("PHASE 1: Environment"))
        self.check_environment()
        
        # Phase 2: Imports
        print(header("PHASE 2: Module Imports"))
        if not self.check_imports():
            print(red("Cannot continue without imports working"))
            return self.summary(start)
        
        # Phase 3: Database
        print(header("PHASE 3: Database Operations"))
        self.check_database()
        
        # Phase 4: API
        print(header("PHASE 4: API Server"))
        self.check_api()
        
        # Phase 5: Render Config
        print(header("PHASE 5: Render Configuration"))
        self.check_render_config()
        
        return self.summary(start)
    
    def check_environment(self):
        # Python version
        py_version = sys.version_info
        self.check(
            f"Python {py_version.major}.{py_version.minor}+",
            py_version >= (3, 10),
            f"Got {py_version.major}.{py_version.minor}"
        )
        
        # Dependencies
        try:
            import flask
            import sqlalchemy
            import openai
            self.check("Dependencies installed", True)
        except ImportError as e:
            self.check("Dependencies installed", False, str(e))
        
        # .env file
        has_env = os.path.exists('.env') or os.environ.get('OPENAI_API_KEY')
        self.check(".env file or env vars", has_env)
    
    def check_imports(self):
        try:
            from app.database import db, init_db
            self.check("Database module", True)
        except Exception as e:
            self.check("Database module", False, str(e))
            return False
        
        try:
            from app.models import db_models
            self.check("Models module", True)
        except Exception as e:
            self.check("Models module", False, str(e))
            return False
        
        try:
            from app import services
            self.check("Services module", True)
        except Exception as e:
            self.check("Services module", False, str(e))
        
        try:
            from app import routes
            self.check("Routes module", True)
        except Exception as e:
            self.check("Routes module", False, str(e))
        
        try:
            from app import create_app
            self.check("App factory", True)
            return True
        except Exception as e:
            self.check("App factory", False, str(e))
            return False
    
    def check_database(self):
        """Test database operations with a fresh temporary database"""
        from app import create_app
        from app.database import db
        from app.models.db_models import DBClient, DBUser, DBContent
        
        # Use a temporary database to avoid conflicts
        temp_db = tempfile.mktemp(suffix='.db')
        os.environ['DATABASE_URL'] = f'sqlite:///{temp_db}'
        
        try:
            app = create_app('testing')
            
            with app.app_context():
                # Drop all and recreate to ensure clean schema
                db.drop_all()
                db.create_all()
                self.check("Create tables", True)
                
                # Test User CRUD
                try:
                    user = DBUser(email='test@test.com', role='admin')
                    user.set_password('test123')
                    db.session.add(user)
                    db.session.commit()
                    
                    found = DBUser.query.filter_by(email='test@test.com').first()
                    self.check("User CRUD", found is not None and found.verify_password('test123'))
                except Exception as e:
                    self.check("User CRUD", False, str(e))
                
                # Test Client CRUD - this is where the column error would show
                try:
                    client = DBClient(
                        business_name='Test Company',
                        industry='hvac',
                        geo='Miami, FL'
                    )
                    db.session.add(client)
                    db.session.commit()
                    
                    found = DBClient.query.filter_by(id=client.id).first()
                    # Verify we can access the social media columns
                    _ = found.facebook_page_id  # This would fail if column missing
                    _ = found.instagram_account_id
                    _ = found.linkedin_org_id
                    self.check("Client CRUD", found is not None)
                except Exception as e:
                    self.check("Client CRUD", False, str(e))
                
                # Test Content CRUD
                try:
                    content = DBContent(
                        client_id=client.id,
                        content_type='blog',
                        title='Test Post',
                        body='Test body content'
                    )
                    db.session.add(content)
                    db.session.commit()
                    
                    found = DBContent.query.filter_by(id=content.id).first()
                    self.check("Content CRUD", found is not None)
                except Exception as e:
                    self.check("Content CRUD", False, str(e))
        finally:
            # Cleanup temp database
            if os.path.exists(temp_db):
                os.remove(temp_db)
            # Reset DATABASE_URL
            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']
    
    def check_api(self):
        """Test API endpoints"""
        import threading
        import requests
        from app import create_app
        from app.database import db
        from app.models.db_models import DBUser
        
        # Use temp database
        temp_db = tempfile.mktemp(suffix='.db')
        os.environ['DATABASE_URL'] = f'sqlite:///{temp_db}'
        
        try:
            app = create_app('testing')
            
            with app.app_context():
                db.drop_all()
                db.create_all()
                
                # Create test admin user
                admin = DBUser(email='admin@test.com', role='admin')
                admin.set_password('testpass123')
                db.session.add(admin)
                db.session.commit()
            
            # Start server in thread
            port = 5099
            server = None
            
            def run_server():
                app.run(port=port, debug=False, use_reloader=False)
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            time.sleep(2)  # Wait for server to start
            
            self.check("Start server", True)
            
            base_url = f'http://127.0.0.1:{port}'
            
            # Test health endpoint
            try:
                r = requests.get(f'{base_url}/health', timeout=5)
                self.check("GET /health", r.status_code == 200)
            except Exception as e:
                self.check("GET /health", False, str(e))
            
            # Test API root
            try:
                r = requests.get(f'{base_url}/api', timeout=5)
                self.check("GET /api", r.status_code == 200)
            except Exception as e:
                self.check("GET /api", False, str(e))
            
            # Test dashboard
            try:
                r = requests.get(f'{base_url}/', timeout=5)
                self.check("GET / (dashboard)", r.status_code == 200)
            except Exception as e:
                self.check("GET / (dashboard)", False, str(e))
            
            # Test auth flow
            try:
                # Login
                r = requests.post(f'{base_url}/api/auth/login', json={
                    'email': 'admin@test.com',
                    'password': 'testpass123'
                }, timeout=5)
                
                if r.status_code == 200:
                    token = r.json().get('token')
                    headers = {'Authorization': f'Bearer {token}'}
                    
                    # Get /me
                    r2 = requests.get(f'{base_url}/api/auth/me', headers=headers, timeout=5)
                    self.check("Auth flow (login → /me)", r2.status_code == 200)
                else:
                    self.check("Auth flow (login → /me)", False, f"Login failed: {r.status_code}")
            except Exception as e:
                self.check("Auth flow (login → /me)", False, str(e))
            
            # Test clients endpoint (requires auth)
            try:
                r = requests.get(f'{base_url}/api/clients/', headers=headers, timeout=5)
                self.check("GET /api/clients/", r.status_code == 200, f"Status code: {r.status_code}")
            except Exception as e:
                self.check("GET /api/clients/", False, str(e))
            
            # Test create client
            try:
                r = requests.post(f'{base_url}/api/clients/', headers=headers, json={
                    'business_name': 'Test Business',
                    'industry': 'hvac',
                    'geo': 'Miami, FL'
                }, timeout=5)
                self.check("POST /api/clients/ (create)", r.status_code in [200, 201], 
                          f"Status code: {r.status_code} - {r.text[:100] if r.text else ''}")
            except Exception as e:
                self.check("POST /api/clients/ (create)", False, str(e))
            
            # Test intake
            try:
                r = requests.post(f'{base_url}/api/intake/analyze', json={
                    'business_info': {
                        'business_name': 'Test HVAC',
                        'industry': 'hvac',
                        'location': 'Tampa, FL'
                    }
                }, timeout=10)
                self.check("POST /api/intake/analyze", r.status_code == 200)
            except Exception as e:
                self.check("POST /api/intake/analyze", False, str(e))
                
        finally:
            # Cleanup
            if os.path.exists(temp_db):
                os.remove(temp_db)
            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']
    
    def check_render_config(self):
        self.check("render.yaml exists", os.path.exists('render.yaml'))
        self.check("build.sh exists", os.path.exists('build.sh'))
        
        # Check postgres URL conversion
        try:
            from app.config import Config
            os.environ['DATABASE_URL'] = 'postgres://user:pass@host/db'
            config = Config()
            converted = config.SQLALCHEMY_DATABASE_URI
            self.check("postgres:// URL conversion", 'postgresql://' in converted)
            del os.environ['DATABASE_URL']
        except Exception as e:
            self.check("postgres:// URL conversion", False, str(e))
    
    def summary(self, start_time):
        elapsed = time.time() - start_time
        
        print("\n" + "╔" + "═"*62 + "╗")
        print("║                        RESULTS                               ║")
        print("╠" + "═"*62 + "╣")
        print(f"║  {self.passed}/{self.passed + self.failed} checks passed".ljust(63) + "║")
        print(f"║  {self.failed} checks failed".ljust(63) + "║")
        
        if self.failures:
            print("║                                                              ║")
            print("║  Failed checks:                                              ║")
            for f in self.failures:
                print(f"║    • {f[:50]}".ljust(63) + "║")
        
        print("║                                                              ║")
        print(f"║  Time: {int(elapsed)} seconds".ljust(63) + "║")
        print("╚" + "═"*62 + "╝")
        
        if self.failed > 0:
            print("\n\033[91m⚠ FIX ISSUES BEFORE DEPLOYING\033[0m")
            print("\n  Review the failed checks above and fix them.")
            print("  Then run this script again.\n")
            return False
        else:
            print("\n\033[92m✓ ALL CHECKS PASSED - READY TO DEPLOY\033[0m")
            print("\n  Run: git add . && git commit -m 'Deploy' && git push\n")
            return True


if __name__ == '__main__':
    checker = PreflightChecker()
    success = checker.run_all()
    sys.exit(0 if success else 1)
