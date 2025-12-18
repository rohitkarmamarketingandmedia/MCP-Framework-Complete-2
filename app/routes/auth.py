"""
MCP Framework - Authentication Routes
User login, registration, and token management
"""
from flask import Blueprint, request, jsonify, current_app
from functools import wraps
import jwt
import os
import secrets
import string
import logging
from datetime import datetime, timedelta

from app.models.db_models import DBUser, UserRole
from app.services.db_service import DataService, create_admin_user
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)
data_service = DataService()

import re

def validate_password(password):
    """
    Validate password meets security requirements.
    Returns: (is_valid: bool, error_message: str or None)
    """
    if not password:
        return False, "Password is required"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, None


@auth_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    from app.database import db
    
    # Check if admin exists
    admin_exists = DBUser.query.filter_by(role='admin', is_active=True).first() is not None
    
    return jsonify({
        'status': 'healthy',
        'service': 'Karma Marketing + Media',
        'version': '5.0.0',
        'admin_exists': admin_exists,
        'setup_required': not admin_exists
    })


@auth_bp.route('/bootstrap', methods=['POST'])
def bootstrap_admin():
    """
    Bootstrap the system by creating the first admin user.
    Only works if NO admin users exist yet.
    
    POST /api/auth/bootstrap
    {
        "email": "admin@example.com",
        "password": "securepassword123",
        "name": "Admin User"
    }
    
    Or without body to auto-generate credentials (returned in response)
    """
    from app.database import db
    
    # Check if any admin exists
    existing_admin = DBUser.query.filter_by(role='admin').first()
    if existing_admin:
        return jsonify({
            'error': 'Admin already exists. Use login instead.',
            'hint': 'If you forgot your password, contact support or reset the database.'
        }), 400
    
    data = request.get_json() or {}
    
    # Get or generate credentials
    email = data.get('email') or os.environ.get('ADMIN_EMAIL') or 'admin@karma.marketing'
    name = data.get('name') or 'Admin'
    
    # Generate password if not provided
    password = data.get('password') or os.environ.get('ADMIN_PASSWORD')
    generated_password = None
    
    if not password:
        # Generate secure random password
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        generated_password = ''.join(secrets.choice(alphabet) for _ in range(16))
        password = generated_password
    
    try:
        # Create admin user - use correct constructor signature
        # DBUser(email, name, password, role)
        admin = DBUser(
            email=email,
            name=name,
            password=password,
            role=UserRole.ADMIN
        )
        # Password is already set in constructor, but we can update it if needed
        # admin.set_password(password)  # Not needed - done in __init__
        
        db.session.add(admin)
        db.session.commit()
        
        # Generate token for immediate use
        token = generate_token(admin)
        
        response = {
            'success': True,
            'message': 'Admin user created successfully',
            'email': email,
            'token': token,
            'user': {
                'id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'role': admin.role
            }
        }
        
        # Only include password if it was auto-generated
        if generated_password:
            response['password'] = generated_password
            response['warning'] = 'SAVE THIS PASSWORD - it will not be shown again!'
        
        return jsonify(response), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create admin. Please try again.'}), 500


