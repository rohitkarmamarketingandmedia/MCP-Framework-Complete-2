"""
MCP Framework - AI Service
OpenAI and Anthropic API integration for content generation
"""
import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
import requests

logger = logging.getLogger(__name__)


class AIService:
    """AI content generation service"""
    
    def __init__(self):
        self._last_call_time = 0
        self._min_call_interval = 2  # seconds between calls to avoid rate limits
    
    @property
    def openai_key(self):
        """Get OpenAI API key at runtime"""
        return os.environ.get('OPENAI_API_KEY', '')
    
    @property
    def anthropic_key(self):
        """Get Anthropic API key at runtime"""
        return os.environ.get('ANTHROPIC_API_KEY', '')
    
    @property
    def default_model(self):
        """Get default AI model at runtime - use gpt-3.5-turbo for speed"""
        return os.environ.get('DEFAULT_AI_MODEL', 'gpt-3.5-turbo')
    
    def _rate_limit_delay(self):
        """Enforce minimum delay between API calls"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_call_interval:
            sleep_time = self._min_call_interval - elapsed
            logger.debug(f"Rate limit delay: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_call_time = time.time()
    
    def generate_blog_post(
        self,
        keyword: str,
        geo: str,
        industry: str,
        word_count: int = 1000,
        tone: str = 'professional',
        business_name: str = '',
        include_faq: bool = True,
        faq_count: int = 5,
        internal_links: List[Dict] = None,
        usps: List[str] = None,
        contact_name: str = None,
        phone: str = None,
        email: str = None,
        related_posts: List[Dict] = None,
        client_id: str = None
    ) -> Dict[str, Any]:
        """
        Generate 100% SEO-optimized blog post with internal linking
        
        Returns:
            {
                'title': str,
                'h1': str,
                'body': str,
                'meta_title': str,
                'meta_description': str,
                'summary': str,
                'key_takeaways': List[str],
                'h2_headings': List[str],
                'h3_headings': List[str],
                'faq_items': List[Dict],
                'faq_schema': Dict,
                'secondary_keywords': List[str],
                'cta': Dict,
                'html': str,
                'seo_score': int
            }
        """
        internal_links = internal_links or []
        usps = usps or []
        related_posts = related_posts or []
        
        logger.info(f"Generating blog: '{keyword}' for {geo}")
        
        # If client_id provided and no related_posts, try to fetch them
        if client_id and not related_posts:
            try:
                related_posts = self._get_related_posts(client_id, keyword)
                logger.info(f"Found {len(related_posts)} related posts for internal linking")
            except Exception as e:
                logger.debug(f"Could not fetch related posts: {e}")
        
        # Try to get agent config for system prompt and settings
        agent_config = None
        try:
            from app.services.agent_service import agent_service
            agent_config = agent_service.get_agent('content_writer')
        except Exception as e:
            logger.debug(f"Could not load content_writer agent: {e}")
        
        # Build the user prompt (what content to generate)
        prompt = self._build_blog_prompt(
            keyword=keyword,
            geo=geo,
            industry=industry,
            word_count=word_count,
            tone=tone,
            business_name=business_name,
            include_faq=include_faq,
            faq_count=faq_count,
            internal_links=internal_links,
            usps=usps,
            contact_name=contact_name,
            phone=phone,
            email=email,
            related_posts=related_posts
        )
        
        # Enforce rate limiting
        self._rate_limit_delay()
        
        # Model selection with appropriate token limits
        # gpt-3.5-turbo: 4096 max tokens
        # gpt-3.5-turbo-16k: 16384 max tokens  
        # gpt-4o: 4096 max tokens (output)
        primary_model = os.environ.get('BLOG_AI_MODEL', 'gpt-3.5-turbo-16k')
        fallback_model = 'gpt-3.5-turbo'
        
        # Calculate tokens based on model limits
        # Need enough tokens for 800+ word content in JSON format
        if '16k' in primary_model:
            max_allowed_tokens = 8000
            min_tokens = 4000  # Ensure we ask for enough
        elif 'gpt-4' in primary_model:
            max_allowed_tokens = 4000
            min_tokens = 3500
        else:
            max_allowed_tokens = 3900  # Safe limit for gpt-3.5-turbo
            min_tokens = 3000
        
        # Request enough tokens for the word count
        tokens_needed = int(word_count * 2) + 1000  # ~2 tokens per word + JSON overhead
        estimated_tokens = min(max_allowed_tokens, max(min_tokens, tokens_needed))
        
        logger.info(f"Blog generation: word_count={word_count}, tokens={estimated_tokens}, model={primary_model}")
        
        # Try primary model first
        response = None
        model_used = primary_model
        
        # Get agent settings or use defaults
        system_prompt = 'You are an expert SEO content writer. Always respond with valid JSON. Never use markdown code blocks.'
        if agent_config:
            system_prompt = agent_config.system_prompt
            system_prompt = system_prompt.replace('{tone}', tone)
            system_prompt = system_prompt.replace('{industry}', industry)
        
        # Try primary model
        logger.info(f"Trying primary model: {primary_model}")
        response = self._call_with_retry(
            prompt, 
            max_tokens=estimated_tokens,
            system_prompt=system_prompt,
            model=primary_model,
            temperature=0.7
        )
        
        # If primary model fails, try fallback with safe token limit
        if response.get('error'):
            logger.warning(f"Primary model {primary_model} failed: {response['error']}, trying fallback {fallback_model}")
            model_used = fallback_model
            fallback_tokens = min(3800, estimated_tokens)  # Safe limit for gpt-3.5-turbo
            response = self._call_with_retry(
                prompt, 
                max_tokens=fallback_tokens,
                system_prompt=system_prompt,
                model=fallback_model,
                temperature=0.7
            )
        
        logger.info(f"Blog generation completed with model={model_used}")
        
        if response.get('error'):
            logger.error(f"Blog generation failed: {response['error']}")
            return response
        
        # Parse the response
        result = self._parse_blog_response(response.get('content', ''))
        
        # Validate we got actual content
        if not result.get('title') and not result.get('body'):
            logger.error(f"Blog parsing returned empty content")
            return {
                'error': 'AI returned invalid response format',
                'raw_response': response.get('content', '')[:500]
            }
        
        body_content = result.get('body', '')
        
        # ===== WORD COUNT VALIDATION =====
        # Count actual words in the body content (strip HTML tags)
        import re
        text_only = re.sub(r'<[^>]+>', ' ', body_content)
        text_only = re.sub(r'\s+', ' ', text_only).strip()
        actual_word_count = len(text_only.split())
        result['actual_word_count'] = actual_word_count
        
        logger.info(f"Blog word count: requested={word_count}, actual={actual_word_count}")
        
        # Log warning if word count is low, but DON'T reject content
        # GPT-3.5 often produces shorter content - let it through
        if actual_word_count < 300:
            logger.warning(f"Blog word count very low: {actual_word_count} words")
        
        # Only reject if body is essentially empty
        if len(body_content) < 200:
            logger.error(f"Blog body too short: {len(body_content)} chars")
            return {
                'error': 'AI returned empty content. Please try again.',
                'raw_response': response.get('content', '')[:500]
            }
        
        # ===== PLACEHOLDER DETECTION =====
        # Check for placeholder text in body and FAQs
        placeholder_patterns = [
            'Question 1 about', 'Question 2 about', 'Question 3 about', 
            'Question 4 about', 'Question 5 about',
            'Answer to question 1', 'Answer to question 2', 'Answer to question 3',
            'Answer to question 4', 'Answer to question 5',
            'Answer 1', 'Answer 2', 'Answer 3', 'Answer 4', 'Answer 5',
            'Response...', 'Insight...', 'Explanation...', 'Advice...', 
            'Information...', 'Clarification...', 'CTA section...', 
            'Content...', 'Details...', 'Details here', 'Content here',
            'Full HTML content', 'WRITE', 'DO NOT put placeholder',
            '[specific', '[factor', '[qualification', '[shorter time]',
            'MANDATORY:', '[COUNT YOUR WORDS', '[60-80 word',
            'Write 100+ words', 'Write 80+ words', 'Write 40+ words',
            '40-60 word answer', 'Real specific question',
            '<FULL HTML', '<THE FULL HTML'
        ]
        
        has_placeholders = any(p.lower() in body_content.lower() for p in placeholder_patterns)
        
        # Check FAQs for placeholders
        faq_items = result.get('faq_items', [])
        for faq in faq_items:
            answer = faq.get('answer', '')
            if len(answer) < 20 or any(p.lower() in answer.lower() for p in placeholder_patterns):
                has_placeholders = True
                logger.warning(f"FAQ has placeholder or too short: {answer[:50]}") 
        
        if has_placeholders:
            logger.error("Blog contains placeholder text - AI did not generate real content")
            return {
                'error': 'AI returned placeholder content instead of real text. Please try again.',
                'raw_response': response.get('content', '')[:500]
            }
        
        # ===== POST-PROCESSING FOR SEO QUALITY =====
        actual_word_count = len(body_content.split())
        
        logger.info(f"Blog raw word count: {actual_word_count} (target: {word_count})")
        
        # Post-process: Inject internal links if not already present
        if internal_links and body_content:
            try:
                from app.services.internal_linking_service import internal_linking_service
                
                # Check how many links already in content
                existing_links = body_content.count('<a href=')
                
                if existing_links < 3:  # Need more links
                    logger.info(f"Adding internal links (current: {existing_links})")
                    body_content, links_added = internal_linking_service.inject_internal_links(
                        content=body_content,
                        service_pages=internal_links,
                        primary_keyword=keyword,
                        max_links=6
                    )
                    result['body'] = body_content
                    result['internal_links_added'] = links_added
                    logger.info(f"Injected {links_added} internal links")
                else:
                    result['internal_links_added'] = existing_links
                    logger.info(f"Content already has {existing_links} internal links")
            except Exception as e:
                logger.warning(f"Failed to inject internal links: {e}")
        
        # Post-process: Ensure H2s have location
        if geo and body_content:
            body_content = self._fix_h2_locations(body_content, geo, keyword)
            result['body'] = body_content
        
        # Ensure we have meta fields - generate if missing
        if not result.get('meta_title'):
            result['meta_title'] = f"{keyword.title()} | {business_name or geo}"[:60]
            logger.warning(f"Generated fallback meta_title: {result['meta_title']}")
        
        if not result.get('meta_description'):
            result['meta_description'] = f"Expert {keyword} services in {geo}. {business_name or 'We'} provide professional {industry} solutions. Contact us today!"[:160]
            logger.warning(f"Generated fallback meta_description")
        
        # Calculate final word count
        result['word_count'] = len(result.get('body', '').split())
        
        logger.info(f"Blog generated successfully: {result.get('title', 'no title')[:50]} ({result['word_count']} words)")
        return result
    
    def _fix_h2_locations(self, content: str, geo: str, keyword: str) -> str:
        """Ensure H2 headings contain location references"""
        import re
        
        def fix_h2(match):
            h2_content = match.group(1)
            # Check if location is already present
            if geo.lower() in h2_content.lower():
                return match.group(0)
            # Add location to H2
            # Common patterns to enhance
            h2_lower = h2_content.lower()
            if 'why' in h2_lower or 'how' in h2_lower or 'what' in h2_lower:
                return f'<h2>{h2_content} in {geo}</h2>'
            elif 'benefits' in h2_lower or 'advantages' in h2_lower:
                return f'<h2>{h2_content} for {geo} Residents</h2>'
            elif 'cost' in h2_lower or 'price' in h2_lower:
                return f'<h2>{h2_content} in the {geo} Area</h2>'
            else:
                return f'<h2>{h2_content} in {geo}</h2>'
        
        # Fix H2s that don't have location
        pattern = r'<h2>([^<]+)</h2>'
        fixed_content = re.sub(pattern, fix_h2, content)
        
        return fixed_content
    
    def generate_social_post(
        self,
        topic: str,
        platform: str,
        business_name: str,
        industry: str,
        geo: str,
        tone: str = 'friendly',
        include_hashtags: bool = True,
        hashtag_count: int = 5,
        link_url: str = ''
    ) -> Dict[str, Any]:
        """Generate social media post for specific platform using social_writer agent"""
        
        logger.info(f"Generating {platform} post: '{topic}'")
        
        platform_limits = {
            'gbp': 1500,
            'facebook': 500,
            'instagram': 2200,
            'linkedin': 700,
            'twitter': 280
        }
        
        char_limit = platform_limits.get(platform, 500)
        
        # Try to get agent config
        agent_config = None
        try:
            from app.services.agent_service import agent_service
            agent_config = agent_service.get_agent('social_writer')
        except Exception as e:
            logger.debug(f"Could not load social_writer agent: {e}")
        
        # Build user prompt
        prompt = f"""Write a {platform.upper()} post for a {industry} business called "{business_name}" in {geo}.

