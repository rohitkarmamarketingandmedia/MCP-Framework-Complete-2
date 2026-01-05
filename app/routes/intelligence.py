"""
MCP Framework - Customer Intelligence Routes
Routes for analyzing interactions and generating content from customer data
"""
from flask import Blueprint, request, jsonify
import logging

from app.routes.auth import token_required
from app.models.db_models import DBClient

logger = logging.getLogger(__name__)
intelligence_bp = Blueprint('intelligence', __name__)


# ==========================================
# CALLRAIL DIRECT ENDPOINTS
# ==========================================

@intelligence_bp.route('/calls/<client_id>', methods=['GET'])
@token_required
def get_client_calls(current_user, client_id):
    """
    Get calls directly from CallRail for a client
    
    GET /api/intelligence/calls/{client_id}?days=30
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = request.args.get('days', 30, type=int)
    
    try:
        from app.services.callrail_service import CallRailConfig, get_callrail_service
        
        # Check if CallRail is configured at server level
        if not CallRailConfig.is_configured():
            return jsonify({
                'error': 'CallRail not configured',
                'message': 'CALLRAIL_API_KEY and CALLRAIL_ACCOUNT_ID must be set in environment variables',
                'calls': [],
                'total': 0
            })
        
        # Get client's company ID
        client = DBClient.query.get(client_id)
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        callrail_company_id = getattr(client, 'callrail_company_id', None)
        callrail_account_id = getattr(client, 'callrail_account_id', None)  # Per-client override
        
        if not callrail_company_id:
            return jsonify({
                'error': 'CallRail Company ID not set',
                'message': 'Set the CallRail Company ID in Settings → Integrations',
                'calls': [],
                'total': 0
            })
        
        logger.info(f"Fetching CallRail calls for company {callrail_company_id}, account {callrail_account_id or 'global'}")
        
        # Get calls from CallRail
        callrail = get_callrail_service()
        calls = callrail.get_recent_calls(
            company_id=callrail_company_id,
            account_id=callrail_account_id,  # Pass per-client account ID
            limit=100,
            include_recordings=True,
            include_transcripts=True
        )
        
        logger.info(f"Got {len(calls)} calls from CallRail")
        
        return jsonify({
            'calls': calls,
            'total': len(calls),
            'company_id': callrail_company_id,
            'account_id': callrail_account_id or CallRailConfig.get_account_id()
        })
        
    except Exception as e:
        logger.error(f"CallRail error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'calls': [],
            'total': 0
        }), 500


@intelligence_bp.route('/callrail/status', methods=['GET'])
@token_required
def callrail_status(current_user):
    """Check CallRail configuration status"""
    from app.services.callrail_service import CallRailConfig
    
    api_key = CallRailConfig.get_api_key()
    account_id = CallRailConfig.get_account_id()
    
    return jsonify({
        'configured': CallRailConfig.is_configured(),
        'api_key_set': bool(api_key),
        'api_key_length': len(api_key) if api_key else 0,
        'account_id_set': bool(account_id),
        'account_id': account_id if account_id else None
    })


# ==========================================
# CALL TRANSCRIPT ANALYSIS
# ==========================================

@intelligence_bp.route('/analyze-call', methods=['POST'])
@token_required
def analyze_single_call(current_user):
    """
    Analyze a single call transcript
    
    POST /api/intelligence/analyze-call
    {
        "transcript": "...",
        "client_id": "..."
    }
    """
    data = request.get_json(silent=True) or {}
    transcript = data.get('transcript')
    client_id = data.get('client_id')
    
    if not transcript:
        return jsonify({'error': 'Transcript required'}), 400
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    analysis = service.analyze_call_transcript(transcript, client_id)
    
    return jsonify(analysis)


@intelligence_bp.route('/analyze-calls/<client_id>', methods=['POST'])
@token_required
def analyze_multiple_calls(current_user, client_id):
    """
    Analyze multiple call transcripts for a client
    
    POST /api/intelligence/analyze-calls/{client_id}
    {
        "transcripts": [
            {"id": "...", "transcript": "...", "date": "..."},
            ...
        ]
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    transcripts = data.get('transcripts', [])
    
    if not transcripts:
        return jsonify({'error': 'No transcripts provided'}), 400
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    analysis = service.analyze_multiple_calls(transcripts, client_id)
    
    return jsonify(analysis)


# ==========================================
# FETCH & ANALYZE FROM CALLRAIL
# ==========================================

@intelligence_bp.route('/fetch-callrail/<client_id>', methods=['POST'])
@token_required
def fetch_and_analyze_callrail(current_user, client_id):
    """
    Fetch recent calls from CallRail and analyze them
    
    POST /api/intelligence/fetch-callrail/{client_id}
    {
        "days": 30,
        "limit": 50
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.callrail_service import CallRailConfig, get_callrail_service
    
    if not CallRailConfig.is_configured():
        return jsonify({'error': 'CallRail not configured'}), 400
    
    data = request.get_json(silent=True) or {}
    days = data.get('days', 30)
    limit = data.get('limit', 50)
    
    # Get client's CallRail company ID
    client = DBClient.query.get(client_id)
    callrail_company_id = getattr(client, 'callrail_company_id', None)
    
    if not callrail_company_id and client:
        callrail = get_callrail_service()
        company = callrail.get_company_by_name(client.business_name)
        if company:
            callrail_company_id = company.get('id')
    
    if not callrail_company_id:
        return jsonify({'error': 'Client not linked to CallRail'}), 400
    
    # Fetch calls with transcripts
    callrail = get_callrail_service()
    calls = callrail.get_recent_calls(
        company_id=callrail_company_id,
        limit=limit,
        include_recordings=False,
        include_transcripts=True
    )
    
    # Filter calls that have transcripts
    transcripts = []
    for call in calls:
        if call.get('has_transcript'):
            transcripts.append({
                'id': call.get('id'),
                'transcript': call.get('transcript_preview', ''),  # Would need full transcript
                'date': call.get('date')
            })
    
    if not transcripts:
        return jsonify({
            'message': 'No calls with transcripts found',
            'calls_checked': len(calls)
        })
    
    # Analyze transcripts
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    analysis = service.analyze_multiple_calls(transcripts, client_id)
    
    return jsonify({
        'calls_analyzed': len(transcripts),
        'analysis': analysis
    })


# ==========================================
# FULL INTELLIGENCE REPORT
# ==========================================

@intelligence_bp.route('/report/<client_id>', methods=['GET'])
@token_required
def get_intelligence_report(current_user, client_id):
    """
    Get full intelligence report from all sources
    
    GET /api/intelligence/report/{client_id}?days=30
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = request.args.get('days', 30, type=int)
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    # Get CallRail data if available
    call_transcripts = None
    total_calls = 0
    all_calls = []
    
    try:
        from app.services.callrail_service import CallRailConfig, get_callrail_service
        
        if CallRailConfig.is_configured():
            client = DBClient.query.get(client_id)
            callrail_company_id = getattr(client, 'callrail_company_id', None)
            callrail_account_id = getattr(client, 'callrail_account_id', None)
            
            if callrail_company_id:
                callrail = get_callrail_service()
                all_calls = callrail.get_recent_calls(
                    company_id=callrail_company_id,
                    account_id=callrail_account_id,
                    days=days,
                    limit=100
                )
                total_calls = len(all_calls)
                logger.info(f"Intelligence report: got {total_calls} calls from CallRail")
                
                # Extract transcripts from calls that have them
                call_transcripts = [
                    {'id': c['id'], 'transcript': c.get('transcript_preview', ''), 'date': c['date']}
                    for c in all_calls if c.get('has_transcript')
                ]
                logger.info(f"Intelligence report: {len(call_transcripts or [])} calls have transcripts")
    except Exception as e:
        logger.warning(f"Could not fetch CallRail data: {e}")
    
    report = service.get_full_intelligence_report(
        client_id,
        call_transcripts=call_transcripts,
        days=days
    )
    
    # Add call count to report (even if no transcripts)
    report['call_count'] = total_calls
    report['calls_with_transcripts'] = len(call_transcripts) if call_transcripts else 0
    
    return jsonify(report)


@intelligence_bp.route('/questions/<client_id>', methods=['GET'])
@token_required
def get_top_questions(current_user, client_id):
    """
    Get top questions from all interactions
    
    GET /api/intelligence/questions/{client_id}?limit=25
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    limit = request.args.get('limit', 25, type=int)
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    report = service.get_full_intelligence_report(client_id)
    questions = report.get('combined_insights', {}).get('top_questions', [])[:limit]
    
    return jsonify({
        'questions': questions,
        'total': len(questions)
    })


# ==========================================
# CONTENT GENERATION
# ==========================================

@intelligence_bp.route('/generate/faq/<client_id>', methods=['POST'])
@token_required
def generate_faq_page(current_user, client_id):
    """
    Generate FAQ page from customer questions
    
    POST /api/intelligence/generate/faq/{client_id}
    {
        "questions": [...],  // Optional - will auto-fetch if not provided
        "max_questions": 15
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    questions = data.get('questions')
    max_questions = data.get('max_questions', 15)
    
    from app.services.content_from_interactions_service import get_content_from_interactions_service
    service = get_content_from_interactions_service()
    
    result = service.generate_faq_page(client_id, questions, max_questions)
    
    return jsonify(result)


@intelligence_bp.route('/generate/blog/<client_id>', methods=['POST'])
@token_required
def generate_blog_from_questions(current_user, client_id):
    """
    Generate blog post from customer questions
    
    POST /api/intelligence/generate/blog/{client_id}
    {
        "questions": ["Question 1?", "Question 2?", ...],
        "topic": "Optional topic override",
        "save_draft": true
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    questions = data.get('questions', [])
    topic = data.get('topic')
    save_draft = data.get('save_draft', True)
    
    if not questions:
        return jsonify({'error': 'Questions required'}), 400
    
    from app.services.content_from_interactions_service import get_content_from_interactions_service
    service = get_content_from_interactions_service()
    
    result = service.generate_blog_from_questions(client_id, questions, topic, save_draft)
    
    return jsonify(result)


@intelligence_bp.route('/generate/service-qa/<client_id>', methods=['POST'])
@token_required
def generate_service_qa(current_user, client_id):
    """
    Generate Q&A section for a service page
    
    POST /api/intelligence/generate/service-qa/{client_id}
    {
        "service": "AC Repair"
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    service = data.get('service')
    
    if not service:
        return jsonify({'error': 'Service required'}), 400
    
    from app.services.content_from_interactions_service import get_content_from_interactions_service
    content_service = get_content_from_interactions_service()
    
    result = content_service.generate_service_page_qa_section(client_id, service)
    
    return jsonify(result)


@intelligence_bp.route('/generate/calendar/<client_id>', methods=['POST'])
@token_required
def generate_content_calendar(current_user, client_id):
    """
    Generate content calendar from customer questions
    
    POST /api/intelligence/generate/calendar/{client_id}
    {
        "weeks": 4,
        "posts_per_week": 2
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    weeks = data.get('weeks', 4)
    posts_per_week = data.get('posts_per_week', 2)
    
    from app.services.content_from_interactions_service import get_content_from_interactions_service
    service = get_content_from_interactions_service()
    
    result = service.generate_content_calendar(client_id, weeks, posts_per_week)
    
    return jsonify(result)


@intelligence_bp.route('/generate/package/<client_id>', methods=['POST'])
@token_required
def generate_content_package(current_user, client_id):
    """
    Generate complete content package from all interactions
    
    POST /api/intelligence/generate/package/{client_id}
    
    Returns: FAQ page, 3 blog posts, content calendar
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    from app.services.content_from_interactions_service import get_content_from_interactions_service
    service = get_content_from_interactions_service()
    
    # Get CallRail transcripts if available
    call_transcripts = None
    try:
        from app.services.callrail_service import CallRailConfig, get_callrail_service
        
        if CallRailConfig.is_configured():
            client = DBClient.query.get(client_id)
            callrail_company_id = getattr(client, 'callrail_company_id', None)
            
            if callrail_company_id:
                callrail = get_callrail_service()
                calls = callrail.get_recent_calls(
                    company_id=callrail_company_id,
                    limit=100,
                    include_transcripts=True
                )
                call_transcripts = [
                    {'id': c['id'], 'transcript': c.get('transcript_preview', ''), 'date': c['date']}
                    for c in calls if c.get('has_transcript')
                ]
    except Exception as e:
        logger.warning(f"Could not fetch CallRail data: {e}")
    
    result = service.auto_generate_content_package(client_id, call_transcripts)
    
    return jsonify(result)


# ==========================================
# CONTENT OPPORTUNITIES
# ==========================================

@intelligence_bp.route('/opportunities/<client_id>', methods=['GET'])
@token_required
def get_content_opportunities(current_user, client_id):
    """
    Get content opportunities identified from interactions
    
    GET /api/intelligence/opportunities/{client_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    report = service.get_full_intelligence_report(client_id)
    opportunities = report.get('content_opportunities', [])
    
    return jsonify({
        'opportunities': opportunities,
        'total': len(opportunities)
    })


# ==========================================
# CHATBOT CONVERSATION ANALYSIS
# ==========================================

@intelligence_bp.route('/chatbot/<client_id>', methods=['GET'])
@token_required
def analyze_chatbot_conversations(current_user, client_id):
    """
    Analyze chatbot conversations for a client
    
    GET /api/intelligence/chatbot/{client_id}?days=30
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = request.args.get('days', 30, type=int)
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    analysis = service.analyze_chatbot_conversations(client_id, days)
    
    return jsonify(analysis)


# ==========================================
# LEAD FORM ANALYSIS
# ==========================================

@intelligence_bp.route('/forms/<client_id>', methods=['GET'])
@token_required
def analyze_lead_forms(current_user, client_id):
    """
    Analyze lead form submissions for a client
    
    GET /api/intelligence/forms/{client_id}?days=30
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = request.args.get('days', 30, type=int)
    
    from app.services.interaction_intelligence_service import get_interaction_intelligence_service
    service = get_interaction_intelligence_service()
    
    analysis = service.analyze_lead_forms(client_id, days)
    
    return jsonify(analysis)
