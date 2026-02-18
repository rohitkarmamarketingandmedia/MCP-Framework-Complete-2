"""
MCP Framework - Analytics Routes
Traffic, rankings, and performance metrics
"""
import os
import logging
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import token_required, admin_required
from app.services.analytics_service import AnalyticsService, ComparativeAnalytics
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

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
    
    period = request.args.get('period', 'month')
    
    # Map old d/w/m format to service format
    mapped_period = 'month'
    if period == '7d' or period == 'week':
        mapped_period = 'week'
    elif period == '30d' or period == 'month':
        mapped_period = 'month'
    elif period == '90d' or period == 'quarter':
        mapped_period = 'quarter'
    
    start_date, end_date, _, _ = comparative.get_period_dates(mapped_period)
    days = (datetime.utcnow() - start_date).days
    
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
    content_list = data_service.get_client_blog_posts(client_id)
    content_this_period = [c for c in content_list if c.created_at and c.created_at >= start_date]
    
    content_stats = {
        'total': len(content_this_period),
        'published': sum(1 for c in content_this_period if c.status == 'published'),
        'draft': sum(1 for c in content_this_period if c.status in ['draft', 'review', 'approved']),
        'scheduled': sum(1 for c in content_this_period if c.status == 'scheduled'),
        'all_time_total': len(content_list)
    }
    
    # Get social stats
    social_posts = data_service.get_client_social_posts(client_id)
    social_this_period = [p for p in social_posts if p.created_at and p.created_at >= start_date]
    
    social_stats = {
        'total': len(social_this_period),
        'published': sum(1 for p in social_this_period if p.status == 'published'),
        'scheduled': sum(1 for p in social_this_period if p.scheduled_for or p.status == 'scheduled'),
        'all_time_total': len(social_posts)
    }
    
    # Get phone calls from CallRail
    calls_count = 0
    answer_rate = 0
    try:
        callrail_id = client.callrail_company_id
        if callrail_id:
            from app.services.callrail_service import CallRailConfig, get_callrail_service
            if CallRailConfig.is_configured():
                callrail = get_callrail_service()
                if callrail:
                    calls = callrail.get_recent_calls(callrail_id, days=days)
                    if calls:
                        calls_count = len(calls)
                        answered = sum(1 for c in calls if c.get('answered'))
                        answer_rate = round(answered / calls_count * 100) if calls_count > 0 else 0
    except Exception as e:
        logger.warning(f"Error getting CallRail data for overview: {e}")
    
    # Get leads count
    leads_count = 0
    try:
        from app.models.db_models import DBLead
        leads_count = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= start_date
        ).count()
    except Exception as e:
        logger.warning(f"Error getting leads count: {e}")
    
    return jsonify({
        'client_id': client_id,
        'period': period,
        'traffic': traffic,
        'content': content_stats,
        'social': social_stats,
        'calls': calls_count,
        'phone_calls': calls_count,
        'answer_rate': answer_rate,
        'leads': leads_count,
        'new_leads': leads_count,
        'content_count': content_stats['total'] + social_stats['total'],
        'blogs_count': content_stats['total'],
        'social_count': social_stats['total'],
        'blogs_published': content_stats['published']
    })


