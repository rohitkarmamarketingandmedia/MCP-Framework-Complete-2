"""
MCP Framework - Client Experience Routes
Routes for health scores, call tracking, and reports
VERSION: 2.0 - FIXED HEALTH SCORE
"""
from flask import Blueprint, request, jsonify
import logging

from app.routes.auth import token_required
from app.models.db_models import DBClient

logger = logging.getLogger(__name__)
logger.info("========== CLIENT_EXPERIENCE.PY VERSION 2.0 LOADED ==========")
client_exp_bp = Blueprint('client_experience', __name__)


# ==========================================
# HEALTH SCORE
# ==========================================

@client_exp_bp.route('/health-score/<client_id>', methods=['GET'])
@token_required
def get_health_score(current_user, client_id):
    """
    Get client health score and breakdown
    
    GET /api/client/health-score/{client_id}?days=30
    """
    logger.info(f"=== HEALTH SCORE v2.0 for {client_id} ===")
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get client directly
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Calculate health score based on actual configured items
    score = 0
    breakdown = {}
    
    # 1. WordPress Connection (25 points)
    logger.info(f"WordPress URL: {client.wordpress_url}")
    if client.wordpress_url:
        score += 25
        breakdown['wordpress'] = {
            'score': 25, 'max': 25, 
            'percent': 100,
            'detail': 'WordPress connected'
        }
    else:
        breakdown['wordpress'] = {
            'score': 0, 'max': 25,
            'percent': 0,
            'detail': 'WordPress not connected'
        }
    
    # 2. Keywords Tracked (20 points)
    keywords = client.get_keywords() if hasattr(client, 'get_keywords') else {}
    primary = keywords.get('primary', []) if isinstance(keywords, dict) else []
    secondary = keywords.get('secondary', []) if isinstance(keywords, dict) else []
    keyword_count = len(primary) + len(secondary)
    logger.info(f"Keywords count: {keyword_count}")
    
    if keyword_count >= 5:
        kw_score = 20
    elif keyword_count > 0:
        kw_score = min(keyword_count * 4, 20)
    else:
        kw_score = 0
    
    score += kw_score
    breakdown['keywords'] = {
        'score': kw_score, 'max': 20,
        'percent': round((kw_score / 20) * 100),
        'detail': f'{keyword_count} keywords tracked' if keyword_count > 0 else 'No keywords defined'
    }
    
    # 3. Content Published (25 points)
    from app.models.db_models import DBBlogPost
    content_count = DBBlogPost.query.filter_by(client_id=client_id, status='published').count()
    logger.info(f"Published content count: {content_count}")
    
    if content_count >= 10:
        content_score = 25
    elif content_count >= 5:
        content_score = 20
    elif content_count > 0:
        content_score = min(content_count * 4, 25)
    else:
        content_score = 0
    
    score += content_score
    breakdown['content'] = {
        'score': content_score, 'max': 25,
        'percent': round((content_score / 25) * 100),
        'detail': f'{content_count} posts published' if content_count > 0 else 'No content published'
    }
    
    # 4. Call Tracking (15 points)
    logger.info(f"CallRail company_id: {client.callrail_company_id}")
    if client.callrail_company_id:
        score += 15
        breakdown['calls'] = {
            'score': 15, 'max': 15,
            'percent': 100,
            'detail': 'Call tracking active'
        }
    else:
        breakdown['calls'] = {
            'score': 0, 'max': 15,
            'percent': 0,
            'detail': 'Call tracking not configured'
        }
    
    # 5. Social Connections (15 points) - Check via social posts or client social_accounts field
    social_count = 0
    try:
        # Try to get social connections from client's social_accounts field
        if hasattr(client, 'social_accounts') and client.social_accounts:
            import json
            accounts = json.loads(client.social_accounts) if isinstance(client.social_accounts, str) else client.social_accounts
            if isinstance(accounts, list):
                social_count = len(accounts)
            elif isinstance(accounts, dict):
                social_count = len([k for k, v in accounts.items() if v])
        
        # Fallback: check if client has any social posts (indicates connection)
        if social_count == 0:
            from app.models.db_models import DBSocialPost
            has_posts = DBSocialPost.query.filter_by(client_id=client_id).first()
            if has_posts:
                social_count = 1
    except Exception as e:
        logger.warning(f"Error checking social connections: {e}")
        social_count = 0
    
    logger.info(f"Social connections count: {social_count}")
    
    if social_count >= 2:
        social_score = 15
    elif social_count > 0:
        social_score = 8
    else:
        social_score = 0
    
    score += social_score
    breakdown['social'] = {
        'score': social_score, 'max': 15,
        'percent': round((social_score / 15) * 100),
        'detail': f'{social_count} social accounts connected' if social_count > 0 else 'No social accounts'
    }
    
    # Determine grade
    if score >= 90:
        grade = 'A+'
        color = '#10b981'  # emerald
    elif score >= 80:
        grade = 'A'
        color = '#10b981'
    elif score >= 70:
        grade = 'B'
        color = '#3b82f6'  # blue
    elif score >= 60:
        grade = 'C'
        color = '#f59e0b'  # amber
    elif score >= 40:
        grade = 'D'
        color = '#f97316'  # orange
    else:
        grade = 'F'
        color = '#ef4444'  # red
    
    logger.info(f"Final health score: {score}, grade: {grade}")
    
    return jsonify({
        'total': score,
        'score': score,
        'health_score': score,
        'grade': grade,
        'color': color,
        'breakdown': breakdown
    })