Topic: {topic}
Tone: {tone}
Character limit: {char_limit}
{"Include a call-to-action with link: " + link_url if link_url else ""}

Requirements:
- Engaging opening hook
- Value proposition clear
- Strong CTA
{"- Include " + str(hashtag_count) + " relevant hashtags" if include_hashtags else ""}

Return as JSON:
{{
    "text": "The complete post text with engaging copy. This must contain actual content, not be empty.",
    "hashtags": ["keyword1", "keyword2"],
    "cta": "call to action text",
    "image_alt": "suggested image alt text"
}}

CRITICAL RULES:
1. Return ONLY valid JSON, no markdown, no explanation
2. "text" MUST contain the actual post copy - never leave it empty
3. "hashtags" must be words WITHOUT the # symbol (we add it later)

Example for HVAC business:
{{
    "text": "Is your AC struggling to keep up with Florida heat? Here are 3 signs it's time for a tune-up! 🌡️ Don't wait until it breaks down.",
    "hashtags": ["HVAC", "ACRepair", "FloridaHeat", "CoolingTips"],
    "cta": "Schedule your tune-up today!",
    "image_alt": "Air conditioning unit being serviced"
}}"""

        # Enforce rate limiting
        self._rate_limit_delay()
        
        # Use agent config if available, but override for speed
        if agent_config:
            fast_model = self.default_model  # gpt-3.5-turbo
            fast_tokens = min(agent_config.max_tokens, 500)  # Cap at 500 for social
            
            response = self._call_with_retry(
                prompt, 
                max_tokens=fast_tokens,
                system_prompt=agent_config.system_prompt,
                model=fast_model,
                temperature=agent_config.temperature
            )
            logger.info(f"Used social_writer agent config (model={fast_model})")
        else:
            response = self._call_with_retry(prompt, max_tokens=500)
        
        if response.get('error'):
            logger.error(f"Social generation failed: {response['error']}")
            return response
        
        try:
            content = response.get('content', '{}')
            # Clean markdown code blocks if present
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
            
            # Try to find JSON object
            content = content.strip()
            if not content.startswith('{'):
                # Try to extract JSON from response
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    content = content[start:end+1]
            
            result = json.loads(content)
            
            # Strip # from hashtags if AI included them
            if 'hashtags' in result and isinstance(result['hashtags'], list):
                result['hashtags'] = [h.lstrip('#') for h in result['hashtags']]
            
            logger.info(f"Social post generated: {len(result.get('text', ''))} chars")
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Social JSON parse failed: {e}, using raw content")
            # Generate a usable fallback - DON'T add # prefix since render adds it
            raw_text = response.get('content', topic)
            return {
                'text': raw_text[:char_limit] if len(raw_text) > char_limit else raw_text,
                'hashtags': [industry.replace(' ', ''), geo.split(',')[0].replace(' ', ''), business_name.replace(' ', '')][:hashtag_count],
                'cta': f"Contact {business_name} today!",
                'image_alt': f"{topic} - {business_name}"
            }
    
    def generate_social_kit(
        self,
        topic: str,
        business_name: str,
        industry: str,
        geo: str,
        tone: str = 'friendly',
        link_url: str = '',
        platforms: List[str] = None
    ) -> Dict[str, Dict]:
        """Generate posts for multiple platforms at once"""
        platforms = platforms or ['gbp', 'facebook', 'instagram', 'linkedin']
        
        logger.info(f"Generating social kit for {len(platforms)} platforms")
        
        kit = {}
        for platform in platforms:
            result = self.generate_social_post(
                topic=topic,
                platform=platform,
                business_name=business_name,
                industry=industry,
                geo=geo,
                tone=tone,
                link_url=link_url
            )
            kit[platform] = result
            
            # Check if we should stop due to errors
            if result.get('error') and 'rate' in str(result['error']).lower():
                logger.warning("Rate limit hit, stopping social kit generation")
                break
        
        return kit
    
    def _build_blog_prompt(
        self,
        keyword: str,
        geo: str,
        industry: str,
        word_count: int,
        tone: str,
        business_name: str,
        include_faq: bool,
        faq_count: int,
        internal_links: List[Dict],
        usps: List[str],
        contact_name: str = None,
        phone: str = None,
        email: str = None,
        related_posts: List[Dict] = None
    ) -> str:
        """Build the blog generation prompt - 100% SEO SCORE GUARANTEED"""
        
        from datetime import datetime
        current_year = datetime.utcnow().year
        
        # Parse geo into city/state
        geo_parts = geo.split(',') if geo else ['', '']
        city = geo_parts[0].strip() if len(geo_parts) > 0 else geo
        state = geo_parts[1].strip() if len(geo_parts) > 1 else ''
        location = f"{city}, {state}" if state else city
        
        # Build MANDATORY internal links section - these MUST appear in content
        internal_links_html = ""
        link_instructions = ""
        if internal_links and len(internal_links) > 0:
            internal_links_html = "\n=== MANDATORY INTERNAL LINKS (MUST INCLUDE ALL) ===\n"
            internal_links_html += "You MUST include these EXACT links in your body content using <a href> tags:\n\n"
            for i, link in enumerate(internal_links[:6], 1):
                url = link.get('url', '')
                kw = link.get('keyword', link.get('title', ''))
                if url and kw:
                    internal_links_html += f'{i}. <a href="{url}">{kw}</a>\n'
            internal_links_html += "\nINSTRUCTION: Copy these EXACT <a href> tags and place them naturally in your body paragraphs.\n"
            link_instructions = f"✓ Include ALL {len(internal_links[:6])} internal links listed above"
        
        # Build related posts section for category interlinking
        related_posts_html = ""
        if related_posts and len(related_posts) > 0:
            related_posts_html = "\n=== RELATED POSTS TO LINK (Same Category) ===\n"
            related_posts_html += "Also include links to these related posts from the same category:\n\n"
            for i, post in enumerate(related_posts[:4], 1):
                url = post.get('url', post.get('published_url', ''))
                title = post.get('title', '')
                if url and title:
                    related_posts_html += f'{i}. <a href="{url}">{title}</a>\n'
        
        # CTA contact logic
        cta_name = contact_name if contact_name else business_name
        contact_methods = []
        if phone:
            contact_methods.append(f"call us at {phone}")
        if email:
            contact_methods.append(f"email us at {email}")
        contact_str = " or ".join(contact_methods) if contact_methods else "contact us today"
        
        # Build USP bullet points
        usp_text = ""
        if usps and len(usps) > 0:
            usp_text = ""
        if usps and len(usps) > 0:
            usp_text = "\nHighlight these unique benefits: " + ", ".join(usps[:3])

        # Build internal links for prompt
        links_text = ""
        if internal_links:
            links_text = "\nInclude these links naturally in the content:\n"
            for link in internal_links[:5]:
                url = link.get('url', '')
                kw = link.get('keyword', link.get('title', ''))
                if url and kw:
                    links_text += f'- <a href="{url}">{kw}</a>\n'

        return f"""Write a comprehensive, helpful blog post about {keyword} for homeowners and businesses in {location}.

