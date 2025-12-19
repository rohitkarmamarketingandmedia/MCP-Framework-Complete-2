"""
MCP Framework - Webhook Routes
Routes for managing webhook endpoints and receiving incoming webhooks

OUTBOUND: MCP fires webhooks to configured endpoints when events happen
INBOUND: External services (CallRail, forms, chatbot) send webhooks to MCP
"""
from flask import Blueprint, request, jsonify, current_app
import logging
import json
import hmac
import hashlib
from datetime import datetime

from app.database import db
from app.routes.auth import token_required, admin_required
from app.models.db_models import DBWebhookLog, DBWebhookEndpoint, DBClient

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint('webhooks', __name__)


# ==========================================
# WEBHOOK STATUS & LIST
# ==========================================

@webhooks_bp.route('/', methods=['GET'])
@webhooks_bp.route('', methods=['GET'])
@token_required
def list_webhooks(current_user):
    """
    List all webhooks for the current user
    
    GET /api/webhooks/
    """
    # Get webhook endpoints
    if current_user.role == 'admin':
        endpoints = DBWebhookEndpoint.query.filter_by(is_active=True).all()
    else:
        # Non-admins see limited info
        endpoints = DBWebhookEndpoint.query.filter_by(is_active=True).limit(10).all()
    
    # Get recent webhook logs
    recent_logs = DBWebhookLog.query.order_by(
        DBWebhookLog.created_at.desc()
    ).limit(20).all()
    
    return jsonify({
        'endpoints': [e.to_dict() for e in endpoints],
        'recent_activity': [
            {
                'id': log.id,
                'event_type': log.event_type,
                'direction': log.direction,
                'status': log.status,
                'created_at': log.created_at.isoformat() if log.created_at else None
            }
            for log in recent_logs
        ],
        'total_endpoints': len(endpoints)
    })


# ==========================================
# WEBHOOK ENDPOINT MANAGEMENT
# ==========================================

@webhooks_bp.route('/endpoints', methods=['GET'])
@token_required
@admin_required
def list_webhook_endpoints(current_user):
    """
    List all configured webhook endpoints
    
    GET /api/webhooks/endpoints
    """
    endpoints = DBWebhookEndpoint.query.filter_by(is_active=True).all()
    
    return jsonify({
        'endpoints': [e.to_dict() for e in endpoints],
        'total': len(endpoints)
    })


@webhooks_bp.route('/endpoints', methods=['POST'])
@token_required
@admin_required
def create_webhook_endpoint(current_user):
    """
    Create a new webhook endpoint
    
    POST /api/webhooks/endpoints
    {
        "name": "Content Publisher",
        "url": "https://your-server.com/webhook/content",
        "event_types": ["content.approved", "content.published"],
        "client_id": null,  // null = all clients
        "secret": "optional-secret"
    }
    """
    data = request.get_json() or {}
    
    name = data.get('name')
    url = data.get('url')
    event_types = data.get('event_types', [])
    
    if not name or not url:
        return jsonify({'error': 'Name and URL required'}), 400
    
    if not event_types:
        return jsonify({'error': 'At least one event type required'}), 400
    
    endpoint = DBWebhookEndpoint(
        name=name,
        url=url,
        event_types=event_types,
        client_id=data.get('client_id'),
        secret=data.get('secret'),
        auth_header=data.get('auth_header')
    )
    
    db.session.add(endpoint)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'endpoint': endpoint.to_dict()
    }), 201


@webhooks_bp.route('/endpoints/<endpoint_id>', methods=['PUT'])
@token_required
@admin_required
def update_webhook_endpoint(current_user, endpoint_id):
    """Update a webhook endpoint"""
    endpoint = DBWebhookEndpoint.query.get(endpoint_id)
    if not endpoint:
        return jsonify({'error': 'Endpoint not found'}), 404
    
    data = request.get_json() or {}
    
    if 'name' in data:
        endpoint.name = data['name']
    if 'url' in data:
        endpoint.url = data['url']
    if 'event_types' in data:
        endpoint.event_types = json.dumps(data['event_types'])
    if 'client_id' in data:
        endpoint.client_id = data['client_id']
    if 'is_active' in data:
        endpoint.is_active = data['is_active']
    if 'secret' in data:
        endpoint.secret = data['secret']
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'endpoint': endpoint.to_dict()
    })


