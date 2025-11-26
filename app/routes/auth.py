"""
MCP Framework - Authentication Routes
User login, registration, and token management
"""
from flask import Blueprint, request, jsonify, current_app
from functools import wraps
import jwt
from datetime import datetime, timedelta

from app.models.db_models import DBUser, UserRole
from app.services.db_service import DataService, create_admin_user

auth_bp = Blueprint('auth', __name__)
data_service = DataService()


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
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password required'}), 400
    
    user = data_service.get_user_by_email(data['email'])
    
    if not user or not user.verify_password(data['password']):
        return jsonify({'error': 'Invalid email or password'}), 401
    
    if not user.is_active:
        return jsonify({'error': 'Account is deactivated'}), 401
    
    # Update last login
    data_service.update_last_login(user.id)
    
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
    data = request.get_json()
    
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
    data = request.get_json()
    
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