BUSINESS INFO:
- Company: {business_name}
- Contact: {cta_name}
- How to reach: {contact_str}
{usp_text}
{links_text}

WRITING REQUIREMENTS:
1. Write like a knowledgeable local expert, not a generic AI
2. Include specific details relevant to {location} (climate, local factors, etc.)
3. Use natural, conversational language
4. Every paragraph must have real, useful information
5. NO placeholder text like "Answer to question 1" - write REAL answers

CONTENT TO WRITE (create actual helpful content for each):

SECTION 1 - INTRODUCTION:
Write 2-3 paragraphs (100+ words) introducing {keyword} and why it matters for {location} residents. Mention local climate considerations.

SECTION 2 - UNDERSTANDING {keyword.upper()}:
Write 2 paragraphs (100+ words) explaining what {keyword} involves, the different types/options available, and how it benefits property owners.

SECTION 3 - KEY BENEFITS:
Write an intro paragraph, then list 5 specific benefits with detailed explanations (not just bullet points - each benefit needs 2-3 sentences explaining WHY it matters).

SECTION 4 - THE PROCESS:
Explain step-by-step what customers can expect when they hire a professional for {keyword}. Include timeline expectations.

SECTION 5 - COST CONSIDERATIONS:
Discuss factors that affect pricing for {keyword} in {location}. Be helpful without giving specific prices.