@client_exp_bp.route('/wins/<client_id>', methods=['GET'])
@token_required
def get_wins(current_user, client_id):
    """
    Get recent wins for a client
    
    GET /api/client/wins/{client_id}?days=7
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = request.args.get('days', 7, type=int)
    
    from app.services.client_health_service import get_client_health_service
    health_service = get_client_health_service()
    
    wins = health_service.get_wins(client_id, days=days)
    
    return jsonify({'wins': wins, 'days': days})


@client_exp_bp.route('/upcoming/<client_id>', methods=['GET'])
@token_required
def get_upcoming(current_user, client_id):
    """
    Get upcoming scheduled content
    
    GET /api/client/upcoming/{client_id}?days=14
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = request.args.get('days', 14, type=int)
    
    from app.services.client_health_service import get_client_health_service
    health_service = get_client_health_service()
    
    upcoming = health_service.get_whats_coming(client_id, days=days)
    
    return jsonify({'upcoming': upcoming, 'days': days})


@client_exp_bp.route('/activity/<client_id>', methods=['GET'])
@token_required
def get_activity(current_user, client_id):
    """
    Get activity feed for a client
    
    GET /api/client/activity/{client_id}?limit=20
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    limit = request.args.get('limit', 20, type=int)
    
    from app.services.client_health_service import get_client_health_service
    health_service = get_client_health_service()
    
    activity = health_service.get_activity_feed(client_id, limit=limit)
    
    return jsonify({'activity': activity})


# ==========================================
# CALL TRACKING (CallRail)
# ==========================================

@client_exp_bp.route('/calls/config', methods=['GET'])
@token_required
def get_callrail_config(current_user):
    """
    Check if CallRail is configured
    
    GET /api/client/calls/config
    """
    from app.services.callrail_service import CallRailConfig
    
    return jsonify({
        'configured': CallRailConfig.is_configured(),
        'account_id': CallRailConfig.ACCOUNT_ID[:4] + '...' if CallRailConfig.ACCOUNT_ID else None
    })


@client_exp_bp.route('/calls/<client_id>', methods=['GET'])
@token_required
def get_calls(current_user, client_id):
    """
    Get recent calls for a client
    
    GET /api/client/calls/{client_id}?limit=20&include_recordings=true
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.callrail_service import CallRailConfig, get_callrail_service
    
    if not CallRailConfig.is_configured():
        # Return demo data so dashboard still looks good
        from datetime import datetime, timedelta
        import random
        
        demo_calls = []
        for i in range(5):
            call_time = datetime.utcnow() - timedelta(hours=random.randint(1, 72))
            demo_calls.append({
                'id': f'demo_call_{i}',
                'date': call_time.isoformat(),
                'duration': random.randint(30, 300),
                'caller_name': ['John S.', 'Mary T.', 'Bob K.', 'Lisa M.', 'Dave R.'][i],
                'caller_number': '(941) 555-****',
                'source': ['Google', 'Direct', 'Referral', 'Facebook', 'Website'][i],
                'answered': i != 2,  # One missed call
                'has_transcript': i < 3,
                'lead_status': ['qualified', 'qualified', 'missed', 'new', 'converted'][i],
                'transcript_preview': 'Demo transcript - configure CallRail for real data' if i < 3 else None
            })
        
        return jsonify({
            'configured': False,
            'demo_mode': True,
            'message': 'Demo data - Add CALLRAIL_API_KEY and CALLRAIL_ACCOUNT_ID for real call tracking',
            'calls': demo_calls,
            'total': 5
        })
    
    limit = request.args.get('limit', 20, type=int)
    include_recordings = request.args.get('include_recordings', 'true').lower() == 'true'
    include_transcripts = request.args.get('include_transcripts', 'true').lower() == 'true'
    
    # Get client's CallRail company ID
    client = DBClient.query.get(client_id)
    callrail_company_id = getattr(client, 'callrail_company_id', None)
    
    if not callrail_company_id and client:
        # Try to match by name
        callrail = get_callrail_service()
        company = callrail.get_company_by_name(client.business_name)
        if company:
            callrail_company_id = company.get('id')
    
    if not callrail_company_id:
        return jsonify({
            'configured': True,
            'message': 'Client not linked to CallRail company',
            'calls': []
        })
    
    callrail = get_callrail_service()
    calls = callrail.get_recent_calls(
        company_id=callrail_company_id,
        limit=limit,
        include_recordings=include_recordings,
        include_transcripts=include_transcripts
    )
    
    return jsonify({
        'configured': True,
        'calls': calls,
        'total': len(calls)
    })