@webhooks_bp.route('/endpoints/<endpoint_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_webhook_endpoint(current_user, endpoint_id):
    """Delete a webhook endpoint"""
    endpoint = DBWebhookEndpoint.query.get(endpoint_id)
    if not endpoint:
        return jsonify({'error': 'Endpoint not found'}), 404
    
    db.session.delete(endpoint)
    db.session.commit()
    
    return jsonify({'success': True})


@webhooks_bp.route('/endpoints/<endpoint_id>/test', methods=['POST'])
@token_required
@admin_required
def test_webhook_endpoint(current_user, endpoint_id):
    """
    Send a test webhook to an endpoint
    
    POST /api/webhooks/endpoints/{id}/test
    """
    endpoint = DBWebhookEndpoint.query.get(endpoint_id)
    if not endpoint:
        return jsonify({'error': 'Endpoint not found'}), 404
    
    from app.services.webhook_events_service import WebhookEvent
    import requests
    
    # Create test event
    test_event = WebhookEvent(
        event_type='test.ping',
        payload={
            'message': 'Test webhook from MCP Framework',
            'endpoint_name': endpoint.name,
            'timestamp': datetime.utcnow().isoformat()
        }
    )
    
    try:
        payload = json.dumps(test_event.to_dict())
        
        headers = {
            'Content-Type': 'application/json',
            'X-MCP-Event': 'test.ping',
            'X-MCP-Event-ID': test_event.event_id
        }
        
        if endpoint.secret:
            signature = hmac.new(
                endpoint.secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            headers['X-MCP-Signature'] = f"sha256={signature}"
        
        if endpoint.auth_header:
            headers['Authorization'] = endpoint.auth_header
        
        response = requests.post(
            endpoint.url,
            data=payload,
            headers=headers,
            timeout=10
        )
        
        return jsonify({
            'success': response.status_code >= 200 and response.status_code < 300,
            'status_code': response.status_code,
            'response': response.text[:500] if response.text else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }), 500


# ==========================================
# WEBHOOK LOGS
# ==========================================

@webhooks_bp.route('/logs', methods=['GET'])
@webhooks_bp.route('/status', methods=['GET'])  # Alias for /api/webhooks/status
@webhooks_bp.route('/status/<client_id>', methods=['GET'])  # Alias for /api/webhooks/status/{id}
@token_required
@admin_required
def list_webhook_logs(current_user, client_id=None):
    """
    List webhook logs
    
    GET /api/webhooks/logs?limit=50&event_type=content.approved&status=failed
    """
    limit = request.args.get('limit', 50, type=int)
    event_type = request.args.get('event_type')
    status = request.args.get('status')
    direction = request.args.get('direction')
    
    query = DBWebhookLog.query
    
    if event_type:
        query = query.filter_by(event_type=event_type)
    if status:
        query = query.filter_by(status=status)
    if direction:
        query = query.filter_by(direction=direction)
    
    logs = query.order_by(DBWebhookLog.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'logs': [l.to_dict() for l in logs],
        'total': len(logs)
    })


@webhooks_bp.route('/logs/<event_id>', methods=['GET'])
@token_required
@admin_required
def get_webhook_log(current_user, event_id):
    """Get detailed webhook log including payload"""
    log = DBWebhookLog.query.filter_by(event_id=event_id).first()
    if not log:
        return jsonify({'error': 'Log not found'}), 404
    
    result = log.to_dict()
    try:
        result['payload'] = json.loads(log.payload) if log.payload else None
    except (json.JSONDecodeError, TypeError):
        result['payload'] = None
    result['response_body'] = log.response_body
    
    return jsonify(result)


# ==========================================
# INBOUND WEBHOOKS (from external services)
# ==========================================

@webhooks_bp.route('/inbound/callrail', methods=['POST'])
def receive_callrail_webhook():
    """
    Receive webhook from CallRail
    
    POST /api/webhooks/inbound/callrail
    
    CallRail sends:
    - Call started
    - Call completed
    - Voicemail received
    - Text received
    """
    data = request.get_json() or {}
    
    # Log the inbound webhook
    import uuid
    event_id = f"in_{uuid.uuid4().hex[:16]}"
    
    log = DBWebhookLog(
        event_id=event_id,
        event_type=f"callrail.{data.get('type', 'unknown')}",
        direction='inbound',
        payload=json.dumps(data),
        status='received'
    )
    db.session.add(log)
    db.session.commit()
    
    # Process based on type
    call_type = data.get('type')
    
    if call_type == 'post_call':
        # Call completed - process it
        _process_callrail_call(data, event_id)
    elif call_type == 'voicemail':
        # Voicemail - could trigger alert
        _process_callrail_voicemail(data, event_id)
    
    return jsonify({'received': True, 'event_id': event_id})


def _process_callrail_call(data: dict, event_id: str):
    """Process a completed call from CallRail"""
    try:
        from app.services.webhook_events_service import get_webhook_events_service
        
        # Extract call data
        call_id = data.get('id') or data.get('call_id')
        caller = data.get('caller_number') or data.get('customer_phone_number')
        duration = data.get('duration', 0)
        company_id = data.get('company_id')
        
        # Find client by CallRail company ID
        client = DBClient.query.filter_by(callrail_company_id=company_id).first()
        client_id = client.id if client else None
        
        # Fire event for external systems
        webhook_service = get_webhook_events_service()
        webhook_service.call_received(
            call_id=call_id,
            client_id=client_id,
            caller=caller,
            duration=duration,
            answered=data.get('answered', False),
            recording_url=data.get('recording'),
            tracking_number=data.get('tracking_phone_number')
        )
        
        # If there's a transcript, fire that event too
        if data.get('transcription'):
            webhook_service.call_transcribed(
                call_id=call_id,
                client_id=client_id,
                transcript=data.get('transcription')
            )
        
        # Update log
        log = DBWebhookLog.query.filter_by(event_id=event_id).first()
        if log:
            log.status = 'processed'
            log.client_id = client_id
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error processing CallRail call: {e}")
        log = DBWebhookLog.query.filter_by(event_id=event_id).first()
        if log:
            log.status = 'error'
            log.error_message = str(e)
            db.session.commit()


def _process_callrail_voicemail(data: dict, event_id: str):
    """Process a voicemail from CallRail"""
    try:
        from app.services.webhook_events_service import get_webhook_events_service
        
        company_id = data.get('company_id')
        client = DBClient.query.filter_by(callrail_company_id=company_id).first()
        client_id = client.id if client else None
        
        # Fire alert
        webhook_service = get_webhook_events_service()
        webhook_service.alert_triggered(
            alert_type='voicemail',
            client_id=client_id,
            message=f"New voicemail from {data.get('caller_number')}",
            severity='info',
            voicemail_url=data.get('voicemail_url'),
            duration=data.get('duration')
        )
        
    except Exception as e:
        logger.error(f"Error processing CallRail voicemail: {e}")


@webhooks_bp.route('/inbound/form', methods=['POST'])
def receive_form_webhook():
    """
    Receive webhook from form submissions (Gravity Forms, WPForms, etc.)
    
    POST /api/webhooks/inbound/form
    """
    data = request.get_json() or {}
    
    import uuid
    event_id = f"in_{uuid.uuid4().hex[:16]}"
    
    # Log it
    log = DBWebhookLog(
        event_id=event_id,
        event_type='form.submission',
        direction='inbound',
        payload=json.dumps(data),
        status='received'
    )
    db.session.add(log)
    db.session.commit()
    
    # Try to identify client
    client_id = data.get('client_id')
    site_url = data.get('site_url')
    
    if not client_id and site_url:
        # Try to match by website URL
        client = DBClient.query.filter(DBClient.website.contains(site_url)).first()
        if client:
            client_id = client.id
    
    # Create lead
    try:
        from app.services.lead_service import get_lead_service
        from app.services.webhook_events_service import get_webhook_events_service
        
        lead_service = get_lead_service()
        
        lead = lead_service.create_lead(
            client_id=client_id,
            name=data.get('name') or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            email=data.get('email'),
            phone=data.get('phone'),
            source='form',
            service_requested=data.get('service') or data.get('subject'),
            notes=data.get('message') or data.get('notes')
        )
        
        # Fire webhook to configured endpoints
        webhook_service = get_webhook_events_service()
        webhook_service.lead_created(
            lead_id=lead.id,
            client_id=client_id,
            source='form',
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            service=lead.service_requested
        )
        
        log.status = 'processed'
        log.client_id = client_id
        db.session.commit()
        
        return jsonify({
            'received': True,
            'lead_id': lead.id
        })
        
    except Exception as e:
        logger.error(f"Error processing form webhook: {e}")
        log.status = 'error'
        log.error_message = str(e)
        db.session.commit()
        
        return jsonify({
            'received': True,
            'error': 'An error occurred. Please try again.'
        }), 500


@webhooks_bp.route('/inbound/chatbot', methods=['POST'])
def receive_chatbot_webhook():
    """
    Receive webhook when chatbot captures a lead
    
    POST /api/webhooks/inbound/chatbot
    """
    data = request.get_json() or {}
    
    import uuid
    event_id = f"in_{uuid.uuid4().hex[:16]}"
    
    log = DBWebhookLog(
        event_id=event_id,
        event_type='chatbot.lead_captured',
        direction='inbound',
        payload=json.dumps(data),
        status='received'
    )
    db.session.add(log)
    db.session.commit()
    
    # Fire to configured endpoints
    try:
        from app.services.webhook_events_service import get_webhook_events_service
        
        webhook_service = get_webhook_events_service()
        webhook_service.lead_created(
            lead_id=data.get('lead_id'),
            client_id=data.get('client_id'),
            source='chatbot',
            conversation_id=data.get('conversation_id'),
            name=data.get('name'),
            email=data.get('email'),
            phone=data.get('phone')
        )
        
        log.status = 'processed'
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error processing chatbot webhook: {e}")
    
    return jsonify({'received': True})


# ==========================================
# MANUAL WEBHOOK TRIGGERS (for testing)
# ==========================================

@webhooks_bp.route('/fire', methods=['POST'])
@token_required
@admin_required
def fire_manual_webhook(current_user):
    """
    Manually fire a webhook event (for testing)
    
    POST /api/webhooks/fire
    {
        "event_type": "content.approved",
        "payload": {...},
        "client_id": "optional"
    }
    """
    data = request.get_json() or {}
    
    event_type = data.get('event_type')
    payload = data.get('payload', {})
    client_id = data.get('client_id')
    
    if not event_type:
        return jsonify({'error': 'event_type required'}), 400
    
    from app.services.webhook_events_service import get_webhook_events_service
    
    webhook_service = get_webhook_events_service()
    result = webhook_service.fire(event_type, payload, client_id, async_send=False)
    
    return jsonify({
        'fired': result,
        'event_type': event_type,
        'message': 'Webhook sent' if result else 'No webhook URL configured'
    })


# ==========================================
# AVAILABLE EVENTS DOCUMENTATION
# ==========================================

@webhooks_bp.route('/events', methods=['GET'])
@token_required
def list_available_events(current_user):
    """
    List all available webhook event types
    
    GET /api/webhooks/events
    """
    events = {
        'content': {
            'content.approved': 'Fired when content is approved and ready to publish',
            'content.published': 'Fired when content is published to WordPress',
            'content.rejected': 'Fired when content is rejected with feedback',
            'content.scheduled': 'Fired when content is scheduled for future publishing'
        },
        'leads': {
            'lead.created': 'Fired when a new lead is created from any source',
            'lead.qualified': 'Fired when a lead is marked as qualified',
            'lead.converted': 'Fired when a lead converts to customer'
        },
        'calls': {
            'call.received': 'Fired when a call is received (from CallRail)',
            'call.transcribed': 'Fired when call transcript is ready',
            'call.analyzed': 'Fired when call is analyzed for intelligence'
        },
        'clients': {
            'client.onboarded': 'Fired when a new client setup is complete',
            'client.updated': 'Fired when client settings are updated'
        },
        'reports': {
            'report.generated': 'Fired when a client report is generated'
        },
        'alerts': {
            'alert.triggered': 'Fired when something needs attention'
        }
    }
    
    return jsonify({
        'events': events,
        'webhook_url_env_vars': [
            'WEBHOOK_URL_DEFAULT',
            'WEBHOOK_URL_CONTENT',
            'WEBHOOK_URL_LEADS',
            'WEBHOOK_URL_CALLS',
            'WEBHOOK_SECRET'
        ]
    })