def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Check query param (for some integrations)
        if not token:
            token = request.args.get('token')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            payload = jwt.decode(
                token, 
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
            user_id = payload.get('user_id')
            if not user_id:
                logger.warning("Token missing user_id")
                return jsonify({'error': 'Invalid token format'}), 401
            
            current_user = data_service.get_user(user_id)
            if not current_user:
                # Try to reload from database in case of stale connection
                from app.database import db
                db.session.expire_all()
                current_user = data_service.get_user(user_id)
                
            if not current_user:
                logger.warning(f"User not found for id: {user_id}")
                return jsonify({'error': 'User not found', 'detail': 'Please log in again'}), 401
            if not current_user.is_active:
                return jsonify({'error': 'User is deactivated'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return jsonify({'error': 'Invalid token'}), 401
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return jsonify({'error': 'Authentication error', 'detail': 'Please log in again'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def optional_token(f):
    """Decorator that allows optional authentication - passes None if no token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        current_user = None
        
        # Check header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Check query param
        if not token:
            token = request.args.get('token')
        
        if token:
            try:
                payload = jwt.decode(
                    token, 
                    current_app.config['JWT_SECRET_KEY'],
                    algorithms=['HS256']
                )
                current_user = data_service.get_user(payload['user_id'])
                if current_user and not current_user.is_active:
                    current_user = None
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                pass
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def admin_required(f):
    """Decorator to require admin role - use AFTER @token_required"""
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.role != UserRole.ADMIN:
            return jsonify({'error': 'Admin access required'}), 403
        return f(current_user, *args, **kwargs)
    return decorated


def generate_token(user: DBUser) -> str:
    """Generate JWT token for user"""
    payload = {
        'user_id': user.id,
        'email': user.email,
        'role': user.role,  # Already a string now
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }
    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    User login
    
    POST /api/auth/login
    {
        "email": "user@example.com",
        "password": "password123"
    }
    """
    data = request.get_json() or {}
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password required'}), 400
    
    user = data_service.get_user_by_email(data['email'])
    
    if not user or not user.verify_password(data['password']):
        # Log failed login attempt
        audit_service.log_login(
            user_id=user.id if user else None,
            user_email=data['email'],
            success=False,
            error='Invalid credentials'
        )
        return jsonify({'error': 'Invalid email or password'}), 401
    
    if not user.is_active:
        audit_service.log_login(user.id, user.email, False, 'Account deactivated')
        return jsonify({'error': 'Account is deactivated'}), 401
    
    # Update last login
    data_service.update_last_login(user.id)
    
    # Log successful login
    audit_service.log_login(user.id, user.email, True)
    
    token = generate_token(user)
    
    return jsonify({
        'token': token,
        'user': user.to_dict()
    })


@auth_bp.route('/register', methods=['POST'])
@admin_required
def register(current_user):
    """
    Register new user (admin only)
    
    POST /api/auth/register
    {
        "email": "user@example.com",
        "name": "John Doe",
        "password": "password123",
        "role": "client",
        "client_ids": ["client_abc123"]
    }
    """
    data = request.get_json() or {}
    
    
    # Validate password
    password = data.get('password', '')
    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return jsonify({'error': error_msg}), 400
    
    required = ['email', 'name', 'password']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Check if email exists
    if data_service.get_user_by_email(data['email']):
        return jsonify({'error': 'Email already registered'}), 400
    
    role = data.get('role', 'client')
    client_ids = data.get('client_ids', [])
    
    # Create user with appropriate role
    user = DBUser(
        email=data['email'],
        name=data['name'],
        password=data['password'],
        role=role if role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.CLIENT, UserRole.VIEWER] else UserRole.CLIENT
    )
    user.set_client_ids(client_ids)
    
    data_service.save_user(user)
    
    return jsonify({
        'message': 'User created successfully',
        'user': user.to_dict()
    }), 201


@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """Get current authenticated user"""
    return jsonify(current_user.to_dict())


@auth_bp.route('/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """
    Change password
    
    POST /api/auth/change-password
    {
        "current_password": "old123",
        "new_password": "new456"
    }
    """
    data = request.get_json() or {}
    
    if not data.get('current_password') or not data.get('new_password'):
        return jsonify({'error': 'Current and new password required'}), 400
    
    if not current_user.verify_password(data['current_password']):
        return jsonify({'error': 'Current password is incorrect'}), 401
    
    current_user.set_password(data['new_password'])
    data_service.save_user(current_user)
    
    return jsonify({'message': 'Password updated successfully'})


@auth_bp.route('/users', methods=['GET'])
@admin_required
def list_users(current_user):
    """List all users (admin only)"""
    users = data_service.get_all_users()
    return jsonify([u.to_dict() for u in users])


@auth_bp.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_user, user_id):
    """Deactivate a user (admin only)"""
    user = data_service.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user.is_active = False
    data_service.save_user(user)
    
    return jsonify({'message': 'User deactivated'})


@auth_bp.route('/users/<user_id>', methods=['PUT'])
@admin_required
def update_user(current_user, user_id):
    """
    Update user details (admin only)
    
    PUT /api/auth/users/<user_id>
    {
        "name": "New Name",
        "role": "manager",
        "client_ids": ["client_1", "client_2"],
        "is_active": true
    }
    """
    user = data_service.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json() or {}
    
    if 'name' in data:
        user.name = data['name']
    
    if 'role' in data:
        valid_roles = [UserRole.ADMIN, UserRole.MANAGER, UserRole.CLIENT, UserRole.VIEWER]
        if data['role'] in valid_roles or data['role'] in ['admin', 'manager', 'client', 'viewer']:
            user.role = data['role']
    
    if 'client_ids' in data:
        user.set_client_ids(data['client_ids'])
    
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    
    data_service.save_user(user)
    
    return jsonify({
        'message': 'User updated successfully',
        'user': user.to_dict()
    })


@auth_bp.route('/users/<user_id>/activate', methods=['POST'])
@admin_required
def activate_user(current_user, user_id):
    """Reactivate a deactivated user (admin only)"""
    user = data_service.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user.is_active = True
    data_service.save_user(user)
    
    return jsonify({'message': 'User activated', 'user': user.to_dict()})


@auth_bp.route('/users/<user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(current_user, user_id):
    """
    Reset user password (admin only)
    
    POST /api/auth/users/<user_id>/reset-password
    {
        "new_password": "newpass123"
    }
    """
    user = data_service.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json() or {}
    if not data.get('new_password'):
        return jsonify({'error': 'new_password is required'}), 400
    
    if len(data['new_password']) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    
    user.set_password(data['new_password'])
    data_service.save_user(user)
    
    return jsonify({'message': 'Password reset successfully'})


@auth_bp.route('/fix-admin', methods=['POST'])
@token_required
def fix_admin_role(current_user):
    """
    Fix admin role if it was corrupted during bootstrap.
    Works if:
    1. No other admin exists, OR
    2. Current user's email matches ADMIN_EMAIL env var, OR
    3. Current user is the only user, OR
    4. Current user is the first user (earliest created_at)
    
    POST /api/auth/fix-admin
    """
    from app.database import db
    
    # Check conditions for allowing the fix
    existing_admin = DBUser.query.filter_by(role=UserRole.ADMIN).first()
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@karma.marketing')
    total_users = DBUser.query.count()
    first_user = DBUser.query.order_by(DBUser.created_at.asc()).first()
    
    # Allow fix if any of these conditions are met
    can_fix = (
        existing_admin is None or  # No admin exists
        current_user.email.lower() == admin_email.lower() or  # Email matches env
        current_user == existing_admin or  # They're the admin but role is corrupted
        total_users == 1 or  # Only one user - they should be admin
        (first_user and current_user.id == first_user.id)  # First user should be admin
    )
    
    if not can_fix:
        return jsonify({
            'error': 'Cannot fix admin role',
            'reason': 'An admin already exists. Contact them to update your role.',
            'your_role': current_user.role,
            'your_email': current_user.email,
            'admin_email_env': admin_email
        }), 403
    
    # Fix the role
    old_role = current_user.role
    current_user.role = UserRole.ADMIN
    db.session.commit()
    
    logger.info(f"Admin role fixed for user {current_user.email}: {old_role} -> ADMIN")
    
    return jsonify({
        'success': True,
        'message': 'Admin role restored',
        'old_role': old_role,
        'new_role': current_user.role,
        'user_id': current_user.id
    })


@auth_bp.route('/force-fix-admin', methods=['POST'])
def force_fix_admin():
    """
    Emergency endpoint to fix admin role.
    Works WITHOUT auth in these cases:
    1. There's exactly one user in the system, OR
    2. No user has admin role, OR
    3. Email provided matches ADMIN_EMAIL env var
    
    POST /api/auth/force-fix-admin
    {
        "email": "user@email.com"  // Email of user to make admin
    }
    
    This is a safety net for bootstrap issues.
    """
    from app.database import db
    
    data = request.get_json() or {}
    email = data.get('email', '').lower().strip()
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@karma.marketing').lower()
    
    # Safety checks
    total_users = DBUser.query.count()
    admin_count = DBUser.query.filter_by(role=UserRole.ADMIN).count()
    
    # Find user to promote
    user = None
    if email:
        user = DBUser.query.filter(DBUser.email.ilike(email)).first()
    
    # Allow if:
    # 1. Single user system
    # 2. No admins exist
    # 3. Email matches ADMIN_EMAIL env var
    # 4. Email matches the first user created
    first_user = DBUser.query.order_by(DBUser.created_at.asc()).first()
    
    can_fix = (
        total_users == 1 or
        admin_count == 0 or
        (email and email == admin_email) or
        (email and first_user and email == first_user.email.lower())
    )
    
    if not can_fix:
        # Return helpful info
        return jsonify({
            'error': 'Cannot force-fix: specify the correct admin email',
            'hint': f'Try with email matching ADMIN_EMAIL env var or first user',
            'total_users': total_users,
            'admin_count': admin_count,
            'first_user_email': first_user.email if first_user else None
        }), 403
    
    # If no specific user requested, use first user
    if not user:
        user = first_user
    
    if not user:
        return jsonify({'error': 'No user found'}), 404
    
    # Fix the role
    old_role = user.role
    user.role = UserRole.ADMIN
    db.session.commit()
    
    logger.warning(f"FORCE admin role fix for user {user.email}: {old_role} -> ADMIN")
    
    return jsonify({
        'success': True,
        'message': 'Admin role force-fixed',
        'user_email': user.email,
        'old_role': old_role,
        'new_role': user.role
    })


@auth_bp.route('/promote-to-admin', methods=['POST'])
@token_required
def promote_to_admin(current_user):
    """
    Promote the currently logged-in user to admin.
    Only works if current user is the first user OR matches ADMIN_EMAIL.
    
    POST /api/auth/promote-to-admin
    """
    from app.database import db
    
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@karma.marketing').lower()
    first_user = DBUser.query.order_by(DBUser.created_at.asc()).first()
    
    # Check if current user should be admin
    can_promote = (
        current_user.email.lower() == admin_email or
        (first_user and current_user.id == first_user.id)
    )
    
    if not can_promote:
        return jsonify({
            'error': 'Cannot promote: you are not the designated admin',
            'your_email': current_user.email,
            'admin_email': admin_email
        }), 403
    
    # Promote
    old_role = current_user.role
    current_user.role = UserRole.ADMIN
    db.session.commit()
    
    logger.info(f"User promoted to admin: {current_user.email}")
    
    return jsonify({
        'success': True,
        'message': 'You are now an admin',
        'old_role': old_role,
        'new_role': current_user.role
    })


@auth_bp.route('/make-me-admin', methods=['POST'])
@token_required
def make_me_admin(current_user):
    """
    NUCLEAR OPTION: Make the currently logged-in user an admin.
    No restrictions - if you can authenticate, you get admin.
    
    This is for development/bootstrap recovery only.
    In production, you should remove or restrict this endpoint.
    
    POST /api/auth/make-me-admin
    """
    from app.database import db
    
    old_role = current_user.role
    current_user.role = UserRole.ADMIN
    db.session.commit()
    
    logger.warning(f"NUCLEAR ADMIN FIX: {current_user.email} promoted from {old_role} to ADMIN")
    
    return jsonify({
        'success': True,
        'message': 'You are now an admin!',
        'email': current_user.email,
        'old_role': old_role,
        'new_role': 'ADMIN'
    })


@auth_bp.route('/debug-users', methods=['GET'])
@admin_required
def debug_users(current_user):
    """
    Debug endpoint to see all users and their roles.
    Helps diagnose permission issues.
    Admin only.
    
    GET /api/auth/debug-users
    """
    users = DBUser.query.all()
    
    return jsonify({
        'total_users': len(users),
        'users': [
            {
                'id': u.id,
                'email': u.email,
                'role': u.role,
                'is_active': u.is_active,
                'created_at': u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    })