SECTION 6 - CHOOSING THE RIGHT PROVIDER:
What should {location} residents look for? Include a call-to-action for {business_name}.

SECTION 7 - FIVE REAL FAQs:
Write 5 SPECIFIC questions that real customers ask, with DETAILED answers (40-60 words each):

FAQ 1: "How often should [specific maintenance question for {keyword}]?"
- Write a real, helpful answer with specific timeframes and recommendations

FAQ 2: "What are the signs that I need [specific service related to {keyword}]?"  
- List actual warning signs customers should watch for

FAQ 3: "How much does {keyword} typically cost in {location}?"
- Discuss price ranges and factors without exact numbers

FAQ 4: "How long does [the {keyword} process] take?"
- Give realistic timeframes for different scenarios

FAQ 5: "Should I attempt DIY or hire a professional for {keyword}?"
- Explain the risks of DIY and benefits of professional service

SECTION 8 - CONCLUSION:
Summarize key points and include strong call-to-action for {business_name}.

OUTPUT FORMAT - Return valid JSON only (no markdown):
{{
    "title": "{keyword} Services in {location} - Expert Guide | {business_name}",
    "meta_title": "{keyword} in {location} | Trusted Local Experts | {business_name}",
    "meta_description": "Need {keyword} in {location}? Learn about costs, benefits, and how to choose the right provider. Contact {business_name} for expert service.",
    "body": "<FULL HTML CONTENT - Must be 800+ words of REAL, HELPFUL content. Use <h2>, <p>, <ul>, <li>, <strong> tags. NO PLACEHOLDER TEXT.>",
    "h2_headings": ["Understanding {keyword}", "Key Benefits", "The Process", "Cost Considerations", "Choosing a Provider", "Frequently Asked Questions", "Ready to Get Started"],
    "faq_items": [
        {{"question": "Real specific question 1?", "answer": "Detailed 40-60 word answer with actual helpful information"}},
        {{"question": "Real specific question 2?", "answer": "Detailed 40-60 word answer with actual helpful information"}},
        {{"question": "Real specific question 3?", "answer": "Detailed 40-60 word answer with actual helpful information"}},
        {{"question": "Real specific question 4?", "answer": "Detailed 40-60 word answer with actual helpful information"}},
        {{"question": "Real specific question 5?", "answer": "Detailed 40-60 word answer with actual helpful information"}}
    ],
    "faq_schema": {{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}},
    "cta": {{"contact_name": "{cta_name}", "company_name": "{business_name}", "phone": "{phone or ''}", "email": "{email or ''}"}}
}}

