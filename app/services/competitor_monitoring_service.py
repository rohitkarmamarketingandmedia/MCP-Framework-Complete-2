"""
MCP Framework - Competitor Monitoring Service
Detects new content from competitors and triggers auto-response
"""
import os
import re
import json
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CompetitorMonitoringService:
    """
    Monitors competitor websites for new content
    Triggers content generation when new posts detected
    """
    
    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.timeout = 15
        self.max_pages_per_crawl = 300
    
    def crawl_sitemap(self, domain: str) -> List[Dict]:
        """
        Crawl a competitor's sitemap to find all pages.
        Tries robots.txt, sitemap.xml, wp-sitemap.xml, then homepage fallback.
        """
        domain = self._clean_domain(domain)
        pages = []
        
        logger.info(f"[CRAWL] Starting crawl for {domain}")
        
        # Step 1: Check robots.txt for sitemap location
        sitemap_from_robots = self._get_sitemap_from_robots(domain)
        
        # Build sitemap URL list
        sitemap_urls = []
        if sitemap_from_robots:
            sitemap_urls.extend(sitemap_from_robots)
        
        sitemap_urls.extend([
            f'https://{domain}/sitemap.xml',
            f'https://{domain}/sitemap_index.xml',
            f'https://{domain}/wp-sitemap.xml',
            f'https://{domain}/post-sitemap.xml',
            f'https://www.{domain}/sitemap.xml',
            f'https://www.{domain}/wp-sitemap.xml',
        ])
        
        # Deduplicate
        seen = set()
        unique_urls = []
        for url in sitemap_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        for sitemap_url in unique_urls:
            try:
                logger.info(f"[CRAWL] Trying sitemap: {sitemap_url}")
                response = requests.get(
                    sitemap_url,
                    headers={'User-Agent': self.user_agent},
                    timeout=self.timeout,
                    allow_redirects=True
                )
                
                if response.status_code == 200 and '<' in response.text[:200]:
                    pages = self._parse_sitemap(response.text, sitemap_url)
                    if pages:
                        logger.info(f"[CRAWL] Found {len(pages)} pages from {sitemap_url}")
                        break
                    else:
                        logger.info(f"[CRAWL] Sitemap found but empty: {sitemap_url}")
                else:
                    logger.info(f"[CRAWL] Sitemap not available: {sitemap_url} (status={response.status_code})")
            except requests.exceptions.Timeout:
                logger.warning(f"[CRAWL] Timeout fetching {sitemap_url}")
            except Exception as e:
                logger.info(f"[CRAWL] Error fetching {sitemap_url}: {e}")
        
        # Step 2: Fallback to homepage crawl
        if not pages:
            logger.info(f"[CRAWL] No sitemap found for {domain}, crawling homepage")
            pages = self._crawl_homepage(domain)
        
        total = len(pages[:self.max_pages_per_crawl])
        logger.info(f"[CRAWL] Complete for {domain}: {total} pages found")
        return pages[:self.max_pages_per_crawl]
    
    def _get_sitemap_from_robots(self, domain: str) -> List[str]:
        """Check robots.txt for Sitemap: directives"""
        sitemaps = []
        for prefix in [f'https://{domain}', f'https://www.{domain}']:
            try:
                response = requests.get(
                    f'{prefix}/robots.txt',
                    headers={'User-Agent': self.user_agent},
                    timeout=8
                )
                if response.status_code == 200:
                    for line in response.text.splitlines():
                        line = line.strip()
                        if line.lower().startswith('sitemap:'):
                            sitemap_url = line.split(':', 1)[1].strip()
                            if sitemap_url.startswith('http'):
                                sitemaps.append(sitemap_url)
                                logger.info(f"[CRAWL] Found sitemap in robots.txt: {sitemap_url}")
                    if sitemaps:
                        return sitemaps
            except Exception:
                continue
        return sitemaps
    
    def _parse_sitemap(self, xml_content: str, base_url: str) -> List[Dict]:
        """Parse sitemap XML and extract URLs"""
        pages = []
        
        try:
            try:
                soup = BeautifulSoup(xml_content, 'xml')
            except Exception:
                soup = BeautifulSoup(xml_content, 'html.parser')
            
            # Check if this is a sitemap index
            sitemap_tags = soup.find_all('sitemap')
            if sitemap_tags:
                logger.info(f"[CRAWL] Sitemap index with {len(sitemap_tags)} child sitemaps")
                for sitemap in sitemap_tags[:10]:
                    loc = sitemap.find('loc')
                    if loc and loc.text:
                        try:
                            child_response = requests.get(
                                loc.text.strip(),
                                headers={'User-Agent': self.user_agent},
                                timeout=self.timeout
                            )
                            if child_response.status_code == 200:
                                child_pages = self._parse_sitemap(child_response.text, loc.text)
                                pages.extend(child_pages)
                                logger.info(f"[CRAWL] Child sitemap {loc.text.strip()}: {len(child_pages)} pages")
                        except Exception as e:
                            logger.info(f"[CRAWL] Failed child sitemap {loc.text}: {e}")
            else:
                url_tags = soup.find_all('url')
                for url_tag in url_tags:
                    loc = url_tag.find('loc')
                    lastmod = url_tag.find('lastmod')
                    
                    if loc and loc.text:
                        url = loc.text.strip()
                        if self._is_content_url(url):
                            pages.append({
                                'url': url,
                                'lastmod': lastmod.text.strip() if lastmod and lastmod.text else None,
                                'discovered_at': datetime.utcnow().isoformat()
                            })
                
                logger.info(f"[CRAWL] Parsed {len(pages)} content URLs from sitemap")
                
        except Exception as e:
            logger.warning(f"[CRAWL] Sitemap parse error for {base_url}: {e}")
        
        return pages
    
    def _crawl_homepage(self, domain: str) -> List[Dict]:
        """Fallback: crawl homepage for content links"""
        pages = []
        crawled_urls = set()
        
        for start_url in [f'https://{domain}', f'https://www.{domain}']:
            try:
                response = requests.get(
                    start_url,
                    headers={'User-Agent': self.user_agent},
                    timeout=self.timeout,
                    allow_redirects=True
                )
                
                if response.status_code != 200:
                    continue
                
                final_domain = urlparse(response.url).netloc.replace('www.', '')
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href'].strip()
                    
                    if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                        continue
                    
                    if href.startswith('/'):
                        href = f'{start_url.rstrip("/")}{href}'
                    elif not href.startswith('http'):
                        href = f'{start_url.rstrip("/")}/{href}'
                    
                    parsed = urlparse(href)
                    link_domain = parsed.netloc.replace('www.', '')
                    
                    if link_domain == final_domain and self._is_content_url(href):
                        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')
                        
                        if clean_url not in crawled_urls:
                            crawled_urls.add(clean_url)
                            pages.append({
                                'url': clean_url,
                                'lastmod': None,
                                'discovered_at': datetime.utcnow().isoformat(),
                                'title': link.text.strip()[:200] if link.text else ''
                            })
                
                if pages:
                    logger.info(f"[CRAWL] Homepage crawl for {domain}: {len(pages)} links")
                    break
                    
            except Exception as e:
                logger.info(f"[CRAWL] Homepage crawl error for {start_url}: {e}")
        
        if not pages:
            logger.warning(f"[CRAWL] No pages found for {domain}")
        
        return pages
    
    def _is_content_url(self, url: str) -> bool:
        """Check if URL is likely a content page"""
        skip_patterns = [
            '/wp-content/', '/wp-admin/', '/wp-includes/', '/wp-json/',
            '/cart', '/checkout', '/my-account', '/login', '/register',
            '/feed', '/rss', '/xmlrpc',
            '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
            '.pdf', '.css', '.js', '.zip', '.xml',
            '/tag/', '/category/', '/author/', '/page/',
            '/cdn-cgi/', '/wp-login',
            '#', '?utm_', '?fbclid', '?gclid'
        ]
        
        url_lower = url.lower()
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False
        
        parsed = urlparse(url_lower)
        path = parsed.path.strip('/')
        if not path:
            return False
        
        return True
    
    def extract_page_content(self, url: str) -> Dict:
        """Extract content from a competitor page"""
        result = {
            'url': url, 'title': '', 'meta_description': '',
            'h1': '', 'h2s': [], 'body_text': '',
            'word_count': 0, 'content_hash': '',
            'crawled_at': datetime.utcnow().isoformat(), 'error': None
        }
        
        try:
            response = requests.get(
                url,
                headers={'User-Agent': self.user_agent},
                timeout=self.timeout,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            title_tag = soup.find('title')
            result['title'] = title_tag.text.strip()[:500] if title_tag else ''
            
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                result['meta_description'] = meta_desc['content'][:500]
            
            h1_tag = soup.find('h1')
            result['h1'] = h1_tag.text.strip()[:500] if h1_tag else ''
            result['h2s'] = [h2.text.strip()[:200] for h2 in soup.find_all('h2')][:10]
            
            content_selectors = [
                'article', 'main', '.post-content', '.entry-content',
                '.blog-content', '.content', '.page-content',
                '#content', '#main-content', '[role="main"]'
            ]
            
            body_text = ''
            for selector in content_selectors:
                if selector.startswith(('.', '#', '[')):
                    container = soup.select_one(selector)
                else:
                    container = soup.find(selector)
                
                if container:
                    for tag in container.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript']):
                        tag.decompose()
                    body_text = container.get_text(separator=' ', strip=True)
                    if len(body_text.split()) > 50:
                        break
                    body_text = ''
            
            if not body_text:
                body = soup.find('body')
                if body:
                    for tag in body.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript', 'iframe']):
                        tag.decompose()
                    body_text = body.get_text(separator=' ', strip=True)
            
            body_text = re.sub(r'\s+', ' ', body_text).strip()
            
            result['body_text'] = body_text[:10000]
            result['word_count'] = len(body_text.split())
            result['content_hash'] = hashlib.md5(body_text.encode()).hexdigest()
            
            logger.info(f"[CRAWL] Extracted {url}: {result['word_count']} words")
            
        except requests.exceptions.Timeout:
            result['error'] = 'Timeout'
            logger.warning(f"[CRAWL] Timeout: {url}")
        except Exception as e:
            result['error'] = str(e)[:200]
            logger.warning(f"[CRAWL] Extract error {url}: {e}")
        
        return result
    
    def detect_new_content(
        self, competitor_domain: str,
        known_pages: List[Dict], last_crawl_at: datetime = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """Compare current sitemap with known pages"""
        current_pages = self.crawl_sitemap(competitor_domain)
        
        known_urls = {p['url']: p for p in known_pages}
        new_pages = []
        updated_pages = []
        
        for page in current_pages:
            url = page['url']
            if url not in known_urls:
                new_pages.append(page)
            elif page.get('lastmod') and known_urls[url].get('lastmod'):
                try:
                    current_mod = datetime.fromisoformat(page['lastmod'].replace('Z', '+00:00'))
                    known_mod = datetime.fromisoformat(known_urls[url]['lastmod'].replace('Z', '+00:00'))
                    if current_mod > known_mod:
                        updated_pages.append(page)
                except Exception:
                    pass
        
        logger.info(f"[CRAWL] detect_new_content {competitor_domain}: {len(new_pages)} new, {len(updated_pages)} updated ({len(current_pages)} total, {len(known_pages)} known)")
        return new_pages, updated_pages
    
    def analyze_competitor_content(self, content: Dict) -> Dict:
        """Analyze extracted content for SEO metrics"""
        analysis = {
            'word_count': content.get('word_count', 0),
            'has_h1': bool(content.get('h1')),
            'h2_count': len(content.get('h2s', [])),
            'has_meta_description': bool(content.get('meta_description')),
            'estimated_read_time': content.get('word_count', 0) // 200,
            'content_quality_signals': []
        }
        
        body = content.get('body_text', '').lower()
        
        if analysis['word_count'] > 1500:
            analysis['content_quality_signals'].append('long_form')
        if analysis['h2_count'] >= 3:
            analysis['content_quality_signals'].append('well_structured')
        if 'faq' in body or 'frequently asked' in body:
            analysis['content_quality_signals'].append('has_faq')
        if any(word in body for word in ['video', 'youtube', 'watch']):
            analysis['content_quality_signals'].append('has_video')
        
        analysis['recommended_word_count'] = max(int(analysis['word_count'] * 1.5), 1200)
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
