"""
Karma Marketing + Media - Settings & Admin Routes
Settings, Audit Logs, and Webhooks management
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

from app.routes.auth import token_required, admin_required
from app.services.audit_service import audit_service
from app.services.webhook_service import webhook_service, WebhookService
from app.models.db_models import DBSetting, DBWebhook, DBAuditLog
from app.database import db
from app.utils import safe_int

settings_bp = Blueprint('settings', __name__)


# ==========================================
# SETTINGS ENDPOINTS
# ==========================================

@settings_bp.route('/', methods=['GET'])
@token_required
def get_settings(current_user):
    """
    Get settings
    
    GET /api/settings?scope=global&category=branding
    """
    scope = request.args.get('scope', 'global')
    scope_id = request.args.get('scope_id')
    category = request.args.get('category')
    
    query = DBSetting.query.filter(DBSetting.scope == scope)
    
    if scope_id:
        query = query.filter(DBSetting.scope_id == scope_id)
    if category:
        query = query.filter(DBSetting.category == category)
    
    settings = query.all()
    
    # Non-admins can't see secrets
    include_secrets = current_user.is_admin
    
    return jsonify({
        'settings': [s.to_dict(include_secret=include_secrets) for s in settings]
    })


@settings_bp.route('/', methods=['POST'])
@admin_required
def create_setting(current_user):
    """
    Create or update a setting
    
    POST /api/settings
    {
        "scope": "global",
        "scope_id": null,
        "category": "branding",
        "key": "agency_name",
        "value": "Karma Marketing + Media",
        "value_type": "string",
        "is_secret": false
    }
    """
    data = request.get_json() or {}
    
    required = ['category', 'key', 'value']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    scope = data.get('scope', 'global')
    scope_id = data.get('scope_id')
    
    # Check for existing setting
    existing = DBSetting.query.filter(
        DBSetting.scope == scope,
        DBSetting.scope_id == scope_id,
        DBSetting.category == data['category'],
        DBSetting.key == data['key']
    ).first()
    
    if existing:
        # Update existing
        old_value = existing.value
        existing.value = str(data['value'])
        existing.value_type = data.get('value_type', 'string')
        existing.is_secret = data.get('is_secret', False)
        existing.description = data.get('description')
        existing.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log the change
        audit_service.log_update(
            resource_type='setting',
            resource_id=str(existing.id),
            resource_name=f"{data['category']}.{data['key']}",
            user_id=current_user.id,
            user_email=current_user.email,
            old_value=old_value,
            new_value=data['value']
        )
        
        return jsonify({'setting': existing.to_dict(include_secret=True), 'updated': True})
    
    # Create new
    setting = DBSetting(
        scope=scope,
        scope_id=scope_id,
        category=data['category'],
        key=data['key'],
        value=str(data['value']),
        value_type=data.get('value_type', 'string'),
        is_secret=data.get('is_secret', False),
        description=data.get('description'),
        created_at=datetime.utcnow()
    )
    
    db.session.add(setting)
    db.session.commit()
    
    # Log creation
    audit_service.log_create(
        resource_type='setting',
        resource_id=str(setting.id),
        resource_name=f"{data['category']}.{data['key']}",
        user_id=current_user.id,
        user_email=current_user.email
    )
    
    return jsonify({'setting': setting.to_dict(include_secret=True), 'created': True}), 201


@settings_bp.route('/bulk', methods=['POST'])
@admin_required
def bulk_update_settings(current_user):
    """
    Update multiple settings at once
    
    POST /api/settings/bulk
    {
        "settings": [
            {"category": "branding", "key": "name", "value": "Test"},
            {"category": "content", "key": "tone", "value": "professional"}
        ]
    }
    """
    data = request.get_json() or {}
    settings = data.get('settings', [])
    
    results = []
    for item in settings:
        if 'category' not in item or 'key' not in item:
            continue
        
        scope = item.get('scope', 'global')
        scope_id = item.get('scope_id')
        
        existing = DBSetting.query.filter(
            DBSetting.scope == scope,
            DBSetting.scope_id == scope_id,
            DBSetting.category == item['category'],
            DBSetting.key == item['key']
        ).first()
        
        if existing:
            existing.value = str(item.get('value', ''))
            existing.updated_at = datetime.utcnow()
        else:
            setting = DBSetting(
                scope=scope,
                scope_id=scope_id,
                category=item['category'],
                key=item['key'],
                value=str(item.get('value', '')),
                value_type=item.get('value_type', 'string'),
                is_secret=item.get('is_secret', False)
            )
            db.session.add(setting)
        
        results.append({'category': item['category'], 'key': item['key']})
    
    db.session.commit()
    
    # Log bulk update
    audit_service.log(
        action='update',
        resource_type='setting',
        description=f"Bulk updated {len(results)} settings",
        user_id=current_user.id,
        user_email=current_user.email,
        metadata={'settings': results}
    )
    
    return jsonify({'updated': len(results), 'settings': results})


@settings_bp.route('/<int:setting_id>', methods=['DELETE'])
@admin_required
def delete_setting(current_user, setting_id):
    """Delete a setting"""
    setting = DBSetting.query.get(setting_id)
    if not setting:
        return jsonify({'error': 'Setting not found'}), 404
    
    # Log deletion
    audit_service.log_delete(
        resource_type='setting',
        resource_id=str(setting_id),
        resource_name=f"{setting.category}.{setting.key}",
        user_id=current_user.id,
        user_email=current_user.email
    )
    
    db.session.delete(setting)
    db.session.commit()
    
    return jsonify({'message': 'Setting deleted'})


# ==========================================
# AUDIT LOG ENDPOINTS
# ==========================================

@settings_bp.route('/audit', methods=['GET'])
@admin_required
def get_audit_logs(current_user):
    """
    Get audit logs
    
    GET /api/settings/audit?action=create&resource_type=client&days=30&limit=100
    """
    action = request.args.get('action')
    resource_type = request.args.get('resource_type')
    resource_id = request.args.get('resource_id')
    user_id = request.args.get('user_id')
    client_id = request.args.get('client_id')
    status = request.args.get('status')
    days = safe_int(request.args.get('days'), 30, max_val=365)
    limit = safe_int(request.args.get('limit'), 100, max_val=500)
    offset = safe_int(request.args.get('offset'), 0, min_val=0)
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    logs = audit_service.get_logs(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        client_id=client_id,
        status=status,
        start_date=start_date,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        'logs': [log.to_dict() for log in logs],
        'count': len(logs),
        'offset': offset,
        'limit': limit
    })


@settings_bp.route('/audit/stats', methods=['GET'])
@admin_required
def get_audit_stats(current_user):
    """Get audit log statistics"""
    days = safe_int(request.args.get('days'), 30, max_val=365)
    stats = audit_service.get_stats(days=days)
    return jsonify(stats)


@settings_bp.route('/audit/user/<user_id>', methods=['GET'])
@admin_required
def get_user_audit(current_user, user_id):
    """Get audit logs for a specific user"""
    days = safe_int(request.args.get('days'), 30, max_val=365)
    limit = safe_int(request.args.get('limit'), 100, max_val=500)
    
    logs = audit_service.get_user_activity(user_id, days=days, limit=limit)
    
    return jsonify({
        'user_id': user_id,
        'logs': [log.to_dict() for log in logs],
        'count': len(logs)
    })


@settings_bp.route('/audit/client/<client_id>', methods=['GET'])
@admin_required
def get_client_audit(current_user, client_id):
    """Get audit logs for a specific client"""
    days = safe_int(request.args.get('days'), 30, max_val=365)
    limit = safe_int(request.args.get('limit'), 100, max_val=500)
    
    logs = audit_service.get_client_activity(client_id, days=days, limit=limit)
    
    return jsonify({
        'client_id': client_id,
        'logs': [log.to_dict() for log in logs],
        'count': len(logs)
    })


@settings_bp.route('/audit/resource/<resource_type>/<resource_id>', methods=['GET'])
@admin_required
def get_resource_audit(current_user, resource_type, resource_id):
    """Get audit history for a specific resource"""
    limit = safe_int(request.args.get('limit'), 50, max_val=200)
    
    logs = audit_service.get_resource_history(resource_type, resource_id, limit=limit)
    
    return jsonify({
        'resource_type': resource_type,
        'resource_id': resource_id,
        'logs': [log.to_dict() for log in logs],
        'count': len(logs)
    })


@settings_bp.route('/audit/export', methods=['GET'])
@admin_required
def export_audit_logs(current_user):
    """Export audit logs as JSON"""
    days = safe_int(request.args.get('days'), 30, max_val=365)
    
    start_date = datetime.utcnow() - timedelta(days=days)
    logs = audit_service.get_logs(start_date=start_date, limit=10000)
    
    # Log the export
    audit_service.log(
        action='export',
        resource_type='audit',
        description=f"Exported {len(logs)} audit logs",
        user_id=current_user.id,
        user_email=current_user.email
    )
    
    # Return as downloadable JSON
    export_data = {
        'exported_at': datetime.utcnow().isoformat(),
        'exported_by': current_user.email,
        'period_days': days,
        'total_records': len(logs),
        'logs': [log.to_dict() for log in logs]
    }
    
    return jsonify(export_data)


# ==========================================
# WEBHOOK ENDPOINTS
# ==========================================

@settings_bp.route('/webhooks', methods=['GET'])
@token_required
def get_webhooks(current_user):
    """Get all webhooks"""
    client_id = request.args.get('client_id')
    
    if current_user.role != 'admin' and client_id:
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    webhooks = webhook_service.get_webhooks(client_id=client_id)
    
    return jsonify({
        'webhooks': [w.to_dict() for w in webhooks],
        'available_events': WebhookService.ALL_EVENTS
    })


@settings_bp.route('/webhooks', methods=['POST'])
@token_required
def create_webhook(current_user):
    """
    Create a new webhook
    
    POST /api/settings/webhooks
    {
        "name": "My CRM Integration",
        "url": "https://mycrm.com/webhook",
        "events": ["lead.created", "lead.converted"],
        "client_id": "client_xxx"
    }
    """
    data = request.get_json() or {}
    
    required = ['name', 'url', 'events']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    client_id = data.get('client_id')
    
    # Check client access if client-scoped
    if client_id and current_user.role != 'admin':
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    result = webhook_service.create_webhook(
        name=data['name'],
        url=data['url'],
        events=data['events'],
        client_id=client_id,
        secret=data.get('secret')
    )
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Log creation
    audit_service.log_create(
        resource_type='webhook',
        resource_id=result['webhook']['id'],
        resource_name=data['name'],
        user_id=current_user.id,
        user_email=current_user.email,
        client_id=client_id
    )
    
    return jsonify(result), 201


@settings_bp.route('/webhooks/<webhook_id>', methods=['PUT'])
@token_required
def update_webhook(current_user, webhook_id):
    """Update a webhook"""
    webhook = DBWebhook.query.get(webhook_id)
    if not webhook:
        return jsonify({'error': 'Webhook not found'}), 404
    
    # Check access
    if webhook.client_id and current_user.role != 'admin':
        if not current_user.has_access_to_client(webhook.client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    
    result = webhook_service.update_webhook(
        webhook_id=webhook_id,
        name=data.get('name'),
        url=data.get('url'),
        events=data.get('events'),
        is_active=data.get('is_active')
    )
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Log update
    audit_service.log_update(
        resource_type='webhook',
        resource_id=webhook_id,
        resource_name=webhook.name,
        user_id=current_user.id,
        user_email=current_user.email,
        client_id=webhook.client_id
    )
    
    return jsonify(result)


@settings_bp.route('/webhooks/<webhook_id>', methods=['DELETE'])
@token_required
def delete_webhook(current_user, webhook_id):
    """Delete a webhook"""
    webhook = DBWebhook.query.get(webhook_id)
    if not webhook:
        return jsonify({'error': 'Webhook not found'}), 404
    
    # Check access
    if webhook.client_id and current_user.role != 'admin':
        if not current_user.has_access_to_client(webhook.client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    # Log deletion
    audit_service.log_delete(
        resource_type='webhook',
        resource_id=webhook_id,
        resource_name=webhook.name,
        user_id=current_user.id,
        user_email=current_user.email,
        client_id=webhook.client_id
    )
    
    result = webhook_service.delete_webhook(webhook_id)
    
    if result.get('error'):
        return jsonify(result), 400
    
    return jsonify(result)


@settings_bp.route('/webhooks/<webhook_id>/test', methods=['POST'])
@token_required
def test_webhook(current_user, webhook_id):
    """Send a test event to a webhook"""
    webhook = DBWebhook.query.get(webhook_id)
    if not webhook:
        return jsonify({'error': 'Webhook not found'}), 404
    
    # Check access
    if webhook.client_id and current_user.role != 'admin':
        if not current_user.has_access_to_client(webhook.client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    result = webhook_service.test_webhook(webhook_id)
    
    return jsonify(result)


@settings_bp.route('/webhooks/stats', methods=['GET'])
@admin_required
def get_webhook_stats(current_user):
    """Get webhook statistics"""
    webhook_id = request.args.get('webhook_id')
    stats = webhook_service.get_webhook_stats(webhook_id=webhook_id)
    
    if stats.get('error'):
        return jsonify(stats), 404
    
    return jsonify(stats)


@settings_bp.route('/integrations/status', methods=['GET'])
@token_required
def get_integrations_status(current_user):
    """
    Get status of server-side integrations (API keys)
    
    GET /api/settings/integrations/status
    
    Returns which integrations have API keys configured
    """
    import os
    
    return jsonify({
        'openai_configured': bool(os.environ.get('OPENAI_API_KEY')),
        'anthropic_configured': bool(os.environ.get('ANTHROPIC_API_KEY')),
        'semrush_configured': bool(os.environ.get('SEMRUSH_API_KEY')),
        'callrail_configured': bool(os.environ.get('CALLRAIL_API_KEY')),
        'sendgrid_configured': bool(os.environ.get('SENDGRID_API_KEY')),
        'facebook_configured': bool(os.environ.get('FACEBOOK_APP_ID')),
        'google_configured': bool(os.environ.get('GOOGLE_CLIENT_ID')),
        'ga4_configured': bool(os.environ.get('GA4_PROPERTY_ID')),  # Global default
    })


@settings_bp.route('/system-status', methods=['GET'])
@token_required
def get_system_status(current_user):
    """
    Get comprehensive system status for debugging
    
    GET /api/settings/system-status
    
    Shows what's configured and what's missing
    """
    import os
    from app import __version__
    
    # Check each integration
    integrations = {
        'ai_content': {
            'name': 'AI Content Generation',
            'status': 'ready' if os.environ.get('OPENAI_API_KEY') else 'not_configured',
            'required_env': ['OPENAI_API_KEY'],
            'features': ['Blog generation', 'Social posts', 'Chatbot', 'Image generation']
        },
        'rankings': {
            'name': 'Keyword Rankings',
            'status': 'ready' if os.environ.get('SEMRUSH_API_KEY') else 'not_configured',
            'required_env': ['SEMRUSH_API_KEY'],
            'features': ['Rank tracking', 'Competitor analysis', 'Traffic value']
        },
        'analytics': {
            'name': 'Traffic Analytics',
            'status': 'ready' if os.environ.get('GA4_PROPERTY_ID') else 'per_client',
            'required_env': ['GA4_PROPERTY_ID (optional - can set per client)'],
            'features': ['Website traffic', 'Page views', 'Bounce rate']
        },
        'call_tracking': {
            'name': 'Call Intelligence',
            'status': 'ready' if (os.environ.get('CALLRAIL_API_KEY') and os.environ.get('CALLRAIL_ACCOUNT_ID')) else 'not_configured',
            'required_env': ['CALLRAIL_API_KEY', 'CALLRAIL_ACCOUNT_ID'],
            'features': ['Call analytics', 'Transcripts', 'AI analysis', 'Lead scoring']
        },
        'email': {
            'name': 'Email Notifications',
            'status': 'ready' if os.environ.get('SENDGRID_API_KEY') else 'not_configured',
            'required_env': ['SENDGRID_API_KEY', 'FROM_EMAIL'],
            'features': ['Notifications', 'Reports', 'Alerts']
        },
        'social_oauth': {
            'name': 'Social Media OAuth',
            'status': 'ready' if os.environ.get('FACEBOOK_APP_ID') else 'manual_only',
            'required_env': ['FACEBOOK_APP_ID', 'FACEBOOK_APP_SECRET', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'],
            'features': ['Facebook posting', 'Instagram posting', 'GBP posting']
        },
        'images': {
            'name': 'AI Image Generation',
            'status': 'ready' if os.environ.get('OPENAI_API_KEY') else 'not_configured',
            'required_env': ['OPENAI_API_KEY (DALL-E)', 'STABILITY_API_KEY (optional)', 'UNSPLASH_ACCESS_KEY (optional)'],
            'features': ['Blog headers', 'Social images', 'Custom prompts']
        }
    }
    
    # Count ready vs not ready
    ready_count = sum(1 for i in integrations.values() if i['status'] == 'ready')
    total_count = len(integrations)
    
    return jsonify({
        'version': __version__,
        'status': 'healthy',
        'integrations': integrations,
        'summary': {
            'ready': ready_count,
            'total': total_count,
            'percentage': round((ready_count / total_count) * 100)
        },
        'quick_start': {
            'minimum_required': ['OPENAI_API_KEY', 'ADMIN_EMAIL', 'ADMIN_PASSWORD'],
            'recommended': ['OPENAI_API_KEY', 'SEMRUSH_API_KEY', 'SENDGRID_API_KEY']
        }
    })
