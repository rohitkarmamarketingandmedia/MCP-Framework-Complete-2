#!/usr/bin/env python3
"""
MCP Framework - Admin Setup Script
Creates the first admin user for fresh installations
"""
import sys
import os

# Add the app to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║            MCP Framework - Admin Setup                       ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Get user input
    print("Create your admin account:\n")
    
    email = input("Email: ").strip()
    if not email or '@' not in email:
        print("❌ Invalid email address")
        sys.exit(1)
    
    name = input("Name: ").strip()
    if not name:
        print("❌ Name is required")
        sys.exit(1)
    
    password = input("Password (min 8 characters): ").strip()
    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        sys.exit(1)
    
    confirm = input("Confirm password: ").strip()
    if password != confirm:
        print("❌ Passwords don't match")
        sys.exit(1)
    
    # Create the user
    try:
        from app import create_app
        from app.database import db
        from app.models.db_models import DBUser, UserRole
        from app.services.db_service import DataService
        
        # Create app context
        app = create_app()
        
        with app.app_context():
            # Ensure tables exist
            db.create_all()
            
            ds = DataService()
            
            # Check if user already exists
            existing = ds.get_user_by_email(email)
            if existing:
                print(f"\n❌ User with email {email} already exists!")
                sys.exit(1)
            
            # Create admin
            admin = DBUser(
                email=email,
                name=name,
                password=password,
                role=UserRole.ADMIN
            )
            ds.save_user(admin)
            
            print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    ✅ SUCCESS!                               ║
╠══════════════════════════════════════════════════════════════╣
║  Admin user created successfully!                            ║
║                                                              ║
║  Email: {email:<50} ║
║  User ID: {admin.id:<48} ║
║                                                              ║
║  You can now start the server with:                          ║
║    python run.py                                             ║
║                                                              ║
║  Then open the dashboard at:                                 ║
║    http://localhost:5000                                     ║
╚══════════════════════════════════════════════════════════════╝
            """)
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("\nMake sure you've installed dependencies:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error creating user: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
