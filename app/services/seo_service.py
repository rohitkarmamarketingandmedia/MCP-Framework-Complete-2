"""
MCP Framework - SEO Service
SEMrush, Ahrefs, and keyword research integration
"""
import os
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime


class SEOService:
    """SEO tools and keyword research service"""
    
    def __init__(self):
        pass  # API keys read at runtime via properties
    
    @property
    def semrush_key(self):
        """Get SEMrush API key at runtime"""
        return os.environ.get('SEMRUSH_API_KEY', '')
    
    @property
    def ahrefs_key(self):
        """Get Ahrefs API key at runtime"""
        return os.environ.get('AHREFS_API_KEY', '')
    
    def get_keyword_rankings(
        self,
        domain: str,
        keywords: List[str] = None
    ) -> Dict[str, Any]:
        """
        Get keyword rankings for a domain
        
        Returns:
            {
                'domain': str,
                'keywords': [
                    {
                        'keyword': str,
                        'position': int,
                        'url': str,
                        'volume': int,
                        'difficulty': int
                    }
                ],
                'timestamp': str
            }
        """
        if not self.semrush_key:
            # Return mock data for development
            return self._mock_rankings(domain, keywords)
        
        try:
            # SEMrush Domain Organic Keywords
            response = requests.get(
                'https://api.semrush.com/',
                params={
                    'type': 'domain_organic',
                    'key': self.semrush_key,
                    'domain': domain.replace('https://', '').replace('http://', '').split('/')[0],
                    'database': 'us',
                    'export_columns': 'Ph,Po,Ur,Nq,Kd',
                    'display_limit': 100
                },
                timeout=30
            )
            
            response.raise_for_status()
            
            # Parse CSV response
            rankings = []
            lines = response.text.strip().split('\n')
            
            for line in lines[1:]:  # Skip header
                parts = line.split(';')
                if len(parts) >= 5:
                    rankings.append({
                        'keyword': parts[0],
                        'position': int(parts[1]) if parts[1].isdigit() else 0,
                        'url': parts[2],
                        'volume': int(parts[3]) if parts[3].isdigit() else 0,
                        'difficulty': int(parts[4]) if parts[4].isdigit() else 0
                    })
            
            # Filter by requested keywords if provided
            if keywords:
                keywords_lower = [k.lower() for k in keywords]
                rankings = [
                    r for r in rankings 
                    if any(kw in r['keyword'].lower() for kw in keywords_lower)
                ]
            
            return {
                'domain': domain,
                'keywords': rankings[:50],  # Limit results
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except requests.RequestException as e:
            return {
                'error': f'SEMrush API error: {str(e)}',
                'domain': domain,
                'keywords': [],
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def get_keyword_ideas(
        self,
        seed_keyword: str,
        geo: str = 'us',
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get keyword ideas based on seed keyword"""
        if not self.semrush_key:
            return self._mock_keyword_ideas(seed_keyword)
        
        try:
            response = requests.get(
                'https://api.semrush.com/',
                params={
                    'type': 'phrase_related',
                    'key': self.semrush_key,
                    'phrase': seed_keyword,
                    'database': geo,
                    'export_columns': 'Ph,Nq,Kd,Co',
                    'display_limit': limit
                },
                timeout=30
            )
            
            response.raise_for_status()
            
            ideas = []
            lines = response.text.strip().split('\n')
            
            for line in lines[1:]:
                parts = line.split(';')
                if len(parts) >= 4:
                    ideas.append({
                        'keyword': parts[0],
                        'volume': int(parts[1]) if parts[1].isdigit() else 0,
                        'difficulty': int(parts[2]) if parts[2].isdigit() else 0,
                        'competition': float(parts[3]) if parts[3] else 0
                    })
            
            return {
                'seed_keyword': seed_keyword,
                'ideas': ideas,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except requests.RequestException as e:
            return {'error': f'SEMrush API error: {str(e)}'}
    
    def analyze_competitors(
        self,
        domain: str,
        competitors: List[str],
        keywords: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze competitor rankings and content"""
        analysis = {
            'domain': domain,
            'competitors': {},
            'keyword_gaps': [],
            'content_gaps': [],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get rankings for main domain
        main_rankings = self.get_keyword_rankings(domain, keywords)
        main_keywords = {r['keyword']: r for r in main_rankings.get('keywords', [])}
        
        # Analyze each competitor
        for comp in competitors:
            comp_rankings = self.get_keyword_rankings(comp, keywords)
            comp_keywords = {r['keyword']: r for r in comp_rankings.get('keywords', [])}
            
            # Find keyword gaps
            gaps = []
            for kw, data in comp_keywords.items():
                if kw not in main_keywords:
                    gaps.append({
                        'keyword': kw,
                        'competitor_position': data['position'],
                        'volume': data['volume']
                    })
                elif main_keywords[kw]['position'] > data['position']:
                    gaps.append({
                        'keyword': kw,
                        'competitor_position': data['position'],
                        'our_position': main_keywords[kw]['position'],
                        'volume': data['volume']
                    })
            
            analysis['competitors'][comp] = {
                'total_keywords': len(comp_keywords),
                'top_10_keywords': sum(1 for r in comp_keywords.values() if r['position'] <= 10),
                'keyword_gaps': gaps[:20]  # Top 20 gaps
            }
            
            analysis['keyword_gaps'].extend(gaps)
        
        # Sort gaps by volume
        analysis['keyword_gaps'] = sorted(
            analysis['keyword_gaps'],
            key=lambda x: x.get('volume', 0),
            reverse=True
        )[:50]
        
        return analysis
    
    def get_backlink_profile(self, domain: str) -> Dict[str, Any]:
        """Get backlink profile for domain"""
        if not self.semrush_key:
            return self._mock_backlinks(domain)
        
        try:
            response = requests.get(
                'https://api.semrush.com/analytics/v1/',
                params={
                    'key': self.semrush_key,
                    'type': 'backlinks_overview',
                    'target': domain,
                    'target_type': 'root_domain'
                },
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            
            return {
                'domain': domain,
                'total_backlinks': data.get('total', 0),
                'referring_domains': data.get('domains_num', 0),
                'authority_score': data.get('ascore', 0),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except requests.RequestException as e:
            return {'error': f'API error: {str(e)}'}
    
    # Mock data methods for development without API keys
    def _mock_rankings(self, domain: str, keywords: List[str] = None) -> Dict:
        """Return mock ranking data for development"""
        mock_keywords = keywords or ['roof repair', 'roofing company', 'roof replacement']
        
        return {
            'domain': domain,
            'keywords': [
                {
                    'keyword': f'{kw} sarasota',
                    'position': i + 3,
                    'url': f'{domain}/services/{kw.replace(" ", "-")}',
                    'volume': 500 - (i * 50),
                    'difficulty': 35 + (i * 5)
                }
                for i, kw in enumerate(mock_keywords)
            ],
            'timestamp': datetime.utcnow().isoformat(),
            'note': 'Mock data - configure SEMRUSH_API_KEY for real data'
        }
    
    def _mock_keyword_ideas(self, seed: str) -> Dict:
        """Return mock keyword ideas"""
        return {
            'seed_keyword': seed,
            'ideas': [
                {'keyword': f'{seed} near me', 'volume': 800, 'difficulty': 30, 'competition': 0.5},
                {'keyword': f'{seed} cost', 'volume': 600, 'difficulty': 25, 'competition': 0.4},
                {'keyword': f'best {seed}', 'volume': 500, 'difficulty': 40, 'competition': 0.6},
                {'keyword': f'{seed} services', 'volume': 400, 'difficulty': 35, 'competition': 0.5},
                {'keyword': f'affordable {seed}', 'volume': 300, 'difficulty': 20, 'competition': 0.3}
            ],
            'timestamp': datetime.utcnow().isoformat(),
            'note': 'Mock data - configure SEMRUSH_API_KEY for real data'
        }
    
    def _mock_backlinks(self, domain: str) -> Dict:
        """Return mock backlink data"""
        return {
            'domain': domain,
            'total_backlinks': 1250,
            'referring_domains': 85,
            'authority_score': 42,
            'timestamp': datetime.utcnow().isoformat(),
            'note': 'Mock data - configure SEMRUSH_API_KEY for real data'
        }
