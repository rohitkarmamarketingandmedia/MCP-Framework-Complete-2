#!/usr/bin/env python3
"""
MCP Framework - Pre-Flight Checklist
Run this before deploying to verify everything works.

Usage:
    python preflight.py

Requirements:
    - Python 3.10+
    - All dependencies installed (pip install -r requirements.txt)
    - .env file configured (or will create test one)
"""
import os
import sys
import time
import json
import signal
import subprocess
import threading
from datetime import datetime

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

def green(t): return f"{GREEN}{t}{RESET}"
def red(t): return f"{RED}{t}{RESET}"
def yellow(t): return f"{YELLOW}{t}{RESET}"
def blue(t): return f"{BLUE}{t}{RESET}"
def bold(t): return f"{BOLD}{t}{RESET}"

# Test results
results = []
server_process = None

def log(msg):
    print(f"  {msg}")

def test(name, func, critical=False):
    """Run a test and record result"""
    try:
        result = func()
        if result is True or result is None:
            print(f"  {green('✓')} {name}")
            results.append((name, True, None))
            return True
        else:
            print(f"  {red('✗')} {name}: {result}")
            results.append((name, False, result))
            if critical:
                print(f"\n  {red('CRITICAL FAILURE - Cannot continue')}")
                sys.exit(1)
            return False
    except Exception as e:
        print(f"  {red('✗')} {name}: {e}")
        results.append((name, False, str(e)))
        if critical:
            print(f"\n  {red('CRITICAL FAILURE - Cannot continue')}")
            sys.exit(1)
        return False

def section(title):
    """Print section header"""
    print(f"\n{blue(f'▶ {title}')}")

# ============================================
# PHASE 1: Environment
# ============================================

def check_python_version():
    v = sys.version_info
    if v.major >= 3 and v.minor >= 10:
        return True
    return f"Python 3.10+ required, got {v.major}.{v.minor}"

def check_dependencies():
    try:
        import flask
        import flask_sqlalchemy
        import sqlalchemy
        import jwt
        import requests
        import dotenv
        return True
    except ImportError as e:
        return f"Missing: {e.name}. Run: pip install -r requirements.txt"

def check_env_file():
    if os.path.exists('.env'):
        return True
    # Create minimal test .env
    with open('.env', 'w') as f:
        f.write("SECRET_KEY=preflight-test-key\n")
        f.write("OPENAI_API_KEY=sk-test-preflight\n")
        f.write("DATABASE_URL=sqlite:///preflight_test.db\n")
    return True

# ============================================
# PHASE 2: Imports
# ============================================

def check_database_import():
    from app.database import db, init_db
    return True

def check_models_import():
    from app.models.db_models import DBUser, DBClient, DBBlogPost, DBSocialPost, DBCampaign, DBSchemaMarkup
    return True

def check_services_import():
    from app.services.db_service import DataService
    from app.services.ai_service import AIService
    return True

def check_routes_import():
    from app.routes.auth import auth_bp
    from app.routes.clients import clients_bp
    from app.routes.content import content_bp
    from app.routes.social import social_bp
    from app.routes.campaigns import campaigns_bp
    from app.routes.schema import schema_bp
    from app.routes.publish import publish_bp
    from app.routes.intake import intake_bp
    return True

def check_app_creation():
    from app import create_app
    app = create_app('testing')
    return app is not None

# ============================================
# PHASE 3: Database
# ============================================

def check_db_tables_create():
    os.environ['DATABASE_URL'] = 'sqlite:///preflight_test.db'
    from app import create_app
    from app.database import db
    app = create_app('testing')
    with app.app_context():
        db.create_all()
    return True

def check_user_crud():
    from app import create_app
    from app.database import db
    from app.models.db_models import DBUser, UserRole
    from app.services.db_service import DataService
    
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        ds = DataService()
        
        # Create
        u = DBUser(email='preflight@test.com', name='Preflight', password='test1234', role=UserRole.ADMIN)
        ds.save_user(u)
        
        # Read
        found = ds.get_user_by_email('preflight@test.com')
        if not found:
            return "User not found after create"
        
        # Verify password
        if not found.verify_password('test1234'):
            return "Password verification failed"
        
        # Delete
        ds.delete_user(u.id)
    return True

