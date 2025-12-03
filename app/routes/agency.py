"""
MCP Framework - Agency Dashboard Routes
Cross-client aggregation for agency owners
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func, desc

from app.routes.auth import token_required, admin_required
from app.database import db
from app.models.db_models import (
    DBClient, DBCompetitor, DBCompetitorPage, DBRankHistory,
    DBContentQueue, DBAlert, DBBlogPost, DBSocialPost, ContentStatus
)

agency_bp = Blueprint('agency', __name__)


def is_admin(user):
    """Check if user is admin - handles both string and enum role types"""
    if hasattr(user, 'role'):
        role = user.role
        if hasattr(role, 'value'):
            return role.value == 'admin'
        return role == 'admin'
    return False


def get_user_clients(user):
    """Get all clients accessible by user"""
    if is_admin(user):
        return DBClient.query.filter_by(is_active=True).all()
    else:
        client_ids = user.get_client_access() if hasattr(user, 'get_client_access') else []
        if client_ids:
            return DBClient.query.filter(
                DBClient.id.in_(client_ids),
                DBClient.is_active == True
            ).all()
        return []


@agency_bp.route('/overview', methods=['GET'])
@token_required
def get_agency_overview(current_user):
    """
    Get high-level agency stats across all clients
    
    Returns:
        - total_clients
        - total_mrr (estimated)
        - total_content_pending
        - total_urgent_alerts
        - total_keywords_tracked
        - total_ranking_improvements
    """
    # Get all clients this user can access
    clients = get_user_clients(current_user)
    
    client_ids = [c.id for c in clients]
    
    # Total content pending approval
    pending_content = DBContentQueue.query.filter(
        DBContentQueue.client_id.in_(client_ids),
        DBContentQueue.status == 'pending'
    ).count()
    
    # Urgent alerts (unread, high priority)
    urgent_alerts = DBAlert.query.filter(
        DBAlert.client_id.in_(client_ids),
        DBAlert.is_read == False,
        DBAlert.priority == 'high'
    ).count()
    
    # Total keywords tracked
    total_keywords = 0
    for client in clients:
        total_keywords += len(client.get_primary_keywords())
        total_keywords += len(client.get_secondary_keywords())
    
    # Ranking improvements (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    improvements = DBRankHistory.query.filter(
        DBRankHistory.client_id.in_(client_ids),
        DBRankHistory.checked_at >= seven_days_ago,
        DBRankHistory.change > 0
    ).count()
    
    # Estimate MRR ($2,500 per active client)
    estimated_mrr = len(clients) * 2500
    
    return jsonify({
        'total_clients': len(clients),
        'estimated_mrr': estimated_mrr,
        'total_content_pending': pending_content,
        'total_urgent_alerts': urgent_alerts,
        'total_keywords_tracked': total_keywords,
        'total_ranking_improvements': improvements
    })


@agency_bp.route('/clients', methods=['GET'])
@token_required
def get_all_clients_status(current_user):
    """
    Get status summary for all clients
    
    Returns list of clients with:
        - Basic info
        - Health status (green/yellow/red)
        - Pending content count
        - Alert count
        - Ranking trend
        - Competitors tracked
    """
    # Get all clients
    clients = get_user_clients(current_user)
    # Sort by business name
    clients = sorted(clients, key=lambda c: c.business_name or '')
    
    result = []
    
    for client in clients:
        # Pending content
        pending = DBContentQueue.query.filter_by(
            client_id=client.id,
            status='pending'
        ).count()
        
        # Unread alerts
        alerts = DBAlert.query.filter_by(
            client_id=client.id,
            is_read=False
        ).count()
        
        urgent_alerts = DBAlert.query.filter_by(
            client_id=client.id,
            is_read=False,
            priority='high'
        ).count()
        
        # Competitors tracked
        competitors = DBCompetitor.query.filter_by(
            client_id=client.id,
            is_active=True
        ).count()
        
        # New competitor content (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        new_competitor_pages = DBCompetitorPage.query.filter(
            DBCompetitorPage.client_id == client.id,
            DBCompetitorPage.discovered_at >= seven_days_ago,
            DBCompetitorPage.is_new == True
        ).count()
        
        # Ranking trend (average change over last 7 days)
        recent_rankings = DBRankHistory.query.filter(
            DBRankHistory.client_id == client.id,
            DBRankHistory.checked_at >= seven_days_ago
        ).all()
        
        avg_change = 0
        if recent_rankings:
            total_change = sum(r.change or 0 for r in recent_rankings)
            avg_change = round(total_change / len(recent_rankings), 1)
        
        # Top 10 count
        # Get most recent ranking per keyword
        latest_rankings = DBRankHistory.query.filter_by(
            client_id=client.id
        ).order_by(DBRankHistory.checked_at.desc()).limit(50).all()
        
        seen_keywords = set()
        top_10_count = 0
        for r in latest_rankings:
            if r.keyword not in seen_keywords:
                seen_keywords.add(r.keyword)
                if r.position and r.position <= 10:
                    top_10_count += 1
        
        # Content stats
        total_blogs = DBBlogPost.query.filter_by(client_id=client.id).count()
        total_social = DBSocialPost.query.filter_by(client_id=client.id).count()
        
        # Determine health status
        health = 'green'
        health_reasons = []
        
        if urgent_alerts > 0:
            health = 'red'
            health_reasons.append(f'{urgent_alerts} urgent alerts')
        elif pending > 3:
            health = 'yellow'
            health_reasons.append(f'{pending} content pending')
        elif avg_change < -3:
            health = 'yellow'
            health_reasons.append('Rankings declining')
        elif new_competitor_pages > 0 and pending == 0:
            health = 'yellow'
            health_reasons.append(f'{new_competitor_pages} competitor posts not countered')
        
        result.append({
            'id': client.id,
            'business_name': client.business_name,
            'industry': client.industry,
            'geo': client.geo,
            'website_url': client.website_url,
            'health': health,
            'health_reasons': health_reasons,
            'stats': {
                'pending_content': pending,
                'total_alerts': alerts,
                'urgent_alerts': urgent_alerts,
                'competitors_tracked': competitors,
                'new_competitor_content': new_competitor_pages,
                'ranking_trend': avg_change,
                'top_10_keywords': top_10_count,
                'total_blogs': total_blogs,
                'total_social': total_social,
                'total_keywords': len(client.get_primary_keywords()) + len(client.get_secondary_keywords())
            },
            'created_at': client.created_at.isoformat() if client.created_at else None
        })
    
    return jsonify({'clients': result})


@agency_bp.route('/needs-attention', methods=['GET'])
@token_required
def get_needs_attention(current_user):
    """
    Get items that need immediate attention across all clients
    
    Returns:
        - Clients with pending content
        - Clients with urgent alerts
        - Clients with ranking drops
        - Recent competitor activity not yet countered
    """
    # Get accessible client IDs
    clients = get_user_clients(current_user)
    
    client_map = {c.id: c for c in clients}
    client_ids = list(client_map.keys())
    
    attention_items = []
    
    # Pending content by client
    pending_by_client = db.session.query(
        DBContentQueue.client_id,
        func.count(DBContentQueue.id).label('count')
    ).filter(
        DBContentQueue.client_id.in_(client_ids),
        DBContentQueue.status == 'pending'
    ).group_by(DBContentQueue.client_id).all()
    
    for client_id, count in pending_by_client:
        if count > 0:
            client = client_map.get(client_id)
            attention_items.append({
                'type': 'pending_content',
                'priority': 'high' if count >= 3 else 'medium',
                'client_id': client_id,
                'client_name': client.business_name if client else 'Unknown',
                'message': f'{count} content pieces awaiting approval',
                'action': 'Review and approve content',
                'link': f'/elite?client={client_id}'
            })
    
    # Urgent alerts
    urgent_alerts = DBAlert.query.filter(
        DBAlert.client_id.in_(client_ids),
        DBAlert.is_read == False,
        DBAlert.priority == 'high'
    ).order_by(DBAlert.created_at.desc()).limit(10).all()
    
    for alert in urgent_alerts:
        client = client_map.get(alert.client_id)
        attention_items.append({
            'type': 'urgent_alert',
            'priority': 'high',
            'client_id': alert.client_id,
            'client_name': client.business_name if client else 'Unknown',
            'message': alert.title,
            'detail': alert.message,
            'action': 'View alert',
            'link': f'/elite?client={alert.client_id}',
            'created_at': alert.created_at.isoformat() if alert.created_at else None
        })
    
    # New competitor content not countered
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    uncountered = DBCompetitorPage.query.filter(
        DBCompetitorPage.client_id.in_(client_ids),
        DBCompetitorPage.discovered_at >= seven_days_ago,
        DBCompetitorPage.was_countered == False
    ).order_by(DBCompetitorPage.discovered_at.desc()).limit(10).all()
    
    for page in uncountered:
        client = client_map.get(page.client_id)
        competitor = DBCompetitor.query.get(page.competitor_id)
        attention_items.append({
            'type': 'competitor_content',
            'priority': 'medium',
            'client_id': page.client_id,
            'client_name': client.business_name if client else 'Unknown',
            'message': f'Competitor published: "{page.title or page.url}"',
            'detail': f'From {competitor.name if competitor else "competitor"}',
            'action': 'Generate counter-content',
            'link': f'/elite?client={page.client_id}',
            'competitor_page_id': page.id
        })
    
    # Sort by priority
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    attention_items.sort(key=lambda x: priority_order.get(x['priority'], 3))
    
    return jsonify({'items': attention_items})


@agency_bp.route('/wins', methods=['GET'])
@token_required
def get_recent_wins(current_user):
    """
    Get ranking wins across all clients (last 7 days)
    
    Returns significant ranking improvements
    """
    # Get accessible client IDs
    clients = get_user_clients(current_user)
    
    client_map = {c.id: c for c in clients}
    client_ids = list(client_map.keys())
    
    # Get significant improvements (3+ positions)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    wins = DBRankHistory.query.filter(
        DBRankHistory.client_id.in_(client_ids),
        DBRankHistory.checked_at >= seven_days_ago,
        DBRankHistory.change >= 3,
        DBRankHistory.position != None
    ).order_by(DBRankHistory.change.desc()).limit(20).all()
    
    result = []
    for win in wins:
        client = client_map.get(win.client_id)
        prev_pos = (win.position + win.change) if win.position else None
        
        result.append({
            'client_id': win.client_id,
            'client_name': client.business_name if client else 'Unknown',
            'keyword': win.keyword,
            'previous_position': prev_pos,
            'current_position': win.position,
            'change': win.change,
            'search_volume': win.search_volume,
            'checked_at': win.checked_at.isoformat() if win.checked_at else None
        })
    
    # Calculate totals
    total_improvement = sum(w['change'] for w in result)
    
    return jsonify({
        'wins': result,
        'total_positions_gained': total_improvement,
        'win_count': len(result)
    })


@agency_bp.route('/activity', methods=['GET'])
@token_required
def get_recent_activity(current_user):
    """
    Get recent activity feed across all clients
    """
    # Get accessible client IDs
    clients = get_user_clients(current_user)
    
    client_map = {c.id: c for c in clients}
    client_ids = list(client_map.keys())
    
    activity = []
    
    # Recent alerts (all types)
    recent_alerts = DBAlert.query.filter(
        DBAlert.client_id.in_(client_ids)
    ).order_by(DBAlert.created_at.desc()).limit(20).all()
    
    for alert in recent_alerts:
        client = client_map.get(alert.client_id)
        
        icon = '🔔'
        if alert.alert_type == 'new_competitor_content':
            icon = '🚨'
        elif alert.alert_type == 'content_ready':
            icon = '✅'
        elif alert.alert_type == 'rank_change':
            icon = '📈'
        
        activity.append({
            'type': alert.alert_type,
            'icon': icon,
            'client_id': alert.client_id,
            'client_name': client.business_name if client else 'Unknown',
            'title': alert.title,
            'message': alert.message,
            'timestamp': alert.created_at.isoformat() if alert.created_at else None,
            'is_read': alert.is_read
        })
    
    # Recent content approvals
    recent_approved = DBContentQueue.query.filter(
        DBContentQueue.client_id.in_(client_ids),
        DBContentQueue.status == 'approved'
    ).order_by(DBContentQueue.approved_at.desc()).limit(10).all()
    
    for item in recent_approved:
        if item.approved_at:
            client = client_map.get(item.client_id)
            activity.append({
                'type': 'content_approved',
                'icon': '✅',
                'client_id': item.client_id,
                'client_name': client.business_name if client else 'Unknown',
                'title': 'Content approved',
                'message': (item.title[:50] + '...' if len(item.title or '') > 50 else item.title) or 'Untitled',
                'timestamp': item.approved_at.isoformat(),
                'is_read': True
            })
    
    # Sort by timestamp
    activity.sort(key=lambda x: x.get('timestamp') or '', reverse=True)
    
    return jsonify({'activity': activity[:30]})


@agency_bp.route('/content-queue', methods=['GET'])
@token_required
def get_all_pending_content(current_user):
    """
    Get all pending content across all clients
    """
    # Get accessible client IDs
    clients = get_user_clients(current_user)
    
    client_map = {c.id: c for c in clients}
    client_ids = list(client_map.keys())
    
    pending = DBContentQueue.query.filter(
        DBContentQueue.client_id.in_(client_ids),
        DBContentQueue.status == 'pending'
    ).order_by(DBContentQueue.created_at.desc()).all()
    
    result = []
    for item in pending:
        client = client_map.get(item.client_id)
        result.append({
            'id': item.id,
            'client_id': item.client_id,
            'client_name': client.business_name if client else 'Unknown',
            'title': item.title,
            'primary_keyword': item.primary_keyword,
            'trigger_type': item.trigger_type,
            'our_seo_score': item.our_seo_score,
            'competitor_seo_score': item.competitor_seo_score,
            'word_count': item.word_count,
            'created_at': item.created_at.isoformat() if item.created_at else None
        })
    
    return jsonify({'content': result})


@agency_bp.route('/stats/rankings', methods=['GET'])
@token_required
def get_ranking_stats(current_user):
    """
    Get ranking statistics across all clients
    """
    # Get accessible client IDs
    clients = get_user_clients(current_user)
    
    client_ids = [c.id for c in clients]
    
    # Get recent rankings
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    recent = DBRankHistory.query.filter(
        DBRankHistory.client_id.in_(client_ids),
        DBRankHistory.checked_at >= seven_days_ago
    ).all()
    
    # Calculate stats
    total_tracked = len(set(r.keyword for r in recent))
    in_top_3 = len([r for r in recent if r.position and r.position <= 3])
    in_top_10 = len([r for r in recent if r.position and r.position <= 10])
    improved = len([r for r in recent if r.change and r.change > 0])
    declined = len([r for r in recent if r.change and r.change < 0])
    
    return jsonify({
        'total_keywords_tracked': total_tracked,
        'in_top_3': in_top_3,
        'in_top_10': in_top_10,
        'improved': improved,
        'declined': declined,
        'net_change': improved - declined
    })