@client_exp_bp.route('/calls/<client_id>/metrics', methods=['GET'])
@token_required
def get_call_metrics(current_user, client_id):
    """
    Get call metrics for a client
    
    GET /api/client/calls/{client_id}/metrics?days=30
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.callrail_service import CallRailConfig, get_callrail_service
    
    if not CallRailConfig.is_configured():
        return jsonify({
            'configured': False,
            'message': 'CallRail not configured'
        })
    
    days = request.args.get('days', 30, type=int)
    
    # Get client's CallRail company ID
    client = DBClient.query.get(client_id)
    callrail_company_id = getattr(client, 'callrail_company_id', None)
    
    if not callrail_company_id and client:
        callrail = get_callrail_service()
        company = callrail.get_company_by_name(client.business_name)
        if company:
            callrail_company_id = company.get('id')
    
    if not callrail_company_id:
        return jsonify({
            'configured': True,
            'message': 'Client not linked to CallRail company'
        })
    
    callrail = get_callrail_service()
    metrics = callrail.get_client_call_metrics(callrail_company_id, days=days)
    
    return jsonify({
        'configured': True,
        'metrics': metrics
    })


@client_exp_bp.route('/calls/<client_id>/hot-leads', methods=['GET'])
@token_required
def get_hot_leads(current_user, client_id):
    """
    Get hot leads (long calls) for follow-up
    
    GET /api/client/calls/{client_id}/hot-leads?days=7
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.callrail_service import CallRailConfig, get_callrail_service
    
    if not CallRailConfig.is_configured():
        return jsonify({
            'configured': False,
            'message': 'CallRail not configured',
            'hot_leads': []
        })
    
    days = request.args.get('days', 7, type=int)
    min_duration = request.args.get('min_duration', 120, type=int)  # 2 minutes
    
    # Get client's CallRail company ID
    client = DBClient.query.get(client_id)
    callrail_company_id = getattr(client, 'callrail_company_id', None)
    
    if not callrail_company_id and client:
        callrail = get_callrail_service()
        company = callrail.get_company_by_name(client.business_name)
        if company:
            callrail_company_id = company.get('id')
    
    if not callrail_company_id:
        return jsonify({
            'configured': True,
            'message': 'Client not linked to CallRail company',
            'hot_leads': []
        })
    
    callrail = get_callrail_service()
    hot_leads = callrail.get_hot_leads(callrail_company_id, days=days, min_duration=min_duration)
    
    return jsonify({
        'configured': True,
        'hot_leads': hot_leads,
        'total': len(hot_leads)
    })