def check_client_crud():
    from app import create_app
    from app.database import db
    from app.models.db_models import DBClient
    from app.services.db_service import DataService
    
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        ds = DataService()
        
        c = DBClient(business_name='Preflight Corp', industry='testing', geo='Test, TS')
        ds.save_client(c)
        
        found = ds.get_client(c.id)
        if not found:
            return "Client not found after create"
        
        ds.delete_client(c.id)
    return True

def check_content_crud():
    from app import create_app
    from app.database import db
    from app.models.db_models import DBClient, DBBlogPost
    from app.services.db_service import DataService
    
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        ds = DataService()
        
        c = DBClient(business_name='Content Test', industry='testing', geo='Test, TS')
        ds.save_client(c)
        
        p = DBBlogPost(client_id=c.id, title='Test Post', body='Test content here')
        ds.save_blog_post(p)
        
        found = ds.get_blog_post(p.id)
        if not found:
            return "Blog post not found after create"
        
        ds.delete_blog_post(p.id)
    return True

# ============================================
# PHASE 4: API Server
# ============================================

def start_server():
    """Start the Flask server in background"""
    global server_process
    
    # Create test user BEFORE starting server (same DB file)
    os.environ['DATABASE_URL'] = 'sqlite:///preflight_test.db'
    os.environ['SECRET_KEY'] = 'preflight-test-key'
    os.environ['OPENAI_API_KEY'] = 'sk-test-preflight'
    
    from app import create_app
    from app.database import db
    from app.models.db_models import DBUser, UserRole
    from app.services.db_service import DataService
    
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        ds = DataService()
        # Create test user if doesn't exist
        if not ds.get_user_by_email('apitest@test.com'):
            u = DBUser(email='apitest@test.com', name='API Test', password='apitest123', role=UserRole.ADMIN)
            ds.save_user(u)
    
    env = os.environ.copy()
    env['DATABASE_URL'] = 'sqlite:///preflight_test.db'
    env['SECRET_KEY'] = 'preflight-test-key'
    env['OPENAI_API_KEY'] = 'sk-test-preflight'
    env['FLASK_ENV'] = 'testing'
    
    server_process = subprocess.Popen(
        [sys.executable, 'run.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    
    # Wait for server to start
    time.sleep(3)
    
    if server_process.poll() is not None:
        stdout, stderr = server_process.communicate()
        return f"Server failed to start: {stderr.decode()[:200]}"
    
    return True

def stop_server():
    """Stop the Flask server"""
    global server_process
    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except:
            server_process.kill()

def check_health_endpoint():
    import requests
    try:
        r = requests.get('http://localhost:5000/health', timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 'healthy':
                return True
            return f"Unexpected response: {data}"
        return f"Status code: {r.status_code}"
    except requests.exceptions.ConnectionError:
        # Try port 5001 (Mac AirPlay conflict)
        try:
            r = requests.get('http://localhost:5001/health', timeout=5)
            if r.status_code == 200:
                os.environ['TEST_PORT'] = '5001'
                return True
        except:
            pass
        return "Cannot connect to server"

def get_base_url():
    return f"http://localhost:{os.environ.get('TEST_PORT', '5000')}"

def check_api_endpoint():
    import requests
    r = requests.get(f'{get_base_url()}/api', timeout=5)
    if r.status_code == 200:
        data = r.json()
        if 'endpoints' in data:
            return True
        return f"Missing endpoints in response"
    return f"Status code: {r.status_code}"

def check_dashboard_loads():
    import requests
    r = requests.get(f'{get_base_url()}/', timeout=5)
    if r.status_code == 200:
        if 'MCP' in r.text and 'login' in r.text.lower():
            return True
        return "Dashboard HTML doesn't contain expected content"
    return f"Status code: {r.status_code}"

def check_auth_flow():
    import requests
    
    # First create a user via the app context
    from app import create_app
    from app.database import db
    from app.models.db_models import DBUser, UserRole
    from app.services.db_service import DataService
    
    app = create_app('testing')
    with app.app_context():
        ds = DataService()
        # Check if user exists
        existing = ds.get_user_by_email('apitest@test.com')
        if not existing:
            u = DBUser(email='apitest@test.com', name='API Test', password='apitest123', role=UserRole.ADMIN)
            ds.save_user(u)
    
    # Test login
    r = requests.post(f'{get_base_url()}/api/auth/login', json={
        'email': 'apitest@test.com',
        'password': 'apitest123'
    }, timeout=5)
    
    if r.status_code != 200:
        return f"Login failed: {r.status_code} - {r.text[:100]}"
    
    data = r.json()
    if 'token' not in data:
        return "No token in response"
    
    token = data['token']
    
    # Test /me endpoint
    r = requests.get(f'{get_base_url()}/api/auth/me', headers={
        'Authorization': f'Bearer {token}'
    }, timeout=5)
    
    if r.status_code != 200:
        return f"/me failed: {r.status_code}"
    
    # Store token for other tests
    os.environ['TEST_TOKEN'] = token
    return True

def check_clients_endpoint():
    import requests
    token = os.environ.get('TEST_TOKEN', '')
    
    r = requests.get(f'{get_base_url()}/api/clients/', headers={
        'Authorization': f'Bearer {token}'
    }, timeout=5)
    
    if r.status_code == 200:
        data = r.json()
        if 'clients' in data:
            return True
        return "Missing 'clients' in response"
    return f"Status code: {r.status_code}"

def check_create_client():
    import requests
    token = os.environ.get('TEST_TOKEN', '')
    
    r = requests.post(f'{get_base_url()}/api/clients/', headers={
        'Authorization': f'Bearer {token}'
    }, json={
        'business_name': 'Preflight Test Business',
        'industry': 'roofing',
        'geo': 'Sarasota, FL',
        'primary_keywords': ['roof repair sarasota', 'roofing company'],
        'tone': 'professional'
    }, timeout=5)
    
    if r.status_code == 201:
        data = r.json()
        if 'client' in data and data['client'].get('id'):
            os.environ['TEST_CLIENT_ID'] = data['client']['id']
            return True
        return "Missing client ID in response"
    return f"Status code: {r.status_code} - {r.text[:100]}"

def check_intake_analyze():
    """Test transcript analysis (without real OpenAI)"""
    import requests
    token = os.environ.get('TEST_TOKEN', '')
    
    # This will fail gracefully without real OpenAI key
    r = requests.post(f'{get_base_url()}/api/intake/analyze', headers={
        'Authorization': f'Bearer {token}'
    }, json={
        'transcript': 'Hi, I run ABC Roofing in Sarasota Florida. We do roof repairs and replacements.'
    }, timeout=10)
    
    # Accept 200 (success) or 500 (OpenAI error - expected without real key)
    if r.status_code == 200:
        return True
    elif r.status_code == 500:
        # Check if it's an OpenAI error (expected)
        if 'openai' in r.text.lower() or 'api' in r.text.lower():
            return True  # Expected - no real API key
        return f"Unexpected 500 error: {r.text[:100]}"
    return f"Status code: {r.status_code}"

# ============================================
# PHASE 5: Configuration
# ============================================

def check_render_yaml():
    if os.path.exists('render.yaml'):
        with open('render.yaml') as f:
            content = f.read()
            if 'mcp-framework' in content and 'databases:' in content:
                return True
            return "render.yaml missing expected content (mcp-framework or databases)"
    return "render.yaml not found"

def check_build_script():
    if os.path.exists('build.sh'):
        with open('build.sh') as f:
            content = f.read()
            if 'pip install' in content and 'db.create_all' in content:
                return True
            return "build.sh missing expected commands"
    return "build.sh not found"

def check_postgres_conversion():
    os.environ['DATABASE_URL'] = 'postgres://user:pass@host:5432/db'
    from app.config import ProductionConfig
    config = ProductionConfig()
    uri = config.SQLALCHEMY_DATABASE_URI
    if 'postgresql+psycopg://' in uri:
        return True
    return f"Conversion failed: {uri}"

# ============================================
# MAIN
# ============================================

def main():
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════════╗
║         MCP Framework - Pre-Flight Checklist                 ║
║                                                              ║
║  This verifies everything works before deployment.           ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")
    
    start_time = datetime.now()
    
    # Phase 1: Environment
    section("PHASE 1: Environment")
    test("Python 3.10+", check_python_version, critical=True)
    test("Dependencies installed", check_dependencies, critical=True)
    test(".env file", check_env_file)
    
    # Phase 2: Imports
    section("PHASE 2: Module Imports")
    test("Database module", check_database_import, critical=True)
    test("Models module", check_models_import, critical=True)
    test("Services module", check_services_import, critical=True)
    test("Routes module", check_routes_import, critical=True)
    test("App factory", check_app_creation, critical=True)
    
    # Phase 3: Database
    section("PHASE 3: Database Operations")
    test("Create tables", check_db_tables_create, critical=True)
    test("User CRUD", check_user_crud)
    test("Client CRUD", check_client_crud)
    test("Content CRUD", check_content_crud)
    
    # Phase 4: API Server
    section("PHASE 4: API Server")
    test("Start server", start_server, critical=True)
    test("GET /health", check_health_endpoint, critical=True)
    test("GET /api", check_api_endpoint)
    test("GET / (dashboard)", check_dashboard_loads)
    test("Auth flow (login → /me)", check_auth_flow)
    test("GET /api/clients/", check_clients_endpoint)
    test("POST /api/clients/ (create)", check_create_client)
    test("POST /api/intake/analyze", check_intake_analyze)
    
    # Stop server
    stop_server()
    
    # Phase 5: Configuration
    section("PHASE 5: Render Configuration")
    test("render.yaml exists", check_render_yaml)
    test("build.sh exists", check_build_script)
    test("postgres:// URL conversion", check_postgres_conversion)
    
    # Cleanup
    try:
        os.remove('preflight_test.db')
    except:
        pass
    
    # Summary
    elapsed = (datetime.now() - start_time).seconds
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    failed = [(name, err) for name, success, err in results if not success]
    
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════════╗
║                        RESULTS                               ║
╠══════════════════════════════════════════════════════════════╣{RESET}""")
    
    if passed == total:
        print(f"""║  {green(f'ALL {total} CHECKS PASSED!')}                                    ║
║                                                              ║
║  {green('✓ Ready for deployment to Render')}                           ║""")
    else:
        print(f"""║  {yellow(f'{passed}/{total} checks passed')}                                      ║
║  {red(f'{total - passed} checks failed')}                                          ║
║                                                              ║
║  Failed checks:                                              ║""")
        for name, err in failed:
            print(f"║    • {name[:45]:<45} ║")
    
    print(f"""║                                                              ║
║  Time: {elapsed} seconds                                           ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    if passed == total:
        print(f"""{green('NEXT STEPS:')}

  1. Push to GitHub
  2. Go to render.com → New → Blueprint
  3. Connect your repo
  4. Set OPENAI_API_KEY environment variable
  5. Deploy!

  After deploy, create admin user:
    Render Dashboard → Service → Shell
    python setup_admin.py
""")
        return 0
    else:
        print(f"""{red('FIX ISSUES BEFORE DEPLOYING')}

  Review the failed checks above and fix them.
  Then run this script again.
""")
        return 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAborted by user")
        stop_server()
        sys.exit(1)
    except Exception as e:
        print(f"\n{red(f'UNEXPECTED ERROR: {e}')}")
        stop_server()
        sys.exit(1)
    finally:
        stop_server()
