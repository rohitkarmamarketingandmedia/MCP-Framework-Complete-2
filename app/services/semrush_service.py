"""
MCP Framework - SEMRush Service
Competitor research, keyword data, and domain analytics
"""
import os
import requests
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class SEMRushService:
    """SEMRush API integration for competitor and keyword research"""
    
    BASE_URL = "https://api.semrush.com/"
    
    def __init__(self):
        self.default_database = 'us'  # US database by default
    
    @property
    def api_key(self):
        """Get API key at runtime so env var changes are picked up"""
        return os.environ.get('SEMRUSH_API_KEY', '')
    
    def is_configured(self) -> bool:
        """Check if SEMRush API key is configured"""
        return bool(self.api_key)
    
    # ==========================================
    # KEYWORD RESEARCH
    # ==========================================
    
    def get_keyword_overview(self, keyword: str, database: str = None) -> Dict[str, Any]:
        """
        Get keyword metrics: volume, CPC, competition, difficulty
        
        Returns:
            {
                'keyword': str,
                'volume': int,
                'cpc': float,
                'competition': float,
                'difficulty': int,
                'results': int
            }
        """
        database = database or self.default_database
        
        params = {
            'type': 'phrase_this',
            'key': self.api_key,
            'phrase': keyword,
            'database': database,
            'export_columns': 'Ph,Nq,Cp,Co,Kd,Nr'
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        # Parse CSV response
        lines = result.get('data', '').strip().split('\n')
        if len(lines) < 2:
            return {'error': 'No data returned', 'keyword': keyword}
        
        # Skip header, parse data
        values = lines[1].split(';')
        
        return {
            'keyword': values[0] if len(values) > 0 else keyword,
            'volume': int(values[1]) if len(values) > 1 and values[1].isdigit() else 0,
            'cpc': float(values[2]) if len(values) > 2 and values[2] else 0.0,
            'competition': float(values[3]) if len(values) > 3 and values[3] else 0.0,
            'difficulty': int(values[4]) if len(values) > 4 and values[4].isdigit() else 0,
            'results': int(values[5]) if len(values) > 5 and values[5].isdigit() else 0
        }
    
    def get_keyword_variations(self, keyword: str, limit: int = 20, database: str = None) -> Dict[str, Any]:
        """
        Get related keyword variations with metrics
        
        Returns:
            {
                'seed_keyword': str,
                'variations': [
                    {'keyword': str, 'volume': int, 'cpc': float, 'competition': float, 'difficulty': int}
                ]
            }
        """
        database = database or self.default_database
        
        params = {
            'type': 'phrase_related',
            'key': self.api_key,
            'phrase': keyword,
            'database': database,
            'export_columns': 'Ph,Nq,Cp,Co,Kd',
            'display_limit': limit
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        variations = self._parse_keyword_results(result.get('data', ''))
        
        return {
            'seed_keyword': keyword,
            'count': len(variations),
            'variations': variations
        }
    
    def get_keyword_questions(self, keyword: str, limit: int = 10, database: str = None) -> Dict[str, Any]:
        """
        Get question-based keywords (great for FAQ content)
        
        Returns:
            {
                'seed_keyword': str,
                'questions': [
                    {'keyword': str, 'volume': int, ...}
                ]
            }
        """
        database = database or self.default_database
        
        params = {
            'type': 'phrase_questions',
            'key': self.api_key,
            'phrase': keyword,
            'database': database,
            'export_columns': 'Ph,Nq,Cp,Co,Kd',
            'display_limit': limit
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        questions = self._parse_keyword_results(result.get('data', ''))
        
        return {
            'seed_keyword': keyword,
            'count': len(questions),
            'questions': questions
        }
    
    def bulk_keyword_overview(self, keywords: List[str], database: str = None) -> Dict[str, Any]:
        """
        Get metrics for multiple keywords at once (more efficient)
        
        Returns:
            {
                'keywords': [
                    {'keyword': str, 'volume': int, 'cpc': float, ...}
                ]
            }
        """
        database = database or self.default_database
        
        # SEMRush accepts semicolon-separated keywords
        keywords_str = ';'.join(keywords[:100])  # Limit to 100
        
        params = {
            'type': 'phrase_these',
            'key': self.api_key,
            'phrase': keywords_str,
            'database': database,
            'export_columns': 'Ph,Nq,Cp,Co,Kd,Nr'
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        keyword_data = self._parse_keyword_results(result.get('data', ''))
        
        return {
            'count': len(keyword_data),
            'keywords': keyword_data
        }
    
    # ==========================================
    # DOMAIN / COMPETITOR ANALYSIS
    # ==========================================
    
    def get_domain_overview(self, domain: str, database: str = None) -> Dict[str, Any]:
        """
        Get domain organic traffic overview
        
        Returns:
            {
                'domain': str,
                'organic_keywords': int,
                'organic_traffic': int,
                'organic_cost': float,
                'adwords_keywords': int,
                'adwords_traffic': int,
                'adwords_cost': float
            }
        """
        database = database or self.default_database
        
        # Clean domain
        domain = self._clean_domain(domain)
        
        params = {
            'type': 'domain_ranks',
            'key': self.api_key,
            'domain': domain,
            'database': database,
            'export_columns': 'Db,Dn,Rk,Or,Ot,Oc,Ad,At,Ac'
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        lines = result.get('data', '').strip().split('\n')
        if len(lines) < 2:
            return {'error': 'No data for domain', 'domain': domain}
        
        values = lines[1].split(';')
        
        return {
            'domain': domain,
            'database': values[0] if len(values) > 0 else database,
            'rank': int(values[2]) if len(values) > 2 and values[2].isdigit() else 0,
            'organic_keywords': int(values[3]) if len(values) > 3 and values[3].isdigit() else 0,
            'organic_traffic': int(values[4]) if len(values) > 4 and values[4].isdigit() else 0,
            'organic_cost': float(values[5]) if len(values) > 5 and values[5] else 0.0,
            'adwords_keywords': int(values[6]) if len(values) > 6 and values[6].isdigit() else 0,
            'adwords_traffic': int(values[7]) if len(values) > 7 and values[7].isdigit() else 0,
            'adwords_cost': float(values[8]) if len(values) > 8 and values[8] else 0.0
        }
    
    def get_domain_organic_keywords(self, domain: str, limit: int = 50, database: str = None) -> Dict[str, Any]:
        """
        Get keywords a domain ranks for organically
        """
        database = database or self.default_database
        domain = self._clean_domain(domain)
        
        params = {
            'type': 'domain_organic',
            'key': self.api_key,
            'domain': domain,
            'database': database,
            'export_columns': 'Ph,Po,Nq,Cp,Co,Kd,Ur',
            'display_limit': limit,
            'display_sort': 'nq_desc'  # Sort by volume
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        # Debug log raw data
        raw = result.get('data', '')
        lines = raw.strip().split('\n')
        logger.info(f"domain_organic for {domain}: {len(lines)} lines")
        if len(lines) >= 2:
            logger.info(f"  Header: {lines[0]}")
            logger.info(f"  First row: {lines[1]}")
        
        keywords = self._parse_domain_keywords(raw)
        
        logger.info(f"  Parsed {len(keywords)} keywords")
        if keywords:
            logger.info(f"  First parsed: {keywords[0]}")
        
        return {
            'domain': domain,
            'count': len(keywords),
            'keywords': keywords
        }
    
    def get_competitors(self, domain: str, limit: int = 10, database: str = None) -> Dict[str, Any]:
        """
        Find organic competitors for a domain
        
        Returns:
            {
                'domain': str,
                'competitors': [
                    {'domain': str, 'common_keywords': int, 'organic_keywords': int, 'organic_traffic': int}
                ]
            }
        """
        database = database or self.default_database
        domain = self._clean_domain(domain)
        
        params = {
            'type': 'domain_organic_organic',
            'key': self.api_key,
            'domain': domain,
            'database': database,
            'export_columns': 'Dn,Cr,Np,Or,Ot,Oc,Ad',
            'display_limit': limit
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        competitors = self._parse_competitors(result.get('data', ''))
        
        return {
            'domain': domain,
            'count': len(competitors),
            'competitors': competitors
        }
    
    def get_keyword_gap(self, domain: str, competitors: List[str], limit: int = 50, database: str = None) -> Dict[str, Any]:
        """
        Find keywords competitors rank for that the target domain doesn't
        
        Returns:
            {
                'domain': str,
                'competitors': [...],
                'gaps': [
                    {'keyword': str, 'volume': int, 'competitor_positions': {...}}
                ]
            }
        """
        database = database or self.default_database
        domain = self._clean_domain(domain)
        competitors = [self._clean_domain(c) for c in competitors[:4]]  # Max 4 competitors
        
        # Build domains string with SEMrush format
        # For gap analysis: keywords where competitors rank but you don't rank well
        # +|or|competitor1.com|+|or|competitor2.com|-|or|yourdomain.com
        all_domains = [domain] + competitors
        domains_str = '*|or|' + '|+|or|'.join(all_domains)
        
        params = {
            'type': 'domain_domains',
            'key': self.api_key,
            'domains': domains_str,
            'database': database,
            'export_columns': 'Ph,Nq,Cp,Co,Kd,' + ','.join([f'P{i}' for i in range(len(all_domains))]),
            'display_limit': limit,
            'display_sort': 'nq_desc',
            'display_filter': '+|P0|Lt|11'  # Target domain not in top 10
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        gaps = self._parse_keyword_gap(result.get('data', ''), competitors)
        
        return {
            'domain': domain,
            'competitors': competitors,
            'count': len(gaps),
            'gaps': gaps
        }
    
    def get_keyword_comparison(self, domain: str, competitors: List[str], limit: int = 200, database: str = None) -> Dict[str, Any]:
        """
        Get ALL keywords across domain and competitors - no restrictive filters.
        Shows every keyword any of the domains rank for, with positions for all.
        
        SEMrush domain_domains format:
        *|or|domain1.com|+|or|domain2.com|+|or|domain3.com
        * = start with all keywords
        +|or| = add organic keywords from this domain
        -|or| = exclude organic keywords from this domain
        """
        database = database or self.default_database
        domain = self._clean_domain(domain)
        competitors = [self._clean_domain(c) for c in competitors[:4]]
        
        # Build domains string with proper SEMrush format
        # *|or|yourdomain.com|+|or|competitor1.com|+|or|competitor2.com
        # This gets ALL keywords where ANY of the domains rank
        all_domains = [domain] + competitors
        domains_str = '*|or|' + '|+|or|'.join(all_domains)
        
        logger.info(f"domain_domains request: domains={domains_str}")
        
        params = {
            'type': 'domain_domains',
            'key': self.api_key,
            'domains': domains_str,
            'database': database,
            'export_columns': 'Ph,Nq,Cp,Co,Kd,' + ','.join([f'P{i}' for i in range(len(all_domains))]),
            'display_limit': limit,
            'display_sort': 'nq_desc'
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            logger.warning(f"domain_domains error: {result.get('error')}")
            return result
        
        # Log raw response
        raw = result.get('data', '')
        lines = raw.strip().split('\n')
        logger.info(f"domain_domains response: {len(lines)} lines")
        if len(lines) >= 2:
            logger.info(f"  Header: {lines[0]}")
            logger.info(f"  First row: {lines[1]}")
        
        keywords = self._parse_keyword_gap(result.get('data', ''), competitors)
        
        logger.info(f"  Parsed {len(keywords)} keywords")
        if keywords:
            logger.info(f"  First parsed: {keywords[0]}")
        
        return {
            'domain': domain,
            'competitors': competitors,
            'count': len(keywords),
            'keywords': keywords
        }
    
    # ==========================================
    # BACKLINK ANALYSIS
    # ==========================================
    
    def get_backlink_overview(self, domain: str) -> Dict[str, Any]:
        """
        Get backlink profile overview
        
        Returns:
            {
                'domain': str,
                'total_backlinks': int,
                'referring_domains': int,
                'referring_ips': int
            }
        """
        domain = self._clean_domain(domain)
        
        params = {
            'type': 'backlinks_overview',
            'key': self.api_key,
            'target': domain,
            'target_type': 'root_domain',
            'export_columns': 'total,domains_num,urls_num,ips_num'
        }
        
        result = self._make_request(params)
        
        if result.get('error'):
            return result
        
        lines = result.get('data', '').strip().split('\n')
        if len(lines) < 2:
            return {'error': 'No backlink data', 'domain': domain}
        
        values = lines[1].split(';')
        
        return {
            'domain': domain,
            'total_backlinks': int(values[0]) if len(values) > 0 and values[0].isdigit() else 0,
            'referring_domains': int(values[1]) if len(values) > 1 and values[1].isdigit() else 0,
            'referring_urls': int(values[2]) if len(values) > 2 and values[2].isdigit() else 0,
            'referring_ips': int(values[3]) if len(values) > 3 and values[3].isdigit() else 0
        }
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _make_request(self, params: Dict) -> Dict[str, Any]:
        """Make API request to SEMRush"""
        if not self.api_key:
            return {'error': 'SEMRush API key not configured'}
        
        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=30
            )
            
            # Check for error responses
            if response.status_code != 200:
                return {'error': f'API error: {response.status_code}', 'details': response.text}
            
            # SEMRush returns errors as text starting with "ERROR"
            if response.text.startswith('ERROR'):
                error_code = response.text.split('::')[0] if '::' in response.text else response.text
                return {'error': response.text, 'code': error_code}
            
            return {'data': response.text}
            
        except requests.RequestException as e:
            return {'error': f'Request failed: {str(e)}'}
    
    def _clean_domain(self, domain: str) -> str:
        """Clean domain URL to just domain name"""
        domain = domain.lower().strip()
        domain = domain.replace('https://', '').replace('http://', '')
        domain = domain.replace('www.', '')
        domain = domain.split('/')[0]
        return domain
    
    def _parse_keyword_results(self, data: str) -> List[Dict]:
        """Parse keyword CSV data"""
        results = []
        lines = data.strip().split('\n')
        
        if len(lines) < 2:
            return results
        
        for line in lines[1:]:  # Skip header
            line = line.strip()  # Remove \r
            values = line.split(';')
            if len(values) >= 5:
                results.append({
                    'keyword': values[0],
                    'volume': int(values[1]) if values[1].isdigit() else 0,
                    'cpc': float(values[2]) if values[2] else 0.0,
                    'competition': float(values[3]) if values[3] else 0.0,
                    'difficulty': int(values[4]) if values[4].isdigit() else 0
                })
        
        return results
    
    def _parse_domain_keywords(self, data: str) -> List[Dict]:
        """Parse domain organic keywords CSV"""
        results = []
        lines = data.strip().split('\n')
        
        if len(lines) < 2:
            return results
        
        for line in lines[1:]:
            line = line.strip()  # Remove \r
            values = line.split(';')
            if len(values) >= 7:
                results.append({
                    'keyword': values[0],
                    'position': int(values[1]) if values[1].isdigit() else 0,
                    'volume': int(values[2]) if values[2].isdigit() else 0,
                    'cpc': float(values[3]) if values[3] else 0.0,
                    'competition': float(values[4]) if values[4] else 0.0,
                    'difficulty': int(values[5]) if values[5].isdigit() else 0,
                    'url': values[6] if len(values) > 6 else ''
                })
        
        return results
    
    def _parse_competitors(self, data: str) -> List[Dict]:
        """Parse competitor CSV data"""
        results = []
        lines = data.strip().split('\n')
        
        if len(lines) < 2:
            return results
        
        for line in lines[1:]:
            line = line.strip()  # Remove \r
            values = line.split(';')
            if len(values) >= 6:
                results.append({
                    'domain': values[0],
                    'competition_level': float(values[1]) if values[1] else 0.0,
                    'common_keywords': int(values[2]) if values[2].isdigit() else 0,
                    'organic_keywords': int(values[3]) if values[3].isdigit() else 0,
                    'organic_traffic': int(values[4]) if values[4].isdigit() else 0,
                    'organic_cost': float(values[5]) if values[5] else 0.0
                })
        
        return results
    
    def _parse_keyword_gap(self, data: str, competitors: List[str]) -> List[Dict]:
        """Parse keyword gap CSV data from domain_domains endpoint"""
        results = []
        lines = data.strip().split('\n')
        
        if len(lines) < 2:
            return results
        
        for line in lines[1:]:
            line = line.strip()  # Remove \r and whitespace
            values = line.split(';')
            if len(values) >= 6:
                # Helper to parse SEMrush integer values (may come as "57.00" or "0")
                def parse_int(val):
                    val = val.strip()
                    if not val:
                        return 0
                    try:
                        return int(float(val))
                    except (ValueError, TypeError):
                        return 0
                
                your_pos_raw = parse_int(values[5]) if len(values) > 5 else 0
                gap = {
                    'keyword': values[0].strip(),
                    'volume': parse_int(values[1]),
                    'cpc': float(values[2].strip()) if values[2].strip() else 0.0,
                    'competition': float(values[3].strip()) if values[3].strip() else 0.0,
                    'difficulty': parse_int(values[4]),
                    'your_position': your_pos_raw if your_pos_raw > 0 else None,  # 0 = not ranking
                    'competitor_positions': {}
                }
                
                # Add competitor positions (0 = not ranking = None)
                for i, comp in enumerate(competitors):
                    pos_idx = 6 + i
                    if len(values) > pos_idx:
                        pos = parse_int(values[pos_idx])
                        gap['competitor_positions'][comp] = pos if pos > 0 else None
                
                results.append(gap)
        
        return results
    
    # ==========================================
    # HIGH-LEVEL RESEARCH METHODS
    # ==========================================
    
    def full_competitor_research(self, domain: str, database: str = None) -> Dict[str, Any]:
        """
        Complete competitor research package
        
        Returns comprehensive analysis including:
        - Domain overview
        - Top organic keywords
        - Top competitors
        - Keyword gaps
        - Backlink overview
        """
        database = database or self.default_database
        
        # Get domain overview
        overview = self.get_domain_overview(domain, database)
        
        # Get top keywords
        keywords = self.get_domain_organic_keywords(domain, limit=30, database=database)
        
        # Find competitors
        competitors = self.get_competitors(domain, limit=5, database=database)
        
        # Get keyword gaps if we found competitors
        gaps = {'gaps': []}
        if competitors.get('competitors'):
            comp_domains = [c['domain'] for c in competitors['competitors'][:3]]
            gaps = self.get_keyword_gap(domain, comp_domains, limit=30, database=database)
        
        # Backlink overview
        backlinks = self.get_backlink_overview(domain)
        
        return {
            'domain': domain,
            'overview': overview,
            'top_keywords': keywords.get('keywords', [])[:20],
            'competitors': competitors.get('competitors', []),
            'keyword_gaps': gaps.get('gaps', [])[:20],
            'backlinks': backlinks
        }
    
    def keyword_research_package(self, seed_keyword: str, location: str = '', database: str = None) -> Dict[str, Any]:
        """
        Complete keyword research for content planning
        
        Returns:
        - Seed keyword metrics
        - Related variations
        - Question keywords (for FAQs)
        - Long-tail opportunities
        """
        database = database or self.default_database
        
        # Add location to keyword if provided
        search_keyword = f"{seed_keyword} {location}".strip() if location else seed_keyword
        
        # Get seed keyword data
        seed_data = self.get_keyword_overview(search_keyword, database)
        
        # Get variations
        variations = self.get_keyword_variations(search_keyword, limit=30, database=database)
        
        # Get questions for FAQ content
        questions = self.get_keyword_questions(seed_keyword, limit=10, database=database)
        
        # Sort variations by volume and identify opportunities
        sorted_variations = sorted(
            variations.get('variations', []),
            key=lambda x: x.get('volume', 0),
            reverse=True
        )
        
        # Identify low competition opportunities
        opportunities = [
            v for v in sorted_variations
            if v.get('difficulty', 100) < 50 and v.get('volume', 0) > 100
        ][:10]
        
        return {
            'seed_keyword': search_keyword,
            'seed_metrics': seed_data,
            'variations': sorted_variations[:20],
            'questions': questions.get('questions', []),
            'opportunities': opportunities,
            'total_variations': len(sorted_variations)
        }