@analytics_bp.route('/traffic/<client_id>', methods=['GET'])
@token_required
def get_traffic(current_user, client_id):
    """
    Get detailed traffic metrics including GA4 data
    
    GET /api/analytics/traffic/<client_id>?start=2024-01-01&end=2024-01-31
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    
    try:
        if start_str:
            start_date = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        else:
            start_date = datetime.utcnow() - timedelta(days=30)
        
        if end_str:
            end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        else:
            end_date = datetime.utcnow()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use ISO format (YYYY-MM-DD)'}), 400
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Check if GA4 is configured (need both property ID AND credentials)
    property_id = getattr(client, 'ga4_property_id', None) or current_app.config.get('GA4_PROPERTY_ID')
    credentials_configured = bool(os.environ.get('GA4_CREDENTIALS_JSON'))
    is_configured = bool(property_id)
    
    if not is_configured:
        return jsonify({
            'configured': False,
            'client_id': client_id,
            'message': 'GA4 not configured. Add your GA4 Property ID in Settings → Integrations.'
        })
    
    if not credentials_configured:
        return jsonify({
            'configured': True,
            'credentials_missing': True,
            'client_id': client_id,
            'sessions': 0,
            'users': 0, 
            'pageviews': 0,
            'bounce_rate': 0,
            'top_pages': [],
            'search_terms': [],
            'message': 'GA4 Property ID saved. Server needs GA4_CREDENTIALS_JSON environment variable with a Google Service Account to fetch data.'
        })
    
    try:
        traffic = analytics_service.get_detailed_traffic(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # Aggregate totals from channels if available
        channels = traffic.get('channels', [])
        total_sessions = sum(c.get('sessions', 0) for c in channels)
        total_users = sum(c.get('users', 0) for c in channels)
        
        # Try to get search terms from Google Search Console
        search_terms = []
        gsc_error = None
        try:
            from app.services.analytics_service import search_console_service
            
            # Get site URL - try gsc_site_url first, then website_url
            gsc_site_url = getattr(client, 'gsc_site_url', None)
            if not gsc_site_url:
                website_url = getattr(client, 'website_url', None)
                if website_url:
                    # Ensure proper format for Search Console
                    # Can be: https://www.example.com/ or sc-domain:example.com
                    if not website_url.startswith('http'):
                        website_url = 'https://' + website_url
                    if not website_url.endswith('/'):
                        website_url = website_url + '/'
                    gsc_site_url = website_url
            
            if gsc_site_url:
                logger.info(f"Fetching GSC search terms for: {gsc_site_url}")
                search_terms = search_console_service.get_search_terms(
                    site_url=gsc_site_url,
                    start_date=start_date,
                    end_date=end_date,
                    limit=10
                )
                if search_terms:
                    logger.info(f"Got {len(search_terms)} search terms from GSC")
                else:
                    logger.info("GSC returned no search terms (may need service account access)")
                    gsc_error = "No data - ensure service account has Search Console access"
            else:
                gsc_error = "No website URL configured"
        except Exception as e:
            logger.warning(f"Could not fetch GSC search terms: {e}")
            gsc_error = str(e)
        
        return jsonify({
            'configured': True,
            'client_id': client_id,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'sessions': total_sessions or traffic.get('sessions', 0),
            'users': total_users or traffic.get('users', 0),
            'pageviews': traffic.get('pageviews', 0),
            'bounce_rate': traffic.get('bounce_rate', 0),
            'avg_session_duration': traffic.get('avg_session_duration', 0),
            'top_pages': traffic.get('top_pages', []),
            'search_terms': search_terms,
            'search_terms_error': gsc_error if not search_terms else None,
            'channels': channels,
            'metrics': traffic
        })
    except Exception as e:
        logger.error(f"GA4 fetch error: {e}")
        return jsonify({
            'configured': True,
            'error': str(e),
            'sessions': 0,
            'users': 0,
            'pageviews': 0,
            'bounce_rate': 0,
            'top_pages': [],
            'search_terms': []
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
        keywords=client.get_primary_keywords()
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
    
    competitors = client.get_competitors()
    if not competitors:
        return jsonify({'error': 'No competitors configured'}), 400
    
    analysis = seo_service.analyze_competitors(
        domain=client.website_url,
        competitors=competitors,
        keywords=client.get_primary_keywords()
    )
    
    return jsonify({
        'client_id': client_id,
        'domain': client.website_url,
        'competitors': competitors,
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
    all_content = data_service.get_client_blog_posts(client_id)
    content_list = [c for c in all_content if c.status == 'published']
    
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
            keywords=client.get_primary_keywords()[:10]  # Top 10
        ) if client.website_url else {},
        'content_summary': _get_content_summary(client_id, start_date),
        'social_summary': _get_social_summary(client_id),
        'generated_at': datetime.utcnow().isoformat()
    }
    
    return jsonify(report)


def _get_content_summary(client_id, start_date):
    """Helper to get content summary stats"""
    all_posts = data_service.get_client_blog_posts(client_id)
    return {
        'total_posts': len(all_posts),
        'published': len([c for c in all_posts if c.status == 'published']),
        'this_period': len([c for c in all_posts if c.created_at and c.created_at >= start_date])
    }


def _get_social_summary(client_id):
    """Helper to get social summary stats"""
    all_posts = data_service.get_client_social_posts(client_id)
    return {
        'total_posts': len(all_posts),
        'published': len([p for p in all_posts if p.status == 'published'])
    }


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
    
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Build analysis input
    client_keywords = client.get_primary_keywords()
    keywords = data.get('keywords', client_keywords if client_keywords else [])
    rankings = data.get('rankings', [])
    industry = data.get('industry', client.industry or 'local business')
    location = data.get('location', client.geo or '')
    
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
    
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Build analysis input
    client_competitors = client.get_competitors()
    competitors = data.get('competitors', client_competitors if client_competitors else [])
    competitor_data = data.get('competitor_data', [])
    industry = data.get('industry', client.industry or 'local business')
    location = data.get('location', client.geo or '')
    
    user_input = f"""
