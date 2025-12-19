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
    data = request.get_json() or {}
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
    
    data = request.get_json() or {}
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
    
    data = request.get_json() or {}
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
    
    report = service.get_full_intelligence_report(
        client_id,
        call_transcripts=call_transcripts,
        days=days
    )
    
    # Flatten response for frontend compatibility
    combined = report.get('combined_insights', {})
    
    # Extract data from combined insights
    questions = [q['question'] for q in combined.get('top_questions', [])]
    keywords = [k['keyword'] for k in combined.get('top_keywords', [])]
    pain_points = [p['pain_point'] for p in combined.get('top_pain_points', [])]
    services = [s['service'] for s in combined.get('top_services', [])]
    opportunities = [o.get('suggested_title', o.get('topic', '')) for o in report.get('content_opportunities', [])]
    total_interactions = combined.get('total_interactions', 0)
    
    # If no data, provide industry-specific demo data
    if not questions and not keywords:
        client = DBClient.query.get(client_id)
        industry = client.industry.lower() if client and client.industry else 'general'
        
        demo_data = _get_demo_intelligence_data(industry, client.geo if client else '')
        questions = demo_data['questions']
        keywords = demo_data['keywords']
        pain_points = demo_data['pain_points']
        services = demo_data['services']
        opportunities = demo_data['opportunities']
    
    # Calculate intelligence score
    intelligence_score = 0
    if questions: intelligence_score += min(len(questions) * 10, 30)
    if keywords: intelligence_score += min(len(keywords) * 5, 25)
    if pain_points: intelligence_score += min(len(pain_points) * 15, 25)
    if services: intelligence_score += min(len(services) * 10, 20)
    intelligence_score = min(intelligence_score, 100)
    
    flattened = {
        **report,
        # Top-level access for frontend
        'questions': questions,
        'keywords': keywords,
        'pain_points': pain_points,
        'services': services,
        'opportunities': opportunities,
        'intelligence_score': intelligence_score,
        'call_count': total_interactions,
        'total_calls': total_interactions,
        'is_demo_data': total_interactions == 0
    }
    
    return jsonify(flattened)


def _get_demo_intelligence_data(industry: str, geo: str = '') -> dict:
    """Generate demo intelligence data based on industry"""
    location = geo.split(',')[0] if geo else 'your area'
    
    industry_demos = {
        'hvac': {
            'questions': [
                'How much does AC repair cost?',
                'Do you offer same-day service?',
                'How long does AC repair take?',
                'Why is my AC not cooling?',
                "What's the diagnostic fee?"
            ],
            'keywords': ['AC repair', 'not cooling', location, 'same-day', 'cost', 'diagnostic', 'filter', 'emergency', 'HVAC'],
            'pain_points': ['AC running but not cooling', 'House is too hot', 'Concerned about cost'],
            'services': ['AC Diagnostic', 'AC Repair', 'Same-day Service', 'Emergency HVAC'],
            'opportunities': ['Blog: "Why Your AC Isn\'t Cooling"', 'FAQ: AC repair costs', 'Service page: Same-day AC repair']
        },
        'plumbing': {
            'questions': [
                'How much does a plumber charge?',
                'Can you fix a leaky faucet?',
                'Do you do emergency plumbing?',
                'How long to fix a water heater?',
                'Why is my drain clogged?'
            ],
            'keywords': ['plumber', 'leak', 'drain', 'water heater', 'emergency', 'clog', 'faucet', location],
            'pain_points': ['Water leak emergency', 'Drain is completely clogged', 'No hot water'],
            'services': ['Leak Repair', 'Drain Cleaning', 'Water Heater Service', 'Emergency Plumbing'],
            'opportunities': ['Blog: "When to Call an Emergency Plumber"', 'FAQ: Plumbing costs', 'Service page: Drain cleaning']
        },
        'roofing': {
            'questions': [
                'How much does a new roof cost?',
                'Do you fix roof leaks?',
                'What type of roofing do you install?',
                'How long does a roof last?',
                'Do you handle insurance claims?'
            ],
            'keywords': ['roof repair', 'leak', 'shingles', 'insurance', 'storm damage', 'replacement', location],
            'pain_points': ['Roof is leaking', 'Storm damage to roof', 'Shingles are missing'],
            'services': ['Roof Inspection', 'Leak Repair', 'Roof Replacement', 'Insurance Claims'],
            'opportunities': ['Blog: "Signs You Need a New Roof"', 'FAQ: Roof replacement costs', 'Service page: Storm damage repair']
        },
        'pest_control': {
            'questions': [
                'How much does pest control cost?',
                'Do you get rid of termites?',
                'How often should I spray?',
                'Are your products safe for pets?',
                'Do you offer one-time service?'
            ],
            'keywords': ['pest control', 'termites', 'ants', 'roaches', 'exterminator', 'safe', 'spray', location],
            'pain_points': ['Found termite damage', 'Ant infestation in kitchen', 'Concerned about chemicals'],
            'services': ['Termite Treatment', 'General Pest Control', 'One-Time Service', 'Quarterly Plan'],
            'opportunities': ['Blog: "Signs of Termite Infestation"', 'FAQ: Pest control safety', 'Service page: Termite treatment']
        }
    }
    
    return industry_demos.get(industry, {
        'questions': [
            'How much do you charge?',
            'Do you offer free estimates?',
            'How quickly can you come out?',
            'What areas do you serve?',
            'Are you licensed and insured?'
        ],
        'keywords': ['service', 'cost', 'estimate', 'licensed', 'insured', location, 'quality'],
        'pain_points': ['Need urgent help', 'Previous contractor was unreliable', 'Concerned about price'],
        'services': ['Free Estimate', 'Same-Day Service', 'Emergency Service', 'Consultation'],
        'opportunities': ['Blog: "How to Choose the Right Contractor"', 'FAQ: Pricing guide', 'Service page: Service areas']
    })


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
    
    data = request.get_json() or {}
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
    
    data = request.get_json() or {}
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
    
    data = request.get_json() or {}
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
    
    data = request.get_json() or {}
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
