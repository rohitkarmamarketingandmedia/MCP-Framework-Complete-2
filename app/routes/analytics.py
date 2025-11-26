"""
MCP Framework - Analytics Routes
Traffic, rankings, and performance metrics
"""
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import token_required
from app.services.analytics_service import AnalyticsService
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)
analytics_service = AnalyticsService()
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
