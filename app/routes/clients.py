"""
MCP Framework - Client Management Routes
CRUD operations for marketing clients
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required, admin_required
from app.services.db_service import DataService
from app.models.db_models import DBClient, UserRole
from datetime import datetime
import json

clients_bp = Blueprint('clients', __name__)
data_service = DataService()


@clients_bp.route('/', methods=['GET'])
@token_required
def list_clients(current_user):
    """List all clients (filtered by user access)"""
    if current_user.role in [UserRole.ADMIN, UserRole.MANAGER]:
        clients = data_service.get_all_clients()
    else:
        clients = [
            data_service.get_client(cid) 
            for cid in current_user.get_client_ids()
        ]
        clients = [c for c in clients if c]  # Filter None
    
    return jsonify({
        'total': len(clients),
        'clients': [c.to_dict() for c in clients]
    })


@clients_bp.route('/', methods=['POST'])
@admin_required
def create_new_client(current_user):
    """
    Create a new client
    
    POST /api/clients
    {
        "business_name": "ABC Roofing",
        "industry": "roofing",
        "geo": "Sarasota, FL",
        "website_url": "https://abcroofing.com",
        "phone": "(941) 555-1234",
        "email": "info@abcroofing.com",
        "primary_keywords": ["roof repair sarasota", "roofing company sarasota"],
        "service_areas": ["Sarasota", "Bradenton", "Venice"],
        "tone": "professional"
    }
    """
    data = request.get_json()
    
    required = ['business_name', 'industry', 'geo']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    client = DBClient(
        business_name=data['business_name'],
        industry=data['industry'],
        geo=data['geo'],
        website_url=data.get('website_url'),
        phone=data.get('phone'),
        email=data.get('email'),
        service_areas=data.get('service_areas', []),
        primary_keywords=data.get('primary_keywords', []),
        secondary_keywords=data.get('secondary_keywords', []),
        competitors=data.get('competitors', []),
        tone=data.get('tone', 'professional'),
        unique_selling_points=data.get('unique_selling_points', []),
        subscription_tier=data.get('subscription_tier', 'standard')
    )
    
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Client created successfully',
        'client': client.to_dict()
    }), 201


@clients_bp.route('/<client_id>', methods=['GET'])
@token_required
def get_client(current_user, client_id):
    """Get client by ID"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    return jsonify(client.to_dict())


@clients_bp.route('/<client_id>', methods=['PUT'])
@token_required
def update_client(current_user, client_id):
    """Update client"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json()
    
    # Update allowed fields
    if 'business_name' in data:
        client.business_name = data['business_name']
    if 'industry' in data:
        client.industry = data['industry']
    if 'geo' in data:
        client.geo = data['geo']
    if 'website_url' in data:
        client.website_url = data['website_url']
    if 'phone' in data:
        client.phone = data['phone']
    if 'email' in data:
        client.email = data['email']
    if 'service_areas' in data:
        client.service_areas = json.dumps(data['service_areas'])
    if 'primary_keywords' in data:
        client.primary_keywords = json.dumps(data['primary_keywords'])
    if 'secondary_keywords' in data:
        client.secondary_keywords = json.dumps(data['secondary_keywords'])
    if 'competitors' in data:
        client.competitors = json.dumps(data['competitors'])
    if 'tone' in data:
        client.tone = data['tone']
    if 'unique_selling_points' in data:
        client.unique_selling_points = json.dumps(data['unique_selling_points'])
    if 'subscription_tier' in data:
        client.subscription_tier = data['subscription_tier']
    if 'is_active' in data:
        client.is_active = data['is_active']
    
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Client updated',
        'client': client.to_dict()
    })


@clients_bp.route('/<client_id>', methods=['DELETE'])
@admin_required
def delete_client(current_user, client_id):
    """Deactivate a client (soft delete)"""
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    client.is_active = False
    client.updated_at = datetime.utcnow()
    data_service.save_client(client)
    
    return jsonify({'message': 'Client deactivated'})


@clients_bp.route('/<client_id>/keywords', methods=['PUT'])
@token_required
def update_keywords(current_user, client_id):
    """
    Update client keywords
    
    PUT /api/clients/<client_id>/keywords
    {
        "primary": ["keyword1", "keyword2"],
        "secondary": ["keyword3", "keyword4"]
    }
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json()
    
    if 'primary' in data:
        client.primary_keywords = json.dumps(data['primary'])
    if 'secondary' in data:
        client.secondary_keywords = json.dumps(data['secondary'])
    
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Keywords updated',
        'primary_keywords': client.get_primary_keywords(),
        'secondary_keywords': client.get_secondary_keywords()
    })


@clients_bp.route('/<client_id>/integrations', methods=['PUT'])
@admin_required
def update_integrations(current_user, client_id):
    """
    Update client API integrations
    
    PUT /api/clients/<client_id>/integrations
    {
        "wordpress_url": "https://client.com",
        "wordpress_api_key": "xxxx",
        "gbp_location_id": "123456",
        "ga4_property_id": "123456789"
    }
    """
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json()
    
    # Store integrations as JSON
    integrations = client.get_integrations()
    
    if 'wordpress_url' in data:
        integrations['wordpress_url'] = data['wordpress_url']
    if 'wordpress_api_key' in data:
        integrations['wordpress_api_key'] = data['wordpress_api_key']
    if 'gbp_location_id' in data:
        integrations['gbp_location_id'] = data['gbp_location_id']
    if 'ga4_property_id' in data:
        integrations['ga4_property_id'] = data['ga4_property_id']
    
    client.integrations = json.dumps(integrations)
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Integrations updated',
        'client_id': client_id
    })


@clients_bp.route('/<client_id>/summary', methods=['GET'])
@token_required
def get_client_summary(current_user, client_id):
    """Get client summary with content counts"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    blog_posts = data_service.get_client_blog_posts(client_id)
    social_posts = data_service.get_client_social_posts(client_id)
    campaigns = data_service.get_client_campaigns(client_id)
    
    return jsonify({
        'client': client.to_dict(),
        'stats': {
            'content': {
                'total': len(blog_posts),
                'published': sum(1 for c in blog_posts if c.status == 'published'),
                'draft': sum(1 for c in blog_posts if c.status == 'draft')
            },
            'social': {
                'total': len(social_posts),
                'by_platform': {}
            },
            'campaigns': {
                'total': len(campaigns),
                'active': sum(1 for c in campaigns if c.status == 'active')
            }
        }
    })
