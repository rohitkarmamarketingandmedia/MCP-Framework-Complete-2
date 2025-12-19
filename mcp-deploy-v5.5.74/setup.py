#!/usr/bin/env python3
"""
MCP Framework - First-time Setup Script
Creates initial admin user and data directories
"""
import os
import sys
import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.user import create_admin_user
from app.services.data_service import DataService


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                MCP Framework Setup                           ║
║              First-time Configuration                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Initialize data service
    data_dir = os.environ.get('DATA_DIR', './data')
    print(f"📁 Data directory: {data_dir}")
    
    data_service = DataService(data_dir)
    
    # Check for existing users
    existing_users = data_service.get_all_users()
    if existing_users:
        print(f"\n⚠️  Found {len(existing_users)} existing user(s).")
        response = input("Create another admin user? (y/N): ")
        if response.lower() != 'y':
            print("Setup complete. Exiting.")
            return
    
    # Create admin user
    print("\n👤 Create Admin User")
    print("-" * 40)
    
    email = input("Email: ").strip()
    if not email:
        print("❌ Email is required")
        return
    
    name = input("Name: ").strip()
    if not name:
        print("❌ Name is required")
        return
    
    password = getpass.getpass("Password: ")
    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        return
    
    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("❌ Passwords do not match")
        return
    
    # Create user
    user = create_admin_user(email, name, password)
    data_service.save_user(user)
    
    print(f"""
✅ Admin user created successfully!

   Email: {email}
   Name: {name}
   API Key: {user.api_key}

⚠️  Save the API key - it won't be shown again.
    """)
    
    # Check environment
    print("\n🔧 Environment Check")
    print("-" * 40)
    
    env_vars = [
        ('OPENAI_API_KEY', 'Required for content generation'),
        ('SECRET_KEY', 'Required for security'),
        ('SEMRUSH_API_KEY', 'Optional for SEO data'),
        ('WP_BASE_URL', 'Optional for WordPress'),
        ('GA4_PROPERTY_ID', 'Optional for analytics'),
    ]
    
    for var, description in env_vars:
        value = os.environ.get(var, '')
        status = "✅" if value else "⚠️ "
        masked = "***" if value else "Not set"
        print(f"   {status} {var}: {masked} - {description}")
    
    print(f"""
🚀 Setup Complete!

To start the server:
   python run.py

Or with Docker:
   docker-compose up -d

API will be available at:
   http://localhost:5000

Login with:
   POST /api/auth/login
   {{"email": "{email}", "password": "YOUR_PASSWORD"}}
    """)


if __name__ == "__main__":
    main()
