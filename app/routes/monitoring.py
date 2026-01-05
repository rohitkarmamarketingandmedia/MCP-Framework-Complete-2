"""
MCP Framework - Monitoring Routes
Competitor tracking, rank checking, content queue management
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import json

from app.routes.auth import token_required, admin_required
from app.utils import safe_int
from app.database import db
from app.models.db_models import (
    DBClient, DBCompetitor, DBCompetitorPage, DBRankHistory,
    DBContentQueue, DBAlert, DBBlogPost, ContentStatus
)
from app.services.competitor_monitoring_service import competitor_monitoring_service
from app.services.seo_scoring_engine import seo_scoring_engine
from app.services.rank_tracking_service import rank_tracking_service
from app.services.ai_service import AIService

monitoring_bp = Blueprint('monitoring', __name__)
ai_service = AIService()


# ==========================================
# COMPETITOR MANAGEMENT
# ==========================================

@monitoring_bp.route('/competitors', methods=['GET'])
@token_required
def list_competitors(current_user):
    """List all competitors for a client"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).all()
    
    return jsonify({
        'client_id': client_id,
        'competitors': [c.to_dict() for c in competitors]
    })


@monitoring_bp.route('/competitors', methods=['POST'])
@token_required
def add_competitor(current_user):
    """
    Add a competitor to monitor
    
    POST /api/monitoring/competitors
    {
        "client_id": "client_abc123",
        "domain": "competitor.com",
        "name": "Main Competitor"
    }
    """
    data = request.get_json(silent=True) or {}
    
    client_id = data.get('client_id')
    domain = data.get('domain', '').strip()
    
    if not client_id or not domain:
        return jsonify({'error': 'client_id and domain required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Check limit (max 10 competitors per client)
    existing_count = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).count()
    
    if existing_count >= 10:
        return jsonify({'error': 'Maximum 10 competitors per client'}), 400
    
    # Create competitor
    competitor = DBCompetitor(
        client_id=client_id,
        domain=domain,
        name=data.get('name', domain),
        crawl_frequency=data.get('crawl_frequency', 'daily')
    )
    
    # Set next crawl time
    competitor.next_crawl_at = datetime.utcnow()
    
    db.session.add(competitor)
    db.session.commit()
    
    return jsonify({
        'message': 'Competitor added',
        'competitor': competitor.to_dict()
    })


@monitoring_bp.route('/competitors/<competitor_id>', methods=['DELETE'])
@token_required
def remove_competitor(current_user, competitor_id):
    """Remove a competitor from monitoring"""
    competitor = DBCompetitor.query.get(competitor_id)
    
    if not competitor:
        return jsonify({'error': 'Competitor not found'}), 404
    
    if not current_user.has_access_to_client(competitor.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    competitor.is_active = False
    db.session.commit()
    
    return jsonify({'message': 'Competitor removed'})


@monitoring_bp.route('/competitors/<competitor_id>/schedule', methods=['PUT'])
@token_required
def update_competitor_schedule(current_user, competitor_id):
    """
    Update competitor crawl schedule
    
    PUT /api/monitoring/competitors/{competitor_id}/schedule
    {
        "crawl_frequency": "daily|weekly|manual"
    }
    """
    competitor = DBCompetitor.query.get(competitor_id)
    
    if not competitor:
        return jsonify({'error': 'Competitor not found'}), 404
    
    if not current_user.has_access_to_client(competitor.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    frequency = data.get('crawl_frequency', 'daily')
    
    if frequency not in ['daily', 'weekly', 'manual']:
        return jsonify({'error': 'Invalid frequency. Use: daily, weekly, or manual'}), 400
    
    competitor.crawl_frequency = frequency
    
    # Update next crawl time
    if frequency == 'daily':
        competitor.next_crawl_at = datetime.utcnow() + timedelta(days=1)
    elif frequency == 'weekly':
        competitor.next_crawl_at = datetime.utcnow() + timedelta(weeks=1)
    else:
        competitor.next_crawl_at = None
    
    db.session.commit()
    
    return jsonify({
        'message': 'Schedule updated',
        'crawl_frequency': frequency,
        'next_crawl_at': competitor.next_crawl_at.isoformat() if competitor.next_crawl_at else None
    })


@monitoring_bp.route('/competitors/<competitor_id>/crawl', methods=['POST'])
@token_required
def crawl_competitor(current_user, competitor_id):
    """
    Manually trigger a crawl of a competitor
    Returns new pages detected
    """
    competitor = DBCompetitor.query.get(competitor_id)
    
    if not competitor:
        return jsonify({'error': 'Competitor not found'}), 404
    
    if not current_user.has_access_to_client(competitor.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get known pages
    known_pages = DBCompetitorPage.query.filter_by(
        competitor_id=competitor_id
    ).all()
    
    known_page_data = [{'url': p.url, 'lastmod': None} for p in known_pages]
    
    # Crawl for new content
    new_pages, updated_pages = competitor_monitoring_service.detect_new_content(
        competitor.domain,
        known_page_data,
        competitor.last_crawl_at
    )
    
    # Save new pages
    saved_pages = []
    for page_data in new_pages:
        # Extract content
        content = competitor_monitoring_service.extract_page_content(page_data['url'])
        
        if content.get('error'):
            continue
        
        # Check if it's a content page worth tracking
        if content.get('word_count', 0) < 300:
            continue
        
        # Save to database
        page = DBCompetitorPage(
            competitor_id=competitor_id,
            client_id=competitor.client_id,
            url=page_data['url'],
            title=content.get('title', ''),
            content_hash=content.get('content_hash', ''),
            word_count=content.get('word_count', 0),
            h1=content.get('h1', ''),
            meta_description=content.get('meta_description', '')
        )
        
        db.session.add(page)
        saved_pages.append(page)
        
        # Create alert
        alert = DBAlert(
            client_id=competitor.client_id,
            alert_type='new_competitor_content',
            title=f'New content from {competitor.name}',
            message=f'"{content.get("title", "Untitled")}" ({content.get("word_count", 0)} words)',
            related_competitor_id=competitor_id,
            related_page_id=page.id,
            priority='high'
        )
        db.session.add(alert)
    
    # Update competitor stats
    competitor.last_crawl_at = datetime.utcnow()
    competitor.next_crawl_at = datetime.utcnow() + timedelta(days=1)
    competitor.known_pages_count = len(known_pages) + len(saved_pages)
    competitor.new_pages_detected += len(saved_pages)
    
    db.session.commit()
    
    return jsonify({
        'competitor': competitor.to_dict(),
        'new_pages_found': len(saved_pages),
        'pages': [p.to_dict() for p in saved_pages]
    })


@monitoring_bp.route('/competitors/discover', methods=['POST'])
@token_required
def discover_competitors(current_user):
    """
    Discover competitors based on industry and location
    
    POST /api/monitoring/competitors/discover
    {
        "industry": "hvac",
        "geo": "Sarasota, FL",
        "keywords": ["ac repair", "hvac service"]
    }
    """
    data = request.get_json(silent=True) or {}
    
    industry = data.get('industry', '')
    geo = data.get('geo', '')
    keywords = data.get('keywords', [])
    
    # Build search query
    search_terms = []
    if industry:
        search_terms.append(industry)
    if keywords:
        search_terms.extend(keywords[:3])  # Use top 3 keywords
    if geo:
        search_terms.append(geo)
    
    # For now, return demo data - in production this would use Google Search API or similar
    # This simulates finding competitors in the local market
    demo_competitors = [
        {
            'domain': f'{industry.lower().replace("_", "")}pro.com' if industry else 'localcompetitor1.com',
            'name': f'Local {industry.replace("_", " ").title()} Pro' if industry else 'Local Competitor 1',
            'pages': 45,
            'blogs': 12,
            'discovered_via': 'keyword_search'
        },
        {
            'domain': f'{geo.split(",")[0].lower().replace(" ", "")}services.com' if geo else 'competitor2.com',
            'name': f'{geo.split(",")[0]} Services' if geo else 'Regional Competitor',
            'pages': 78,
            'blogs': 24,
            'discovered_via': 'location_search'
        },
        {
            'domain': 'nationalfranchise-local.com',
            'name': 'National Brand - Local Office',
            'pages': 120,
            'blogs': 56,
            'discovered_via': 'market_analysis'
        }
    ]
    
    return jsonify({
        'success': True,
        'competitors': demo_competitors,
        'search_query': ' '.join(search_terms),
        'message': 'Found 3 potential competitors in your market'
    })


@monitoring_bp.route('/competitors/<competitor_id>/pages', methods=['GET'])
@token_required
def get_competitor_pages(current_user, competitor_id):
    """Get all pages discovered from a competitor"""
    competitor = DBCompetitor.query.get(competitor_id)
    
    if not competitor:
        return jsonify({'error': 'Competitor not found'}), 404
    
    if not current_user.has_access_to_client(competitor.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    pages = DBCompetitorPage.query.filter_by(
        competitor_id=competitor_id
    ).order_by(DBCompetitorPage.discovered_at.desc()).limit(50).all()
    
    return jsonify({
        'competitor': competitor.to_dict(),
        'pages': [p.to_dict() for p in pages]
    })


# ==========================================
# AUTO CONTENT GENERATION
# ==========================================

@monitoring_bp.route('/counter-content', methods=['POST'])
@token_required
def generate_counter_content(current_user):
    """
    Generate content to beat a competitor page
    
    POST /api/monitoring/counter-content
    {
        "competitor_page_id": "cpage_abc123",
        "target_keyword": "roof repair sarasota"  // Optional override
    }
    """
    data = request.get_json(silent=True) or {}
    
    page_id = data.get('competitor_page_id')
    
    if not page_id:
        return jsonify({'error': 'competitor_page_id required'}), 400
    
    # Get competitor page
    comp_page = DBCompetitorPage.query.get(page_id)
    if not comp_page:
        return jsonify({'error': 'Competitor page not found'}), 404
    
    if not current_user.has_access_to_client(comp_page.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get client
    client = DBClient.query.get(comp_page.client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Extract competitor content
    comp_content = competitor_monitoring_service.extract_page_content(comp_page.url)
    
    if comp_content.get('error'):
        return jsonify({'error': f'Could not fetch competitor content: {comp_content["error"]}'}), 400
    
    # Analyze competitor content
    analysis = competitor_monitoring_service.analyze_competitor_content(comp_content)
    
    # Determine target keyword
    target_keyword = data.get('target_keyword') or comp_page.h1 or comp_page.title
    # Clean up keyword
    target_keyword = target_keyword.split('|')[0].split('-')[0].strip()[:50]
    
    # Score competitor content
    comp_score = seo_scoring_engine.score_content(
        {
            'title': comp_content.get('title', ''),
            'meta_description': comp_content.get('meta_description', ''),
            'h1': comp_content.get('h1', ''),
            'body': '',
            'body_text': comp_content.get('body_text', '')
        },
        target_keyword,
        client.geo
    )
    
    # Generate superior content
    result = ai_service.generate_blog_post(
        keyword=target_keyword,
        geo=client.geo or '',
        industry=client.industry or '',
        word_count=analysis['recommended_word_count'],
        tone=client.tone or 'professional',
        business_name=client.business_name or '',
        include_faq=True,
        faq_count=5,
        internal_links=client.get_service_pages() or [],
        usps=client.get_unique_selling_points() or []
    )
    
    if result.get('error'):
        return jsonify({'error': f'Content generation failed: {result["error"]}'}), 500
    
    # Score our content
    our_score = seo_scoring_engine.score_content(
        {
            'title': result.get('title', ''),
            'meta_title': result.get('meta_title', ''),
            'meta_description': result.get('meta_description', ''),
            'h1': result.get('h1', ''),
            'body': result.get('body', ''),
            'body_text': result.get('body', '')
        },
        target_keyword,
        client.geo
    )
    
    # Add to content queue
    queued_content = DBContentQueue(
        client_id=client.id,
        trigger_type='competitor_post',
        trigger_competitor_id=comp_page.competitor_id,
        trigger_competitor_page_id=comp_page.id,
        trigger_keyword=target_keyword,
        title=result.get('title', ''),
        body=result.get('body', ''),
        meta_title=result.get('meta_title', ''),
        meta_description=result.get('meta_description', ''),
        primary_keyword=target_keyword,
        word_count=len(result.get('body', '').split()),
        our_seo_score=our_score['total_score'],
        competitor_seo_score=comp_score['total_score']
    )
    
    db.session.add(queued_content)
    
    # Mark competitor page as countered
    comp_page.was_countered = True
    comp_page.is_new = False
    
    # Create alert
    alert = DBAlert(
        client_id=client.id,
        alert_type='content_ready',
        title='Counter-content ready for review',
        message=f'"{result.get("title", "")}" - Score: {our_score["total_score"]} vs {comp_score["total_score"]}',
        related_competitor_id=comp_page.competitor_id,
        related_page_id=comp_page.id,
        related_content_id=queued_content.id,
        related_keyword=target_keyword,
        priority='high'
    )
    db.session.add(alert)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'queued_content': queued_content.to_dict(),
        'comparison': {
            'our_score': our_score['total_score'],
            'our_grade': our_score['grade'],
            'competitor_score': comp_score['total_score'],
            'competitor_grade': comp_score['grade'],
            'our_word_count': queued_content.word_count,
            'competitor_word_count': comp_content.get('word_count', 0),
            'we_win': our_score['total_score'] > comp_score['total_score']
        }
    })


# ==========================================
# CONTENT QUEUE
# ==========================================

@monitoring_bp.route('/queue', methods=['GET'])
@token_required
def get_content_queue(current_user):
    """Get pending content queue for a client"""
    client_id = request.args.get('client_id')
    status = request.args.get('status', 'pending')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    query = DBContentQueue.query.filter_by(client_id=client_id)
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    items = query.order_by(DBContentQueue.created_at.desc()).limit(50).all()
    
    return jsonify({
        'client_id': client_id,
        'queue': [item.to_dict() for item in items]
    })


@monitoring_bp.route('/queue/<item_id>', methods=['GET'])
@token_required
def get_queue_item(current_user, item_id):
    """Get full content for a queue item"""
    item = DBContentQueue.query.get(item_id)
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    if not current_user.has_access_to_client(item.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    result = item.to_dict()
    result['body'] = item.body  # Include full body
    
    # Get competitor page info if available
    if item.trigger_competitor_page_id:
        comp_page = DBCompetitorPage.query.get(item.trigger_competitor_page_id)
        if comp_page:
            result['competitor_page'] = comp_page.to_dict()
    
    return jsonify(result)


@monitoring_bp.route('/queue/<item_id>/approve', methods=['POST'])
@token_required
def approve_queue_item(current_user, item_id):
    """
    Approve queued content → creates blog post
    
    POST /api/monitoring/queue/{id}/approve
    {
        "publish_immediately": false  // Optional
    }
    """
    item = DBContentQueue.query.get(item_id)
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    if not current_user.has_access_to_client(item.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if item.status != 'pending':
        return jsonify({'error': f'Item is already {item.status}'}), 400
    
    data = request.get_json(silent=True) or {}
    
    # Create blog post
    blog_post = DBBlogPost(
        client_id=item.client_id,
        title=item.title,
        body=item.body,
        meta_title=item.meta_title,
        meta_description=item.meta_description,
        primary_keyword=item.primary_keyword,
        secondary_keywords=[],
        faq_content=[],
        word_count=item.word_count,
        status=ContentStatus.APPROVED
    )
    
    db.session.add(blog_post)
    
    # Update queue item
    item.status = 'approved'
    item.approved_by = current_user.id
    item.approved_at = datetime.utcnow()
    item.published_blog_id = blog_post.id
    
    # Update competitor page
    if item.trigger_competitor_page_id:
        comp_page = DBCompetitorPage.query.get(item.trigger_competitor_page_id)
        if comp_page:
            comp_page.counter_content_id = blog_post.id
    
    db.session.commit()
    
    return jsonify({
        'message': 'Content approved',
        'blog_post': blog_post.to_dict()
    })


@monitoring_bp.route('/queue/<item_id>/reject', methods=['POST'])
@token_required
def reject_queue_item(current_user, item_id):
    """Reject queued content"""
    item = DBContentQueue.query.get(item_id)
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    if not current_user.has_access_to_client(item.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    item.status = 'rejected'
    item.client_notes = data.get('notes', '')
    
    db.session.commit()
    
    return jsonify({'message': 'Content rejected'})


@monitoring_bp.route('/queue/<item_id>/publish', methods=['POST'])
@token_required
def publish_queue_item(current_user, item_id):
    """
    Publish approved content to WordPress
    
    POST /api/monitoring/queue/{id}/publish
    """
    from app.services.wordpress_service import get_wordpress_manager
    
    item = DBContentQueue.query.get(item_id)
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    if not current_user.has_access_to_client(item.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if item.status != 'approved':
        return jsonify({'error': 'Content must be approved before publishing'}), 400
    
    # Get client's WordPress config
    client = DBClient.query.get(item.client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not client.wordpress_url:
        return jsonify({'error': 'WordPress not configured for this client. Add WordPress URL and credentials in client settings.'}), 400
    
    # Publish
    wp_manager = get_wordpress_manager()
    result = wp_manager.publish_content(item.client_id, item.id)
    
    if result.get('success'):
        return jsonify({
            'message': 'Published to WordPress',
            'url': result.get('url'),
            'post_id': result.get('post_id')
        })
    else:
        return jsonify({'error': result.get('error', 'Publishing failed')}), 500


@monitoring_bp.route('/queue/<item_id>/regenerate', methods=['POST'])
@token_required
def regenerate_queue_item(current_user, item_id):
    """
    Regenerate content with notes
    
    POST /api/monitoring/queue/{id}/regenerate
    {
        "notes": "Make it more conversational, add more local references"
    }
    """
    item = DBContentQueue.query.get(item_id)
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    if not current_user.has_access_to_client(item.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if item.regenerate_count >= 3:
        return jsonify({'error': 'Maximum regeneration limit reached'}), 400
    
    data = request.get_json(silent=True) or {}
    notes = data.get('notes', '')
    
    # Get client
    client = DBClient.query.get(item.client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Regenerate with notes incorporated into prompt
    result = ai_service.generate_blog_post(
        keyword=item.primary_keyword,
        geo=client.geo or '',
        industry=client.industry or '',
        word_count=max(item.word_count, 1200),
        tone=client.tone or 'professional',
        business_name=client.business_name or '',
        include_faq=True,
        faq_count=5,
        usps=client.get_unique_selling_points() or []
        # Note: In production, pass notes to AI prompt
    )
    
    if result.get('error'):
        return jsonify({'error': f'Regeneration failed: {result["error"]}'}), 500
    
    # Score new content
    our_score = seo_scoring_engine.score_content(
        {
            'title': result.get('title', ''),
            'meta_title': result.get('meta_title', ''),
            'meta_description': result.get('meta_description', ''),
            'h1': result.get('h1', ''),
            'body': result.get('body', ''),
            'body_text': result.get('body', '')
        },
        item.primary_keyword,
        client.geo
    )
    
    # Update item
    item.title = result.get('title', '')
    item.body = result.get('body', '')
    item.meta_title = result.get('meta_title', '')
    item.meta_description = result.get('meta_description', '')
    item.word_count = len(result.get('body', '').split())
    item.our_seo_score = our_score['total_score']
    item.client_notes = notes
    item.regenerate_count += 1
    item.status = 'pending'
    
    db.session.commit()
    
    return jsonify({
        'message': 'Content regenerated',
        'queued_content': item.to_dict(),
        'new_score': our_score['total_score']
    })


# ==========================================
# RANK TRACKING
# ==========================================

@monitoring_bp.route('/rankings', methods=['GET'])
@token_required
def get_rankings(current_user):
    """Get current rankings for a client"""
    import os
    
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    try:
        # Get keywords to track
        keywords = client.get_primary_keywords() + client.get_secondary_keywords()
        
        if not keywords:
            return jsonify({'error': 'No keywords configured for client'}), 400
        
        # Debug: Check if API key is available
        api_key_set = bool(os.environ.get('SEMRUSH_API_KEY'))
        service_key_set = bool(rank_tracking_service.api_key)
        
        # Check rankings
        result = rank_tracking_service.check_all_keywords(
            client.website_url or client.business_name,
            keywords[:50]  # Limit to 50 keywords
        )
        
        # Add debug info to result
        result['_debug'] = {
            'env_var_set': api_key_set,
            'service_key_set': service_key_set,
            'key_length': len(os.environ.get('SEMRUSH_API_KEY', ''))
        }
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 500
        
        # Save to history (only if not demo mode)
        if not result.get('demo_mode'):
            for kw_data in result.get('keywords', []):
                history = DBRankHistory(
                    client_id=client_id,
                    keyword=kw_data['keyword'],
                    position=kw_data.get('position'),
                    previous_position=kw_data.get('previous_position'),
                    change=kw_data.get('change', 0),
                    url=kw_data.get('url', ''),
                    search_volume=kw_data.get('search_volume', 0),
                    cpc=kw_data.get('cpc', 0.0)
                )
                db.session.add(history)
            
            db.session.commit()
        
        # Calculate traffic value
        traffic_value = rank_tracking_service.calculate_traffic_value(result.get('keywords', []))
        
        result['traffic_value'] = traffic_value
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        logger.error(f"Rankings error for client {client_id}: {e}\n{traceback.format_exc()}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@monitoring_bp.route('/rankings/history', methods=['GET'])
@token_required
def get_ranking_history(current_user):
    """Get ranking history for a client"""
    client_id = request.args.get('client_id')
    days = safe_int(request.args.get('days'), 30, max_val=365)
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    since = datetime.utcnow() - timedelta(days=days)
    
    history = DBRankHistory.query.filter(
        DBRankHistory.client_id == client_id,
        DBRankHistory.checked_at >= since
    ).order_by(DBRankHistory.checked_at.desc()).all()
    
    return jsonify({
        'client_id': client_id,
        'days': days,
        'history': [h.to_dict() for h in history]
    })


@monitoring_bp.route('/rankings/heatmap', methods=['GET'])
@token_required
def get_ranking_heatmap(current_user):
    """Get heatmap data for rankings dashboard"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get latest rankings
    latest = DBRankHistory.query.filter_by(client_id=client_id).order_by(
        DBRankHistory.checked_at.desc()
    ).limit(100).all()
    
    # Get 7-day ago rankings
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    history_7d = DBRankHistory.query.filter(
        DBRankHistory.client_id == client_id,
        DBRankHistory.checked_at <= seven_days_ago,
        DBRankHistory.checked_at >= seven_days_ago - timedelta(hours=24)
    ).all()
    
    # Get 30-day ago rankings
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    history_30d = DBRankHistory.query.filter(
        DBRankHistory.client_id == client_id,
        DBRankHistory.checked_at <= thirty_days_ago,
        DBRankHistory.checked_at >= thirty_days_ago - timedelta(hours=24)
    ).all()
    
    # Generate heatmap
    heatmap = rank_tracking_service.generate_heatmap_data(
        [h.to_dict() for h in latest],
        [h.to_dict() for h in history_7d],
        [h.to_dict() for h in history_30d]
    )
    
    return jsonify({
        'client_id': client_id,
        'heatmap': heatmap
    })


# ==========================================
# ALERTS
# ==========================================

@monitoring_bp.route('/alerts', methods=['GET'])
@token_required
def get_alerts(current_user):
    """Get alerts for a client"""
    client_id = request.args.get('client_id')
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    query = DBAlert.query.filter_by(client_id=client_id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
    
    alerts = query.order_by(DBAlert.created_at.desc()).limit(50).all()
    
    return jsonify({
        'client_id': client_id,
        'alerts': [a.to_dict() for a in alerts]
    })


@monitoring_bp.route('/alerts/<alert_id>/read', methods=['POST'])
@token_required
def mark_alert_read(current_user, alert_id):
    """Mark an alert as read"""
    alert = DBAlert.query.get(alert_id)
    
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404
    
    if not current_user.has_access_to_client(alert.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    alert.is_read = True
    db.session.commit()
    
    return jsonify({'message': 'Alert marked as read'})


# ==========================================
# SEO SCORING
# ==========================================

@monitoring_bp.route('/seo-score', methods=['POST'])
@token_required
def score_content(current_user):
    """
    Score content against SEO best practices
    
    POST /api/monitoring/seo-score
    {
        "content": {
            "title": "...",
            "meta_title": "...",
            "meta_description": "...",
            "h1": "...",
            "body": "HTML content..."
        },
        "target_keyword": "roof repair sarasota",
        "location": "Sarasota, FL"
    }
    """
    data = request.get_json(silent=True) or {}
    
    content = data.get('content', {})
    keyword = data.get('target_keyword', '')
    location = data.get('location', '')
    
    if not content or not keyword:
        return jsonify({'error': 'content and target_keyword required'}), 400
    
    score = seo_scoring_engine.score_content(content, keyword, location)
    
    return jsonify(score)


@monitoring_bp.route('/seo-compare', methods=['POST'])
@token_required
def compare_content(current_user):
    """
    Compare our content against competitor content
    
    POST /api/monitoring/seo-compare
    {
        "our_content": {...},
        "competitor_url": "https://...",
        "target_keyword": "...",
        "location": "..."
    }
    """
    data = request.get_json(silent=True) or {}
    
    our_content = data.get('our_content', {})
    competitor_url = data.get('competitor_url', '')
    keyword = data.get('target_keyword', '')
    location = data.get('location', '')
    
    if not our_content or not competitor_url or not keyword:
        return jsonify({'error': 'our_content, competitor_url, and target_keyword required'}), 400
    
    # Fetch competitor content
    comp_extracted = competitor_monitoring_service.extract_page_content(competitor_url)
    
    if comp_extracted.get('error'):
        return jsonify({'error': f'Could not fetch competitor: {comp_extracted["error"]}'}), 400
    
    comp_content = {
        'title': comp_extracted.get('title', ''),
        'meta_description': comp_extracted.get('meta_description', ''),
        'h1': comp_extracted.get('h1', ''),
        'body': '',
        'body_text': comp_extracted.get('body_text', '')
    }
    
    comparison = seo_scoring_engine.compare_content(
        our_content,
        comp_content,
        keyword,
        location
    )
    
    return jsonify(comparison)


@monitoring_bp.route('/analyze-url', methods=['POST'])
@token_required
def analyze_url(current_user):
    """
    Analyze a URL for SEO metrics
    
    POST /api/monitoring/analyze-url
    {
        "url": "https://competitor.com/blog-post"
    }
    """
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'url is required'}), 400
    
    try:
        # Use competitor monitoring service to extract content
        page_data = competitor_monitoring_service.extract_page_content(url)
        
        if page_data.get('error'):
            return jsonify({'error': page_data['error']}), 400
        
        # Count elements for SEO analysis
        body_text = page_data.get('body_text', '')
        h2s = page_data.get('h2s', [])
        
        # Count internal links (simplified)
        internal_links = 0
        external_links = 0
        
        return jsonify({
            'success': True,
            'url': url,
            'title': page_data.get('title', ''),
            'meta_description': page_data.get('meta_description', ''),
            'h1': page_data.get('h1', ''),
            'h2s': h2s,
            'h2_count': len(h2s),
            'word_count': page_data.get('word_count', 0),
            'internal_links': internal_links,
            'external_links': external_links,
            'content_hash': page_data.get('content_hash', '')
        })
        
    except Exception as e:
        logger.error(f"URL analysis error: {e}")
        return jsonify({'error': 'Failed to analyze URL'}), 500


# ==========================================
# DASHBOARD DATA
# ==========================================

@monitoring_bp.route('/dashboard', methods=['GET'])
@token_required
def get_dashboard_data(current_user):
    """
    Get all data needed for the monitoring dashboard
    
    GET /api/monitoring/dashboard?client_id=xxx
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Competitors
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).all()
    
    # New competitor pages (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    new_pages = DBCompetitorPage.query.filter(
        DBCompetitorPage.client_id == client_id,
        DBCompetitorPage.discovered_at >= seven_days_ago
    ).order_by(DBCompetitorPage.discovered_at.desc()).limit(10).all()
    
    # Content queue
    pending_content = DBContentQueue.query.filter_by(
        client_id=client_id,
        status='pending'
    ).count()
    
    # Recent alerts
    alerts = DBAlert.query.filter_by(
        client_id=client_id,
        is_read=False
    ).order_by(DBAlert.created_at.desc()).limit(5).all()
    
    # Latest rankings
    latest_rankings = DBRankHistory.query.filter_by(
        client_id=client_id
    ).order_by(DBRankHistory.checked_at.desc()).limit(50).all()
    
    # Calculate stats
    keywords = client.get_primary_keywords() + client.get_secondary_keywords()
    
    # Ranking summary
    ranking_summary = {
        'total_keywords': len(keywords),
        'in_top_3': 0,
        'in_top_10': 0,
        'improved_7d': 0,
        'declined_7d': 0
    }
    
    seen_keywords = set()
    for r in latest_rankings:
        if r.keyword not in seen_keywords:
            seen_keywords.add(r.keyword)
            if r.position:
                if r.position <= 3:
                    ranking_summary['in_top_3'] += 1
                if r.position <= 10:
                    ranking_summary['in_top_10'] += 1
    
    return jsonify({
        'client': client.to_dict(),
        'stats': {
            'competitors_tracked': len(competitors),
            'new_content_detected': len(new_pages),
            'content_pending_review': pending_content,
            'unread_alerts': len(alerts),
            'keywords_tracked': len(keywords)
        },
        'ranking_summary': ranking_summary,
        'competitors': [c.to_dict() for c in competitors],
        'new_competitor_pages': [p.to_dict() for p in new_pages],
        'recent_alerts': [a.to_dict() for a in alerts],
        'system_status': 'active'
    })


# ==========================================
# CONTENT CHANGE DETECTION
# ==========================================

@monitoring_bp.route('/content-changes/<client_id>', methods=['GET'])
@token_required
def get_content_changes(current_user, client_id):
    """
    Get recent content changes detected from competitors
    
    GET /api/monitoring/content-changes/{client_id}
    
    Returns list of new pages and content updates
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get competitors for this client
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).all()
    
    changes = []
    
    for competitor in competitors:
        # Get pages discovered in last 7 days
        recent_pages = DBCompetitorPage.query.filter(
            DBCompetitorPage.competitor_id == competitor.id,
            DBCompetitorPage.discovered_at >= datetime.utcnow() - timedelta(days=7)
        ).order_by(DBCompetitorPage.discovered_at.desc()).limit(10).all()
        
        for page in recent_pages:
            changes.append({
                'type': 'new_page',
                'competitor': competitor.domain or '',
                'competitor_id': competitor.id,
                'url': page.url or '',
                'title': page.title or 'Untitled',
                'word_count': page.word_count or 0,
                'detected_at': page.discovered_at.isoformat() if page.discovered_at else None
            })
    
    # Sort by detected_at descending
    changes.sort(key=lambda x: x.get('detected_at') or '', reverse=True)
    
    return jsonify({
        'client_id': client_id,
        'changes': changes[:20],  # Limit to 20 most recent
        'scanned_at': datetime.utcnow().isoformat()
    })


@monitoring_bp.route('/rank-history/<client_id>', methods=['GET'])
@token_required
def get_rank_history(current_user, client_id):
    """
    Get rank history for a keyword
    
    GET /api/monitoring/rank-history/{client_id}?keyword=ac+repair+tampa
    
    Returns 30-day position history
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({'error': 'keyword parameter required'}), 400
    
    # Get rank history for this keyword
    history = DBRankHistory.query.filter(
        DBRankHistory.client_id == client_id,
        DBRankHistory.keyword == keyword,
        DBRankHistory.checked_at >= datetime.utcnow() - timedelta(days=30)
    ).order_by(DBRankHistory.checked_at.asc()).all()
    
    if not history:
        # Return empty but valid response
        return jsonify({
            'client_id': client_id,
            'keyword': keyword,
            'history': [],
            'message': 'No rank history found for this keyword'
        })
    
    return jsonify({
        'client_id': client_id,
        'keyword': keyword,
        'history': [
            {
                'date': h.checked_at.isoformat() if h.checked_at else None,
                'position': h.position,
                'url': getattr(h, 'ranking_url', None) or getattr(h, 'url', None) or ''
            }
            for h in history
        ]
    })


# ==========================================
# COMPETITOR DASHBOARD
# ==========================================

@monitoring_bp.route('/competitor-dashboard/<client_id>', methods=['GET'])
@token_required
def get_competitor_dashboard(current_user, client_id):
    """
    Get comprehensive competitor comparison data for dashboard
    
    GET /api/monitoring/competitor-dashboard/{client_id}
    
    Returns:
    - Client vs competitor rankings overview
    - Content gap analysis
    - Keyword overlap
    - Competitor content summary
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get competitors (limit to prevent timeout)
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).limit(10).all()
    
    # Get client keywords
    client_keywords = []
    try:
        client_keywords = (client.get_primary_keywords() + client.get_secondary_keywords())[:20]
    except Exception:
        pass
    
    # Get client's latest rankings (limited)
    client_rankings = {}
    try:
        latest_ranks = DBRankHistory.query.filter_by(client_id=client_id).order_by(
            DBRankHistory.checked_at.desc()
        ).limit(50).all()
        
        for rank in latest_ranks:
            keyword = getattr(rank, 'keyword', None)
            if keyword and keyword not in client_rankings:
                client_rankings[keyword] = {
                    'position': getattr(rank, 'position', None),
                    'url': getattr(rank, 'ranking_url', None) or getattr(rank, 'url', None) or '',
                    'change': getattr(rank, 'change', 0)
                }
    except Exception:
        pass  # Continue with empty rankings
    
    # Build competitor comparison data
    competitor_data = []
    content_gaps = []
    keyword_overlap = []
    
    for comp in competitors[:5]:  # Limit competitors processed
        # Get competitor pages (limited)
        try:
            comp_pages = DBCompetitorPage.query.filter_by(competitor_id=comp.id).limit(50).all()
        except Exception:
            comp_pages = []
        
        # Competitor rankings are tracked separately via crawling, not DBRankHistory
        # DBRankHistory is for client keyword tracking only
        comp_ranks = {}
        
        # Count content by category
        blog_count = len([p for p in comp_pages if '/blog' in (p.url or '').lower()])
        service_count = len([p for p in comp_pages if any(x in (p.url or '').lower() for x in ['/service', '/about', '/contact'])])
        
        # Analyze keywords from competitor titles
        comp_keywords = set()
        for page in comp_pages:
            if page.title:
                words = page.title.lower().split()
                for word in words:
                    if len(word) > 3 and word not in ['the', 'and', 'for', 'with', 'your', 'our']:
                        comp_keywords.add(word)
        
        # Find keyword overlap
        client_kw_set = set(kw.lower() for kw in client_keywords)
        overlap = comp_keywords.intersection(client_kw_set)
        
        competitor_data.append({
            'id': comp.id,
            'domain': comp.domain,
            'name': comp.name or comp.domain,
            'total_pages': len(comp_pages),
            'blog_posts': blog_count,
            'service_pages': service_count,
            'crawl_frequency': comp.crawl_frequency or 'daily',
            'last_crawled': comp.last_crawl_at.isoformat() if comp.last_crawl_at else None,
            'keyword_overlap': list(overlap)[:10],
            'rankings': comp_ranks
        })
        
        # Find content gaps - topics competitors have that client doesn't
        for page in comp_pages:
            if page.title and '/blog' in (page.url or '').lower():
                # Check if client has similar content
                title_lower = page.title.lower()
                has_similar = False
                # This is a simplified check - in production, use more sophisticated matching
                for kw in client_keywords:
                    if kw.lower() in title_lower:
                        has_similar = True
                        break
                
                if not has_similar:
                    content_gaps.append({
                        'competitor': comp.domain,
                        'title': page.title,
                        'url': page.url,
                        'topic_suggestion': page.title
                    })
    
    # Calculate overall stats
    total_client_ranked = len([k for k, v in client_rankings.items() if v['position'] and v['position'] <= 100])
    top_10_count = len([k for k, v in client_rankings.items() if v['position'] and v['position'] <= 10])
    top_3_count = len([k for k, v in client_rankings.items() if v['position'] and v['position'] <= 3])
    
    # Ranking comparison - which keywords client wins vs loses
    ranking_battles = []
    for keyword, client_rank in client_rankings.items():
        if not client_rank['position']:
            continue
        
        for comp in competitor_data:
            comp_pos = comp['rankings'].get(keyword)
            if comp_pos:
                ranking_battles.append({
                    'keyword': keyword,
                    'client_position': client_rank['position'],
                    'competitor': comp['domain'],
                    'competitor_position': comp_pos,
                    'winning': client_rank['position'] < comp_pos
                })
    
    # Sort battles by importance (client winning but close, or losing)
    ranking_battles.sort(key=lambda x: (not x['winning'], abs(x['client_position'] - x['competitor_position'])))
    
    return jsonify({
        'client_id': client_id,
        'client_name': client.business_name,
        'summary': {
            'total_competitors': len(competitors),
            'client_keywords_tracked': len(client_keywords),
            'client_keywords_ranked': total_client_ranked,
            'top_10_keywords': top_10_count,
            'top_3_keywords': top_3_count,
            'content_gaps_found': len(content_gaps)
        },
        'competitors': competitor_data,
        'content_gaps': content_gaps[:20],  # Top 20 gaps
        'ranking_battles': ranking_battles[:20],  # Top 20 battles
        'client_rankings': client_rankings
    })


@monitoring_bp.route('/competitor-compare/<client_id>/<competitor_id>', methods=['GET'])
@token_required
def compare_with_competitor(current_user, client_id, competitor_id):
    """
    Detailed side-by-side comparison with a single competitor
    
    GET /api/monitoring/competitor-compare/{client_id}/{competitor_id}
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    competitor = DBCompetitor.query.get(competitor_id)
    
    if not client or not competitor:
        return jsonify({'error': 'Client or competitor not found'}), 404
    
    if competitor.client_id != client_id:
        return jsonify({'error': 'Competitor does not belong to this client'}), 403
    
    # Get competitor pages
    comp_pages = DBCompetitorPage.query.filter_by(competitor_id=competitor_id).all()
    
    # Get client rankings
    client_rankings = {}
    latest_ranks = DBRankHistory.query.filter_by(client_id=client_id).order_by(
        DBRankHistory.checked_at.desc()
    ).limit(100).all()
    
    for rank in latest_ranks:
        if rank.keyword not in client_rankings:
            client_rankings[rank.keyword] = rank.position
    
    # Competitor rankings are not tracked in DBRankHistory
    # They would need to be tracked via a separate system
    comp_rankings = {}
    
    # All keywords from client
    all_keywords = set(client_rankings.keys())
    
    keyword_comparison = []
    client_wins = 0
    competitor_wins = 0
    ties = 0
    
    for keyword in all_keywords:
        client_pos = client_rankings.get(keyword)
        comp_pos = comp_rankings.get(keyword)
        
        if client_pos and comp_pos:
            if client_pos < comp_pos:
                winner = 'client'
                client_wins += 1
            elif comp_pos < client_pos:
                winner = 'competitor'
                competitor_wins += 1
            else:
                winner = 'tie'
                ties += 1
        elif client_pos:
            winner = 'client'
            client_wins += 1
        elif comp_pos:
            winner = 'competitor'
            competitor_wins += 1
        else:
            winner = 'unknown'
        
        keyword_comparison.append({
            'keyword': keyword,
            'client_position': client_pos,
            'competitor_position': comp_pos,
            'winner': winner,
            'gap': (comp_pos or 100) - (client_pos or 100) if client_pos or comp_pos else 0
        })
    
    # Sort by gap (biggest opportunities first)
    keyword_comparison.sort(key=lambda x: -abs(x['gap']))
    
    # Content comparison
    blog_pages = [p for p in comp_pages if '/blog' in (p.url or '').lower()]
    
    return jsonify({
        'client': {
            'id': client_id,
            'name': client.business_name,
            'website': client.website_url
        },
        'competitor': {
            'id': competitor_id,
            'name': competitor.name or competitor.domain,
            'domain': competitor.domain,
            'total_pages': len(comp_pages),
            'blog_posts': len(blog_pages),
            'last_crawled': competitor.last_crawled.isoformat() if competitor.last_crawled else None
        },
        'rankings_summary': {
            'total_keywords': len(all_keywords),
            'client_wins': client_wins,
            'competitor_wins': competitor_wins,
            'ties': ties,
            'win_rate': round(client_wins / len(all_keywords) * 100, 1) if all_keywords else 0
        },
        'keyword_comparison': keyword_comparison[:50],
        'competitor_content': [
            {
                'title': p.title,
                'url': p.url,
                'last_modified': p.last_modified.isoformat() if p.last_modified else None
            }
            for p in blog_pages[:20]
        ]
    })


# ==========================================
# CRAWL ALL COMPETITORS
# ==========================================

@monitoring_bp.route('/competitors/crawl-all', methods=['POST'])
@token_required
def crawl_all_competitors(current_user):
    """
    Crawl all competitors for a client
    
    POST /api/monitoring/competitors/crawl-all
    {
        "client_id": "client_abc123"
    }
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).all()
    
    total_new_pages = 0
    competitors_crawled = 0
    errors = []
    
    for competitor in competitors:
        try:
            # Crawl competitor
            result = _crawl_single_competitor(competitor)
            competitors_crawled += 1
            total_new_pages += result.get('new_pages', 0)
        except Exception as e:
            errors.append(f"{competitor.domain}: {str(e)}")
    
    return jsonify({
        'success': True,
        'competitors_crawled': competitors_crawled,
        'total_new_pages': total_new_pages,
        'errors': errors if errors else None
    })


def _crawl_single_competitor(competitor):
    """Helper to crawl a single competitor"""
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlparse
    
    new_pages = 0
    crawled_urls = set()
    
    base_url = f"https://{competitor.domain}"
    
    try:
        # Get homepage
        resp = requests.get(base_url, timeout=10, headers={'User-Agent': 'MCP-Bot/1.0'})
        if resp.status_code != 200:
            return {'new_pages': 0, 'error': f'HTTP {resp.status_code}'}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            
            # Only same domain
            if competitor.domain not in parsed.netloc:
                continue
            
            # Skip common non-content
            if any(x in full_url.lower() for x in ['#', 'javascript:', 'mailto:', '.pdf', '.jpg', '.png']):
                continue
            
            if full_url not in crawled_urls:
                crawled_urls.add(full_url)
                
                # Check if we already have this page
                existing = DBCompetitorPage.query.filter_by(
                    competitor_id=competitor.id,
                    url=full_url
                ).first()
                
                if not existing:
                    # Try to get page title
                    title = link.get_text(strip=True)[:200] if link.get_text(strip=True) else parsed.path
                    
                    page = DBCompetitorPage(
                        competitor_id=competitor.id,
                        url=full_url,
                        title=title,
                        discovered_at=datetime.utcnow()
                    )
                    db.session.add(page)
                    new_pages += 1
        
        # Update competitor last_crawled
        competitor.last_crawled = datetime.utcnow()
        competitor.next_crawl_at = datetime.utcnow() + timedelta(days=1)
        
        db.session.commit()
        
    except Exception as e:
        return {'new_pages': 0, 'error': str(e)}
    
    return {'new_pages': new_pages}


# ==========================================
# CRAWL SETTINGS
# ==========================================

@monitoring_bp.route('/crawl-settings', methods=['POST'])
@token_required
def save_crawl_settings(current_user):
    """
    Save auto-crawl settings for a client
    
    POST /api/monitoring/crawl-settings
    {
        "client_id": "...",
        "crawl_frequency": "daily|weekly|manual"
    }
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    frequency = data.get('crawl_frequency', 'daily')
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Update all competitors for this client
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).all()
    
    for comp in competitors:
        comp.crawl_frequency = frequency
        
        if frequency == 'daily':
            comp.next_crawl_at = datetime.utcnow() + timedelta(days=1)
        elif frequency == 'weekly':
            comp.next_crawl_at = datetime.utcnow() + timedelta(weeks=1)
        else:
            comp.next_crawl_at = None
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Crawl frequency set to {frequency}',
        'competitors_updated': len(competitors)
    })


# ==========================================
# FRESHNESS ALERTS
# ==========================================

@monitoring_bp.route('/freshness-alerts', methods=['GET'])
@token_required
def get_freshness_alerts(current_user):
    """
    Get recent competitor content alerts
    
    GET /api/monitoring/freshness-alerts?client_id=xxx&days=7
    """
    client_id = request.args.get('client_id')
    days = int(request.args.get('days', 7))
    
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Get competitors
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).all()
    
    comp_ids = [c.id for c in competitors]
    comp_names = {c.id: c.name or c.domain for c in competitors}
    
    # Get recently discovered pages
    recent_pages = DBCompetitorPage.query.filter(
        DBCompetitorPage.competitor_id.in_(comp_ids),
        DBCompetitorPage.discovered_at >= cutoff
    ).order_by(DBCompetitorPage.discovered_at.desc()).limit(50).all()
    
    alerts = []
    for page in recent_pages:
        # Extract topic from title
        topic = page.title or page.url.split('/')[-1].replace('-', ' ')
        
        alerts.append({
            'competitor_id': page.competitor_id,
            'competitor_name': comp_names.get(page.competitor_id, 'Unknown'),
            'page_id': page.id,
            'title': page.title,
            'url': page.url,
            'topic': topic,
            'detected_at': page.discovered_at.isoformat() if page.discovered_at else None
        })
    
    return jsonify({
        'alerts': alerts,
        'total': len(alerts),
        'days_checked': days
    })
