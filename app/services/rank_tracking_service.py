"""
MCP Framework - Rank Tracking Service
Daily keyword position tracking using SEMRush API
WITH CACHING to reduce API unit consumption
"""
import os
import re
import json
import requests
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# In-memory cache for SEMrush results
# Format: {domain: {'data': result, 'timestamp': datetime, 'expires': datetime}}
_semrush_cache = {}
CACHE_DURATION_HOURS = 6  # Cache results for 6 hours to save API units


class RankTrackingService:
    """
    Tracks keyword rankings over time using SEMRush API
    Provides heatmap data and trend analysis
    WITH CACHING to minimize API unit usage
    """
    
    def __init__(self):
        self.base_url = 'https://api.semrush.com/'
        self.default_database = 'us'
    
    @property
    def api_key(self):
        """Get API key at runtime so env var changes are picked up"""
        key = os.environ.get('SEMRUSH_API_KEY', '')
        # Strip whitespace and quotes that might accidentally be included
        if key:
            key = key.strip().strip('"').strip("'").strip()
        return key
    
    def _get_cached(self, cache_key: str) -> Optional[Dict]:
        """Get cached result if not expired"""
        if cache_key in _semrush_cache:
            cached = _semrush_cache[cache_key]
            if datetime.utcnow() < cached['expires']:
                logger.info(f"SEMrush cache HIT for {cache_key} (expires in {(cached['expires'] - datetime.utcnow()).seconds // 60} min)")
                return cached['data']
            else:
                logger.info(f"SEMrush cache EXPIRED for {cache_key}")
                del _semrush_cache[cache_key]
        return None
    
    def _set_cached(self, cache_key: str, data: Dict):
        """Cache result with expiration"""
        _semrush_cache[cache_key] = {
            'data': data,
            'timestamp': datetime.utcnow(),
            'expires': datetime.utcnow() + timedelta(hours=CACHE_DURATION_HOURS)
        }
        logger.info(f"SEMrush cache SET for {cache_key} (expires in {CACHE_DURATION_HOURS} hours)")
    
    def clear_cache(self, domain: str = None):
        """Clear cache for a domain or all domains"""
        global _semrush_cache
        if domain:
            keys_to_delete = [k for k in _semrush_cache if domain in k]
            for k in keys_to_delete:
                del _semrush_cache[k]
            logger.info(f"Cleared SEMrush cache for {domain}")
        else:
            _semrush_cache = {}
            logger.info("Cleared all SEMrush cache")
    
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
                # Return empty result if API fails - don't break the flow
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
        database: str = None,
        force_refresh: bool = False
    ) -> Dict:
        """
        Check positions for multiple keywords
        More efficient - uses single API call
        WITH CACHING - results cached for 6 hours to save API units
        
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
                },
                'cached': bool  # True if from cache
            }
        """
        domain = self._clean_domain(domain)
        database = database or self.default_database
        
        # Check cache first (unless force refresh)
        cache_key = f"{domain}:{database}"
        if not force_refresh:
            cached = self._get_cached(cache_key)
            if cached:
                cached['cached'] = True
                return cached
        
        # Debug logging
        api_key = self.api_key
        logger.info(f"SEMrush check_all_keywords: api_key length={len(api_key) if api_key else 0}, domain={domain}")
        
        # If no API key, return simulated data so dashboard still works
        if not api_key:
            logger.warning("SEMrush API key not found, returning demo data")
            return self._generate_demo_rankings(domain, keywords)
        
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
                'key': api_key,
                'display_limit': 500,
                'export_columns': 'Ph,Po,Pp,Ur,Nq,Cp,Co,Fk,Kd',  # Added Fk (SERP Features) and Kd (Keyword Difficulty)
                'domain': domain,
                'database': database
            }
            
            logger.info(f"SEMrush API request: domain={domain}, database={database}")
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code != 200:
                # Log the error for debugging
                logger.error(f"SEMrush API error: status={response.status_code}, response={response.text[:500]}")
                
                # Check for common errors
                error_text = response.text.lower()
                if 'error' in error_text:
                    # Return error info instead of silently falling back to demo
                    return {
                        'domain': domain,
                        'checked_at': datetime.utcnow().isoformat(),
                        'keywords': [],
                        'summary': {'total': len(keywords), 'in_top_3': 0, 'in_top_10': 0, 'in_top_20': 0, 'not_ranking': len(keywords)},
                        'demo_mode': True,
                        'error': f'SEMrush API error: {response.text[:200]}',
                        'message': 'SEMrush API returned an error. Check your API key and account status.'
                    }
                
                # Fall back to demo mode if API fails
                result = self._generate_demo_rankings(domain, keywords)
                result['api_status'] = response.status_code
                return result
            
            # Check if response is an error message (SEMrush returns 200 even for errors sometimes)
            if response.text.startswith('ERROR'):
                logger.error(f"SEMrush returned error: {response.text[:200]}")
                return {
                    'domain': domain,
                    'checked_at': datetime.utcnow().isoformat(),
                    'keywords': [],
                    'summary': {'total': len(keywords), 'in_top_3': 0, 'in_top_10': 0, 'in_top_20': 0, 'not_ranking': len(keywords)},
                    'demo_mode': True,
                    'error': response.text[:200],
                    'message': 'SEMrush API error. Common causes: invalid API key, expired subscription, rate limit exceeded.'
                }
            
            logger.info(f"SEMrush API success: got {len(response.text)} bytes")
            
            # Log a sample of the raw response to debug SERP features
            sample_lines = response.text.strip().split('\n')[:3]
            logger.info(f"SEMrush response header: {sample_lines[0] if sample_lines else 'empty'}")
            if len(sample_lines) > 1:
                logger.info(f"SEMrush first data row (sample): {sample_lines[1][:200]}")
            
            # Parse response into lookup dict
            domain_keywords = {}
            lines = response.text.strip().split('\n')
            
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.split(';')
                    if len(parts) >= 7:
                        kw = parts[0].strip('"').lower()
                        
                        # Parse SERP features (column 7 if present)
                        serp_features = []
                        if len(parts) > 7 and parts[7]:
                            serp_features = self._parse_serp_features(parts[7].strip('"'))
                            if serp_features:
                                logger.debug(f"SERP features for '{kw}': {[f['name'] for f in serp_features]}")
                        
                        # Parse keyword difficulty (column 8 if present)
                        kd = 0
                        if len(parts) > 8 and parts[8]:
                            try:
                                kd = float(parts[8])
                            except:
                                kd = 0
                        
                        domain_keywords[kw] = {
                            'position': int(parts[1]) if parts[1] else None,
                            'previous_position': int(parts[2]) if parts[2] else None,
                            'url': parts[3].strip('"') if parts[3] else None,
                            'search_volume': int(parts[4]) if parts[4] else 0,
                            'cpc': float(parts[5]) if parts[5] else 0.0,
                            'competition': float(parts[6]) if parts[6] else 0.0,
                            'serp_features': serp_features,
                            'keyword_difficulty': kd
                        }
            
            # Log stats about parsed keywords
            kws_with_features = sum(1 for kw in domain_keywords.values() if kw.get('serp_features'))
            logger.info(f"SEMrush parsed {len(domain_keywords)} keywords, {kws_with_features} have SERP features")
            
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
                    'competition': 0.0,
                    'serp_features': [],
                    'keyword_difficulty': 0
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
            
            # Cache successful result
            result['cached'] = False
            self._set_cached(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"SEMrush check_all_keywords exception: {e}")
            result['error'] = str(e)
            return result
    
    def _parse_serp_features(self, features_str: str) -> List[Dict]:
        """
        Parse SEMrush SERP features string into structured list
        
        SEMrush returns features as comma-separated codes like:
        "0,1,3,7,8,14" where each number represents a feature type
        """
        if not features_str:
            return []
        
        # SEMrush SERP feature codes mapping
        SERP_FEATURE_MAP = {
            '0': {'code': 'featured_snippet', 'name': 'Featured Snippet', 'icon': '📄'},
            '1': {'code': 'local_pack', 'name': 'Local Pack', 'icon': '📍'},
            '2': {'code': 'reviews', 'name': 'Reviews', 'icon': '⭐'},
            '3': {'code': 'sitelinks', 'name': 'Sitelinks', 'icon': '🔗'},
            '4': {'code': 'image_pack', 'name': 'Image Pack', 'icon': '🖼️'},
            '5': {'code': 'video', 'name': 'Video', 'icon': '🎬'},
            '6': {'code': 'knowledge_panel', 'name': 'Knowledge Panel', 'icon': '📚'},
            '7': {'code': 'top_stories', 'name': 'Top Stories', 'icon': '📰'},
            '8': {'code': 'people_also_ask', 'name': 'People Also Ask', 'icon': '❓'},
            '9': {'code': 'shopping', 'name': 'Shopping Results', 'icon': '🛒'},
            '10': {'code': 'twitter', 'name': 'Twitter/X Results', 'icon': '🐦'},
            '11': {'code': 'thumbnail', 'name': 'Thumbnail', 'icon': '🖼️'},
            '12': {'code': 'instant_answer', 'name': 'Instant Answer', 'icon': '⚡'},
            '13': {'code': 'jobs', 'name': 'Jobs', 'icon': '💼'},
            '14': {'code': 'ads', 'name': 'Ads (Top)', 'icon': '💰'},
            '15': {'code': 'ads_bottom', 'name': 'Ads (Bottom)', 'icon': '💰'},
            '16': {'code': 'carousel', 'name': 'Carousel', 'icon': '🎠'},
            '17': {'code': 'faq', 'name': 'FAQ Rich Result', 'icon': '📋'},
        }
        
        features = []
        try:
            codes = features_str.replace('"', '').split(',')
            for code in codes:
                code = code.strip()
                if code in SERP_FEATURE_MAP:
                    features.append(SERP_FEATURE_MAP[code])
                elif code:
                    # Unknown feature code
                    features.append({
                        'code': f'unknown_{code}',
                        'name': f'Feature {code}',
                        'icon': '🔹'
                    })
        except Exception as e:
            logger.debug(f"Error parsing SERP features '{features_str}': {e}")
        
        return features
    
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
    
    def _generate_demo_rankings(self, domain: str, keywords: List[str]) -> Dict:
        """
        Generate simulated ranking data when SEMRush API is not configured.
        Shows realistic demo data so the dashboard is still usable.
        """
        import random
        import hashlib
        
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
            },
            'demo_mode': True,
            'message': 'Demo data - Add SEMRUSH_API_KEY for real rankings'
        }
        
        for keyword in keywords:
            # Use hash for consistent "random" positions per keyword
            seed = int(hashlib.md5(keyword.encode()).hexdigest()[:8], 16)
            random.seed(seed)
            
            # 70% chance to be ranking
            if random.random() < 0.7:
                position = random.choice([
                    random.randint(1, 3),   # 20% top 3
                    random.randint(4, 10),  # 30% top 10
                    random.randint(11, 20), # 25% top 20
                    random.randint(21, 50)  # 25% 21-50
                ])
                change = random.choice([-3, -2, -1, 0, 0, 0, 1, 1, 2, 3, 5])
                prev_pos = position - change if position - change > 0 else None
            else:
                position = None
                prev_pos = None
                change = 0
            
            # Estimate search volume (higher for shorter keywords)
            base_volume = max(100, 2000 - len(keyword) * 50)
            volume = base_volume + random.randint(-200, 500)
            
            kw_data = {
                'keyword': keyword,
                'position': position,
                'previous_position': prev_pos,
                'change': change,
                'url': f'https://{domain}/{"".join(keyword.split()[:2]).lower()}' if position else None,
                'search_volume': max(10, volume),
                'cpc': round(random.uniform(0.5, 8.0), 2),
                'competition': round(random.uniform(0.3, 0.9), 2)
            }
            
            result['keywords'].append(kw_data)
            
            # Update summary
            if position:
                if position <= 3:
                    result['summary']['in_top_3'] += 1
                if position <= 10:
                    result['summary']['in_top_10'] += 1
                if position <= 20:
                    result['summary']['in_top_20'] += 1
                
                if change > 0:
                    result['summary']['improved'] += 1
                elif change < 0:
                    result['summary']['declined'] += 1
                else:
                    result['summary']['unchanged'] += 1
            else:
                result['summary']['not_ranking'] += 1
        
        return result
    
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
