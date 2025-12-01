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
from datetime import datetime, timedelta

from app.models.db_models import DBUser, UserRole
from app.services.db_service import DataService, create_admin_user
from app.services.audit_service import audit_service

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
        # Create admin user
        admin = DBUser(
            email=email,
            name=name,
            role=UserRole.ADMIN,
            is_active=True,
            can_generate_content=True,
            can_manage_clients=True,
            can_view_reports=True
        )
        admin.set_password(password)
        
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
            current_user = data_service.get_user(payload['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
            if not current_user.is_active:
                return jsonify({'error': 'User is deactivated'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
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
    """Decorator to require admin role"""
    @wraps(f)
    @token_required
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
