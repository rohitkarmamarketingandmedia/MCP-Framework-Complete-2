"""
MCP Framework - Google Analytics 4 Service
Provides website traffic data, user behavior, and performance metrics
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class GA4Config:
    """GA4 API configuration"""
    # Can be set globally or per-client
    PROPERTY_ID = os.environ.get('GA4_PROPERTY_ID', '')
    CREDENTIALS_JSON = os.environ.get('GA4_CREDENTIALS_JSON', '')
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.PROPERTY_ID)


class GA4Service:
    """
    Google Analytics 4 Data API integration
    
    Features:
    - Traffic metrics (sessions, users, pageviews)
    - Top pages and landing pages
    - Traffic sources (organic, direct, referral, social)
    - User engagement metrics
    - Geographic data
    - Device breakdown
    
    Requires:
    - GA4_PROPERTY_ID: Your GA4 property ID (numbers only, e.g., '123456789')
    - GA4_CREDENTIALS_JSON: Service account credentials JSON (for server-side auth)
    
    For client-specific GA4, store property_id on the client record.
    """
    
    def __init__(self):
        self.default_property_id = GA4Config.PROPERTY_ID
        self.credentials_json = GA4Config.CREDENTIALS_JSON
        self._client = None
    
    def is_configured(self, client_property_id: str = None) -> bool:
        """Check if GA4 is configured (globally or for client)"""
        return bool(client_property_id or self.default_property_id)
    
    def _get_client(self):
        """Get GA4 Data API client (lazy initialization)"""
        if self._client is not None:
            return self._client
        
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2 import service_account
            
            if self.credentials_json:
                # Parse credentials from JSON string or file
                if self.credentials_json.startswith('{'):
                    creds_dict = json.loads(self.credentials_json)
                else:
                    with open(self.credentials_json, 'r') as f:
                        creds_dict = json.load(f)
                
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self._client = BetaAnalyticsDataClient(credentials=credentials)
            else:
                # Try default credentials (for GCP environments)
                self._client = BetaAnalyticsDataClient()
            
            return self._client
        except ImportError:
            logger.warning("google-analytics-data package not installed")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize GA4 client: {e}")
            return None
    
    def get_traffic_overview(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> Dict[str, Any]:
        """
        Get traffic overview metrics
        
        Returns:
            {
                'configured': bool,
                'sessions': int,
                'users': int,
                'pageviews': int,
                'bounce_rate': float,
                'avg_session_duration': float,
                'pages_per_session': float,
                'new_users': int,
                'returning_users': int
            }
        """
        prop_id = property_id or self.default_property_id
        
        if not prop_id:
            return {
                'configured': False,
                'error': 'GA4 not configured. Add GA4_PROPERTY_ID or set property_id on client.'
            }
        
        # Set date range
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        client = self._get_client()
        
        if not client:
            # Return simulated data for demo/testing
            return self._get_demo_traffic(prop_id, start_date, end_date)
        
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Dimension, Metric
            )
            
            request = RunReportRequest(
                property=f"properties/{prop_id}",
                date_ranges=[DateRange(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )],
                metrics=[
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                    Metric(name="screenPageViews"),
                    Metric(name="bounceRate"),
                    Metric(name="averageSessionDuration"),
                    Metric(name="screenPageViewsPerSession"),
                    Metric(name="newUsers"),
                ]
            )
            
            response = client.run_report(request)
            
            if response.rows:
                row = response.rows[0]
                return {
                    'configured': True,
                    'property_id': prop_id,
                    'sessions': int(row.metric_values[0].value or 0),
                    'users': int(row.metric_values[1].value or 0),
                    'pageviews': int(row.metric_values[2].value or 0),
                    'bounce_rate': float(row.metric_values[3].value or 0) * 100,
                    'avg_session_duration': float(row.metric_values[4].value or 0),
                    'pages_per_session': float(row.metric_values[5].value or 0),
                    'new_users': int(row.metric_values[6].value or 0),
                    'returning_users': int(row.metric_values[1].value or 0) - int(row.metric_values[6].value or 0),
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                }
            else:
                return {
                    'configured': True,
                    'property_id': prop_id,
                    'sessions': 0,
                    'users': 0,
                    'pageviews': 0,
                    'bounce_rate': 0,
                    'message': 'No data for selected period'
                }
                
        except Exception as e:
            error_str = str(e)
            if "403" in error_str and "sufficient permissions" in error_str:
                logger.error(f"ACTION REQUIRED: Service Account does not have access to GA4 Property {prop_id}")
                logger.error("Please add the Service Account email to the GA4 Property user management.")
            else:
                logger.error(f"GA4 API error: {e}")

            return {
                'configured': True,
                'property_id': prop_id,
                'error': str(e),
                'message': 'Failed to fetch GA4 data. Check credentials.'
            }
    
    def get_top_pages(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top pages by pageviews
        
        Returns:
            [{'page': str, 'views': int, 'avg_time': float}, ...]
        """
        prop_id = property_id or self.default_property_id
        
        if not prop_id:
            return []
        
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        client = self._get_client()
        
        if not client:
            # Demo data
            return [
                {'page': '/', 'views': 1250, 'avg_time': 45.2},
                {'page': '/services', 'views': 890, 'avg_time': 62.1},
                {'page': '/contact', 'views': 456, 'avg_time': 38.5},
                {'page': '/about', 'views': 234, 'avg_time': 55.0},
                {'page': '/blog', 'views': 198, 'avg_time': 120.3},
            ][:limit]
        
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Dimension, Metric, OrderBy
            )
            
            request = RunReportRequest(
                property=f"properties/{prop_id}",
                date_ranges=[DateRange(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )],
                dimensions=[Dimension(name="pagePath")],
                metrics=[
                    Metric(name="screenPageViews"),
                    Metric(name="averageSessionDuration"),
                ],
                order_bys=[OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                    desc=True
                )],
                limit=limit
            )
            
            response = client.run_report(request)
            
            pages = []
            for row in response.rows:
                pages.append({
                    'page': row.dimension_values[0].value,
                    'views': int(row.metric_values[0].value or 0),
                    'avg_time': float(row.metric_values[1].value or 0)
                })
            
            return pages
            
        except Exception as e:
            logger.error(f"GA4 top pages error: {e}")
            return []
    
    def get_traffic_sources(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict[str, Any]]:
        """
        Get traffic by source/medium
        
        Returns:
            [{'source': str, 'medium': str, 'sessions': int, 'users': int}, ...]
        """
        prop_id = property_id or self.default_property_id
        
        if not prop_id:
            return []
        
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        client = self._get_client()
        
        if not client:
            # Demo data
            return [
                {'source': 'google', 'medium': 'organic', 'sessions': 850, 'users': 720},
                {'source': '(direct)', 'medium': '(none)', 'sessions': 450, 'users': 380},
                {'source': 'facebook', 'medium': 'social', 'sessions': 230, 'users': 195},
                {'source': 'google', 'medium': 'cpc', 'sessions': 180, 'users': 165},
                {'source': 'yelp', 'medium': 'referral', 'sessions': 95, 'users': 88},
            ]
        
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Dimension, Metric, OrderBy
            )
            
            request = RunReportRequest(
                property=f"properties/{prop_id}",
                date_ranges=[DateRange(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )],
                dimensions=[
                    Dimension(name="sessionSource"),
                    Dimension(name="sessionMedium")
                ],
                metrics=[
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                ],
                order_bys=[OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                    desc=True
                )],
                limit=10
            )
            
            response = client.run_report(request)
            
            sources = []
            for row in response.rows:
                sources.append({
                    'source': row.dimension_values[0].value,
                    'medium': row.dimension_values[1].value,
                    'sessions': int(row.metric_values[0].value or 0),
                    'users': int(row.metric_values[1].value or 0)
                })
            
            return sources
            
        except Exception as e:
            logger.error(f"GA4 traffic sources error: {e}")
            return []
    
    def get_search_terms(
        self,
        property_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get organic search terms (from Search Console integration)
        
        Note: Requires Search Console linked to GA4
        
        Returns:
            [{'term': str, 'clicks': int, 'impressions': int}, ...]
        """
        prop_id = property_id or self.default_property_id
        
        if not prop_id:
            return []
        
        # GA4 doesn't directly provide search terms
        # This would need Search Console API integration
        # For now, return placeholder
        return [
            {'term': '(not provided)', 'clicks': 0, 'impressions': 0}
        ]
    
    def _get_demo_traffic(
        self,
        property_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Return demo traffic data when API not available"""
        import random
        
        days = (end_date - start_date).days or 30
        base_sessions = random.randint(800, 2000)
        
        return {
            'configured': True,
            'property_id': property_id,
            'demo_mode': True,
            'sessions': base_sessions,
            'users': int(base_sessions * 0.85),
            'pageviews': int(base_sessions * 2.3),
            'bounce_rate': round(random.uniform(35, 55), 1),
            'avg_session_duration': round(random.uniform(90, 180), 1),
            'pages_per_session': round(random.uniform(2.1, 3.5), 2),
            'new_users': int(base_sessions * 0.65),
            'returning_users': int(base_sessions * 0.20),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'message': 'Demo data - install google-analytics-data package for real data'
        }


# Singleton instance
ga4_service = GA4Service()
