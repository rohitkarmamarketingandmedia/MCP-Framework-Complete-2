"""
MCP Framework - Analytics Service
Google Analytics 4 integration
"""
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta


class AnalyticsService:
    """Google Analytics 4 reporting service"""
    
    def __init__(self):
        self._client = None
    
    @property
    def ga4_property_id(self):
        return os.environ.get('GA4_PROPERTY_ID', '')
    
    @property
    def credentials_json(self):
        return os.environ.get('GA4_CREDENTIALS_JSON', '')
    
    def _get_client(self):
        """Initialize GA4 client (lazy loading)"""
        if self._client:
            return self._client
        
        if not self.credentials_json:
            return None
        
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2 import service_account
            import json
            
            credentials_info = json.loads(self.credentials_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
            self._client = BetaAnalyticsDataClient(credentials=credentials)
            return self._client
        except Exception:
            return None
    
    def get_traffic_metrics(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> Dict[str, Any]:
        """
        Get basic traffic metrics
        
        Returns:
            {
                'sessions': int,
                'users': int,
                'pageviews': int,
                'bounce_rate': float,
                'avg_session_duration': float,
                'organic_sessions': int
            }
        """
        property_id = property_id or self.ga4_property_id
        
        if not property_id:
            return self._mock_traffic_metrics()
        
        client = self._get_client()
        if not client:
            return self._mock_traffic_metrics()
        
        start_date = start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = end_date or datetime.utcnow()
        
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest,
                DateRange,
                Dimension,
                Metric
            )
            
            request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[DateRange(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )],
                metrics=[
                    Metric(name='sessions'),
                    Metric(name='totalUsers'),
                    Metric(name='screenPageViews'),
                    Metric(name='bounceRate'),
                    Metric(name='averageSessionDuration')
                ]
            )
            
            response = client.run_report(request)
            
            if response.rows:
                row = response.rows[0]
                return {
                    'sessions': int(row.metric_values[0].value),
                    'users': int(row.metric_values[1].value),
                    'pageviews': int(row.metric_values[2].value),
                    'bounce_rate': float(row.metric_values[3].value),
                    'avg_session_duration': float(row.metric_values[4].value),
                    'period': {
                        'start': start_date.isoformat(),
                        'end': end_date.isoformat()
                    }
                }
            
            return self._mock_traffic_metrics()
            
        except Exception as e:
            return {'error': str(e), **self._mock_traffic_metrics()}
    
    def get_detailed_traffic(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> Dict[str, Any]:
        """Get detailed traffic breakdown by source/medium"""
        property_id = property_id or self.ga4_property_id
        
        if not property_id or not self._get_client():
            return self._mock_detailed_traffic()
        
        start_date = start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = end_date or datetime.utcnow()
        
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest,
                DateRange,
                Dimension,
                Metric
            )
            
            client = self._get_client()
            
            request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[DateRange(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )],
                dimensions=[
                    Dimension(name='sessionDefaultChannelGrouping')
                ],
                metrics=[
                    Metric(name='sessions'),
                    Metric(name='totalUsers'),
                    Metric(name='conversions')
                ]
            )
            
            response = client.run_report(request)
            
            channels = []
            for row in response.rows:
                channels.append({
                    'channel': row.dimension_values[0].value,
                    'sessions': int(row.metric_values[0].value),
                    'users': int(row.metric_values[1].value),
                    'conversions': int(row.metric_values[2].value)
                })
            
            return {
                'channels': channels,
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            }
            
        except Exception as e:
            return {'error': str(e), **self._mock_detailed_traffic()}
    
    def get_page_metrics(
        self,
        property_id: str = None,
        page_path: str = None
    ) -> Dict[str, Any]:
        """Get metrics for a specific page"""
        property_id = property_id or self.ga4_property_id
        
        if not property_id or not page_path or not self._get_client():
            return self._mock_page_metrics(page_path)
        
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest,
                DateRange,
                Dimension,
                Metric,
                FilterExpression,
                Filter
            )
            
            client = self._get_client()
            
            request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[DateRange(
                    start_date='30daysAgo',
                    end_date='today'
                )],
                dimensions=[Dimension(name='pagePath')],
                metrics=[
                    Metric(name='screenPageViews'),
                    Metric(name='averageSessionDuration'),
                    Metric(name='bounceRate')
                ],
                dimension_filter=FilterExpression(
                    filter=Filter(
                        field_name='pagePath',
                        string_filter=Filter.StringFilter(
                            match_type=Filter.StringFilter.MatchType.CONTAINS,
                            value=page_path
                        )
                    )
                )
            )
            
            response = client.run_report(request)
            
            if response.rows:
                row = response.rows[0]
                return {
                    'page_path': page_path,
                    'pageviews': int(row.metric_values[0].value),
                    'avg_time_on_page': float(row.metric_values[1].value),
                    'bounce_rate': float(row.metric_values[2].value)
                }
            
            return self._mock_page_metrics(page_path)
            
        except Exception as e:
            return {'error': str(e), **self._mock_page_metrics(page_path)}
    
    def get_conversion_metrics(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        goal_names: List[str] = None
    ) -> Dict[str, Any]:
        """Get conversion/goal metrics"""
        return self._mock_conversion_metrics()
    
    # Mock data methods
    def _mock_traffic_metrics(self) -> Dict:
        return {
            'sessions': 2450,
            'users': 1890,
            'pageviews': 6720,
            'bounce_rate': 42.5,
            'avg_session_duration': 185.3,
            'organic_sessions': 1420,
            'note': 'Mock data - configure GA4_PROPERTY_ID and GA4_CREDENTIALS_JSON for real data'
        }
    
    def _mock_detailed_traffic(self) -> Dict:
        return {
            'channels': [
                {'channel': 'Organic Search', 'sessions': 1420, 'users': 1180, 'conversions': 35},
                {'channel': 'Direct', 'sessions': 580, 'users': 450, 'conversions': 12},
                {'channel': 'Referral', 'sessions': 280, 'users': 240, 'conversions': 8},
                {'channel': 'Social', 'sessions': 170, 'users': 150, 'conversions': 5}
            ],
            'note': 'Mock data - configure GA4 credentials for real data'
        }
    
    def _mock_page_metrics(self, page_path: str = None) -> Dict:
        return {
            'page_path': page_path or '/unknown',
            'pageviews': 245,
            'avg_time_on_page': 142.5,
            'bounce_rate': 38.2,
            'note': 'Mock data'
        }
    
    def _mock_conversion_metrics(self) -> Dict:
        return {
            'total_conversions': 62,
            'conversion_rate': 2.53,
            'goals': [
                {'name': 'Contact Form', 'completions': 35},
                {'name': 'Phone Click', 'completions': 27}
            ],
            'note': 'Mock data'
        }


