"""
MCP Framework - Competitor Monitoring Service
Detects new content from competitors and triggers auto-response
"""
import os
import re
import json
import hashlib
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


class CompetitorMonitoringService:
    """
    Monitors competitor websites for new content
    Triggers content generation when new posts detected
    """
    
    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (compatible; MCPBot/1.0; +https://karmamarketing.com)'
        self.timeout = 10  # Reduced from 30 to avoid worker timeout
        self.max_pages_per_crawl = 10  # Reduced from 50 to be faster
    
    def crawl_sitemap(self, domain: str) -> List[Dict]:
        """
        Crawl a competitor's sitemap to find all pages
        Returns list of {url, lastmod, title}
        """
        domain = self._clean_domain(domain)
        pages = []
        
        # Try common sitemap locations
        sitemap_urls = [
            f'https://{domain}/sitemap.xml',
            f'https://{domain}/sitemap_index.xml',
            f'https://{domain}/wp-sitemap.xml',
            f'https://www.{domain}/sitemap.xml',
        ]
        
        for sitemap_url in sitemap_urls:
            try:
                response = requests.get(
                    sitemap_url,
                    headers={'User-Agent': self.user_agent},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    pages = self._parse_sitemap(response.text, sitemap_url)
                    if pages:
                        break
            except Exception:
                continue
        
        # If no sitemap, try crawling homepage for links
        if not pages:
            pages = self._crawl_homepage(domain)
        
        return pages[:self.max_pages_per_crawl]
    
    def _parse_sitemap(self, xml_content: str, base_url: str) -> List[Dict]:
        """Parse sitemap XML and extract URLs"""
        pages = []
        
        try:
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Check if this is a sitemap index
            sitemap_tags = soup.find_all('sitemap')
            if sitemap_tags:
                # This is an index, crawl child sitemaps
                for sitemap in sitemap_tags[:5]:  # Limit to 5 child sitemaps
                    loc = sitemap.find('loc')
                    if loc:
                        try:
                            child_response = requests.get(
                                loc.text,
                                headers={'User-Agent': self.user_agent},
                                timeout=self.timeout
                            )
                            if child_response.status_code == 200:
                                child_pages = self._parse_sitemap(child_response.text, loc.text)
                                pages.extend(child_pages)
                        except Exception:
                            continue
            else:
                # Regular sitemap
                url_tags = soup.find_all('url')
                for url_tag in url_tags:
                    loc = url_tag.find('loc')
                    lastmod = url_tag.find('lastmod')
                    
                    if loc:
                        page = {
                            'url': loc.text,
                            'lastmod': lastmod.text if lastmod else None,
                            'discovered_at': datetime.utcnow().isoformat()
                        }
                        pages.append(page)
        except Exception as e:
            logger.info(f"Sitemap parse error: {e}")
        
        return pages
    
    def _crawl_homepage(self, domain: str) -> List[Dict]:
        """Fallback: crawl homepage for blog/page links"""
        pages = []
        
        try:
            response = requests.get(
                f'https://{domain}',
                headers={'User-Agent': self.user_agent},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    # Convert relative to absolute
                    if href.startswith('/'):
                        href = f'https://{domain}{href}'
                    
                    # Only include links from same domain
                    if domain in href:
                        # Filter for likely content pages
                        if self._is_content_url(href):
                            pages.append({
                                'url': href,
                                'lastmod': None,
                                'discovered_at': datetime.utcnow().isoformat()
                            })
        except Exception:
            pass
        
        # Deduplicate
        seen = set()
        unique_pages = []
        for page in pages:
            if page['url'] not in seen:
                seen.add(page['url'])
                unique_pages.append(page)
        
        return unique_pages
    
    def _is_content_url(self, url: str) -> bool:
        """Check if URL is likely a content page (blog, service, etc.)"""
        # Skip common non-content patterns
        skip_patterns = [
            '/wp-content/', '/wp-admin/', '/wp-includes/',
            '/cart', '/checkout', '/my-account', '/login',
            '.jpg', '.png', '.gif', '.pdf', '.css', '.js',
            '/tag/', '/category/', '/author/', '/page/',
            '#', '?'
        ]
        
        url_lower = url.lower()
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False
        
        return True
    
    def extract_page_content(self, url: str) -> Dict:
        """
        Extract content from a competitor page
        Returns title, meta, headings, body, word count
        """
        result = {
            'url': url,
            'title': '',
            'meta_description': '',
            'h1': '',
            'h2s': [],
            'body_text': '',
            'word_count': 0,
            'content_hash': '',
            'crawled_at': datetime.utcnow().isoformat(),
            'error': None
        }
        
        try:
            response = requests.get(
                url,
                headers={'User-Agent': self.user_agent},
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Title
            title_tag = soup.find('title')
            result['title'] = title_tag.text.strip() if title_tag else ''
            
            # Meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                result['meta_description'] = meta_desc['content']
            
            # H1
            h1_tag = soup.find('h1')
            result['h1'] = h1_tag.text.strip() if h1_tag else ''
            
            # H2s
            result['h2s'] = [h2.text.strip() for h2 in soup.find_all('h2')][:10]
            
            # Main content - try common content containers
            content_selectors = [
                'article', '.post-content', '.entry-content', 
                '.blog-content', '.content', 'main', '#content'
            ]
            
            body_text = ''
            for selector in content_selectors:
                if selector.startswith('.') or selector.startswith('#'):
                    container = soup.select_one(selector)
                else:
                    container = soup.find(selector)
                
                if container:
                    # Remove scripts and styles
                    for tag in container.find_all(['script', 'style', 'nav', 'footer']):
                        tag.decompose()
                    
                    body_text = container.get_text(separator=' ', strip=True)
                    break
            
            if not body_text:
                # Fallback to body
                body = soup.find('body')
                if body:
                    for tag in body.find_all(['script', 'style', 'nav', 'footer', 'header']):
                        tag.decompose()
                    body_text = body.get_text(separator=' ', strip=True)
            
            # Clean up whitespace
            body_text = re.sub(r'\s+', ' ', body_text).strip()
            
            result['body_text'] = body_text[:10000]  # Limit stored text
            result['word_count'] = len(body_text.split())
            result['content_hash'] = hashlib.md5(body_text.encode()).hexdigest()
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def detect_new_content(
        self,
        competitor_domain: str,
        known_pages: List[Dict],
        last_crawl_at: datetime = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Compare current sitemap with known pages
        Returns (new_pages, updated_pages)
        """
        current_pages = self.crawl_sitemap(competitor_domain)
        
        known_urls = {p['url']: p for p in known_pages}
        
        new_pages = []
        updated_pages = []
        
        for page in current_pages:
            url = page['url']
            
            if url not in known_urls:
                # Brand new page
                new_pages.append(page)
            elif page.get('lastmod') and known_urls[url].get('lastmod'):
                # Check if updated
                try:
                    current_mod = datetime.fromisoformat(page['lastmod'].replace('Z', '+00:00'))
                    known_mod = datetime.fromisoformat(known_urls[url]['lastmod'].replace('Z', '+00:00'))
                    
                    if current_mod > known_mod:
                        updated_pages.append(page)
                except Exception:
                    pass
        
        return new_pages, updated_pages
    
    def analyze_competitor_content(self, content: Dict) -> Dict:
        """
        Analyze extracted content for SEO metrics
        Used to determine how to beat it
        """
        analysis = {
            'word_count': content.get('word_count', 0),
            'has_h1': bool(content.get('h1')),
            'h2_count': len(content.get('h2s', [])),
            'has_meta_description': bool(content.get('meta_description')),
            'estimated_read_time': content.get('word_count', 0) // 200,  # 200 wpm
            'content_quality_signals': []
        }
        
        body = content.get('body_text', '').lower()
        
        # Check for quality signals
        if analysis['word_count'] > 1500:
            analysis['content_quality_signals'].append('long_form')
        if analysis['h2_count'] >= 3:
            analysis['content_quality_signals'].append('well_structured')
        if 'faq' in body or 'frequently asked' in body:
            analysis['content_quality_signals'].append('has_faq')
        if any(word in body for word in ['video', 'youtube', 'watch']):
            analysis['content_quality_signals'].append('has_video')
        if any(word in body for word in ['infographic', 'chart', 'graph']):
            analysis['content_quality_signals'].append('has_visuals')
        
        # Calculate beat strategy
        analysis['recommended_word_count'] = int(analysis['word_count'] * 1.5)  # 50% longer
        if analysis['recommended_word_count'] < 1200:
            analysis['recommended_word_count'] = 1200
        
        analysis['recommended_h2_count'] = max(analysis['h2_count'] + 2, 5)
        
        return analysis
    
    def _clean_domain(self, domain: str) -> str:
        """Clean domain string"""
        domain = domain.lower().strip()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        domain = domain.rstrip('/')
        return domain.split('/')[0]


# Singleton
competitor_monitoring_service = CompetitorMonitoringService()
