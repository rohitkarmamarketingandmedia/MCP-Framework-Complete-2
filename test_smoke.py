#!/usr/bin/env python3
"""
MCP Framework - Smoke Test
Verifies the full flow works end-to-end

Run: python test_smoke.py
"""
import sys
import os
import json

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
NC = '\033[0m'

def test(name, condition):
    if condition:
        print(f"  {GREEN}✓{NC} {name}")
        return True
    else:
        print(f"  {RED}✗{NC} {name}")
        return False

def main():
    print(f"""
{BLUE}╔══════════════════════════════════════════════════════════════╗
║              MCP Framework - Smoke Test                      ║
╚══════════════════════════════════════════════════════════════╝{NC}
    """)
    
    all_passed = True
    
    # ============================================
    # Test 1: Imports
    # ============================================
    print(f"{YELLOW}1. Testing imports...{NC}")
    
    try:
        from app import create_app
        all_passed &= test("Flask app factory", True)
    except Exception as e:
        all_passed &= test(f"Flask app factory: {e}", False)
    
    try:
        from app.models import User, Client, BlogPost, Campaign
        all_passed &= test("Data models", True)
    except Exception as e:
        all_passed &= test(f"Data models: {e}", False)
    
    try:
        from app.services import AIService, DataService, SEOService
        all_passed &= test("Services", True)
    except Exception as e:
        all_passed &= test(f"Services: {e}", False)
    
    # ============================================
    # Test 2: App Creation
    # ============================================
    print(f"\n{YELLOW}2. Testing app creation...{NC}")
    
    try:
        app = create_app('testing')
        all_passed &= test("Create Flask app", True)
    except Exception as e:
        all_passed &= test(f"Create Flask app: {e}", False)
        print(f"\n{RED}Cannot continue without app. Exiting.{NC}")
        sys.exit(1)
    
    # ============================================
    # Test 3: Data Service
    # ============================================
    print(f"\n{YELLOW}3. Testing data service...{NC}")
    
    try:
        from app.services.data_service import DataService
        from app.models.user import create_admin_user
        from app.models.client import Client
        
        ds = DataService()
        all_passed &= test("DataService initializes", True)
        
        # Create test user
        test_user = create_admin_user(
            email='smoke_test@test.com',
            name='Smoke Test',
            password='test123456'
        )
        ds.save_user(test_user)
        all_passed &= test("Create user", True)
        
        # Retrieve user
        retrieved = ds.get_user(test_user.id)
        all_passed &= test("Retrieve user", retrieved is not None)
        
        # Create test client
        test_client = Client(
            id="",
            business_name="Test Roofing Co",
            industry="roofing",
            geo="Sarasota, FL",
            primary_keywords=["roof repair sarasota"],
            service_areas=["Sarasota", "Bradenton"]
        )
        ds.save_client(test_client)
        all_passed &= test("Create client", True)
        
        # Retrieve client
        retrieved_client = ds.get_client(test_client.id)
        all_passed &= test("Retrieve client", retrieved_client is not None)
        
        # Cleanup
        ds.delete_user(test_user.id)
        ds.delete_client(test_client.id)
        all_passed &= test("Cleanup test data", True)
        
    except Exception as e:
        all_passed &= test(f"Data service: {e}", False)
    
    # ============================================
    # Test 4: API Routes
    # ============================================
    print(f"\n{YELLOW}4. Testing API routes...{NC}")
    
    try:
        with app.test_client() as client:
            # Health check
            resp = client.get('/health')
            all_passed &= test("GET /health", resp.status_code == 200)
            
            # API info
            resp = client.get('/api')
            all_passed &= test("GET /api", resp.status_code == 200)
            
            # Dashboard
            resp = client.get('/')
            all_passed &= test("GET / (dashboard)", resp.status_code == 200)
            
            # Auth endpoint exists
            resp = client.post('/api/auth/login', 
                json={'email': 'fake', 'password': 'fake'})
            all_passed &= test("POST /api/auth/login (endpoint exists)", 
                resp.status_code in [400, 401])
            
    except Exception as e:
        all_passed &= test(f"API routes: {e}", False)
    
    # ============================================
    # Test 5: AI Service (mock)
    # ============================================
    print(f"\n{YELLOW}5. Testing AI service (structure only)...{NC}")
    
    try:
        from app.services.ai_service import AIService
        ai = AIService()
        all_passed &= test("AIService initializes", True)
        all_passed &= test("Has generate_blog_post method", 
            hasattr(ai, 'generate_blog_post'))
        all_passed &= test("Has generate_social_post method", 
            hasattr(ai, 'generate_social_post'))
    except Exception as e:
        all_passed &= test(f"AI service: {e}", False)
    
    # ============================================
    # Test 6: Environment
    # ============================================
    print(f"\n{YELLOW}6. Checking environment...{NC}")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    secret_key = os.environ.get('SECRET_KEY', '')
    all_passed &= test("SECRET_KEY configured", 
        secret_key and secret_key != 'your-secret-key-change-in-production')
    
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    has_openai = openai_key and openai_key.startswith('sk-') and openai_key != 'sk-your-openai-key'
    if has_openai:
        all_passed &= test("OPENAI_API_KEY configured", True)
    else:
        print(f"  {YELLOW}⚠{NC} OPENAI_API_KEY not configured (content generation won't work)")
    
    # ============================================
    # Summary
    # ============================================
    print(f"\n{'='*60}")
    
    if all_passed:
        print(f"""
{GREEN}╔══════════════════════════════════════════════════════════════╗
║                    ALL TESTS PASSED! ✓                       ║
╚══════════════════════════════════════════════════════════════╝{NC}

  Your MCP Framework is ready to use.
  
  Start the server with:  {BLUE}bash start.sh{NC}
  
  Then open: {BLUE}http://localhost:5000{NC}
        """)
    else:
        print(f"""
{RED}╔══════════════════════════════════════════════════════════════╗
║                    SOME TESTS FAILED ✗                       ║
╚══════════════════════════════════════════════════════════════╝{NC}

  Please fix the issues above before running.
  
  Need help? Check DEPLOYMENT.md
        """)
        sys.exit(1)


if __name__ == '__main__':
    main()