# ==========================================
# COMPARATIVE ANALYTICS SERVICE
# ==========================================

class ComparativeAnalytics:
    """Service for period-over-period comparative analytics"""
    
    def get_period_dates(self, period: str = 'month') -> tuple:
        """
        Get start/end dates for current and previous periods
        
        Args:
            period: 'week', 'month', 'quarter', 'year'
            
        Returns:
            (current_start, current_end, previous_start, previous_end)
        """
        now = datetime.utcnow()
        
        if period == 'week':
            current_start = now - timedelta(days=7)
            previous_start = now - timedelta(days=14)
            previous_end = current_start
        elif period == 'month':
            current_start = now - timedelta(days=30)
            previous_start = now - timedelta(days=60)
            previous_end = current_start
        elif period == 'quarter':
            current_start = now - timedelta(days=90)
            previous_start = now - timedelta(days=180)
            previous_end = current_start
        elif period == 'year':
            current_start = now - timedelta(days=365)
            previous_start = now - timedelta(days=730)
            previous_end = current_start
        else:
            current_start = now - timedelta(days=30)
            previous_start = now - timedelta(days=60)
            previous_end = current_start
        
        return current_start, now, previous_start, previous_end
    
    def calculate_change(self, current: float, previous: float) -> Dict:
        """Calculate percentage change and direction"""
        if previous == 0:
            if current == 0:
                return {'change': 0, 'direction': 'flat', 'percent': '0%'}
            return {'change': 100, 'direction': 'up', 'percent': '+100%'}
        
        change = ((current - previous) / previous) * 100
        direction = 'up' if change > 0 else 'down' if change < 0 else 'flat'
        percent = f"+{change:.1f}%" if change > 0 else f"{change:.1f}%"
        
        return {
            'change': round(change, 1),
            'direction': direction,
            'percent': percent
        }
    
    def get_lead_analytics(self, client_id: Optional[str] = None, period: str = 'month') -> Dict:
        """Get lead analytics with period-over-period comparison"""
        from app.models.db_models import DBLead
        
        current_start, current_end, previous_start, previous_end = self.get_period_dates(period)
        
        base_query = DBLead.query
        if client_id:
            base_query = base_query.filter(DBLead.client_id == client_id)
        
        # Current period
        current_leads = base_query.filter(
            DBLead.created_at >= current_start,
            DBLead.created_at <= current_end
        ).all()
        
        current_total = len(current_leads)
        current_converted = len([l for l in current_leads if l.status == 'converted'])
        current_revenue = sum(l.actual_value or 0 for l in current_leads if l.status == 'converted')
        
        # Previous period
        previous_leads = base_query.filter(
            DBLead.created_at >= previous_start,
            DBLead.created_at <= previous_end
        ).all()
        
        previous_total = len(previous_leads)
        previous_converted = len([l for l in previous_leads if l.status == 'converted'])
        previous_revenue = sum(l.actual_value or 0 for l in previous_leads if l.status == 'converted')
        
        current_rate = (current_converted / current_total * 100) if current_total > 0 else 0
        previous_rate = (previous_converted / previous_total * 100) if previous_total > 0 else 0
        
        # Source breakdown
        sources = {}
        for lead in current_leads:
            source = lead.source or 'unknown'
            if source not in sources:
                sources[source] = {'count': 0, 'converted': 0, 'revenue': 0}
            sources[source]['count'] += 1
            if lead.status == 'converted':
                sources[source]['converted'] += 1
                sources[source]['revenue'] += lead.actual_value or 0
        
        return {
            'period': period,
            'current': {
                'total_leads': current_total,
                'converted': current_converted,
                'conversion_rate': round(current_rate, 1),
                'revenue': current_revenue
            },
            'previous': {
                'total_leads': previous_total,
                'converted': previous_converted,
                'conversion_rate': round(previous_rate, 1),
                'revenue': previous_revenue
            },
            'comparison': {
                'leads': self.calculate_change(current_total, previous_total),
                'converted': self.calculate_change(current_converted, previous_converted),
                'revenue': self.calculate_change(current_revenue, previous_revenue)
            },
            'by_source': sources
        }
    
    def get_content_analytics(self, client_id: Optional[str] = None, period: str = 'month') -> Dict:
        """Get content production analytics"""
        from app.models.db_models import DBBlogPost, DBSocialPost, DBServicePage, DBContentQueue
        
        current_start, current_end, previous_start, previous_end = self.get_period_dates(period)
        
        # Blogs
        blog_query = DBBlogPost.query
        if client_id:
            blog_query = blog_query.filter(DBBlogPost.client_id == client_id)
        
        current_blogs = blog_query.filter(DBBlogPost.created_at >= current_start).count()
        previous_blogs = blog_query.filter(
            DBBlogPost.created_at >= previous_start,
            DBBlogPost.created_at <= previous_end
        ).count()
        
        # Social
        social_query = DBSocialPost.query
        if client_id:
            social_query = social_query.filter(DBSocialPost.client_id == client_id)
        
        current_social = social_query.filter(DBSocialPost.created_at >= current_start).count()
        previous_social = social_query.filter(
            DBSocialPost.created_at >= previous_start,
            DBSocialPost.created_at <= previous_end
        ).count()
        
        # Pages
        page_query = DBServicePage.query
        if client_id:
            page_query = page_query.filter(DBServicePage.client_id == client_id)
        
        current_pages = page_query.filter(DBServicePage.created_at >= current_start).count()
        previous_pages = page_query.filter(
            DBServicePage.created_at >= previous_start,
            DBServicePage.created_at <= previous_end
        ).count()
        
        # Queue
        queue_query = DBContentQueue.query
        if client_id:
            queue_query = queue_query.filter(DBContentQueue.client_id == client_id)
        
        pending = queue_query.filter(DBContentQueue.status == 'pending').count()
        
        total_current = current_blogs + current_social + current_pages
        total_previous = previous_blogs + previous_social + previous_pages
        
        return {
            'period': period,
            'current': {
                'blogs': current_blogs,
                'social': current_social,
                'pages': current_pages,
                'total': total_current
            },
            'previous': {
                'blogs': previous_blogs,
                'social': previous_social,
                'pages': previous_pages,
                'total': total_previous
            },
            'comparison': {
                'blogs': self.calculate_change(current_blogs, previous_blogs),
                'social': self.calculate_change(current_social, previous_social),
                'pages': self.calculate_change(current_pages, previous_pages),
                'total': self.calculate_change(total_current, total_previous)
            },
            'pending_queue': pending
        }
    
    def get_ranking_analytics(self, client_id: str, period: str = 'month') -> Dict:
        """Get keyword ranking analytics with top movers"""
        from app.models.db_models import DBRankHistory
        
        current_start, current_end, previous_start, previous_end = self.get_period_dates(period)
        
        # Current rankings (latest per keyword)
        current_rankings = DBRankHistory.query.filter(
            DBRankHistory.client_id == client_id,
            DBRankHistory.checked_at >= current_start
        ).order_by(DBRankHistory.checked_at.desc()).all()
        
        current_positions = {}
        for r in current_rankings:
            if r.keyword not in current_positions:
                current_positions[r.keyword] = r.position
        
        # Previous rankings
        previous_rankings = DBRankHistory.query.filter(
            DBRankHistory.client_id == client_id,
            DBRankHistory.checked_at >= previous_start,
            DBRankHistory.checked_at <= previous_end
        ).order_by(DBRankHistory.checked_at.desc()).all()
        
        previous_positions = {}
        for r in previous_rankings:
            if r.keyword not in previous_positions:
                previous_positions[r.keyword] = r.position
        
        # Calculate metrics
        current_top_3 = sum(1 for p in current_positions.values() if p and p <= 3)
        current_top_10 = sum(1 for p in current_positions.values() if p and p <= 10)
        previous_top_3 = sum(1 for p in previous_positions.values() if p and p <= 3)
        previous_top_10 = sum(1 for p in previous_positions.values() if p and p <= 10)
        
        # Top movers
        movers = []
        for keyword, current_pos in current_positions.items():
            previous_pos = previous_positions.get(keyword)
            if current_pos and previous_pos:
                change = previous_pos - current_pos
                movers.append({
                    'keyword': keyword,
                    'current': current_pos,
                    'previous': previous_pos,
                    'change': change,
                    'direction': 'up' if change > 0 else 'down' if change < 0 else 'flat'
                })
        
        top_gainers = sorted([m for m in movers if m['change'] > 0], key=lambda x: x['change'], reverse=True)[:5]
        top_losers = sorted([m for m in movers if m['change'] < 0], key=lambda x: x['change'])[:5]
        avg_change = sum(m['change'] for m in movers) / len(movers) if movers else 0
        
        return {
            'period': period,
            'current': {
                'keywords': len(current_positions),
                'top_3': current_top_3,
                'top_10': current_top_10
            },
            'previous': {
                'keywords': len(previous_positions),
                'top_3': previous_top_3,
                'top_10': previous_top_10
            },
            'comparison': {
                'top_3': self.calculate_change(current_top_3, previous_top_3),
                'top_10': self.calculate_change(current_top_10, previous_top_10)
            },
            'avg_position_change': round(avg_change, 1),
            'top_gainers': top_gainers,
            'top_losers': top_losers
        }
    
    def get_client_health_score(self, client_id: str) -> Dict:
        """Calculate comprehensive health score (0-100)"""
        scores = {'leads': 0, 'content': 0, 'rankings': 0}
        
        # Lead score (33 points max)
        lead_data = self.get_lead_analytics(client_id, 'month')
        lead_change = lead_data['comparison']['leads']['change']
        if lead_change >= 20:
            scores['leads'] = 33
        elif lead_change >= 0:
            scores['leads'] = 25
        elif lead_change >= -10:
            scores['leads'] = 15
        else:
            scores['leads'] = 5
        
        # Content score (33 points max)
        content_data = self.get_content_analytics(client_id, 'month')
        if content_data['current']['total'] >= 10:
            scores['content'] = 33
        elif content_data['current']['total'] >= 5:
            scores['content'] = 25
        elif content_data['current']['total'] >= 2:
            scores['content'] = 15
        else:
            scores['content'] = 5
        
        # Ranking score (34 points max)
        rank_data = self.get_ranking_analytics(client_id, 'month')
        if rank_data['current']['top_10'] >= 10:
            scores['rankings'] = 34
        elif rank_data['current']['top_10'] >= 5:
            scores['rankings'] = 25
        elif rank_data['current']['top_10'] >= 2:
            scores['rankings'] = 15
        else:
            scores['rankings'] = 5
        
        total = sum(scores.values())
        
        if total >= 85:
            status, color = 'excellent', 'green'
        elif total >= 65:
            status, color = 'good', 'green'
        elif total >= 45:
            status, color = 'fair', 'yellow'
        else:
            status, color = 'needs_attention', 'red'
        
        return {
            'client_id': client_id,
            'score': total,
            'status': status,
            'color': color,
            'breakdown': scores
        }
    
    def get_agency_summary(self, period: str = 'month') -> Dict:
        """Get agency-wide analytics summary"""
        from app.models.db_models import DBClient, DBLead, DBBlogPost, DBSocialPost
        from app.database import db
        from sqlalchemy import func
        
        current_start, current_end, previous_start, previous_end = self.get_period_dates(period)
        
        total_clients = DBClient.query.count()
        new_clients = DBClient.query.filter(DBClient.created_at >= current_start).count()
        
        current_leads = DBLead.query.filter(DBLead.created_at >= current_start).count()
        previous_leads = DBLead.query.filter(
            DBLead.created_at >= previous_start,
            DBLead.created_at <= previous_end
        ).count()
        
        current_content = (
            DBBlogPost.query.filter(DBBlogPost.created_at >= current_start).count() +
            DBSocialPost.query.filter(DBSocialPost.created_at >= current_start).count()
        )
        previous_content = (
            DBBlogPost.query.filter(
                DBBlogPost.created_at >= previous_start,
                DBBlogPost.created_at <= previous_end
            ).count() +
            DBSocialPost.query.filter(
                DBSocialPost.created_at >= previous_start,
                DBSocialPost.created_at <= previous_end
            ).count()
        )
        
        current_revenue = db.session.query(func.sum(DBLead.actual_value)).filter(
            DBLead.status == 'converted',
            DBLead.converted_at >= current_start
        ).scalar() or 0
        
        previous_revenue = db.session.query(func.sum(DBLead.actual_value)).filter(
            DBLead.status == 'converted',
            DBLead.converted_at >= previous_start,
            DBLead.converted_at <= previous_end
        ).scalar() or 0
        
        return {
            'period': period,
            'clients': {'total': total_clients, 'new': new_clients},
            'leads': {
                'current': current_leads,
                'previous': previous_leads,
                'change': self.calculate_change(current_leads, previous_leads)
            },
            'content': {
                'current': current_content,
                'previous': previous_content,
                'change': self.calculate_change(current_content, previous_content)
            },
            'revenue': {
                'current': current_revenue,
                'previous': previous_revenue,
                'change': self.calculate_change(current_revenue, previous_revenue)
            }
        }


# Singleton instances
analytics_service = AnalyticsService()
comparative_analytics = ComparativeAnalytics()
