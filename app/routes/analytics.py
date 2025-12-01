"""
MCP Framework - Analytics Routes
Traffic, rankings, and performance metrics
"""
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import token_required, admin_required
from app.services.analytics_service import AnalyticsService, ComparativeAnalytics
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)
analytics_service = AnalyticsService()
comparative = ComparativeAnalytics()
seo_service = SEOService()
data_service = DataService()


@analytics_bp.route('/overview/<client_id>', methods=['GET'])
@token_required
def get_overview(current_user, client_id):
    """
    Get analytics overview for a client
    
    GET /api/analytics/overview/<client_id>?period=30d
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    period = request.args.get('period', '30d')
    
    # Parse period
    if period.endswith('d'):
        days = int(period[:-1])
    elif period.endswith('w'):
        days = int(period[:-1]) * 7
    elif period.endswith('m'):
        days = int(period[:-1]) * 30
    else:
        days = 30
    
    start_date = datetime.utcnow() - timedelta(days=days)
    end_date = datetime.utcnow()
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get metrics
    traffic = analytics_service.get_traffic_metrics(
        property_id=client.ga4_property_id or current_app.config['GA4_PROPERTY_ID'],
        start_date=start_date,
        end_date=end_date
    )
    
    # Get content stats
    content_list = data_service.get_content_by_client(client_id)
    content_stats = {
        'total': len(content_list),
        'published': sum(1 for c in content_list if c.status.value == 'published'),
        'draft': sum(1 for c in content_list if c.status.value == 'draft')
    }
    
    # Get social stats
    social_posts = data_service.get_social_posts_by_client(client_id)
    social_stats = {
        'total': len(social_posts),
        'published': sum(1 for p in social_posts if p.status.value == 'published'),
        'scheduled': sum(1 for p in social_posts if p.scheduled_at)
    }
    
    return jsonify({
        'client_id': client_id,
        'period': period,
        'traffic': traffic,
        'content': content_stats,
        'social': social_stats
    })


@analytics_bp.route('/traffic/<client_id>', methods=['GET'])
@token_required
def get_traffic(current_user, client_id):
    """
    Get detailed traffic metrics
    
    GET /api/analytics/traffic/<client_id>?start=2024-01-01&end=2024-01-31
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    
    if start_str:
        start_date = datetime.fromisoformat(start_str)
    else:
        start_date = datetime.utcnow() - timedelta(days=30)
    
    if end_str:
        end_date = datetime.fromisoformat(end_str)
    else:
        end_date = datetime.utcnow()
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    traffic = analytics_service.get_detailed_traffic(
        property_id=client.ga4_property_id or current_app.config['GA4_PROPERTY_ID'],
        start_date=start_date,
        end_date=end_date
    )
    
    return jsonify({
        'client_id': client_id,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'metrics': traffic
    })


@analytics_bp.route('/rankings/<client_id>', methods=['GET'])
@token_required
def get_rankings(current_user, client_id):
    """
    Get keyword rankings
    
    GET /api/analytics/rankings/<client_id>
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not client.website_url:
        return jsonify({'error': 'Client website URL not configured'}), 400
    
    # Get rankings from SEMrush
    rankings = seo_service.get_keyword_rankings(
        domain=client.website_url,
        keywords=client.primary_keywords
    )
    
    return jsonify({
        'client_id': client_id,
        'domain': client.website_url,
        'rankings': rankings
    })


@analytics_bp.route('/competitors/<client_id>', methods=['GET'])
@token_required
def get_competitor_analysis(current_user, client_id):
    """
    Get competitor analysis
    
    GET /api/analytics/competitors/<client_id>
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not client.competitors:
        return jsonify({'error': 'No competitors configured'}), 400
    
    analysis = seo_service.analyze_competitors(
        domain=client.website_url,
        competitors=client.competitors,
        keywords=client.primary_keywords
    )
    
    return jsonify({
        'client_id': client_id,
        'domain': client.website_url,
        'competitors': client.competitors,
        'analysis': analysis
    })


