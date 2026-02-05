"""
MCP Framework - Analytics Service
Google Analytics 4 integration
"""
import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
            date_range = DateRange(
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            # Request 1: Channel breakdown
            channel_request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[date_range],
                dimensions=[
                    Dimension(name='sessionDefaultChannelGrouping')
                ],
                metrics=[
                    Metric(name='sessions'),
                    Metric(name='totalUsers'),
                    Metric(name='conversions')
                ]
            )
            
            channel_response = client.run_report(channel_request)
            
            channels = []
            for row in channel_response.rows:
                channels.append({
                    'channel': row.dimension_values[0].value,
                    'sessions': int(row.metric_values[0].value),
                    'users': int(row.metric_values[1].value),
                    'conversions': int(row.metric_values[2].value)
                })
            
            # Request 2: Overall metrics (pageviews, bounce rate)
            metrics_request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[date_range],
                metrics=[
                    Metric(name='screenPageViews'),
                    Metric(name='bounceRate'),
                    Metric(name='averageSessionDuration')
                ]
            )
            
            metrics_response = client.run_report(metrics_request)
            
            pageviews = 0
            bounce_rate = 0
            avg_session_duration = 0
            if metrics_response.rows:
                row = metrics_response.rows[0]
                pageviews = int(float(row.metric_values[0].value))
                bounce_rate = round(float(row.metric_values[1].value) * 100, 1)
                avg_session_duration = round(float(row.metric_values[2].value), 1)
            
            # Request 3: Top pages
            pages_request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[date_range],
                dimensions=[
                    Dimension(name='pagePath')
                ],
                metrics=[
                    Metric(name='screenPageViews')
                ],
                limit=10
            )
            
            pages_response = client.run_report(pages_request)
            
            top_pages = []
            for row in pages_response.rows:
                top_pages.append({
                    'page': row.dimension_values[0].value,
                    'views': int(row.metric_values[0].value)
                })
            
            return {
                'channels': channels,
                'pageviews': pageviews,
                'bounce_rate': bounce_rate,
                'avg_session_duration': avg_session_duration,
                'top_pages': top_pages,
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"GA4 detailed traffic error: {e}")
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
    
    def get_period_dates(self, period: str = 'month', use_calendar: bool = True) -> tuple:
        """
        Get start/end dates for current and previous periods
        
        Args:
            period: 'week', 'month', 'quarter', 'year'
            use_calendar: If true, use calendar boundaries (e.g. 1st of month)
            
        Returns:
            (current_start, current_end, previous_start, previous_end)
        """
        now = datetime.utcnow()
        
        if period == 'month' and use_calendar:
            # Current month: 1st of this month to now
            current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Previous month: 1st of last month to last day of last month
            if current_start.month == 1:
                previous_start = current_start.replace(year=current_start.year - 1, month=12)
            else:
                previous_start = current_start.replace(month=current_start.month - 1)
            
            previous_end = current_start - timedelta(microseconds=1)
            
        elif period == 'week' and use_calendar:
            # Current week: Monday to now
            current_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            previous_start = current_start - timedelta(days=7)
            previous_end = current_start - timedelta(microseconds=1)
            
        elif period == 'week':
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
        from app.services.client_health_service import get_client_health_service
        
        health_service = get_client_health_service()
        health = health_service.calculate_health_score(client_id)
        
        return {
            'client_id': client_id,
            'score': health.total,
            'status': health.status,
            'color': health.color,
            'breakdown': health.to_dict()['breakdown'],
            'grade': health.grade
        }
        
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


class SearchConsoleService:
    """
    Google Search Console API integration for search terms data
    
    Requires:
    - GSC_CREDENTIALS_JSON environment variable with service account credentials
    - Site verified in Google Search Console
    """
    
    def __init__(self):
        self._client = None
    
    def _get_client(self):
        """Get or create Search Console API client"""
        if self._client:
            return self._client
        
        try:
            import json
            import os
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            credentials_json = os.environ.get('GSC_CREDENTIALS_JSON') or os.environ.get('GA4_CREDENTIALS_JSON')
            if not credentials_json:
                logger.debug("No GSC_CREDENTIALS_JSON or GA4_CREDENTIALS_JSON found")
                return None
            
            credentials_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/webmasters.readonly']
            )
            
            self._client = build('searchconsole', 'v1', credentials=credentials)
            return self._client
            
        except ImportError:
            logger.warning("Google API client not installed. Run: pip install google-api-python-client")
            return None
        except Exception as e:
            logger.error(f"Failed to create Search Console client: {e}")
            return None
    
    def get_search_terms(
        self,
        site_url: str,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top search terms from Google Search Console
        
        Args:
            site_url: Site URL (e.g., 'https://example.com' or 'sc-domain:example.com')
            start_date: Start date
            end_date: End date
            limit: Max number of terms to return
        
        Returns:
            [{'term': str, 'clicks': int, 'impressions': int, 'ctr': float, 'position': float}]
        """
        if not site_url:
            return []
        
        client = self._get_client()
        if not client:
            return []
        
        start_date = start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = end_date or datetime.utcnow()
        
        try:
            request = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['query'],
                'rowLimit': limit,
                'startRow': 0
            }
            
            response = client.searchanalytics().query(
                siteUrl=site_url,
                body=request
            ).execute()
            
            terms = []
            for row in response.get('rows', []):
                terms.append({
                    'term': row['keys'][0],
                    'clicks': int(row.get('clicks', 0)),
                    'impressions': int(row.get('impressions', 0)),
                    'ctr': round(row.get('ctr', 0) * 100, 1),
                    'position': round(row.get('position', 0), 1)
                })
            
            return terms
            
        except Exception as e:
            logger.error(f"Search Console API error: {e}")
            return []
    
    def get_top_pages(
        self,
        site_url: str,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top pages from Search Console"""
        if not site_url:
            return []
        
        client = self._get_client()
        if not client:
            return []
        
        start_date = start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = end_date or datetime.utcnow()
        
        try:
            request = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['page'],
                'rowLimit': limit
            }
            
            response = client.searchanalytics().query(
                siteUrl=site_url,
                body=request
            ).execute()
            
            pages = []
            for row in response.get('rows', []):
                pages.append({
                    'page': row['keys'][0],
                    'clicks': int(row.get('clicks', 0)),
                    'impressions': int(row.get('impressions', 0)),
                    'position': round(row.get('position', 0), 1)
                })
            
            return pages
            
        except Exception as e:
            logger.error(f"Search Console API error: {e}")
            return []


# Singleton instances
analytics_service = AnalyticsService()
comparative_analytics = ComparativeAnalytics()
search_console_service = SearchConsoleService()
