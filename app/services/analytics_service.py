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
        self.ga4_property_id = os.environ.get('GA4_PROPERTY_ID', '')
        self.credentials_json = os.environ.get('GA4_CREDENTIALS_JSON', '')
        self._client = None
    
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
