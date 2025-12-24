"""
MCP Framework - Leads API Routes
Lead capture, management, and analytics
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from app.routes.auth import token_required
from app.utils import safe_int
from app.services.lead_service import lead_service
from app.services.review_service import review_service
from app.models.db_models import DBLead, DBClient
from app.database import db

leads_bp = Blueprint('leads', __name__)


# ==========================================
# Public Lead Capture (No Auth Required)
# ==========================================

@leads_bp.route('/capture', methods=['POST'])
def capture_lead():
    """
    Public endpoint for capturing leads from forms
    
    POST /api/leads/capture
    {
        "client_id": "client_xxx",
        "name": "John Smith",
        "phone": "941-555-1234",
        "email": "john@example.com",
        "service_requested": "Roof Repair",
        "message": "I need help with...",
        "source": "form",
        "source_detail": "homepage",
        "landing_page": "https://example.com/roof-repair"
    }
    """
    data = request.get_json(silent=True) or {}
    
    client_id = data.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    result = lead_service.capture_lead(client_id, data)
    
    if result.get('error'):
        return jsonify(result), 400
    
    return jsonify(result)


@leads_bp.route('/capture/<client_id>', methods=['POST'])
def capture_lead_for_client(client_id):
    """
    Alternative endpoint with client_id in URL
    """
    data = request.get_json(silent=True) or {}
    data['client_id'] = client_id
    
    result = lead_service.capture_lead(client_id, data)
    
    if result.get('error'):
        return jsonify(result), 400
    
    return jsonify(result)


# ==========================================
# Lead Management (Auth Required)
# ==========================================

@leads_bp.route('/', methods=['GET'])
@token_required
def get_leads(current_user):
    """
    Get leads with optional filters
    
    GET /api/leads?client_id=xxx&status=new&source=form&days=30&limit=100
    """
    try:
        client_id = request.args.get('client_id')
        
        if not client_id:
            return jsonify({'error': 'client_id is required'}), 400
        
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
        
        status = request.args.get('status')
        source = request.args.get('source')
        days = safe_int(request.args.get('days'), 30, max_val=365)
        limit = safe_int(request.args.get('limit'), 100, max_val=500)
        
        leads = lead_service.get_client_leads(
            client_id=client_id,
            status=status,
            source=source,
            days=days,
            limit=limit
        )
        
        return jsonify({
            'leads': leads,
            'total': len(leads)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to load leads',
            'message': str(e),
            'leads': [],
            'total': 0
        }), 500


@leads_bp.route('/<lead_id>', methods=['GET'])
@token_required
def get_lead(current_user, lead_id):
    """Get a single lead"""
    lead = lead_service.get_lead(lead_id)
    
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    
    if not current_user.has_access_to_client(lead.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({'lead': lead.to_dict()})


@leads_bp.route('/<lead_id>/status', methods=['PUT'])
@token_required
def update_lead_status(current_user, lead_id):
    """
    Update lead status
    
    PUT /api/leads/<lead_id>/status
    {
        "status": "contacted",
        "notes": "Left voicemail",
        "auto_review_request": true  // Optional: trigger review request when converted
    }
    """
    lead = lead_service.get_lead(lead_id)
    
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    
    if not current_user.has_access_to_client(lead.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    notes = data.get('notes')
    auto_review = data.get('auto_review_request', True)  # Default to true
    
    if not status:
        return jsonify({'error': 'status is required'}), 400
    
    # Track if this is a conversion (for review request trigger)
    old_status = lead.status
    is_conversion = old_status != 'converted' and status == 'converted'
    
    result = lead_service.update_lead_status(lead_id, status, notes)
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Trigger review request when lead is converted
    review_result = None
    if is_conversion and auto_review:
        try:
            # Get client's review URL from GBP or default
            client = DBClient.query.get(lead.client_id)
            review_url = None
            
            if client and client.gbp_place_id:
                # Use Google Business Profile review URL
                review_url = f"https://search.google.com/local/writereview?placeid={client.gbp_place_id}"
            elif client and client.website_url:
                # Fallback to generic review page
                review_url = f"{client.website_url.rstrip('/')}/reviews"
            
            if review_url and (lead.email or lead.phone):
                # Send review request (tries email first, then SMS if available)
                method = 'email' if lead.email else 'sms'
                review_result = review_service.send_review_request_to_lead(
                    lead_id=lead.id,
                    review_url=review_url,
                    method=method
                )
        except Exception as e:
            # Don't fail the status update if review request fails
            review_result = {'error': 'An error occurred. Please try again.'}
    
    result['review_request'] = review_result
    result['is_conversion'] = is_conversion
    
    return jsonify(result)


@leads_bp.route('/<lead_id>/value', methods=['PUT'])
@token_required
def update_lead_value(current_user, lead_id):
    """
    Update lead monetary value
    
    PUT /api/leads/<lead_id>/value
    {
        "estimated_value": 5000,
        "actual_value": 4800
    }
    """
    lead = lead_service.get_lead(lead_id)
    
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    
    if not current_user.has_access_to_client(lead.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    result = lead_service.set_lead_value(
        lead_id,
        estimated_value=data.get('estimated_value'),
        actual_value=data.get('actual_value')
    )
    
    if result.get('error'):
        return jsonify(result), 400
    
    return jsonify(result)


@leads_bp.route('/<lead_id>', methods=['DELETE'])
@token_required
def delete_lead(current_user, lead_id):
    """Delete a lead"""
    lead = lead_service.get_lead(lead_id)
    
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    
    if not current_user.has_access_to_client(lead.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    db.session.delete(lead)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Lead deleted'})


# ==========================================
# Analytics
# ==========================================

@leads_bp.route('/stats', methods=['GET'])
@token_required
def get_lead_stats(current_user):
    """
    Get lead statistics
    
    GET /api/leads/stats?client_id=xxx&days=30
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = safe_int(request.args.get('days'), 30, max_val=365)
    
    stats = lead_service.get_lead_stats(client_id, days)
    
    return jsonify(stats)


