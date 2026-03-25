"""
MCP Framework - Customer Intelligence Routes
Routes for analyzing interactions and generating content from customer data
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from typing import List, Dict
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
        
        logger.info(f"Fetching CallRail calls for company {callrail_company_id}, account {callrail_account_id or 'global'}, days={days}")
        
        # Get calls from CallRail
        callrail = get_callrail_service()
        calls = callrail.get_recent_calls(
            company_id=callrail_company_id,
            account_id=callrail_account_id,  # Pass per-client account ID
            limit=100,
            include_recordings=True,
            include_transcripts=True,
            days=days  # Pass days parameter
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
    
    # Get client info for validation
    client = DBClient.query.get(client_id)
    client_name = client.business_name if client else 'Unknown'
    client_industry = client.industry.lower() if client and client.industry else None
    
    try:
        from app.services.callrail_service import CallRailConfig, get_callrail_service
        
        if CallRailConfig.is_configured():
            callrail_company_id = getattr(client, 'callrail_company_id', None)
            callrail_account_id = getattr(client, 'callrail_account_id', None)
            
            # STRICT: Only fetch if company_id is set for THIS client
            if callrail_company_id:
                logger.info(f"=" * 60)
                logger.info(f"Intelligence report for: {client_name} (ID: {client_id})")
                logger.info(f"Industry: {client_industry}")
                logger.info(f"CallRail company_id: {callrail_company_id}")
                logger.info(f"CallRail account_id: {callrail_account_id or 'global'}")
                logger.info(f"=" * 60)
                
                callrail = get_callrail_service()
                all_calls = callrail.get_recent_calls(
                    company_id=callrail_company_id,
                    account_id=callrail_account_id,
                    days=days,
                    limit=100
                )
                total_calls = len(all_calls)
                logger.info(f"Got {total_calls} calls from CallRail")
                
                # Log first few calls for debugging
                for i, call in enumerate(all_calls[:3]):
                    logger.info(f"Call {i+1}: date={call.get('date')}, duration={call.get('duration')}, has_transcript={call.get('has_transcript')}")
                    if call.get('transcript'):
                        preview = call.get('transcript', '')[:100]
                        logger.info(f"  Transcript preview: {preview}...")
                
                # Extract transcripts from calls that have them
                call_transcripts = [
                    {
                        'id': c['id'], 
                        'transcript': c.get('transcript', '') or c.get('transcript_preview', ''), 
                        'date': c['date'],
                        'duration': c.get('duration', 0)
                    }
                    for c in all_calls if c.get('has_transcript') and (c.get('transcript') or c.get('transcript_preview'))
                ]
                logger.info(f"{len(call_transcripts or [])} calls have transcripts")
                
                if call_transcripts:
                    # Log first transcript for debugging
                    first = call_transcripts[0]
                    first_transcript = first.get('transcript', '')
                    logger.info(f"First transcript ({len(first_transcript)} chars): {first_transcript[:200]}...")
            else:
                logger.info(f"Intelligence report for {client_name}: NO CallRail company_id set - skipping CallRail data")
    except Exception as e:
        logger.warning(f"Could not fetch CallRail data: {e}")
        import traceback
        traceback.print_exc()
    
    # Pass client industry to the service for better filtering
    report = service.get_full_intelligence_report(
        client_id,
        call_transcripts=call_transcripts,
        days=days,
        all_calls=all_calls
    )
    
    # Add metadata to report
    report['call_count'] = total_calls
    report['calls_with_transcripts'] = len(call_transcripts) if call_transcripts else 0
    report['client_name'] = client_name
    report['client_industry'] = client_industry
    
    # If we have calls but no transcripts, generate metadata-based insights
    if total_calls > 0 and not call_transcripts:
        logger.info(f"Generating metadata insights for {total_calls} calls (no transcripts)")
        try:
            report['metadata_insights'] = _generate_metadata_insights(all_calls)
            report['transcript_note'] = 'Call transcripts require CallRail Conversation Intelligence add-on. Showing insights from call metadata.'
            logger.info(f"Metadata insights generated: {report['metadata_insights'].get('call_summary', {})}")
        except Exception as e:
            logger.error(f"Error generating metadata insights: {e}")
            import traceback
            traceback.print_exc()

    # ── AI-POWERED INSIGHT REFINEMENT ──────────────────────────
    # If we have combined_insights with raw questions, run them through Claude
    # to deduplicate, categorize and produce genuinely useful insights.
    combined = report.get('combined_insights')
    if combined and combined.get('top_questions'):
        try:
            refined = _refine_insights_with_ai(
                combined, client_name, client_industry, client_id
            )
            if refined:
                report['combined_insights'] = refined
                logger.info("AI-refined insights applied")
        except Exception as e:
            logger.warning(f"AI insight refinement failed, using raw data: {e}")

    return jsonify(report)


# ──────────────────────────────────────────────────────────────
# AI Insight Refinement — in-memory cache (client_id → {ts, data})
# ──────────────────────────────────────────────────────────────
_AI_INSIGHT_CACHE: Dict[str, dict] = {}
_AI_INSIGHT_CACHE_TTL = 3600 * 4  # 4 hours


def _refine_insights_with_ai(
    raw_insights: Dict,
    client_name: str,
    client_industry: str,
    client_id: str,
) -> Dict | None:
    """
    Send raw extracted call data through Claude to:
    1. Deduplicate near-identical questions
    2. Rephrase conversational fragments into clean FAQ-style questions
    3. Categorize pain points (pricing, scheduling, trust, urgency)
    4. Rank by business impact / content opportunity value
    5. Generate an "executive summary" of what callers care about

    Returns a replacement `combined_insights` dict, or None on failure.
    Caches results for _AI_INSIGHT_CACHE_TTL seconds per client.
    """
    import time, json as _json

    # Check cache
    cached = _AI_INSIGHT_CACHE.get(client_id)
    if cached and (time.time() - cached['ts']) < _AI_INSIGHT_CACHE_TTL:
        logger.info(f"Using cached AI insights for {client_id}")
        return cached['data']

    # Build concise input from raw data
    raw_questions = [
        q.get('question', q) if isinstance(q, dict) else q
        for q in (raw_insights.get('top_questions') or [])[:30]
    ]
    raw_pain_points = [
        p.get('pain_point', p) if isinstance(p, dict) else p
        for p in (raw_insights.get('top_pain_points') or [])[:15]
    ]
    raw_keywords = [
        k.get('keyword', k) if isinstance(k, dict) else k
        for k in (raw_insights.get('top_keywords') or [])[:30]
    ]
    raw_services = [
        s.get('service', s) if isinstance(s, dict) else s
        for s in (raw_insights.get('services_requested') or [])[:15]
    ]

    if not raw_questions:
        return None

    prompt = f"""You are analyzing phone call data for "{client_name}", a {client_industry or 'local service'} business.

