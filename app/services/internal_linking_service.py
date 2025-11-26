"""
MCP Framework - Internal Linking Service
Auto-insert internal links and enforce SEO rules
"""
import re
from typing import List, Dict, Tuple, Optional


class InternalLinkingService:
    """Handles internal link injection and SEO formatting"""
    
    def __init__(self):
        self.min_links_per_post = 3
        self.max_links_per_post = 8
        self.min_words_between_links = 150
    
    def inject_internal_links(
        self,
        content: str,
        service_pages: List[Dict],
        primary_keyword: str = '',
        max_links: int = None
    ) -> Tuple[str, int]:
        """
        Inject internal links into content based on service pages
        
        Args:
            content: HTML blog content
            service_pages: List of {"keyword": str, "url": str, "title": str}
            primary_keyword: Main keyword (avoid linking this)
            max_links: Maximum links to insert
            
        Returns:
            Tuple of (modified_content, link_count)
        """
        if not service_pages:
            return content, 0
        
        max_links = max_links or self.max_links_per_post
        links_inserted = 0
        used_urls = set()
        
        # Sort service pages by keyword length (longer first for better matching)
        sorted_pages = sorted(service_pages, key=lambda x: len(x.get('keyword', '')), reverse=True)
        
        # Track positions where links are inserted to maintain spacing
        link_positions = []
        
        for page in sorted_pages:
            if links_inserted >= max_links:
                break
            
            keyword = page.get('keyword', '').strip()
            url = page.get('url', '').strip()
            title = page.get('title', keyword)
            
            if not keyword or not url:
                continue
            
            # Skip if URL already used
            if url in used_urls:
                continue
            
            # Skip if keyword matches primary keyword
            if primary_keyword and keyword.lower() == primary_keyword.lower():
                continue
            
            # Find the keyword in content (case insensitive, whole word)
            pattern = re.compile(
                r'(?<![<>/\w])(' + re.escape(keyword) + r')(?![<>\w])',
                re.IGNORECASE
            )
            
            matches = list(pattern.finditer(content))
            
            for match in matches:
                if links_inserted >= max_links:
                    break
                
                start_pos = match.start()
                
                # Check if already inside a link tag
                preceding = content[max(0, start_pos-100):start_pos]
                if '<a ' in preceding and '</a>' not in preceding:
                    continue
                
                # Check spacing from other links
                too_close = False
                for prev_pos in link_positions:
                    words_between = len(content[min(prev_pos, start_pos):max(prev_pos, start_pos)].split())
                    if words_between < self.min_words_between_links:
                        too_close = True
                        break
                
                if too_close:
                    continue
                
                # Build the link
                matched_text = match.group(1)
                link_html = f'<a href="{url}" title="{title}">{matched_text}</a>'
                
                # Replace this occurrence
                content = content[:start_pos] + link_html + content[match.end():]
                
                links_inserted += 1
                used_urls.add(url)
                link_positions.append(start_pos)
                
                # Only replace first occurrence of each keyword
                break
        
        return content, links_inserted
    
    def validate_headings(
        self,
        content: str,
        primary_keyword: str,
        location: str
    ) -> Dict:
        """
        Validate that headings follow SEO rules:
        - H2s should start with keyword + location
        - H3s should include keyword or related terms
        
        Returns validation report
        """
        report = {
            'valid': True,
            'h2_count': 0,
            'h3_count': 0,
            'issues': [],
            'suggestions': []
        }
        
        # Find all H2 tags
        h2_pattern = re.compile(r'<h2[^>]*>(.*?)</h2>', re.IGNORECASE | re.DOTALL)
        h2_matches = h2_pattern.findall(content)
        report['h2_count'] = len(h2_matches)
        
        keyword_lower = primary_keyword.lower()
        location_lower = location.lower()
        
        for i, h2_text in enumerate(h2_matches):
            h2_clean = re.sub(r'<[^>]+>', '', h2_text).strip().lower()
            
            # Check if H2 starts with keyword
            if not h2_clean.startswith(keyword_lower[:20]):  # Check first 20 chars
                report['issues'].append(f'H2 #{i+1} does not start with keyword')
                report['valid'] = False
            
            # Check if location is in H2
            if location_lower.split(',')[0].strip() not in h2_clean:
                report['issues'].append(f'H2 #{i+1} missing location')
                report['valid'] = False
        
        # Find all H3 tags
        h3_pattern = re.compile(r'<h3[^>]*>(.*?)</h3>', re.IGNORECASE | re.DOTALL)
        h3_matches = h3_pattern.findall(content)
        report['h3_count'] = len(h3_matches)
        
        return report
    
    def fix_headings(
        self,
        content: str,
        primary_keyword: str,
        location: str,
        secondary_keywords: List[str] = None
    ) -> str:
        """
        Attempt to fix headings to comply with SEO rules
        """
        # Get location city
        location_city = location.split(',')[0].strip() if location else ''
        
        # Fix H2 tags - prepend keyword + location if missing
        def fix_h2(match):
            h2_content = match.group(1)
            h2_clean = re.sub(r'<[^>]+>', '', h2_content).strip().lower()
            
            keyword_lower = primary_keyword.lower()
            
            # If H2 already starts with keyword, return as-is
            if h2_clean.startswith(keyword_lower[:15]):
                # Check for location
                if location_city.lower() in h2_clean:
                    return match.group(0)
                else:
                    # Add location
                    h2_content_clean = re.sub(r'<[^>]+>', '', h2_content).strip()
                    return f'<h2>{h2_content_clean} in {location_city}</h2>'
            
            # H2 doesn't start with keyword - prepend it
            h2_content_clean = re.sub(r'<[^>]+>', '', h2_content).strip()
            new_h2 = f'{primary_keyword.title()} in {location_city}: {h2_content_clean}'
            return f'<h2>{new_h2}</h2>'
        
        content = re.sub(r'<h2[^>]*>(.*?)</h2>', fix_h2, content, flags=re.IGNORECASE | re.DOTALL)
        
        return content
    
    def count_links(self, content: str) -> int:
        """Count internal links in content"""
        pattern = re.compile(r'<a[^>]*href=[^>]*>', re.IGNORECASE)
        return len(pattern.findall(content))
    
    def get_linked_urls(self, content: str) -> List[str]:
        """Extract all linked URLs from content"""
        pattern = re.compile(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
        return pattern.findall(content)
    
    def ensure_minimum_links(
        self,
        content: str,
        service_pages: List[Dict],
        primary_keyword: str = ''
    ) -> Tuple[str, int]:
        """
        Ensure content has minimum required internal links
        Add generic CTA links if needed
        """
        current_count = self.count_links(content)
        
        if current_count >= self.min_links_per_post:
            return content, current_count
        
        # Need to add more links
        needed = self.min_links_per_post - current_count
        
        # First try to inject more based on service pages
        content, added = self.inject_internal_links(
            content, 
            service_pages, 
            primary_keyword,
            max_links=needed
        )
        
        return content, current_count + added
    
    def generate_cta_paragraph(
        self,
        service_pages: List[Dict],
        business_name: str,
        location: str
    ) -> str:
        """
        Generate a CTA paragraph with internal links
        Useful for adding at end of blog posts
        """
        if not service_pages:
            return ''
        
        # Select up to 3 service pages for CTA
        selected = service_pages[:3]
        
        links = []
        for page in selected:
            keyword = page.get('keyword', '')
            url = page.get('url', '')
            title = page.get('title', keyword)
            if keyword and url:
                links.append(f'<a href="{url}" title="{title}">{keyword}</a>')
        
        if not links:
            return ''
        
        if len(links) == 1:
            link_text = links[0]
        elif len(links) == 2:
            link_text = f'{links[0]} and {links[1]}'
        else:
            link_text = f'{", ".join(links[:-1])}, and {links[-1]}'
        
        return f'''
<p><strong>Ready to get started?</strong> {business_name} provides professional {link_text} services in {location}. Contact us today for a free consultation!</p>
'''
    
    def process_blog_content(
        self,
        content: str,
        service_pages: List[Dict],
        primary_keyword: str,
        location: str,
        business_name: str,
        fix_headings: bool = True,
        add_cta: bool = True
    ) -> Dict:
        """
        Complete blog content processing:
        1. Fix headings to comply with SEO rules
        2. Inject internal links
        3. Add CTA paragraph if needed
        
        Returns processed content and metadata
        """
        result = {
            'original_content': content,
            'content': content,
            'links_added': 0,
            'headings_fixed': False,
            'cta_added': False,
            'validation': {}
        }
        
        # Step 1: Fix headings
        if fix_headings:
            original_content = content
            content = self.fix_headings(content, primary_keyword, location)
            result['headings_fixed'] = content != original_content
        
        # Step 2: Validate headings
        result['validation'] = self.validate_headings(content, primary_keyword, location)
        
        # Step 3: Inject internal links
        content, links_added = self.inject_internal_links(
            content,
            service_pages,
            primary_keyword
        )
        result['links_added'] = links_added
        
        # Step 4: Ensure minimum links
        content, total_links = self.ensure_minimum_links(
            content,
            service_pages,
            primary_keyword
        )
        result['total_links'] = total_links
        
        # Step 5: Add CTA if enabled and we have service pages
        if add_cta and service_pages:
            cta = self.generate_cta_paragraph(service_pages, business_name, location)
            if cta:
                content += cta
                result['cta_added'] = True
        
        result['content'] = content
        return result


# Singleton instance
internal_linking_service = InternalLinkingService()
