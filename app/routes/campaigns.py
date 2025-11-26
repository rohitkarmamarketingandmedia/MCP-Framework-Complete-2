"""
MCP Framework - Campaign Routes
Marketing campaign management
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.db_service import DataService
from app.models.db_models import DBCampaign, CampaignStatus, UserRole
from datetime import datetime
import json

campaigns_bp = Blueprint('campaigns', __name__)
data_service = DataService()


@campaigns_bp.route('/', methods=['GET'])
@token_required
def list_campaigns(current_user):
    """List all campaigns (filtered by user access)"""
    if current_user.role in [UserRole.ADMIN, UserRole.MANAGER]:
        # Admin/Manager sees all - get campaigns from all clients
        clients = data_service.get_all_clients()
        campaigns = []
        for client in clients:
            campaigns.extend(data_service.get_client_campaigns(client.id))
    else:
        campaigns = []
        for cid in current_user.get_client_ids():
            campaigns.extend(data_service.get_client_campaigns(cid))
    
    return jsonify({
        'total': len(campaigns),
        'campaigns': [c.to_dict() for c in campaigns]
    })


@campaigns_bp.route('/', methods=['POST'])
@token_required
def create_campaign(current_user):
    """
    Create a new campaign
    
    POST /api/campaigns
    {
        "client_id": "client_abc123",
        "name": "Q1 SEO Push",
        "campaign_type": "seo",
        "description": "Push for top rankings",
        "budget": 2500
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    required = ['client_id', 'name']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    if not current_user.has_access_to_client(data['client_id']):
        return jsonify({'error': 'Access denied to this client'}), 403
    
    campaign = DBCampaign(
        client_id=data['client_id'],
        name=data['name'],
        campaign_type=data.get('campaign_type', 'content'),
        description=data.get('description', ''),
        budget=data.get('budget', 0.0),
        status=CampaignStatus.DRAFT
    )
    
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': 'Campaign created',
        'campaign': campaign.to_dict()
    }), 201


@campaigns_bp.route('/<campaign_id>', methods=['GET'])
@token_required
def get_campaign(current_user, campaign_id):
    """Get campaign by ID"""
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(campaign.to_dict())


@campaigns_bp.route('/<campaign_id>', methods=['PUT'])
@token_required
def update_campaign(current_user, campaign_id):
    """Update campaign"""
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    
    if 'name' in data:
        campaign.name = data['name']
    if 'description' in data:
        campaign.description = data['description']
    if 'campaign_type' in data:
        campaign.campaign_type = data['campaign_type']
    if 'budget' in data:
        campaign.budget = data['budget']
    if 'status' in data:
        campaign.status = data['status']
    
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': 'Campaign updated',
        'campaign': campaign.to_dict()
    })


@campaigns_bp.route('/<campaign_id>/activate', methods=['POST'])
@token_required
def activate_campaign(current_user, campaign_id):
    """Activate a campaign"""
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    campaign.status = CampaignStatus.ACTIVE
    campaign.start_date = datetime.utcnow()
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': 'Campaign activated',
        'status': campaign.status,
        'start_date': campaign.start_date.isoformat() if campaign.start_date else None
    })


@campaigns_bp.route('/<campaign_id>/pause', methods=['POST'])
@token_required
def pause_campaign(current_user, campaign_id):
    """Pause a campaign"""
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    campaign.status = CampaignStatus.PAUSED
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': 'Campaign paused',
        'status': campaign.status
    })


@campaigns_bp.route('/<campaign_id>/complete', methods=['POST'])
@token_required
def complete_campaign(current_user, campaign_id):
    """Mark campaign as completed"""
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    campaign.status = CampaignStatus.COMPLETED
    campaign.end_date = datetime.utcnow()
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': 'Campaign completed',
        'status': campaign.status,
        'end_date': campaign.end_date.isoformat() if campaign.end_date else None
    })


@campaigns_bp.route('/<campaign_id>/content', methods=['POST'])
@token_required
def add_content_to_campaign(current_user, campaign_id):
    """
    Add content to campaign
    
    POST /api/campaigns/<campaign_id>/content
    {
        "content_ids": ["content_abc", "content_xyz"]
    }
    """
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    content_ids = data.get('content_ids', [])
    
    # Get existing content_ids and add new ones
    existing = json.loads(campaign.content_ids)
    for cid in content_ids:
        if cid not in existing:
            existing.append(cid)
    campaign.content_ids = json.dumps(existing)
    
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': f'Added {len(content_ids)} content items',
        'total_content': len(existing)
    })


@campaigns_bp.route('/<campaign_id>/metrics', methods=['PUT'])
@token_required
def update_campaign_metrics(current_user, campaign_id):
    """
    Update campaign metrics
    
    PUT /api/campaigns/<campaign_id>/metrics
    {
        "organic_traffic": 1500,
        "conversions": 25,
        "keyword_rankings": {"roof repair": 3}
    }
    """
    campaign = data_service.get_campaign(campaign_id)
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    if not current_user.has_access_to_client(campaign.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    
    # Merge with existing metrics
    existing = json.loads(campaign.metrics)
    existing.update(data)
    campaign.metrics = json.dumps(existing)
    
    data_service.save_campaign(campaign)
    
    return jsonify({
        'message': 'Metrics updated',
        'metrics': existing
    })


@campaigns_bp.route('/client/<client_id>', methods=['GET'])
@token_required
def list_client_campaigns(current_user, client_id):
    """List all campaigns for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    campaigns = data_service.get_client_campaigns(client_id)
    
    # Optional status filter
    status_filter = request.args.get('status')
    if status_filter:
        campaigns = [c for c in campaigns if c.status == status_filter]
    
    return jsonify({
        'client_id': client_id,
        'total': len(campaigns),
        'campaigns': [c.to_dict() for c in campaigns]
    })