Below are RAW questions, pain points, keywords and services extracted directly from call transcripts. Many are duplicates, conversational fragments, or scheduling chatter.

RAW CUSTOMER QUESTIONS (may have duplicates/fragments):
{chr(10).join(f'- {q}' for q in raw_questions)}

RAW PAIN POINTS:
{chr(10).join(f'- {p}' for p in raw_pain_points) if raw_pain_points else '(none extracted)'}

RAW KEYWORDS MENTIONED:
{', '.join(raw_keywords[:20]) if raw_keywords else '(none)'}

RAW SERVICES REQUESTED:
{', '.join(raw_services[:10]) if raw_services else '(none)'}

TASK: Transform this raw data into polished, actionable business intelligence. Return ONLY valid JSON:
{{
  "executive_summary": "2-3 sentence summary of what customers care most about and the biggest business opportunity",
  "top_questions": ["question1", "question2", ...],
  "top_pain_points": ["pain1", "pain2", ...],
  "top_keywords": ["keyword1", "keyword2", ...],
  "services_requested": ["service1", "service2", ...],
  "content_recommendations": ["recommendation1", "recommendation2", ...]
}}

RULES for top_questions (return 8-12):
- Merge duplicates and near-duplicates into ONE clean question
- Rewrite conversational fragments as clear FAQ-style questions (e.g. "how much is a cleaning?" → "How much does a dental cleaning cost?")
- REMOVE scheduling/availability questions ("can I come in tomorrow?", "what time are you open?")
- REMOVE generic pleasantries ("can you help me?", "is there any way?")
- KEEP only questions a potential customer would Google or want answered on a website
- Sort by business value (questions that would make the best blog/FAQ content first)

