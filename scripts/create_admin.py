#!/usr/bin/env python3
"""
Karma Marketing + Media - Create Admin User
Run this script to create the first admin user for production.

Usage:
    python scripts/create_admin.py

Or with environment variables:
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=securepass123 python scripts/create_admin.py
"""
import os
import sys
import secrets
import string

# Add parent directory to path so we can import the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db
from app.models.db_models import DBUser


def generate_password(length=16):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def create_admin_user():
    """Create the admin user"""
    app = create_app()
    
    with app.app_context():
        # Check if admin already exists
        existing = DBUser.query.filter_by(role='admin').first()
        if existing:
            print(f"\n⚠ Admin user already exists: {existing.email}")
            response = input("Create another admin? (y/N): ")
            if response.lower() != 'y':
                print("Aborted.")
                return
        
        # Get credentials from env or prompt
        email = os.environ.get('ADMIN_EMAIL')
        password = os.environ.get('ADMIN_PASSWORD')
        
        if not email:
            print("\n" + "="*50)
            print("  KARMA MARKETING + MEDIA")
            print("  Admin User Setup")
            print("="*50 + "\n")
            email = input("Admin email: ").strip()
        
        if not email or '@' not in email:
            print("Error: Valid email required")
            return
        
        # Check if this email exists
        if DBUser.query.filter_by(email=email).first():
            print(f"Error: User with email {email} already exists")
            return
        
        if not password:
            generated = generate_password()
            use_generated = input(f"Generate password? (Y/n): ").strip().lower()
            
            if use_generated != 'n':
                password = generated
                print(f"\n🔐 Generated password: {password}")
                print("   (Save this somewhere safe!)\n")
            else:
                import getpass
                password = getpass.getpass("Enter password: ")
                password2 = getpass.getpass("Confirm password: ")
                if password != password2:
                    print("Error: Passwords don't match")
                    return
        
        if len(password) < 8:
            print("Error: Password must be at least 8 characters")
            return
        
        # Create the user
        user = DBUser(
            email=email,
            name="Admin",
            role='admin',
            is_active=True,
            can_generate_content=True
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        print("\n" + "="*50)
        print("  ✅ ADMIN USER CREATED SUCCESSFULLY")
        print("="*50)
        print(f"\n  Email:    {email}")
        print(f"  Role:     admin")
        print(f"  Password: {'*' * len(password)}")
        print(f"\n  Login at: /admin")
        print("="*50 + "\n")


if __name__ == '__main__':
    create_admin_user()