Analyze competitors for a {industry} business in {location}.

Business: {client.business_name}

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


@analytics_bp.route('/gsc/<client_id>', methods=['GET'])
@token_required
def get_gsc_data(current_user, client_id):
    """
    Get Google Search Console data for a client
    
    GET /api/analytics/gsc/<client_id>?days=30
    
    Returns: top queries, top pages, clicks/impressions over time
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    days = min(int(request.args.get('days', 30)), 90)
    
    try:
        from app.services.analytics_service import search_console_service
        
        # Determine site URL
        gsc_site_url = getattr(client, 'gsc_site_url', None)
        if not gsc_site_url:
            website_url = getattr(client, 'website_url', None)
            if website_url:
                if not website_url.startswith('http'):
                    website_url = 'https://' + website_url
                if not website_url.endswith('/'):
                    website_url = website_url + '/'
                gsc_site_url = website_url
        
        if not gsc_site_url:
            return jsonify({
                'configured': False,
                'error': 'No website URL configured for this client'
            })
        
        # Check if GSC service is configured
        gsc_client = search_console_service._get_client()
        if not gsc_client:
            return jsonify({
                'configured': False,
                'error': 'Google Search Console not configured. Add GSC_CREDENTIALS_JSON environment variable with service account credentials.'
            })
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get top queries (50)
        top_queries = search_console_service.get_search_terms(
            site_url=gsc_site_url,
            start_date=start_date,
            end_date=end_date,
            limit=50
        )
        
        # Get top pages (20)
        top_pages = search_console_service.get_top_pages(
            site_url=gsc_site_url,
            start_date=start_date,
            end_date=end_date,
            limit=20
        )
        
        # Get daily click/impression data for chart
        daily_data = []
        try:
            request_body = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['date'],
                'rowLimit': 90
            }
            
            response = gsc_client.searchanalytics().query(
                siteUrl=gsc_site_url,
                body=request_body
            ).execute()
            
            for row in response.get('rows', []):
                daily_data.append({
                    'date': row['keys'][0],
                    'clicks': int(row.get('clicks', 0)),
                    'impressions': int(row.get('impressions', 0)),
                    'ctr': round(row.get('ctr', 0) * 100, 2),
                    'position': round(row.get('position', 0), 1)
                })
        except Exception as e:
            logger.warning(f"GSC daily data error: {e}")
        
        # Calculate totals
        total_clicks = sum(d['clicks'] for d in daily_data) if daily_data else sum(q.get('clicks', 0) for q in top_queries)
        total_impressions = sum(d['impressions'] for d in daily_data) if daily_data else sum(q.get('impressions', 0) for q in top_queries)
        avg_ctr = round((total_clicks / total_impressions * 100), 1) if total_impressions > 0 else 0
        avg_position = round(sum(q.get('position', 0) for q in top_queries) / len(top_queries), 1) if top_queries else 0
        
        return jsonify({
            'configured': True,
            'site_url': gsc_site_url,
            'days': days,
            'summary': {
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'avg_ctr': avg_ctr,
                'avg_position': avg_position
            },
            'top_queries': top_queries,
            'top_pages': top_pages,
            'daily_data': daily_data
        })
        
    except Exception as e:
        logger.error(f"GSC data fetch error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'configured': False,
            'error': str(e)
        })