CRITICAL RULES:
- DO NOT use placeholder text like "Question 1 about..." or "Answer to question..."
- DO NOT copy the template structure literally
- WRITE real, specific, helpful content that would actually help someone researching {keyword}
- Each FAQ answer must be a complete, informative response (40-60 words)
- Total content must be 800+ words of REAL information"""
    
    def _get_related_posts(self, client_id: str, current_keyword: str, limit: int = 4) -> List[Dict]:
        """
        Fetch related blog posts from the same client for internal linking.
        Returns posts that are published and have URLs.
        """
        try:
            from app.models.db_models import DBBlogPost
            
            # Get published posts for this client (excluding current keyword)
            posts = DBBlogPost.query.filter(
                DBBlogPost.client_id == client_id,
                DBBlogPost.status == 'published',
                DBBlogPost.published_url.isnot(None)
            ).order_by(DBBlogPost.published_at.desc()).limit(limit + 5).all()
            
            related = []
            for post in posts:
                # Skip if same keyword
                if post.primary_keyword and post.primary_keyword.lower() == current_keyword.lower():
                    continue
                
                if post.published_url:
                    related.append({
                        'title': post.title,
                        'url': post.published_url,
                        'keyword': post.primary_keyword
                    })
                
                if len(related) >= limit:
                    break
            
            return related
            
        except Exception as e:
            logger.debug(f"Error fetching related posts: {e}")
            return []
    
    def _parse_blog_response(self, content: str) -> Dict[str, Any]:
        """Parse AI response into structured blog data"""
        try:
            original_content = content
            
            # Clean markdown if present
            if '```' in content:
                parts = content.split('```')
                for part in parts:
                    part = part.strip()
                    if part.startswith('json'):
                        content = part[4:].strip()
                        break
                    elif part.startswith('{'):
                        content = part
                        break
            
            # Try to find JSON object if not starting with {
            content = content.strip()
            if not content.startswith('{'):
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1 and end > start:
                    content = content[start:end+1]
            
            data = json.loads(content)
            
            # Validate body content - make sure it's not accidentally containing JSON
            body_content = data.get('body', '')
            if body_content.strip().startswith('{') or '"title":' in body_content:
                logger.warning("Body appears to contain JSON - parsing may have failed")
                # Try to extract just the text content
                body_content = re.sub(r'[{}\[\]"]', '', body_content)
                body_content = re.sub(r'(title|h1|meta_title|meta_description|body|h2_headings|h3_headings|faq_items|secondary_keywords|word_count)\s*:', '', body_content)
                data['body'] = f"<p>{body_content[:500]}...</p>"
            
            # Generate HTML if not present
            if 'html' not in data and 'body' in data:
                data['html'] = data['body']
            
            logger.debug(f"Parsed blog: title='{data.get('title', '')[:30]}', body_len={len(data.get('body', ''))}")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Failed content: {content[:500]}")
            
            # Try to extract body content from the failed JSON
            body_match = re.search(r'"body"\s*:\s*"(.*?)(?:"\s*,\s*"h2_headings|"\s*,\s*"faq_items|"\s*})', original_content, re.DOTALL)
            if body_match:
                extracted_body = body_match.group(1)
                # Unescape the JSON string
                extracted_body = extracted_body.replace('\\"', '"').replace('\\n', '\n')
                logger.info(f"Extracted body from failed JSON: {len(extracted_body)} chars")
            else:
                # Fallback - try to get any paragraph content
                p_match = re.search(r'<p>.*?</p>', original_content, re.DOTALL)
                if p_match:
                    extracted_body = original_content[p_match.start():]
                else:
                    extracted_body = f"<p>Content generation encountered an error. Please try again.</p>"
            
            # Try to extract title
            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', original_content)
            extracted_title = title_match.group(1) if title_match else ''
            
            # Try to extract meta
            meta_title_match = re.search(r'"meta_title"\s*:\s*"([^"]+)"', original_content)
            meta_desc_match = re.search(r'"meta_description"\s*:\s*"([^"]+)"', original_content)
            
            return {
                'title': extracted_title,
                'h1': extracted_title,
                'body': extracted_body,
                'meta_title': meta_title_match.group(1) if meta_title_match else '',
                'meta_description': meta_desc_match.group(1) if meta_desc_match else '',
                'summary': '',
                'key_takeaways': [],
                'h2_headings': [],
                'h3_headings': [],
                'faq_items': [],
                'secondary_keywords': [],
                'cta': {},
                'html': extracted_body,
                'parse_error': str(e)
            }
    
    def _call_with_retry(self, prompt: str, max_tokens: int = 2000, max_retries: int = 3, system_prompt: str = None, model: str = None, temperature: float = 0.7) -> Dict[str, Any]:
        """Call OpenAI with retry logic for rate limits"""
        
        for attempt in range(max_retries):
            response = self._call_openai(prompt, max_tokens, system_prompt=system_prompt, model=model, temperature=temperature)
            
            if not response.get('error'):
                return response
            
            error_msg = str(response.get('error', '')).lower()
            
            # Check if it's a rate limit error
            if 'rate' in error_msg or '429' in error_msg:
                wait_time = (attempt + 1) * 10  # 10s, 20s, 30s
                logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                continue
            
            # Check if quota exceeded
            if 'quota' in error_msg or 'insufficient' in error_msg:
                logger.error("OpenAI quota exceeded - need to add credits")
                return response
            
            # Other error, don't retry
            return response
        
        return {'error': 'Max retries exceeded due to rate limits'}
    
    def _call_openai(self, prompt: str, max_tokens: int = 2000, system_prompt: str = None, model: str = None, temperature: float = 0.7) -> Dict[str, Any]:
        """Call OpenAI API"""
        if not self.openai_key:
            return {'error': 'OpenAI API key not configured'}
        
        # Default system prompt if not provided
        if system_prompt is None:
            system_prompt = 'You are an expert SEO content writer. Always respond with valid JSON when requested. Never wrap JSON in markdown code blocks.'
        
        try:
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.openai_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': model or self.default_model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': prompt}
                    ],
                    'max_tokens': max_tokens,
                    'temperature': temperature
                },
                timeout=180  # 3 minutes for long content generation
            )
            
            if response.status_code == 429:
                return {'error': 'Rate limit exceeded (429)'}
            
            response.raise_for_status()
            data = response.json()
            
            return {
                'content': data['choices'][0]['message']['content'],
                'usage': data.get('usage', {})
            }
            
        except requests.exceptions.Timeout:
            return {'error': 'Request timed out after 180 seconds. Try a shorter word count or try again.'}
        except requests.RequestException as e:
            error_detail = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json().get('error', {}).get('message', str(e))
                except Exception as e:
                    error_detail = e.response.text[:200]
            return {'error': f'OpenAI API error: {error_detail}'}
    
    def _call_anthropic(self, prompt: str, max_tokens: int = 2000, system_prompt: str = None, model: str = None, temperature: float = 0.7) -> Dict[str, Any]:
        """Call Anthropic Claude API (fallback)"""
        if not self.anthropic_key:
            return {'error': 'Anthropic API key not configured'}
        
        try:
            payload = {
                'model': model or 'claude-3-sonnet-20240229',
                'max_tokens': max_tokens,
                'messages': [
                    {'role': 'user', 'content': prompt}
                ]
            }
            
            # Add system prompt if provided
            if system_prompt:
                payload['system'] = system_prompt
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': self.anthropic_key,
                    'Content-Type': 'application/json',
                    'anthropic-version': '2023-06-01'
                },
                json=payload,
                timeout=90
            )
            
            response.raise_for_status()
            data = response.json()
            
            return {
                'content': data['content'][0]['text'],
                'usage': data.get('usage', {})
            }
            
        except requests.RequestException as e:
            return {'error': f'Anthropic API error: {str(e)}'}
    
    def generate_with_agent(
        self,
        agent_name: str,
        user_input: str,
        variables: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Generate content using a configured agent
        
        Args:
            agent_name: Name of the agent to use (e.g., 'content_writer', 'review_responder')
            user_input: The user prompt/input
            variables: Variables to substitute in the system prompt
            
        Returns:
            {content: str, usage: dict} or {error: str}
        """
        from app.services.agent_service import agent_service
        
        agent = agent_service.get_agent(agent_name)
        if not agent:
            logger.warning(f"Agent '{agent_name}' not found, using default behavior")
            return self._call_openai(user_input, max_tokens=1000)
        
        # Get system prompt with variable substitution
        system_prompt = agent.system_prompt
        if variables:
            for key, value in variables.items():
                system_prompt = system_prompt.replace(f'{{{key}}}', str(value))
        
        # Override model for speed on Render free tier
        fast_model = self.default_model  # gpt-3.5-turbo
        fast_tokens = min(agent.max_tokens, 1000)  # Cap at 1000
        
        logger.info(f"Using agent '{agent_name}' with model {fast_model} (override)")
        
        # Always use OpenAI with fast model
        return self._call_openai(
            prompt=user_input,
            max_tokens=fast_tokens,
            system_prompt=system_prompt,
            model=fast_model,
            temperature=agent.temperature
        )
    
    def generate_raw(self, prompt: str, max_tokens: int = 2000) -> str:
        """Generate raw text response (for simple prompts)"""
        self._rate_limit_delay()
        result = self._call_openai(prompt, max_tokens)
        return result.get('content', '')
    
    def generate_raw_with_agent(
        self,
        agent_name: str,
        user_input: str,
        variables: Dict[str, str] = None
    ) -> str:
        """Generate raw text using an agent (convenience method)"""
        self._rate_limit_delay()
        result = self.generate_with_agent(agent_name, user_input, variables)
        return result.get('content', '')

# Singleton instance
ai_service = AIService()
