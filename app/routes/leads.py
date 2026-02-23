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


# Simple test endpoint (no auth)
@leads_bp.route('/test', methods=['GET'])
def test_leads():
    """Simple test to verify leads blueprint is working"""
    return jsonify({'status': 'ok', 'message': 'Leads blueprint is working'})


# Authenticated test endpoint
@leads_bp.route('/test-auth', methods=['GET'])
@token_required
def test_leads_auth(current_user):
    """Test with authentication"""
    return jsonify({
        'status': 'ok', 
        'message': 'Auth working',
        'user': current_user.email
    })


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

@leads_bp.route('', methods=['GET'])
@leads_bp.route('/', methods=['GET'])
@token_required
def get_leads(current_user):
    """Get leads - simplified"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=== GET LEADS START ===")
    
    client_id = request.args.get('client_id')
    logger.info(f"Client: {client_id}, User: {current_user.email}")
    
    if not client_id:
        logger.info("No client_id")
        return jsonify({'error': 'client_id required', 'leads': [], 'total': 0}), 400
    
    # Skip access check for now to test
    logger.info("Querying leads...")
    
    try:
        # Full query with all fields needed for the leads display
        from sqlalchemy import text
        result = db.session.execute(
            text("""SELECT id, name, email, phone, source, status, created_at, 
                    message, source_detail, service_requested, 
                    notes, estimated_value, landing_page
                    FROM leads WHERE client_id = :cid 
                    ORDER BY created_at DESC LIMIT 200"""),
            {'cid': client_id}
        )
        
        leads = []
        for row in result:
            leads.append({
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'phone': row[3],
                'source': row[4],
                'status': row[5],
                'created_at': row[6].isoformat() if row[6] else None,
                'message': row[7],
                'source_detail': row[8],
                'service_requested': row[9],
                'notes': row[10],
                'estimated_value': row[11],
                'landing_page': row[12]
            })
        
        # Debug: log source values
        source_counts = {}
        for l in leads:
            src = l.get('source', 'None')
            source_counts[src] = source_counts.get(src, 0) + 1
        logger.info(f"Found {len(leads)} leads, sources: {source_counts}")
        return jsonify({'leads': leads, 'total': len(leads)})
        
    except Exception as e:
        logger.error(f"DB Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'leads': [], 'total': 0}), 500


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
    
    days_val = safe_int(request.args.get('days'), 30, max_val=365)
    
    # Check if we should use calendar month
    use_calendar = request.args.get('calendar', 'true').lower() == 'true'
    period = 'month'
    if days_val <= 7: period = 'week'
    elif days_val > 60: period = 'quarter'
    
    start_date, end_date, _, _ = comparative.get_period_dates(period, use_calendar=use_calendar)
    
    # We need to update lead_service to take dates, but for now we can calculate effective days
    effective_days = (datetime.utcnow() - start_date).days
    stats = lead_service.get_lead_stats(client_id, effective_days)
    
    # Override period_days in response to show it's correctly calculating
    stats['period_days'] = effective_days
    stats['start_date'] = start_date.isoformat()
    
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
    
    days_val = safe_int(request.args.get('days'), 30, max_val=365)
    
    # Check if we should use calendar month
    use_calendar = request.args.get('calendar', 'true').lower() == 'true'
    period = 'month'
    if days_val <= 7: period = 'week'
    elif days_val > 60: period = 'quarter'
    
    start_date, end_date, _, _ = comparative.get_period_dates(period, use_calendar=use_calendar)
    effective_days = (datetime.utcnow() - start_date).days
    
    trends = lead_service.get_lead_trends(client_id, effective_days)
    
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


# ==========================================
# Wufoo Integration (Admin/Manager only)
# ==========================================

def _require_admin_or_manager(current_user):
    """Check if user is admin or manager"""
    role = getattr(current_user, 'role', 'client')
    if role not in ('admin', 'manager'):
        return False
    return True

@leads_bp.route('/wufoo/test', methods=['POST'])
@token_required
def test_wufoo(current_user):
    """Test Wufoo connection - admin/manager only"""
    if not _require_admin_or_manager(current_user):
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    data = request.get_json(silent=True) or {}
    subdomain = data.get('subdomain', '').strip()
    api_key = data.get('api_key', '').strip()
    
    if not subdomain or not api_key:
        return jsonify({'success': False, 'message': 'Subdomain and API key required'}), 400
    
    from app.services.wufoo_service import get_wufoo_service
    wufoo = get_wufoo_service()
    result = wufoo.test_connection(subdomain, api_key)
    return jsonify(result)


@leads_bp.route('/wufoo/save', methods=['POST'])
@token_required
def save_wufoo_config(current_user):
    """Save Wufoo configuration for a client - admin/manager only"""
    if not _require_admin_or_manager(current_user):
        return jsonify({'error': 'Admin access required'}), 403
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    integrations = client.get_integrations()
    integrations['wufoo'] = {
        'subdomain': data.get('subdomain', '').strip(),
        'api_key': data.get('api_key', '').strip(),
        'form_hashes': data.get('form_hashes', []),
        'last_synced': integrations.get('wufoo', {}).get('last_synced')
    }
    
    import json
    client.integrations = json.dumps(integrations)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Wufoo config saved'})


@leads_bp.route('/wufoo/sync', methods=['POST'])
@token_required
def sync_wufoo(current_user):
    """Sync Wufoo form entries as leads - admin/manager only"""
    if not _require_admin_or_manager(current_user):
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    from app.services.wufoo_service import get_wufoo_service
    wufoo = get_wufoo_service()
    
    # First cleanup any cross-contaminated leads from old sync behavior
    cleanup = wufoo.cleanup_cross_client_leads(client)
    
    # Then sync only assigned forms
    result = wufoo.sync_entries_for_client(client)
    result['cleanup'] = cleanup
    
    return jsonify(result)


@leads_bp.route('/wufoo/cleanup', methods=['POST'])
@token_required
def cleanup_wufoo(current_user):
    """Remove Wufoo leads from non-assigned forms - fixes cross-client data"""
    if not _require_admin_or_manager(current_user):
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    from app.services.wufoo_service import get_wufoo_service
    wufoo = get_wufoo_service()
    result = wufoo.cleanup_cross_client_leads(client)
    
    return jsonify(result)


@leads_bp.route('/wufoo/forms', methods=['GET'])
@token_required
def get_wufoo_forms(current_user):
    """Get available Wufoo forms for a client - admin/manager only"""
    if not _require_admin_or_manager(current_user):
        return jsonify({'error': 'Admin access required', 'forms': []}), 403
    
    import logging
    logger = logging.getLogger(__name__)
    
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    integrations = client.get_integrations()
    wufoo_config = integrations.get('wufoo', {})
    
    subdomain = wufoo_config.get('subdomain')
    api_key = wufoo_config.get('api_key')
    
    if not subdomain or not api_key:
        return jsonify({'forms': [], 'error': 'Wufoo not configured - enter subdomain and API key first'})
    
    logger.info(f"Loading Wufoo forms for {client.business_name}, subdomain: {subdomain}")
    
    from app.services.wufoo_service import get_wufoo_service
    wufoo = get_wufoo_service()
    forms = wufoo.get_forms(subdomain, api_key)
    
    logger.info(f"Wufoo returned {len(forms)} forms")
    
    return jsonify({
        'forms': forms,
        'total': len(forms),
        'selected_hashes': wufoo_config.get('form_hashes', [])
    })
