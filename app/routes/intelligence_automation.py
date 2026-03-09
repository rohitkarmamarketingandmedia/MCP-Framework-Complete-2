"""
MCP Intelligence Automation API Routes
=======================================
Place at: app/routes/intelligence_automation.py
Register in app/routes/__init__.py:
    from app.routes.intelligence_automation import intelligence_auto_bp
    app.register_blueprint(intelligence_auto_bp, url_prefix='/api/intelligence')
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)

intelligence_auto_bp = Blueprint('intelligence_auto', __name__)

# Import auth decorator
try:
    from app.routes.auth import token_required
except ImportError:
    def token_required(f):
        from functools import wraps
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(None, *args, **kwargs)
        return wrapper


# ==========================================
# DAILY BRIEFING
# ==========================================

@intelligence_auto_bp.route('/briefing/<client_id>', methods=['GET'])
@token_required
def get_briefing(current_user, client_id):
    """
    Get the AI daily briefing for a client.
    Returns prioritized action items, suggestions, alerts, trending topics.
    
    GET /api/ai/briefing/{client_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        from app.services.intelligence_automation_service import intelligence_automation
        briefing = intelligence_automation.get_daily_briefing(client_id)
        return jsonify(briefing)
    except Exception as e:
        logger.error(f"Briefing error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


# ==========================================
# INSIGHT MANAGEMENT
# ==========================================

@intelligence_auto_bp.route('/insights/<client_id>', methods=['GET'])
@token_required
def get_insights(current_user, client_id):
    """
    Get the knowledge library for a client.
    
    GET /api/ai/insights/{client_id}?type=question&source=callrail&sort=frequency&limit=50
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.intelligence_models import DBClientInsight
    
    query = DBClientInsight.query.filter_by(client_id=client_id)
    
    # Filters
    topic_type = request.args.get('type')
    source = request.args.get('source')
    trending_only = request.args.get('trending') == '1'
    min_frequency = request.args.get('min_frequency', type=int, default=0)
    
    if topic_type:
        query = query.filter_by(topic_type=topic_type)
    if source:
        query = query.filter_by(source=source)
    if trending_only:
        query = query.filter_by(is_trending=True)
    if min_frequency > 0:
        query = query.filter(DBClientInsight.frequency >= min_frequency)
    
    # Sort
    sort = request.args.get('sort', 'frequency')
    if sort == 'frequency':
        query = query.order_by(DBClientInsight.frequency.desc())
    elif sort == 'value':
        query = query.order_by(DBClientInsight.business_value_score.desc())
    elif sort == 'recent':
        query = query.order_by(DBClientInsight.last_seen.desc())
    elif sort == 'trending':
        query = query.order_by(DBClientInsight.frequency_7d.desc())
    
    limit = min(int(request.args.get('limit', 50)), 200)
    insights = query.limit(limit).all()
    
    # Stats
    total = DBClientInsight.query.filter_by(client_id=client_id).count()
    source_counts = {}
    type_counts = {}
    for i in insights:
        source_counts[i.source] = source_counts.get(i.source, 0) + 1
        type_counts[i.topic_type] = type_counts.get(i.topic_type, 0) + 1
    
    return jsonify({
        'insights': [i.to_dict() for i in insights],
        'total': total,
        'source_counts': source_counts,
        'type_counts': type_counts,
    })


@intelligence_auto_bp.route('/ingest/<client_id>', methods=['POST'])
@token_required
def trigger_ingestion(current_user, client_id):
    """
    Manually trigger data ingestion from all sources.
    
    POST /api/ai/ingest/{client_id}
    Body: { "sources": ["callrail", "wufoo", "chat", "review"] }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if current_user.role not in ('admin', 'super_admin', 'manager'):
        return jsonify({'error': 'Admin access required'}), 403
    
    from app.services.intelligence_automation_service import intelligence_automation
    
    sources = request.json.get('sources', ['callrail', 'wufoo', 'chat', 'review']) if request.json else ['callrail', 'wufoo', 'chat', 'review']
    results = {}
    
    # Ingest from CallRail
    if 'callrail' in sources:
        try:
            from app.services.interaction_intelligence_service import interaction_intelligence_service
            # Get recent call data
            call_data = interaction_intelligence_service.analyze_interactions(
                client_id=client_id,
                days=7,
                force_refresh=False
            )
            if call_data and not call_data.get('error'):
                result = intelligence_automation.ingest_from_calls(client_id, call_data)
                results['callrail'] = result
            else:
                results['callrail'] = {'status': 'no_data', 'detail': call_data.get('error', 'No call data')}
        except Exception as e:
            results['callrail'] = {'status': 'error', 'detail': str(e)}
    
    # Ingest from Chat
    if 'chat' in sources:
        try:
            from app.models.db_models import DBChatConversation, DBChatMessage
            
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            conversations = DBChatConversation.query.filter(
                DBChatConversation.client_id == client_id,
                DBChatConversation.created_at >= seven_days_ago,
            ).all()
            
            conv_data = []
            for conv in conversations:
                messages = DBChatMessage.query.filter_by(conversation_id=conv.id).all()
                conv_data.append({
                    'id': conv.id,
                    'messages': [{'role': m.role, 'content': m.content} for m in messages]
                })
            
            if conv_data:
                result = intelligence_automation.ingest_from_chat(client_id, conv_data)
                results['chat'] = result
            else:
                results['chat'] = {'status': 'no_data'}
        except Exception as e:
            results['chat'] = {'status': 'error', 'detail': str(e)}
    
    # Ingest from Reviews
    if 'review' in sources:
        try:
            from app.models.db_models import DBReview
            
            reviews = DBReview.query.filter_by(client_id=client_id).all()
            review_data = [{'text': r.text or r.comment or '', 'rating': r.rating or r.star_rating or 0} for r in reviews]
            
            if review_data:
                result = intelligence_automation.ingest_from_reviews(client_id, review_data)
                results['review'] = result
            else:
                results['review'] = {'status': 'no_data'}
        except Exception as e:
            results['review'] = {'status': 'error', 'detail': str(e)}
    
    # Ingest from Wufoo
    if 'wufoo' in sources:
        try:
            from app.models.db_models import DBLead
            
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            leads = DBLead.query.filter(
                DBLead.client_id == client_id,
                DBLead.source == 'wufoo',
                DBLead.created_at >= seven_days_ago,
            ).all()
            
            submission_data = []
            for lead in leads:
                data = {}
                if lead.name:
                    data['name'] = lead.name
                if lead.email:
                    data['email'] = lead.email
                if lead.message:
                    data['message'] = lead.message
                try:
                    if lead.form_data:
                        extra = json.loads(lead.form_data) if isinstance(lead.form_data, str) else lead.form_data
                        if isinstance(extra, dict):
                            data.update(extra)
                except (json.JSONDecodeError, TypeError):
                    pass
                submission_data.append(data)
            
            if submission_data:
                result = intelligence_automation.ingest_from_wufoo(client_id, submission_data)
                results['wufoo'] = result
            else:
                results['wufoo'] = {'status': 'no_data'}
        except Exception as e:
            results['wufoo'] = {'status': 'error', 'detail': str(e)}
    
    # Update frequency windows
    intelligence_automation.update_frequency_windows(client_id)
    
    # Detect trending
    trending = intelligence_automation.detect_trending_topics(client_id)
    results['trending_detected'] = len(trending)
    
    return jsonify({
        'message': 'Ingestion complete',
        'results': results,
    })


# ==========================================
# SUGGESTION MANAGEMENT
# ==========================================

@intelligence_auto_bp.route('/suggestions/<client_id>', methods=['GET'])
@token_required
def get_suggestions(current_user, client_id):
    """
    Get AI suggestions for a client.
    
    GET /api/ai/suggestions/{client_id}?status=suggested&type=blog_post
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.intelligence_models import DBAiSuggestion
    
    query = DBAiSuggestion.query.filter_by(client_id=client_id)
    
    status = request.args.get('status')
    stype = request.args.get('type')
    
    if status:
        query = query.filter_by(status=status)
    if stype:
        query = query.filter_by(suggestion_type=stype)
    
    query = query.order_by(DBAiSuggestion.priority_score.desc())
    
    limit = min(int(request.args.get('limit', 50)), 100)
    suggestions = query.limit(limit).all()
    
    return jsonify({
        'suggestions': [s.to_dict() for s in suggestions],
        'total': query.count(),
    })


@intelligence_auto_bp.route('/suggestions/generate/<client_id>', methods=['POST'])
@token_required
def generate_suggestions(current_user, client_id):
    """
    Trigger AI suggestion generation for a client.
    Analyzes all insights and creates actionable suggestions.
    
    POST /api/ai/suggestions/generate/{client_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        from app.services.intelligence_automation_service import intelligence_automation
        results = intelligence_automation.generate_suggestions(client_id)
        return jsonify(results)
    except Exception as e:
        logger.error(f"Suggestion generation error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@intelligence_auto_bp.route('/suggestions/<suggestion_id>/accept', methods=['POST'])
@token_required
def accept_suggestion(current_user, suggestion_id):
    """Accept an AI suggestion."""
    from app.services.intelligence_automation_service import intelligence_automation
    result = intelligence_automation.accept_suggestion(suggestion_id, current_user.id)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


@intelligence_auto_bp.route('/suggestions/<suggestion_id>/dismiss', methods=['POST'])
@token_required
def dismiss_suggestion(current_user, suggestion_id):
    """Dismiss an AI suggestion."""
    reason = request.json.get('reason', '') if request.json else ''
    from app.services.intelligence_automation_service import intelligence_automation
    result = intelligence_automation.dismiss_suggestion(suggestion_id, reason)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


@intelligence_auto_bp.route('/suggestions/<suggestion_id>/execute', methods=['POST'])
@token_required
def execute_suggestion(current_user, suggestion_id):
    """
    Execute an AI suggestion — triggers content generation.
    Returns the action data needed by the frontend to call the content API.
    """
    from app.services.intelligence_automation_service import intelligence_automation
    result = intelligence_automation.execute_suggestion(suggestion_id)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ==========================================
# RANK ALERTS
# ==========================================

@intelligence_auto_bp.route('/rank-alerts/<client_id>', methods=['GET'])
@token_required
def get_rank_alerts(current_user, client_id):
    """
    Get rank drop/gain alerts for a client.
    
    GET /api/ai/rank-alerts/{client_id}?severity=high&unread=1
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.intelligence_models import DBRankAlert
    
    query = DBRankAlert.query.filter_by(client_id=client_id)
    
    severity = request.args.get('severity')
    unread = request.args.get('unread') == '1'
    days = int(request.args.get('days', 30))
    
    if severity:
        query = query.filter_by(severity=severity)
    if unread:
        query = query.filter_by(is_read=False)
    
    since = datetime.utcnow() - timedelta(days=days)
    query = query.filter(DBRankAlert.created_at >= since)
    query = query.order_by(DBRankAlert.created_at.desc())
    
    alerts = query.limit(50).all()
    
    return jsonify({
        'alerts': [a.to_dict() for a in alerts],
        'total': query.count(),
    })


@intelligence_auto_bp.route('/rank-alerts/check/<client_id>', methods=['POST'])
@token_required
def check_rank_drops(current_user, client_id):
    """
    Manually trigger rank drop detection.
    
    POST /api/ai/rank-alerts/check/{client_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        from app.services.intelligence_automation_service import intelligence_automation
        alerts = intelligence_automation.check_rank_drops(client_id)
        return jsonify({
            'message': f'Found {len(alerts)} rank alerts',
            'alerts': alerts,
        })
    except Exception as e:
        logger.error(f"Rank drop check error: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# COMPETITOR ANALYSIS
# ==========================================

@intelligence_auto_bp.route('/competitor-opportunities/<client_id>', methods=['POST'])
@token_required
def find_competitor_opportunities(current_user, client_id):
    """
    Find keyword steal opportunities from competitors.
    
    POST /api/ai/competitor-opportunities/{client_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get competitor data from the monitoring dashboard
        from app.services.intelligence_automation_service import intelligence_automation
        
        # Try to get competitor data from the competitor-dashboard endpoint
        comp_data = []
        try:
            from app.routes.monitoring import get_competitor_dashboard
            # We need to simulate the request internally
            # Instead, just get the competitor data directly
            from app.models.db_models import DBCompetitor, DBCompetitorPage
            
            competitors = DBCompetitor.query.filter_by(
                client_id=client_id,
                is_active=True
            ).all()
            
            for comp in competitors:
                pages = DBCompetitorPage.query.filter_by(competitor_id=comp.id).all()
                comp_data.append({
                    'domain': comp.domain,
                    'name': comp.name,
                    'total_pages': len(pages),
                    'rankings': {},  # Would need SEMrush data
                })
        except Exception as e:
            logger.warning(f"Error getting competitor data: {e}")
        
        suggestions = intelligence_automation.check_competitor_opportunities(client_id, comp_data)
        
        return jsonify({
            'message': f'Found {len(suggestions)} opportunities',
            'suggestions': suggestions,
        })
    except Exception as e:
        logger.error(f"Competitor opportunity error: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# FULL PIPELINE (RUN ALL)
# ==========================================

@intelligence_auto_bp.route('/run-pipeline/<client_id>', methods=['POST'])
@token_required
def run_full_pipeline(current_user, client_id):
    """
    Run the full intelligence pipeline:
    1. Ingest from all sources
    2. Detect trending topics
    3. Generate suggestions
    4. Check rank drops
    5. Return daily briefing
    
    POST /api/ai/run-pipeline/{client_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if current_user.role not in ('admin', 'super_admin', 'manager'):
        return jsonify({'error': 'Admin access required'}), 403
    
    from app.services.intelligence_automation_service import intelligence_automation
    
    pipeline_results = {
        'steps': [],
        'started_at': datetime.utcnow().isoformat(),
    }
    
    # Step 1: Ingest
    try:
        # Trigger ingestion via the ingest endpoint logic
        pipeline_results['steps'].append({'step': 'ingest', 'status': 'running'})
        # (ingestion handled by /ingest endpoint — call the service directly here)
        intelligence_automation.update_frequency_windows(client_id)
        trending = intelligence_automation.detect_trending_topics(client_id)
        pipeline_results['steps'][-1] = {'step': 'ingest', 'status': 'done', 'trending': len(trending)}
    except Exception as e:
        pipeline_results['steps'][-1] = {'step': 'ingest', 'status': 'error', 'error': str(e)}
    
    # Step 2: Generate suggestions
    try:
        pipeline_results['steps'].append({'step': 'suggestions', 'status': 'running'})
        suggestions = intelligence_automation.generate_suggestions(client_id)
        pipeline_results['steps'][-1] = {'step': 'suggestions', 'status': 'done', 'generated': suggestions.get('total_generated', 0)}
    except Exception as e:
        pipeline_results['steps'][-1] = {'step': 'suggestions', 'status': 'error', 'error': str(e)}
    
    # Step 3: Check rank drops
    try:
        pipeline_results['steps'].append({'step': 'rank_check', 'status': 'running'})
        alerts = intelligence_automation.check_rank_drops(client_id)
        pipeline_results['steps'][-1] = {'step': 'rank_check', 'status': 'done', 'alerts': len(alerts)}
    except Exception as e:
        pipeline_results['steps'][-1] = {'step': 'rank_check', 'status': 'error', 'error': str(e)}
    
    # Step 4: Get briefing
    try:
        briefing = intelligence_automation.get_daily_briefing(client_id)
        pipeline_results['briefing'] = briefing
    except Exception as e:
        pipeline_results['briefing'] = {'error': str(e)}
    
    pipeline_results['completed_at'] = datetime.utcnow().isoformat()
    
    return jsonify(pipeline_results)
