"""
MCP Framework - CallRail Integration Service
Provides call tracking, recordings, and transcripts for client reporting
"""
import os
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from functools import lru_cache

logger = logging.getLogger(__name__)


class CallRailConfig:
    """CallRail API configuration"""
    BASE_URL = 'https://api.callrail.com/v3'
    
    @classmethod
    def get_api_key(cls):
        """Get API key at runtime"""
        return os.environ.get('CALLRAIL_API_KEY', '')
    
    @classmethod
    def get_account_id(cls):
        """Get account ID at runtime"""
        return os.environ.get('CALLRAIL_ACCOUNT_ID', '')
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_api_key() and cls.get_account_id())


class CallRailService:
    """
    CallRail API integration for call tracking and analytics
    
    Features:
    - List calls with filters (date, duration, answered, etc.)
    - Get call recordings (MP3 URLs)
    - Get call transcripts (requires Conversation Intelligence)
    - Call summaries and metrics
    - Lead quality scoring based on call duration
    """
    
    def __init__(self):
        self.base_url = CallRailConfig.BASE_URL
    
    @property
    def api_key(self):
        """Get API key at runtime so env var changes are picked up"""
        return CallRailConfig.get_api_key()
    
    @property
    def account_id(self):
        """Get account ID at runtime so env var changes are picked up"""
        return CallRailConfig.get_account_id()
    
    def _get_session(self):
        """Create a new session with current credentials"""
        session = requests.Session()
        session.headers.update({
            'Authorization': f'Token token={self.api_key}',
            'Content-Type': 'application/json'
        })
        return session
    
    def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
        """Make API request to CallRail"""
        url = f"{self.base_url}/a/{self.account_id}{endpoint}"
        
        try:
            session = self._get_session()
            response = session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=15  # Reduced timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Don't spam logs on 4xx client errors
            if response.status_code >= 400 and response.status_code < 500:
                logger.debug(f"CallRail API {response.status_code}: {endpoint}")
            else:
                logger.error(f"CallRail API error: {e}")
            return {'error': str(e), 'status_code': response.status_code}
        except requests.exceptions.Timeout:
            logger.warning(f"CallRail API timeout: {endpoint}")
            return {'error': 'Request timeout', 'status_code': 408}
        except requests.exceptions.RequestException as e:
            logger.error(f"CallRail API error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # CALLS
    # ==========================================
    
    def get_calls(
        self,
        company_id: str = None,
        start_date: str = None,
        end_date: str = None,
        date_range: str = 'this_month',
        answered: bool = None,
        min_duration: int = None,
        per_page: int = 100,
        page: int = 1,
        fields: List[str] = None
    ) -> Dict[str, Any]:
        """
        Get list of calls with optional filters
        
        Args:
            company_id: Filter by specific company/client
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            date_range: Preset range (today, yesterday, this_week, last_week, this_month, last_month, all_time)
            answered: Filter by answered status
            min_duration: Minimum call duration in seconds
            per_page: Results per page (max 250)
            page: Page number
            fields: Specific fields to include (e.g., ['recording', 'transcription'])
        
        Returns:
            Dictionary with calls list and pagination info
        """
        params = {
            'per_page': per_page,
            'page': page,
            'sort': 'start_time',
            'order': 'desc'
        }
        
        if company_id:
            params['company_id'] = company_id
        
        if start_date and end_date:
            params['start_date'] = start_date
            params['end_date'] = end_date
        else:
            params['date_range'] = date_range
        
        if answered is not None:
            params['answered'] = 'true' if answered else 'false'
        
        if min_duration:
            params['min_duration'] = min_duration
        
        if fields:
            params['fields'] = ','.join(fields)
        
        result = self._request('GET', '/calls.json', params=params)
        
        if 'error' not in result:
            # Enhance calls with lead quality scoring
            for call in result.get('calls', []):
                call['lead_quality'] = self._calculate_lead_quality(call)
        
        return result
    
    def get_call(self, call_id: str, include_recording: bool = True, include_transcript: bool = True) -> Dict[str, Any]:
        """
        Get single call details with recording and transcript
        
        Args:
            call_id: The call ID
            include_recording: Include recording URL
            include_transcript: Include transcription (requires CI plan)
        
        Returns:
            Call details dictionary
        """
        fields = []
        if include_recording:
            fields.append('recording')
        if include_transcript:
            fields.extend(['transcription', 'conversational_transcript'])
        
        params = {}
        if fields:
            params['fields'] = ','.join(fields)
        
        return self._request('GET', f'/calls/{call_id}.json', params=params)
    
    def get_call_recording_url(self, call_id: str) -> Optional[str]:
        """Get the MP3 recording URL for a call"""
        result = self._request('GET', f'/calls/{call_id}/recording.json')
        return result.get('url')
    
    # ==========================================
    # METRICS & SUMMARIES
    # ==========================================
    
    def get_call_summary(
        self,
        company_id: str = None,
        date_range: str = 'this_month',
        start_date: str = None,
        end_date: str = None,
        group_by: str = 'day'
    ) -> Dict[str, Any]:
        """
        Get call summary/metrics report
        
        Args:
            company_id: Filter by company
            date_range: Preset date range
            start_date: Custom start date
            end_date: Custom end date
            group_by: Grouping (day, week, month, source, campaign, keyword)
        
        Returns:
            Summary metrics dictionary
        """
        params = {
            'group_by': group_by
        }
        
        if company_id:
            params['company_id'] = company_id
        
        if start_date and end_date:
            params['start_date'] = start_date
            params['end_date'] = end_date
        else:
            params['date_range'] = date_range
        
        return self._request('GET', '/reports/calls/summary.json', params=params)
    
    def get_client_call_metrics(self, company_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive call metrics for a client
        
        Returns metrics formatted for the client portal dashboard
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Get all calls for period
        calls_result = self.get_calls(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            per_page=250,
            fields=['duration', 'answered', 'voicemail', 'source', 'first_call']
        )
        
        calls = calls_result.get('calls', [])
        
        if not calls:
            return {
                'total_calls': 0,
                'answered': 0,
                'missed': 0,
                'voicemails': 0,
                'answer_rate': 0,
                'avg_duration': 0,
                'first_time_callers': 0,
                'hot_leads': 0,
                'by_source': {},
                'by_day': [],
                'trend': 0
            }
        
        # Calculate metrics
        total = len(calls)
        answered = len([c for c in calls if c.get('answered')])
        missed = total - answered
        voicemails = len([c for c in calls if c.get('voicemail')])
        first_time = len([c for c in calls if c.get('first_call')])
        
        # Hot leads = calls > 2 minutes (120 seconds)
        hot_leads = len([c for c in calls if c.get('duration', 0) > 120])
        
        # Average duration (answered calls only)
        answered_calls = [c for c in calls if c.get('answered')]
        avg_duration = sum(c.get('duration', 0) for c in answered_calls) / len(answered_calls) if answered_calls else 0
        
        # By source
        by_source = {}
        for call in calls:
            source = call.get('source', 'Direct')
            by_source[source] = by_source.get(source, 0) + 1
        
        # By day (for chart)
        by_day = {}
        for call in calls:
            day = call.get('start_time', '')[:10]
            if day:
                by_day[day] = by_day.get(day, 0) + 1
        
        by_day_list = [{'date': k, 'calls': v} for k, v in sorted(by_day.items())]
        
        # Calculate trend vs previous period
        prev_start = (datetime.now() - timedelta(days=days*2)).strftime('%Y-%m-%d')
        prev_end = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        prev_calls = self.get_calls(
            company_id=company_id,
            start_date=prev_start,
            end_date=prev_end,
            per_page=1
        )
        prev_total = prev_calls.get('total_records', 0)
        
        trend = 0
        if prev_total > 0:
            trend = round(((total - prev_total) / prev_total) * 100)
        
        return {
            'total_calls': total,
            'answered': answered,
            'missed': missed,
            'voicemails': voicemails,
            'answer_rate': round((answered / total) * 100) if total > 0 else 0,
            'avg_duration': round(avg_duration),
            'avg_duration_formatted': self._format_duration(avg_duration),
            'first_time_callers': first_time,
            'hot_leads': hot_leads,
            'by_source': by_source,
            'by_day': by_day_list,
            'trend': trend,
            'period_days': days
        }
    
    def get_recent_calls(
        self,
        company_id: str,
        limit: int = 10,
        include_recordings: bool = True,
        include_transcripts: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get recent calls for display in client portal
        
        Returns formatted call data for UI display
        """
        fields = ['duration', 'answered', 'voicemail', 'source', 'first_call', 
                  'caller_name', 'caller_number', 'tracking_phone_number']
        
        if include_recordings:
            fields.append('recording')
        if include_transcripts:
            fields.extend(['transcription', 'conversational_transcript'])
        
        result = self.get_calls(
            company_id=company_id,
            date_range='this_month',
            per_page=limit,
            fields=fields
        )
        
        calls = []
        for call in result.get('calls', [])[:limit]:
            calls.append({
                'id': call.get('id'),
                'date': call.get('start_time'),
                'caller_name': call.get('caller_name') or 'Unknown',
                'caller_number': self._format_phone(call.get('caller_number', '')),
                'tracking_number': self._format_phone(call.get('tracking_phone_number', '')),
                'duration': call.get('duration', 0),
                'duration_formatted': self._format_duration(call.get('duration', 0)),
                'answered': call.get('answered', False),
                'voicemail': call.get('voicemail', False),
                'first_call': call.get('first_call', False),
                'source': call.get('source', 'Direct'),
                'recording_url': call.get('recording'),
                'has_transcript': bool(call.get('transcription') or call.get('conversational_transcript')),
                'transcript_preview': self._get_transcript_preview(call),
                'lead_quality': self._calculate_lead_quality(call)
            })
        
        return calls
    
    def get_hot_leads(self, company_id: str, days: int = 7, min_duration: int = 120) -> List[Dict[str, Any]]:
        """
        Get hot leads (calls > 2 minutes) for follow-up
        
        Hot leads are calls where the conversation lasted long enough
        to indicate genuine interest
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        result = self.get_calls(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            answered=True,
            min_duration=min_duration,
            fields=['caller_name', 'caller_number', 'duration', 'source', 'transcription']
        )
        
        hot_leads = []
        for call in result.get('calls', []):
            hot_leads.append({
                'id': call.get('id'),
                'date': call.get('start_time'),
                'caller_name': call.get('caller_name') or 'Unknown',
                'caller_number': self._format_phone(call.get('caller_number', '')),
                'duration': self._format_duration(call.get('duration', 0)),
                'source': call.get('source', 'Direct'),
                'transcript_preview': self._get_transcript_preview(call),
                'lead_quality': 'hot'
            })
        
        return hot_leads
    
    # ==========================================
    # COMPANIES (for multi-client setup)
    # ==========================================
    
    def get_companies(self) -> List[Dict[str, Any]]:
        """Get all companies in the CallRail account"""
        result = self._request('GET', '/companies.json')
        return result.get('companies', [])
    
    def get_company_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a company by name (for matching to MCP clients)"""
        companies = self.get_companies()
        for company in companies:
            if company.get('name', '').lower() == name.lower():
                return company
        return None
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _calculate_lead_quality(self, call: dict) -> str:
        """
        Calculate lead quality based on call characteristics
        
        Returns: 'hot', 'warm', 'cold', or 'missed'
        """
        if not call.get('answered'):
            return 'missed'
        
        duration = call.get('duration', 0)
        
        if duration > 180:  # > 3 minutes
            return 'hot'
        elif duration > 60:  # > 1 minute
            return 'warm'
        else:
            return 'cold'
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to MM:SS"""
        if not seconds:
            return '0:00'
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    
    def _format_phone(self, phone: str) -> str:
        """Format phone number for display"""
        if not phone:
            return ''
        # Remove non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return phone
    
    def _get_transcript_preview(self, call: dict, max_length: int = 150) -> Optional[str]:
        """Get a preview of the call transcript"""
        transcript = call.get('conversational_transcript') or call.get('transcription')
        if not transcript:
            return None
        
        # Clean up and truncate
        preview = transcript.strip()
        if len(preview) > max_length:
            preview = preview[:max_length] + '...'
        
        return preview


# Singleton instance
_callrail_service = None

def get_callrail_service() -> CallRailService:
    """Get or create CallRail service singleton"""
    global _callrail_service
    if _callrail_service is None:
        _callrail_service = CallRailService()
    return _callrail_service