@client_exp_bp.route('/calls/recording/<call_id>', methods=['GET'])
@token_required
def get_call_recording(current_user, call_id):
    """
    Get recording URL for a specific call
    
    GET /api/client/calls/recording/{call_id}
    """
    from app.services.callrail_service import CallRailConfig, get_callrail_service
    
    if not CallRailConfig.is_configured():
        return jsonify({'error': 'CallRail not configured'}), 400
    
    callrail = get_callrail_service()
    url = callrail.get_call_recording_url(call_id)
    
    if url:
        return jsonify({'recording_url': url})
    else:
        return jsonify({'error': 'Recording not found'}), 404


# ==========================================
# REPORTS
# ==========================================

@client_exp_bp.route('/report/<client_id>/snapshot', methods=['GET'])
@token_required
def get_3day_snapshot(current_user, client_id):
    """
    Get 3-day snapshot report data
    
    GET /api/client/report/{client_id}/snapshot
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.client_report_service import get_client_report_service
    report_service = get_client_report_service()
    
    report = report_service.generate_3day_snapshot(client_id)
    
    return jsonify(report)


@client_exp_bp.route('/report/<client_id>/send', methods=['POST'])
@token_required
def send_report(current_user, client_id):
    """
    Send 3-day snapshot report via email
    
    POST /api/client/report/{client_id}/send
    {
        "email": "override@example.com"  // Optional
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    recipient_email = data.get('email')
    
    from app.services.client_report_service import get_client_report_service
    report_service = get_client_report_service()
    
    success = report_service.send_3day_report(client_id, recipient_email)
    
    if success:
        return jsonify({'success': True, 'message': 'Report sent successfully'})
    else:
        return jsonify({'error': 'Failed to send report'}), 500


@client_exp_bp.route('/report/send-all', methods=['POST'])
@token_required
def send_all_reports(current_user):
    """
    Send 3-day reports to all active clients
    
    POST /api/client/report/send-all
    """
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    
    from app.services.client_report_service import get_client_report_service
    report_service = get_client_report_service()
    
    results = report_service.send_all_3day_reports()
    
    return jsonify({
        'success': True,
        'sent': results['sent'],
        'failed': results['failed']
    })


# ==========================================
# DASHBOARD DATA (Combined endpoint)
# ==========================================

@client_exp_bp.route('/dashboard/<client_id>', methods=['GET'])
@token_required
def get_dashboard_data(current_user, client_id):
    """
    Get all dashboard data in one call for the portal
    
    GET /api/client/dashboard/{client_id}
    
    Returns: health score, wins, activity, upcoming, leads summary, call metrics
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.client_health_service import get_client_health_service
    health_service = get_client_health_service()
    
    # Get all components
    health = health_service.calculate_health_score(client_id, days=30)
    wins = health_service.get_wins(client_id, days=7)
    activity = health_service.get_activity_feed(client_id, limit=10)
    upcoming = health_service.get_whats_coming(client_id, days=14)
    
    # Get call metrics if available
    call_metrics = None
    try:
        from app.services.callrail_service import CallRailConfig, get_callrail_service
        
        if CallRailConfig.is_configured():
            client = DBClient.query.get(client_id)
            callrail_company_id = getattr(client, 'callrail_company_id', None)
            
            if not callrail_company_id and client:
                callrail = get_callrail_service()
                company = callrail.get_company_by_name(client.business_name)
                if company:
                    callrail_company_id = company.get('id')
            
            if callrail_company_id:
                callrail = get_callrail_service()
                call_metrics = callrail.get_client_call_metrics(callrail_company_id, days=30)
    except Exception as e:
        logger.warning(f"Error getting call metrics: {e}")
    
    # Get client info
    client = DBClient.query.get(client_id)
    
    return jsonify({
        'client': {
            'id': client_id,
            'name': client.business_name if client else 'Unknown',
            'industry': client.industry if client else None
        },
        'health_score': health.to_dict(),
        'wins': wins,
        'activity': activity,
        'upcoming': upcoming,
        'calls': call_metrics
    })
