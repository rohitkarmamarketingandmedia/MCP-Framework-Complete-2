"""
MCP Framework - AI Service
OpenAI and Anthropic API integration for content generation
"""
import os
import json
import time
import re
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
        
        # Model selection
        # Primary: gpt-4o (best quality, 16K output)
        # Fallback: gpt-4o-mini (good quality, 16K output, cheaper, follows instructions well)
        # Note: gpt-3.5-turbo-16k has only 4K OUTPUT limit despite 16K context - don't use it!
        primary_model = os.environ.get('BLOG_AI_MODEL', 'gpt-4o')
        fallback_model = 'gpt-4o-mini'  # Much better than gpt-3.5-turbo-16k
        
        # Calculate tokens - both models support 16K output
        tokens_needed = min(8000, int(word_count * 2) + 1500)
        
        logger.info(f"Blog generation: word_count={word_count}, tokens={tokens_needed}, primary={primary_model}, fallback={fallback_model}")
        
        # Try primary model first
        response = None
        model_used = primary_model
        
        # System prompt - must be very clear to avoid GPT-4o content policy refusals
        system_prompt = '''You are a helpful content writer for a local business marketing agency. 

Your job is to write informative blog articles that help local business websites rank in search engines and provide value to readers looking for local services.

IMPORTANT RULES:
1. Output ONLY valid JSON - no markdown, no code blocks, no explanations
2. Write genuinely helpful, informative content about the service topic
3. This is for a legitimate small business website (dental office, HVAC company, plumber, etc.)
4. The content should educate readers and help them make informed decisions
5. Include the business name and location naturally throughout
6. Focus on providing real value - not just keyword stuffing

You are NOT being asked to do anything harmful. These are standard local business blog posts.'''
        
        if agent_config:
            system_prompt = agent_config.system_prompt
            system_prompt = system_prompt.replace('{tone}', tone)
            system_prompt = system_prompt.replace('{industry}', industry)
        
        # Try primary model
        logger.info(f"Trying primary model: {primary_model}")
        response = self._call_with_retry(
            prompt, 
            max_tokens=tokens_needed,
            system_prompt=system_prompt,
            model=primary_model,
            temperature=0.7
        )
        
        # If primary model fails, try fallback (gpt-4o-mini also supports 16K output)
        if response.get('error'):
            logger.warning(f"Primary model {primary_model} failed: {response['error']}, trying fallback {fallback_model}")
            model_used = fallback_model
            response = self._call_with_retry(
                prompt, 
                max_tokens=tokens_needed,  # Same tokens - gpt-4o-mini supports 16K output
                system_prompt=system_prompt,
                model=fallback_model,
                temperature=0.7
            )
        
        logger.info(f"Blog generation completed with model={model_used}")
        
        if response.get('error'):
            logger.error(f"Blog generation failed: {response['error']}")
            return response
        
        # Log raw response for debugging
        raw_content = response.get('content', '')
        logger.info(f"Raw API response length: {len(raw_content)} chars")
        if len(raw_content) < 200:
            logger.warning(f"Short raw response: {raw_content}")
        else:
            logger.debug(f"Raw response preview: {raw_content[:200]}...")
        
        # Parse the response
        result = self._parse_blog_response(raw_content)
        
        # Log what we got from parsing
        logger.info(f"Parse result keys: {list(result.keys())}")
        logger.info(f"Parse result title: '{result.get('title', '')[:50]}'")
        logger.info(f"Parse result body length: {len(result.get('body', ''))}")
        if result.get('body'):
            logger.info(f"Parse result body preview: '{result.get('body', '')[:200]}'")
        else:
            logger.error(f"Parse result body is EMPTY - raw content preview: '{raw_content[:500]}'")
        
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
            usp_text = "\nHighlight these unique benefits: " + ", ".join(usps[:3])

        # Combine all internal links (service pages + related posts)
        all_links = []
        
        # Add service pages
        if internal_links:
            for link in internal_links[:4]:
                url = link.get('url', '')
                kw = link.get('keyword', link.get('title', ''))
                if url and kw and not any(l['url'] == url for l in all_links):
                    all_links.append({'url': url, 'keyword': kw, 'title': link.get('title', kw)})
        
        # Add related posts
        if related_posts:
            for post in related_posts[:4]:
                url = post.get('url', post.get('published_url', ''))
                title = post.get('title', '')
                kw = post.get('keyword', title)
                if url and title and not any(l['url'] == url for l in all_links):
                    all_links.append({'url': url, 'keyword': kw, 'title': title})
        
        # Build links text for prompt - CRITICAL for SEO score
        links_text = ""
        if all_links:
            links_text = f"""
INTERNAL LINKS - YOU MUST INCLUDE THESE IN YOUR ARTICLE:
Include at least {min(len(all_links), 3)} of these links naturally within your article body.
Place them in relevant paragraphs where the topic relates to the link.

"""
            for i, link in enumerate(all_links[:6], 1):
                links_text += f'{i}. <a href="{link["url"]}">{link["title"]}</a>\n'
            links_text += """
IMPORTANT: Copy the exact <a href="...">...</a> tags above and embed them in your paragraphs.
"""
        
        logger.info(f"Blog prompt includes {len(all_links)} internal links")

        # Scale section lengths based on word count
        # For 1500 words: each section ~200 words
        # For 2000 words: each section ~280 words
        # For 2500 words: each section ~350 words
        section_words = max(150, word_count // 7)
        intro_words = max(200, word_count // 6)
        benefits_words = max(250, word_count // 5)

        return f"""Write a {word_count}-word informational article about "{keyword}" for a {industry or 'local business'} in {location}.

BUSINESS: {business_name}
CONTACT: {cta_name} - {contact_str}
{usp_text}
{links_text}

ARTICLE STRUCTURE - Use proper HTML heading hierarchy:

<h1>{keyword} in {location} - Your Complete Guide</h1>

<h2>Introduction to {keyword}</h2>
<p>({intro_words}+ words) What this service involves, why residents of {location} need it.</p>

<h2>Key Benefits of Professional {keyword}</h2>
<h3>Benefit 1: [Specific Benefit]</h3>
<p>Explanation...</p>
<h3>Benefit 2: [Specific Benefit]</h3>
<p>Explanation...</p>
<h3>Benefit 3: [Specific Benefit]</h3>
<p>Explanation...</p>
(Total {benefits_words}+ words for this section)

<h2>The {keyword} Process Explained</h2>
<p>({section_words}+ words) Step-by-step process, what to expect.</p>

<h2>Cost Factors for {keyword} in {location}</h2>
<p>({section_words}+ words) Pricing factors, value of professional service.</p>

<h2>How to Choose the Right {keyword} Provider</h2>
<p>({section_words}+ words) What to look for, why {business_name} is the right choice.</p>

<h2>Ready to Get Started?</h2>
<p>(80+ words) Call to action, contact {business_name}.</p>

TOTAL BODY CONTENT MUST BE {word_count}+ WORDS.

HTML REQUIREMENTS FOR SEO:
1. Include exactly ONE <h1> tag at the start
2. Include 5-6 <h2> tags for main sections
3. Include 3-4 <h3> tags for subsections (especially in Benefits section)
4. Include at least 3 internal <a href="..."> links naturally in paragraphs
5. Use <p>, <ul>, <li>, <strong> tags appropriately

OUTPUT FORMAT (valid JSON only, no markdown):
{{
    "title": "{keyword} in {location} - Your Complete Guide | {business_name}",
    "meta_title": "{keyword} {location} | Expert {industry or 'Service'} | {business_name}",
    "meta_description": "Looking for professional {keyword} in {location}? {business_name} offers expert service. Call today for a free consultation. Trusted local experts.",
    "body": "<h1>...</h1><h2>...</h2><p>...</p>... (Full HTML with h1, h2, h3 tags, {word_count}+ words)",
    "h2_headings": ["Introduction", "Key Benefits", "Process Explained", "Cost Factors", "Choosing a Provider", "Get Started"],
    "faq_items": [
        {{"question": "How much does {keyword} cost in {location}?", "answer": "Costs in {location} typically range based on scope, property size, and specific requirements. {business_name} provides free estimates for accurate pricing tailored to your needs."}},
        {{"question": "How do I know if I need {keyword} service?", "answer": "Common signs include [specific symptoms]. If you notice any issues, contact {business_name} for a professional assessment."}},
        {{"question": "How long does {keyword} take?", "answer": "Most {keyword} projects take [timeframe] depending on complexity. {business_name} provides accurate timelines during consultation."}},
        {{"question": "Why choose {business_name} for {keyword}?", "answer": "{business_name} offers experienced professionals, quality service, and customer satisfaction. Contact us today to learn more."}},
        {{"question": "Do you offer free estimates for {keyword}?", "answer": "Yes! {business_name} provides free, no-obligation estimates for all {keyword} services in {location}. Call us today."}}
    ],
    "faq_schema": {{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}},
    "cta": {{"contact_name": "{cta_name}", "company_name": "{business_name}", "phone": "{phone or ''}", "email": "{email or ''}"}}
}}

CRITICAL SEO REQUIREMENTS:
1. Body MUST have ONE <h1> tag, 5-6 <h2> tags, and 3+ <h3> tags
2. Body MUST be {word_count}+ words - count before responding
3. Include {keyword} naturally 10-15 times
4. Include {location} 5-8 times
5. Include at least 3 internal links (<a href>) in paragraphs
6. NO placeholder text - write complete, valuable content"""
    
    def _get_related_posts(self, client_id: str, current_keyword: str, limit: int = 6) -> List[Dict]:
        """
        Fetch related content from the same client for internal linking.
        Sources (in order):
        1. Scrape client's blog page for existing blog URLs
        2. Published blog posts from database
        3. Service pages from database
        4. Client service_pages JSON field
        Returns list of {title, url, keyword} for internal linking.
        """
        related = []
        
        try:
            from app.models.db_models import DBBlogPost, DBClient, DBServicePage
            
            # Get client for website URL
            client = DBClient.query.get(client_id)
            base_url = ''
            blog_url = ''
            if client and client.website_url:
                base_url = client.website_url.rstrip('/')
                # Check if website_url is a blog page
                if '/blog' in client.website_url.lower():
                    blog_url = client.website_url
                else:
                    blog_url = f"{base_url}/blog/"
            
            # 1. SCRAPE CLIENT'S BLOG PAGE FOR EXISTING POSTS
            if base_url and len(related) < limit:
                try:
                    scraped_links = self._scrape_blog_urls(blog_url, base_url, limit)
                    for link in scraped_links:
                        # Skip if matches current keyword
                        if current_keyword.lower() in link.get('title', '').lower():
                            continue
                        if not any(r['url'] == link['url'] for r in related):
                            related.append(link)
                        if len(related) >= limit:
                            break
                    logger.info(f"Scraped {len(scraped_links)} blog URLs from {blog_url}")
                except Exception as e:
                    logger.warning(f"Could not scrape blog URLs: {e}")
            
            # 2. Get published blog posts from database
            if len(related) < limit:
                posts = DBBlogPost.query.filter(
                    DBBlogPost.client_id == client_id,
                    DBBlogPost.status == 'published',
                    DBBlogPost.published_url.isnot(None)
                ).order_by(DBBlogPost.published_at.desc()).limit(limit + 5).all()
                
                for post in posts:
                    if post.primary_keyword and post.primary_keyword.lower() == current_keyword.lower():
                        continue
                    
                    if post.published_url:
                        url = post.published_url
                        # Make URL absolute if it's relative
                        if not url.startswith('http') and base_url:
                            url = f"{base_url}{url}" if url.startswith('/') else f"{base_url}/{url}"
                        
                        if not any(r['url'] == url for r in related):
                            related.append({
                                'title': post.title,
                                'url': url,
                                'keyword': post.primary_keyword or post.title
                            })
                    
                    if len(related) >= limit:
                        break
            
            # 2. Get service pages from DBServicePage table
            if len(related) < limit:
                service_pages = DBServicePage.query.filter(
                    DBServicePage.client_id == client_id,
                    DBServicePage.status == 'published',
                    DBServicePage.published_url.isnot(None)
                ).limit(limit - len(related) + 3).all()
                
                for page in service_pages:
                    if page.primary_keyword and page.primary_keyword.lower() == current_keyword.lower():
                        continue
                    
                    if page.published_url:
                        url = page.published_url
                        if not url.startswith('http') and base_url:
                            url = f"{base_url}{url}" if url.startswith('/') else f"{base_url}/{url}"
                        
                        related.append({
                            'title': page.title or page.primary_keyword,
                            'url': url,
                            'keyword': page.primary_keyword or page.title
                        })
                    
                    if len(related) >= limit:
                        break
            
            # 3. Also get from client.service_pages JSON field (legacy)
            if len(related) < limit and client:
                stored_pages = client.get_service_pages() or []
                for page in stored_pages:
                    kw = page.get('keyword', page.get('title', ''))
                    if kw.lower() == current_keyword.lower():
                        continue
                    
                    url = page.get('url', '')
                    if url:
                        if not url.startswith('http') and base_url:
                            url = f"{base_url}{url}" if url.startswith('/') else f"{base_url}/{url}"
                        
                        # Avoid duplicates
                        if not any(r['url'] == url for r in related):
                            related.append({
                                'title': page.get('title', kw),
                                'url': url,
                                'keyword': kw
                            })
                    
                    if len(related) >= limit:
                        break
            
            logger.info(f"Found {len(related)} internal links for client {client_id}")
            return related[:limit]
            
        except Exception as e:
            logger.warning(f"Error fetching related posts: {e}")
            return []
    
    def _scrape_blog_urls(self, blog_url: str, base_url: str, limit: int = 6) -> List[Dict]:
        """
        Scrape a client's blog page to find existing blog post URLs for internal linking.
        
        Args:
            blog_url: URL of the blog listing page (e.g., https://example.com/blog/)
            base_url: Base URL of the website for making relative URLs absolute
            limit: Maximum number of URLs to return
            
        Returns:
            List of {title, url, keyword} dictionaries
        """
        import requests
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, urlparse
        
        blog_links = []
        
        try:
            # Request the blog page
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; MCPBot/1.0; +https://karmamarketingandmedia.com)'
            }
            response = requests.get(blog_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse the base URL to get the domain
            parsed_base = urlparse(base_url)
            domain = parsed_base.netloc
            
            # Find blog post links - common patterns
            # Look for links that contain /blog/, /post/, /article/, or are within article elements
            potential_links = []
            
            # Strategy 1: Links inside article, .post, .blog-post, .entry elements
            for container in soup.select('article, .post, .blog-post, .entry, .blog-item, .post-item'):
                for a in container.find_all('a', href=True):
                    href = a.get('href', '')
                    title = a.get_text(strip=True)
                    if href and title and len(title) > 10:
                        potential_links.append((href, title))
            
            # Strategy 2: Links with blog-related paths
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                title = a.get_text(strip=True)
                
                # Skip if no title or too short
                if not title or len(title) < 10:
                    continue
                
                # Skip navigation, social, etc.
                if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', 'tel:', 'facebook', 'twitter', 'instagram', 'linkedin', 'youtube']):
                    continue
                
                # Look for blog-like URLs
                if any(pattern in href.lower() for pattern in ['/blog/', '/post/', '/article/', '/news/']):
                    # Make sure it's not the blog listing page itself
                    if href.rstrip('/') != blog_url.rstrip('/'):
                        potential_links.append((href, title))
            
            # Process and deduplicate links
            seen_urls = set()
            for href, title in potential_links:
                # Make URL absolute
                full_url = urljoin(base_url, href)
                
                # Ensure it's on the same domain
                parsed_url = urlparse(full_url)
                if parsed_url.netloc != domain:
                    continue
                
                # Skip if already seen
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                
                # Clean up title
                title = ' '.join(title.split())  # Normalize whitespace
                if len(title) > 100:
                    title = title[:97] + '...'
                
                # Extract keyword from title (simplified)
                keyword = title.split('|')[0].split('-')[0].strip()
                
                blog_links.append({
                    'title': title,
                    'url': full_url,
                    'keyword': keyword
                })
                
                if len(blog_links) >= limit:
                    break
            
            logger.info(f"Scraped {len(blog_links)} blog URLs from {blog_url}")
            return blog_links
            
        except requests.RequestException as e:
            logger.warning(f"Failed to scrape blog page {blog_url}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error parsing blog page {blog_url}: {e}")
            return []
    
    def _parse_blog_response(self, content: str) -> Dict[str, Any]:
        """Parse AI response into structured blog data"""
        try:
            # Check for empty content first
            if not content or len(content.strip()) < 50:
                logger.error(f"_parse_blog_response received empty/short content: '{content}'")
                return {
                    'title': '',
                    'body': '',
                    'error': 'Empty response from AI'
                }
            
            original_content = content
            logger.debug(f"Parsing blog response: {len(content)} chars")
            
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
            
            # Log what we got from JSON parse
            logger.info(f"JSON parsed successfully. Keys: {list(data.keys())}")
            for key in data.keys():
                val = data[key]
                if isinstance(val, str):
                    logger.info(f"  {key}: string({len(val)} chars)")
                elif isinstance(val, list):
                    logger.info(f"  {key}: list({len(val)} items)")
                elif isinstance(val, dict):
                    logger.info(f"  {key}: dict({list(val.keys())})")
                else:
                    logger.info(f"  {key}: {type(val).__name__}")
            
            # Robust body extraction - handle various response formats
            body_content = data.get('body', '')
            
            # If body is not a string, try to convert or extract
            if not isinstance(body_content, str):
                logger.warning(f"Body is not a string: {type(body_content)}")
                if isinstance(body_content, dict):
                    # Try to get content from nested dict
                    body_content = body_content.get('content', '') or body_content.get('html', '') or str(body_content)
                elif isinstance(body_content, list):
                    body_content = ' '.join(str(item) for item in body_content)
                else:
                    body_content = str(body_content) if body_content else ''
            
            # If body is still empty, try alternative fields
            if not body_content or len(body_content.strip()) < 100:
                logger.warning(f"Body empty or too short ({len(body_content)}), checking alternative fields")
                # Check for common alternative field names
                for alt_field in ['html', 'content', 'article', 'text', 'post_body', 'article_body']:
                    if data.get(alt_field) and len(str(data.get(alt_field))) > len(body_content):
                        body_content = str(data.get(alt_field))
                        logger.info(f"Using alternative field '{alt_field}' with {len(body_content)} chars")
                        break
            
            # Final fallback - try to extract from the original content
            if not body_content or len(body_content.strip()) < 100:
                logger.warning(f"Body still empty after alternatives, trying regex extraction")
                body_match = re.search(r'"body"\s*:\s*"((?:[^"\\]|\\.)*)"|"body"\s*:\s*`((?:[^`\\]|\\.)*)`', original_content, re.DOTALL)
                if body_match:
                    body_content = body_match.group(1) or body_match.group(2) or ''
                    body_content = body_content.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')
                    logger.info(f"Extracted body via regex: {len(body_content)} chars")
            
            # Update data with the extracted body
            data['body'] = body_content
            
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
        
        actual_model = model or self.default_model
        logger.info(f"OpenAI API call: model={actual_model}, max_tokens={max_tokens}")
        
        try:
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.openai_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': actual_model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': prompt}
                    ],
                    'max_tokens': max_tokens,
                    'temperature': temperature
                },
                timeout=180  # 3 minutes for long content generation
            )
            
            logger.info(f"OpenAI API response status: {response.status_code}")
            
            if response.status_code == 429:
                return {'error': 'Rate limit exceeded (429). Please wait a minute and try again.'}
            
            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(f"OpenAI API error response: {error_text}")
                return {'error': f'OpenAI API error ({response.status_code}): {error_text}'}
            
            data = response.json()
            
            # Check for API errors in response
            if 'error' in data:
                error_msg = data['error'].get('message', str(data['error']))
                logger.error(f"OpenAI API returned error: {error_msg}")
                return {'error': f'OpenAI API error: {error_msg}'}
            
            # Check for valid response structure
            if 'choices' not in data or len(data['choices']) == 0:
                logger.error(f"OpenAI API returned no choices: {data}")
                return {'error': 'OpenAI API returned empty response'}
            
            content = data['choices'][0].get('message', {}).get('content', '')
            
            # Check finish reason
            finish_reason = data['choices'][0].get('finish_reason', '')
            if finish_reason == 'length':
                logger.warning(f"OpenAI response was truncated (finish_reason=length)")
            
            # Log content length for debugging
            logger.info(f"OpenAI API success: content length={len(content)}, finish_reason={finish_reason}")
            
            if not content or len(content) < 50:
                logger.error(f"OpenAI returned very short content: '{content[:100]}'")
                return {'error': 'OpenAI returned empty or very short content. Try again.'}
            
            return {
                'content': content,
                'usage': data.get('usage', {}),
                'finish_reason': finish_reason
            }
            
        except requests.exceptions.Timeout:
            logger.error("OpenAI API timeout after 180 seconds")
            return {'error': 'Request timed out after 180 seconds. Try a shorter word count or try again.'}
        except requests.RequestException as e:
            error_detail = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json().get('error', {}).get('message', str(e))
                except Exception:
                    error_detail = e.response.text[:200]
            logger.error(f"OpenAI API request error: {error_detail}")
            return {'error': f'OpenAI API error: {error_detail}'}
        except Exception as e:
            logger.error(f"OpenAI API unexpected error: {e}")
            return {'error': f'Unexpected error calling OpenAI: {str(e)}'}
    
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