@analytics_bp.route('/content-performance/<client_id>', methods=['GET'])
@token_required
def get_content_performance(current_user, client_id):
    """
    Get content performance metrics
    
    GET /api/analytics/content-performance/<client_id>
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get published content
    content_list = data_service.get_content_by_client(client_id, status='published')
    
    performance = []
    for content in content_list:
        if content.published_url:
            # Get page-level analytics
            page_metrics = analytics_service.get_page_metrics(
                property_id=client.ga4_property_id,
                page_path=content.published_url
            )
            
            performance.append({
                'content_id': content.id,
                'title': content.title,
                'url': content.published_url,
                'published_at': content.published_at.isoformat() if content.published_at else None,
                'metrics': page_metrics
            })
    
    return jsonify({
        'client_id': client_id,
        'total_content': len(content_list),
        'performance': performance
    })


@analytics_bp.route('/report/<client_id>', methods=['GET'])
@token_required
def generate_report(current_user, client_id):
    """
    Generate comprehensive analytics report
    
    GET /api/analytics/report/<client_id>?period=30d&format=json
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    period = request.args.get('period', '30d')
    report_format = request.args.get('format', 'json')
    
    # Parse period
    days = int(period.replace('d', '').replace('w', '') or 30)
    if 'w' in period:
        days *= 7
    
    start_date = datetime.utcnow() - timedelta(days=days)
    end_date = datetime.utcnow()
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Compile full report
    report = {
        'client': {
            'id': client_id,
            'name': client.business_name,
            'industry': client.industry
        },
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'days': days
        },
        'traffic': analytics_service.get_traffic_metrics(
            property_id=client.ga4_property_id,
            start_date=start_date,
            end_date=end_date
        ),
        'rankings': seo_service.get_keyword_rankings(
            domain=client.website_url,
            keywords=client.primary_keywords[:10]  # Top 10
        ) if client.website_url else {},
        'content_summary': {
            'total_posts': len(data_service.get_content_by_client(client_id)),
            'published': len(data_service.get_content_by_client(client_id, status='published')),
            'this_period': len([
                c for c in data_service.get_content_by_client(client_id)
                if c.created_at >= start_date
            ])
        },
        'social_summary': {
            'total_posts': len(data_service.get_social_posts_by_client(client_id)),
            'published': len(data_service.get_social_posts_by_client(client_id, status='published'))
        },
        'generated_at': datetime.utcnow().isoformat()
    }
    
    return jsonify(report)


# ==========================================
# COMPARATIVE ANALYTICS ENDPOINTS
# ==========================================

@analytics_bp.route('/compare/leads', methods=['GET'])
@token_required
def compare_leads(current_user):
    """
    Get lead analytics with period-over-period comparison
    
    GET /api/analytics/compare/leads?client_id=xxx&period=month
    """
    client_id = request.args.get('client_id')
    period = request.args.get('period', 'month')
    
    if client_id and not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Non-admins must specify client_id
    if not client_id and current_user.role != 'admin':
        return jsonify({'error': 'client_id required'}), 400
    
    data = comparative.get_lead_analytics(client_id, period)
    return jsonify(data)


@analytics_bp.route('/compare/content', methods=['GET'])
@token_required
def compare_content(current_user):
    """
    Get content analytics with period-over-period comparison
    
    GET /api/analytics/compare/content?client_id=xxx&period=month
    """
    client_id = request.args.get('client_id')
    period = request.args.get('period', 'month')
    
    if client_id and not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if not client_id and current_user.role != 'admin':
        return jsonify({'error': 'client_id required'}), 400
    
    data = comparative.get_content_analytics(client_id, period)
    return jsonify(data)


@analytics_bp.route('/compare/rankings/<client_id>', methods=['GET'])
@token_required
def compare_rankings(current_user, client_id):
    """
    Get ranking analytics with top movers
    
    GET /api/analytics/compare/rankings/<client_id>?period=month
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    period = request.args.get('period', 'month')
    data = comparative.get_ranking_analytics(client_id, period)
    return jsonify(data)


@analytics_bp.route('/health/<client_id>', methods=['GET'])
@token_required
def get_health_score(current_user, client_id):
    """
    Get comprehensive health score for a client
    
    GET /api/analytics/health/<client_id>
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = comparative.get_client_health_score(client_id)
    return jsonify(data)