RULES for top_pain_points (return 3-6):
- Summarize into clear, concise pain points
- Focus on emotional/financial concerns (cost worry, urgency, trust, past bad experience)
- Remove duplicates

RULES for top_keywords (return 10-15):
- Only include industry-relevant SEO keywords
- Remove generic words (schedule, appointment, time, today, tomorrow, phone, call)
- Include service-specific terms customers actually use

RULES for services_requested (return 3-8):
- Clean service names (e.g. "Root Canal" not "i need a root canal done")
- Deduplicate
- Sort by frequency

RULES for content_recommendations (return 3-5):
- Specific blog post or FAQ ideas based on what customers actually ask about
- Format: "Blog: [title idea]" or "FAQ: [topic]"
"""

    import anthropic as _anthropic
    import time as _time

    # Haiku first (faster, lower-load), Sonnet as quality upgrade if Haiku fails.
    # max_retries=0 disables the SDK's own retry loop so we control all backoff
    # ourselves — prevents the double-retry storm seen in logs.
    model_sequence = [
        ("claude-haiku-4-5-20251001",  1500),   # Haiku — 3 attempts, 2s/4s/6s backoff
        ("claude-sonnet-4-20250514",   2000),   # Sonnet — 2 attempts, 3s/6s backoff
    ]

    ai_client = _anthropic.Anthropic(max_retries=0)  # we handle all retries manually

    for model, max_tok in model_sequence:
        max_attempts = 3 if 'haiku' in model else 2
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = ai_client.messages.create(
                    model=model,
                    max_tokens=max_tok,
                    temperature=0.3,
                    system="You are a business intelligence analyst. Return ONLY valid JSON, no markdown.",
                    messages=[{"role": "user", "content": prompt}],
                )
                text = "".join(b.text for b in response.content if hasattr(b, 'text')).strip()

                # Strip possible markdown fences
                text = text.replace('```json', '').replace('```', '').strip()
                result = _json.loads(text)

                refined = dict(raw_insights)
                refined['top_questions']           = result.get('top_questions',           raw_insights.get('top_questions', []))
                refined['top_pain_points']         = result.get('top_pain_points',         raw_insights.get('top_pain_points', []))
                refined['top_keywords']            = result.get('top_keywords',            raw_insights.get('top_keywords', []))
                refined['services_requested']      = result.get('services_requested',      raw_insights.get('services_requested', []))
                refined['content_recommendations'] = result.get('content_recommendations', [])
                refined['executive_summary']       = result.get('executive_summary', '')
                refined['ai_refined'] = True
                refined['ai_model']   = model

                _AI_INSIGHT_CACHE[client_id] = {'ts': _time.time(), 'data': refined}
                logger.info(f"AI insight refinement complete ({model}, attempt {attempt+1}): "
                            f"{len(refined['top_questions'])} questions, {len(refined['top_pain_points'])} pain points")
                return refined

            except Exception as e:
                last_error = e
                err_str = str(e)
                is_overloaded = '529' in err_str or 'overloaded' in err_str.lower()
                is_rate_limit  = '429' in err_str or 'rate' in err_str.lower()

                if is_overloaded or is_rate_limit:
                    # Exponential backoff: 2s, 4s, 6s
                    wait = (attempt + 1) * 2.0
                    logger.warning(f"Claude {model} {'overloaded' if is_overloaded else 'rate-limited'} "
                                   f"(attempt {attempt+1}/{max_attempts}), waiting {wait}s…")
                    _time.sleep(wait)
                    continue

                # Non-retriable error (auth, bad request, etc.) — skip to next model
                logger.warning(f"Claude {model} non-retriable error: {e}")
                break

        logger.warning(f"Claude {model} exhausted all {max_attempts} attempts, last error: {last_error}")

    logger.error("AI insight refinement failed on all models — returning raw insights")
    return None


def _generate_metadata_insights(calls: List[Dict]) -> Dict:
    """Generate useful insights from call metadata when transcripts aren't available"""
    if not calls:
        return {}
    
    # Analyze call patterns
    total_calls = len(calls)
    answered_calls = sum(1 for c in calls if c.get('answered'))
    voicemails = sum(1 for c in calls if c.get('voicemail'))
    
    # Duration analysis
    durations = [c.get('duration', 0) for c in calls]
    avg_duration = sum(durations) / len(durations) if durations else 0
    long_calls = sum(1 for d in durations if d > 120)  # Over 2 minutes
    
    # Time patterns
    call_hours = []
    call_days = []
    for call in calls:
        if call.get('date'):
            try:
                dt = datetime.fromisoformat(call['date'].replace('Z', '+00:00'))
                call_hours.append(dt.hour)
                call_days.append(dt.strftime('%A'))
            except:
                pass
    
    # Find peak hours
    from collections import Counter
    hour_counts = Counter(call_hours)
    peak_hours = hour_counts.most_common(3)
    day_counts = Counter(call_days)
    busiest_days = day_counts.most_common(3)
    
    # Caller locations (from city if available)
    locations = []
    for call in calls:
        if isinstance(call.get('caller_name'), str):
            # Extract city from caller info if present
            pass
    
    return {
        'call_summary': {
            'total_calls': total_calls,
            'answered': answered_calls,
            'answer_rate': round(answered_calls / total_calls * 100) if total_calls else 0,
            'voicemails': voicemails,
            'avg_duration_seconds': round(avg_duration),
            'avg_duration_formatted': f"{int(avg_duration // 60)}:{int(avg_duration % 60):02d}",
            'long_calls': long_calls,
            'long_call_rate': round(long_calls / total_calls * 100) if total_calls else 0
        },
        'peak_times': {
            'busiest_hours': [
                {'hour': h, 'count': c, 'display': f"{h}:00 - {h+1}:00"}
                for h, c in peak_hours
            ],
            'busiest_days': [
                {'day': d, 'count': c}
                for d, c in busiest_days
            ]
        },
        'recommendations': _generate_recommendations_from_metadata(
            answer_rate=answered_calls / total_calls * 100 if total_calls else 0,
            avg_duration=avg_duration,
            peak_hours=peak_hours
        )
    }


def _generate_recommendations_from_metadata(answer_rate: float, avg_duration: float, peak_hours: list) -> List[str]:
    """Generate actionable recommendations from call metadata"""
    recommendations = []
    
    if answer_rate < 80:
        recommendations.append("Consider adding more staff during peak hours - missing calls means missing leads")
    
    if answer_rate < 60:
        recommendations.append("High missed call rate! Consider call forwarding or answering service")
    
    if avg_duration < 60:
        recommendations.append("Short average call duration - ensure staff are engaging callers effectively")
    
    if avg_duration > 300:
        recommendations.append("Long average call duration - consider FAQ page to answer common questions before calls")
    
    if peak_hours:
        peak_hour = peak_hours[0][0]
        if 8 <= peak_hour <= 10:
            recommendations.append("Morning is your busiest time - ensure full staff coverage 8-11 AM")
        elif 12 <= peak_hour <= 14:
            recommendations.append("Lunch hour is busy - consider staggered lunch breaks for staff")
        elif 16 <= peak_hour <= 18:
            recommendations.append("Late afternoon is peak time - maintain coverage until 6 PM")
    
    if not recommendations:
        recommendations.append("Good call patterns! Consider enabling CallRail Conversation Intelligence for deeper insights")
    
    return recommendations


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