@leads_bp.route('/trends', methods=['GET'])
@token_required
def get_lead_trends(current_user):
    """
    Get daily lead trends
    
    GET /api/leads/trends?client_id=xxx&days=30
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = safe_int(request.args.get('days'), 30, max_val=365)
    
    trends = lead_service.get_lead_trends(client_id, days)
    
    return jsonify({'trends': trends})


# ==========================================
# Form Builder
# ==========================================

@leads_bp.route('/form-embed', methods=['POST'])
@token_required
def generate_form_embed(current_user):
    """
    Generate embeddable form HTML
    
    POST /api/leads/form-embed
    {
        "client_id": "client_xxx",
        "fields": ["name", "phone", "email", "service", "message"],
        "services": ["Roof Repair", "New Roof", "Storm Damage"],
        "button_text": "Get My Free Quote",
        "button_color": "#2563eb",
        "success_message": "Thanks! We'll call you shortly."
    }
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    html = lead_service.generate_form_embed(client_id, data)
    
    return jsonify({
        'html': html,
        'client_id': client_id
    })


# ==========================================
# Notification Settings
# ==========================================

@leads_bp.route('/notifications', methods=['PUT'])
@token_required
def update_notification_settings(current_user):
    """
    Update lead notification settings for a client
    
    PUT /api/leads/notifications
    {
        "client_id": "client_xxx",
        "notification_email": "owner@business.com",
        "notification_phone": "+19415551234",
        "enabled": true
    }
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if 'notification_email' in data:
        client.lead_notification_email = data['notification_email']
    
    if 'notification_phone' in data:
        client.lead_notification_phone = data['notification_phone']
    
    if 'enabled' in data:
        client.lead_notification_enabled = data['enabled']
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'notification_email': client.lead_notification_email,
        'notification_phone': client.lead_notification_phone,
        'enabled': client.lead_notification_enabled
    })