@analytics_bp.route('/agency-summary', methods=['GET'])
@admin_required
def get_agency_summary(current_user):
    """
    Get agency-wide analytics summary (admin only)
    
    GET /api/analytics/agency-summary?period=month
    """
    period = request.args.get('period', 'month')
    data = comparative.get_agency_summary(period)
    return jsonify(data)


@analytics_bp.route('/ai-seo-analysis/<client_id>', methods=['POST'])
@token_required
def ai_seo_analysis(current_user, client_id):
    """
    AI-powered SEO opportunity analysis using seo_analyzer agent
    
    POST /api/analytics/ai-seo-analysis/<client_id>
    {
        "keywords": ["keyword1", "keyword2"],
        "rankings": [{"keyword": "x", "position": 15, "volume": 1000}],
        "industry": "HVAC",
        "location": "Sarasota, FL"
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Build analysis input
    keywords = data.get('keywords', client.primary_keywords if client.primary_keywords else [])
    rankings = data.get('rankings', [])
    industry = data.get('industry', client.industry or 'local business')
    location = data.get('location', client.location or '')
    
    user_input = f"""
Analyze SEO opportunities for a {industry} business in {location}.

Current Keywords: {', '.join(keywords) if keywords else 'None specified'}

Current Rankings:
{chr(10).join([f"- {r.get('keyword')}: Position {r.get('position')}, Volume {r.get('volume')}" for r in rankings]) if rankings else 'No ranking data available'}

Identify:
1. High-opportunity keywords (high volume, achievable rankings)
2. Quick wins (currently ranking 11-20)
3. Content gaps to fill
4. Local keyword opportunities
"""
    
    try:
        from app.services.ai_service import ai_service
        result = ai_service.generate_with_agent('seo_analyzer', user_input)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        return jsonify({
            'client_id': client_id,
            'analysis': result.get('content', ''),
            'usage': result.get('usage', {}),
            'agent': 'seo_analyzer'
        })
    except Exception as e:
        current_app.logger.error(f"AI SEO analysis failed: {e}")
        return jsonify({'error': 'An error occurred. Please try again.'}), 500


@analytics_bp.route('/ai-competitor-analysis/<client_id>', methods=['POST'])
@token_required
def ai_competitor_analysis(current_user, client_id):
    """
    AI-powered competitor analysis using competitor_analyzer agent
    
    POST /api/analytics/ai-competitor-analysis/<client_id>
    {
        "competitors": ["competitor1.com", "competitor2.com"],
        "competitor_data": [{"name": "X", "strengths": [...], "weaknesses": [...]}],
        "industry": "HVAC",
        "location": "Sarasota, FL"
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Build analysis input
    competitors = data.get('competitors', client.competitors if client.competitors else [])
    competitor_data = data.get('competitor_data', [])
    industry = data.get('industry', client.industry or 'local business')
    location = data.get('location', client.location or '')
    
    user_input = f"""
Analyze competitors for a {industry} business in {location}.

Business: {client.name}

Competitors to Analyze: {', '.join(competitors) if competitors else 'None specified'}

Competitor Data:
{chr(10).join([f"- {c.get('name')}: Strengths: {c.get('strengths', [])}, Weaknesses: {c.get('weaknesses', [])}" for c in competitor_data]) if competitor_data else 'No detailed competitor data available'}

Provide:
1. Key insights about competitor strategies
2. Content opportunities they're missing
3. Our competitive advantages to emphasize
4. Threats to watch
5. Priority actions to outrank them
"""
    
    try:
        from app.services.ai_service import ai_service
        result = ai_service.generate_with_agent('competitor_analyzer', user_input)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        return jsonify({
            'client_id': client_id,
            'analysis': result.get('content', ''),
            'usage': result.get('usage', {}),
            'agent': 'competitor_analyzer'
        })
    except Exception as e:
        current_app.logger.error(f"AI competitor analysis failed: {e}")
        return jsonify({'error': 'An error occurred. Please try again.'}), 500
