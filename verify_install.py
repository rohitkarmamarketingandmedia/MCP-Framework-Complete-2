#!/usr/bin/env python3
"""
MCP Framework - Installation Verification
Run this to check if everything is set up correctly
"""
import sys
import os

def check(name, condition, fix=""):
    if condition:
        print(f"  ✅ {name}")
        return True
    else:
        print(f"  ❌ {name}")
        if fix:
            print(f"     Fix: {fix}")
        return False

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║         MCP Framework - Installation Verification            ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    all_good = True
    
    # 1. Python version
    print("1. Python Environment")
    py_version = sys.version_info
    all_good &= check(
        f"Python {py_version.major}.{py_version.minor}.{py_version.micro}",
        py_version >= (3, 10),
        "Install Python 3.10 or higher"
    )
    
    # 2. Required packages
    print("\n2. Required Packages")
    packages = ['flask', 'flask_cors', 'jwt', 'requests']
    for pkg in packages:
        try:
            __import__(pkg)
            all_good &= check(f"{pkg} installed", True)
        except ImportError:
            all_good &= check(f"{pkg} installed", False, "pip install -r requirements.txt")
    
    # 3. App imports
    print("\n3. Application Modules")
    try:
        from app import create_app
        all_good &= check("Flask app factory", True)
    except Exception as e:
        all_good &= check("Flask app factory", False, str(e))
    
    try:
        from app.models import User, Client, BlogPost, Campaign
        all_good &= check("Data models", True)
    except Exception as e:
        all_good &= check("Data models", False, str(e))
    
    try:
        from app.services import AIService, DataService
        all_good &= check("Services", True)
    except Exception as e:
        all_good &= check("Services", False, str(e))
    
    # 4. Environment configuration
    print("\n4. Environment Configuration")
    
    env_file = os.path.exists('.env')
    all_good &= check(".env file exists", env_file, "cp .env.example .env")
    
    if env_file:
        from dotenv import load_dotenv
        load_dotenv()
    
    secret_key = os.environ.get('SECRET_KEY', '')
    all_good &= check(
        "SECRET_KEY configured",
        secret_key and secret_key != 'your-secret-key-change-in-production',
        "Set SECRET_KEY in .env"
    )
    
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    all_good &= check(
        "OPENAI_API_KEY configured",
        openai_key and openai_key.startswith('sk-'),
        "Set OPENAI_API_KEY in .env"
    )
    
    # 5. Data directories
    print("\n5. Data Storage")
    data_dir = os.environ.get('DATA_DIR', './data')
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        print(f"  📁 Created {data_dir}")
    
    subdirs = ['users', 'clients', 'content', 'social', 'schemas', 'campaigns']
    for subdir in subdirs:
        path = os.path.join(data_dir, subdir)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
    
    all_good &= check("Data directories exist", True)
    
    # 6. Check for admin user
    print("\n6. Admin User")
    try:
        from app.services.data_service import DataService
        ds = DataService()
        users = ds.get_all_users()
        admin_exists = any(u.role.value == 'admin' for u in users)
        all_good &= check(
            "Admin user exists",
            admin_exists,
            "Run: python setup_admin.py"
        )
    except Exception as e:
        all_good &= check("Admin user check", False, str(e))
    
    # Summary
    print("\n" + "="*60)
    if all_good:
        print("""
✅ ALL CHECKS PASSED!

You're ready to go. Start the server with:
  python run.py

Then test with:
  curl http://localhost:5000/health
        """)
    else:
        print("""
❌ SOME CHECKS FAILED

Please fix the issues above before running the server.
See DEPLOYMENT.md for detailed instructions.
        """)
        sys.exit(1)


if __name__ == '__main__':
    main()
