#!/usr/bin/env python3
"""
MCP Framework - Complete Test Suite
Run this to verify the installation is working correctly
"""
import os
import sys

# Set test environment
os.environ['DATABASE_URL'] = 'sqlite:///test_suite.db'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
os.environ['OPENAI_API_KEY'] = 'sk-test-key'

def green(text): return f"\033[92m{text}\033[0m"
def red(text): return f"\033[91m{text}\033[0m"
def yellow(text): return f"\033[93m{text}\033[0m"

def test(name, func):
    try:
        func()
        print(f"  {green('✓')} {name}")
        return True
    except Exception as e:
        print(f"  {red('✗')} {name}: {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("  MCP Framework - Complete Test Suite")
    print("=" * 60 + "\n")
    
    results = []
    
    # 1. Imports
    print("1. Testing imports...")
    results.append(test("database module", lambda: __import__('app.database')))
    results.append(test("db_models module", lambda: __import__('app.models.db_models')))
    results.append(test("db_service module", lambda: __import__('app.services.db_service')))
    results.append(test("all route modules", lambda: [
        __import__('app.routes.auth'),
        __import__('app.routes.clients'),
        __import__('app.routes.content'),
        __import__('app.routes.social'),
        __import__('app.routes.campaigns'),
        __import__('app.routes.schema'),
        __import__('app.routes.publish'),
        __import__('app.routes.analytics'),
        __import__('app.routes.intake'),
    ]))
    
    # 2. App Creation
    print("\n2. Testing app creation...")
    from app import create_app
    from app.database import db
    app = create_app('testing')
    results.append(test("create_app()", lambda: app is not None))
    
    # 3. Database Operations
    print("\n3. Testing database operations...")
    from app.models.db_models import DBUser, DBClient, DBBlogPost, DBSocialPost, DBCampaign, DBSchemaMarkup, UserRole
    from app.services.db_service import DataService
    
    with app.app_context():
        db.create_all()
        ds = DataService()
        
        # User CRUD
        def test_user():
            u = DBUser(email='crud@test.com', name='CRUD Test', password='test1234', role=UserRole.ADMIN)
            ds.save_user(u)
            assert ds.get_user_by_email('crud@test.com') is not None
            ds.delete_user(u.id)
        results.append(test("User CRUD", test_user))
        
        # Client CRUD
        def test_client():
            c = DBClient(business_name='CRUD Client', industry='test', geo='Test, TS')
            ds.save_client(c)
            assert ds.get_client(c.id) is not None
            ds.delete_client(c.id)
        results.append(test("Client CRUD", test_client))
        
        # BlogPost CRUD
        def test_blog():
            c = DBClient(business_name='Blog Test', industry='test', geo='Test, TS')
            ds.save_client(c)
            p = DBBlogPost(client_id=c.id, title='Test Post', body='Content')
            ds.save_blog_post(p)
            assert ds.get_blog_post(p.id) is not None
            ds.delete_blog_post(p.id)
        results.append(test("BlogPost CRUD", test_blog))
        
        # SocialPost CRUD
        def test_social():
            c = DBClient(business_name='Social Test', industry='test', geo='Test, TS')
            ds.save_client(c)
            p = DBSocialPost(client_id=c.id, platform='facebook', content='Test')
            ds.save_social_post(p)
            assert ds.get_social_post(p.id) is not None
            ds.delete_social_post(p.id)
        results.append(test("SocialPost CRUD", test_social))
        
        # Campaign CRUD
        def test_campaign():
            c = DBClient(business_name='Campaign Test', industry='test', geo='Test, TS')
            ds.save_client(c)
            camp = DBCampaign(client_id=c.id, name='Test Campaign')
            ds.save_campaign(camp)
            assert ds.get_campaign(camp.id) is not None
            ds.delete_campaign(camp.id)
        results.append(test("Campaign CRUD", test_campaign))
        
        # Schema CRUD
        def test_schema():
            c = DBClient(business_name='Schema Test', industry='test', geo='Test, TS')
            ds.save_client(c)
            s = DBSchemaMarkup(client_id=c.id, schema_type='FAQ', json_ld={'@type': 'FAQ'})
            ds.save_schema(s)
            assert ds.get_schema(s.id) is not None
            ds.delete_schema(s.id)
        results.append(test("Schema CRUD", test_schema))
    
    # 4. API Endpoints
    print("\n4. Testing API endpoints...")
    with app.app_context():
        db.create_all()
        ds = DataService()
        
        # Create test user
        test_user = DBUser(email='api@test.com', name='API Test', password='apitest123', role=UserRole.ADMIN)
        ds.save_user(test_user)
    
    with app.test_client() as c:
        results.append(test("GET /health", lambda: c.get('/health').status_code == 200))
        results.append(test("GET /api", lambda: c.get('/api').status_code == 200))
        results.append(test("GET / (dashboard)", lambda: c.get('/').status_code == 200))
        
        # Auth
        results.append(test("POST /api/auth/login (invalid)", lambda: c.post('/api/auth/login', json={'email': 'wrong', 'password': 'wrong'}).status_code == 401))
        
        r = c.post('/api/auth/login', json={'email': 'api@test.com', 'password': 'apitest123'})
        results.append(test("POST /api/auth/login (valid)", lambda: r.status_code == 200))
        
        token = r.json.get('token', '')
        headers = {'Authorization': f'Bearer {token}'}
        
        results.append(test("GET /api/auth/me", lambda: c.get('/api/auth/me', headers=headers).status_code == 200))
        results.append(test("GET /api/clients/", lambda: c.get('/api/clients/', headers=headers).status_code == 200))
    
    # 5. Config
    print("\n5. Testing configuration...")
    from app.config import ProductionConfig
    
    def test_postgres_conversion():
        os.environ['DATABASE_URL'] = 'postgres://u:p@h:5432/d'
        config = ProductionConfig()
        db_uri = config.SQLALCHEMY_DATABASE_URI
        assert 'postgresql+psycopg://' in db_uri, f"Expected postgresql+psycopg://, got: {db_uri}"
    results.append(test("postgres:// → postgresql+psycopg:// conversion", test_postgres_conversion))
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(green(f"  ALL {total} TESTS PASSED! ✓"))
    else:
        print(yellow(f"  {passed}/{total} tests passed"))
        print(red(f"  {total - passed} tests failed"))
    
    print("=" * 60 + "\n")
    
    # Cleanup
    try:
        os.remove('test_suite.db')
    except:
        pass
    
    return 0 if passed == total else 1

if __name__ == '__main__':
    sys.exit(main())
