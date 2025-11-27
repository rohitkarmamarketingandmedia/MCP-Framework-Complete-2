"""
MCP Framework - Rank Tracking Service
Daily keyword position tracking using SEMRush API
"""
import os
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class RankTrackingService:
    """
    Tracks keyword rankings over time using SEMRush API
    Provides heatmap data and trend analysis
    """
    
    def __init__(self):
        self.api_key = os.environ.get('SEMRUSH_API_KEY', '')
        self.base_url = 'https://api.semrush.com/'
        self.default_database = 'us'
    
    def check_keyword_position(
        self,
        domain: str,
        keyword: str,
        database: str = None
    ) -> Dict:
        """
        Check position for a single keyword using SEMRush
        
        Returns:
            {
                'keyword': str,
                'position': int or None,
                'url': str (ranking URL),
                'previous_position': int or None,
                'change': int,
                'search_volume': int,
                'cpc': float,
                'competition': float,
                'checked_at': str
            }
        """
        if not self.api_key:
            return {'error': 'SEMRush API key not configured', 'keyword': keyword}
        
        domain = self._clean_domain(domain)
        database = database or self.default_database
        
        result = {
            'keyword': keyword,
            'position': None,
            'url': None,
            'previous_position': None,
            'change': 0,
            'search_volume': 0,
            'cpc': 0.0,
            'competition': 0.0,
            'checked_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Use domain_organic endpoint to find keyword positions
            params = {
                'type': 'domain_organic',
                'key': self.api_key,
                'display_limit': 100,
                'export_columns': 'Ph,Po,Pp,Ur,Nq,Cp,Co',
                'domain': domain,
                'phrase': keyword,
                'database': database
            }
            
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code != 200:
                result['error'] = f'API error: {response.status_code}'
                return result
            
            # Parse CSV response
            lines = response.text.strip().split('\n')
            
            if len(lines) > 1:
                # Skip header, find matching keyword
                for line in lines[1:]:
                    parts = line.split(';')
                    if len(parts) >= 7:
                        kw = parts[0].strip('"')
                        if kw.lower() == keyword.lower():
                            result['position'] = int(parts[1]) if parts[1] else None
                            result['previous_position'] = int(parts[2]) if parts[2] else None
                            result['url'] = parts[3].strip('"') if parts[3] else None
                            result['search_volume'] = int(parts[4]) if parts[4] else 0
                            result['cpc'] = float(parts[5]) if parts[5] else 0.0
                            result['competition'] = float(parts[6]) if parts[6] else 0.0
                            
                            if result['position'] and result['previous_position']:
                                result['change'] = result['previous_position'] - result['position']
                            break
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            return result
    
    def check_all_keywords(
        self,
        domain: str,
        keywords: List[str],
        database: str = None
    ) -> Dict:
        """
        Check positions for multiple keywords
        More efficient - uses single API call
        
        Returns:
            {
                'domain': str,
                'checked_at': str,
                'keywords': [
                    {keyword, position, change, volume, ...}
                ],
                'summary': {
                    'total': int,
                    'in_top_3': int,
                    'in_top_10': int,
                    'in_top_20': int,
                    'not_ranking': int,
                    'improved': int,
                    'declined': int,
                    'unchanged': int
                }
            }
        """
        if not self.api_key:
            return {'error': 'SEMRush API key not configured'}
        
        domain = self._clean_domain(domain)
        database = database or self.default_database
        
        result = {
            'domain': domain,
            'checked_at': datetime.utcnow().isoformat(),
            'keywords': [],
            'summary': {
                'total': len(keywords),
                'in_top_3': 0,
                'in_top_10': 0,
                'in_top_20': 0,
                'not_ranking': 0,
                'improved': 0,
                'declined': 0,
                'unchanged': 0
            }
        }
        
        try:
            # Get all organic keywords for domain
            params = {
                'type': 'domain_organic',
                'key': self.api_key,
                'display_limit': 500,
                'export_columns': 'Ph,Po,Pp,Ur,Nq,Cp,Co',
                'domain': domain,
                'database': database
            }
            
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code != 200:
                result['error'] = f'API error: {response.status_code}'
                return result
            
            # Parse response into lookup dict
            domain_keywords = {}
            lines = response.text.strip().split('\n')
            
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.split(';')
                    if len(parts) >= 7:
                        kw = parts[0].strip('"').lower()
                        domain_keywords[kw] = {
                            'position': int(parts[1]) if parts[1] else None,
                            'previous_position': int(parts[2]) if parts[2] else None,
                            'url': parts[3].strip('"') if parts[3] else None,
                            'search_volume': int(parts[4]) if parts[4] else 0,
                            'cpc': float(parts[5]) if parts[5] else 0.0,
                            'competition': float(parts[6]) if parts[6] else 0.0
                        }
            
            # Match requested keywords
            for keyword in keywords:
                kw_lower = keyword.lower()
                kw_result = {
                    'keyword': keyword,
                    'position': None,
                    'previous_position': None,
                    'change': 0,
                    'url': None,
                    'search_volume': 0,
                    'cpc': 0.0,
                    'competition': 0.0
                }
                
                if kw_lower in domain_keywords:
                    data = domain_keywords[kw_lower]
                    kw_result.update(data)
                    
                    if data['position'] and data['previous_position']:
                        kw_result['change'] = data['previous_position'] - data['position']
                
                result['keywords'].append(kw_result)
                
                # Update summary
                pos = kw_result['position']
                change = kw_result['change']
                
                if pos is None:
                    result['summary']['not_ranking'] += 1
                else:
                    if pos <= 3:
                        result['summary']['in_top_3'] += 1
                    if pos <= 10:
                        result['summary']['in_top_10'] += 1
                    if pos <= 20:
                        result['summary']['in_top_20'] += 1
                    
                    if change > 0:
                        result['summary']['improved'] += 1
                    elif change < 0:
                        result['summary']['declined'] += 1
                    else:
                        result['summary']['unchanged'] += 1
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            return result
    
    def get_ranking_history(
        self,
        history_data: List[Dict],
        keyword: str
    ) -> Dict:
        """
        Analyze ranking history for a keyword
        
        Args:
            history_data: List of past rank checks from database
            keyword: Keyword to analyze
            
        Returns:
            {
                'keyword': str,
                'current_position': int,
                'best_position': int,
                'worst_position': int,
                'average_position': float,
                'trend': 'improving' | 'declining' | 'stable',
                'days_to_top_3': int (estimated),
                'history': [{date, position}]
            }
        """
        keyword_history = [
            h for h in history_data 
            if h.get('keyword', '').lower() == keyword.lower()
        ]
        
        if not keyword_history:
            return {'keyword': keyword, 'error': 'No history found'}
        
        # Sort by date
        keyword_history.sort(key=lambda x: x.get('checked_at', ''))
        
        positions = [h['position'] for h in keyword_history if h.get('position')]
        
        if not positions:
            return {'keyword': keyword, 'error': 'No position data'}
        
        result = {
            'keyword': keyword,
            'current_position': positions[-1] if positions else None,
            'best_position': min(positions),
            'worst_position': max(positions),
            'average_position': sum(positions) / len(positions),
            'history': [
                {'date': h.get('checked_at'), 'position': h.get('position')}
                for h in keyword_history
            ]
        }
        
        # Calculate trend (last 7 data points)
        recent = positions[-7:] if len(positions) >= 7 else positions
        if len(recent) >= 2:
            first_half_avg = sum(recent[:len(recent)//2]) / (len(recent)//2)
            second_half_avg = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
            
            if second_half_avg < first_half_avg - 2:
                result['trend'] = 'improving'
            elif second_half_avg > first_half_avg + 2:
                result['trend'] = 'declining'
            else:
                result['trend'] = 'stable'
        else:
            result['trend'] = 'insufficient_data'
        
        # Estimate days to top 3
        if result['trend'] == 'improving' and result['current_position']:
            current = result['current_position']
            if current <= 3:
                result['days_to_top_3'] = 0
            elif len(recent) >= 2:
                # Calculate average daily improvement
                improvement_per_day = (recent[0] - recent[-1]) / max(len(recent) - 1, 1)
                if improvement_per_day > 0:
                    positions_to_go = current - 3
                    result['days_to_top_3'] = int(positions_to_go / improvement_per_day)
                else:
                    result['days_to_top_3'] = None
            else:
                result['days_to_top_3'] = None
        else:
            result['days_to_top_3'] = None
        
        return result
    
    def generate_heatmap_data(
        self,
        current_rankings: List[Dict],
        history_7d: List[Dict] = None,
        history_30d: List[Dict] = None
    ) -> List[Dict]:
        """
        Generate heatmap-ready data for dashboard
        
        Returns list of:
            {
                'keyword': str,
                'current': int,
                'change_24h': int,
                'change_7d': int,
                'change_30d': int,
                'volume': int,
                'status': 'rising' | 'falling' | 'stable' | 'new' | 'lost'
            }
        """
        history_7d = history_7d or []
        history_30d = history_30d or []
        
        # Build lookup dicts
        history_7d_map = {h['keyword'].lower(): h.get('position') for h in history_7d}
        history_30d_map = {h['keyword'].lower(): h.get('position') for h in history_30d}
        
        heatmap = []
        
        for ranking in current_rankings:
            kw_lower = ranking['keyword'].lower()
            current = ranking.get('position')
            previous = ranking.get('previous_position')
            
            pos_7d = history_7d_map.get(kw_lower)
            pos_30d = history_30d_map.get(kw_lower)
            
            row = {
                'keyword': ranking['keyword'],
                'current': current,
                'volume': ranking.get('search_volume', 0),
                'change_24h': (previous - current) if current and previous else 0,
                'change_7d': (pos_7d - current) if current and pos_7d else 0,
                'change_30d': (pos_30d - current) if current and pos_30d else 0
            }
            
            # Determine status
            if current is None and previous:
                row['status'] = 'lost'
            elif current and previous is None:
                row['status'] = 'new'
            elif row['change_7d'] > 5:
                row['status'] = 'rising'
            elif row['change_7d'] < -5:
                row['status'] = 'falling'
            else:
                row['status'] = 'stable'
            
            heatmap.append(row)
        
        # Sort by volume (highest first)
        heatmap.sort(key=lambda x: x['volume'], reverse=True)
        
        return heatmap
    
    def calculate_traffic_value(
        self,
        rankings: List[Dict]
    ) -> Dict:
        """
        Estimate monthly traffic value based on rankings
        Uses click-through rate estimates
        """
        # CTR by position (approximate)
        ctr_by_position = {
            1: 0.28, 2: 0.15, 3: 0.11,
            4: 0.08, 5: 0.07, 6: 0.05,
            7: 0.04, 8: 0.03, 9: 0.03, 10: 0.02
        }
        
        total_clicks = 0
        total_value = 0
        
        for ranking in rankings:
            pos = ranking.get('position')
            volume = ranking.get('search_volume', 0)
            cpc = ranking.get('cpc', 0)
            
            if pos and pos <= 10 and volume > 0:
                ctr = ctr_by_position.get(pos, 0.01)
                clicks = volume * ctr
                value = clicks * cpc
                
                total_clicks += clicks
                total_value += value
        
        return {
            'estimated_monthly_clicks': int(total_clicks),
            'estimated_monthly_value': round(total_value, 2),
            'estimated_annual_value': round(total_value * 12, 2)
        }
    
    def _clean_domain(self, domain: str) -> str:
        """Clean domain string"""
        domain = domain.lower().strip()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        return domain.rstrip('/').split('/')[0]


# Singleton
rank_tracking_service = RankTrackingService()
