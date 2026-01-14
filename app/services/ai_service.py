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
        word_count: int = 1200,
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
                if related_posts:
                    for i, rp in enumerate(related_posts[:3]):
                        logger.info(f"  Link {i+1}: {rp.get('title', '')[:40]} -> {rp.get('url', '')[:50]}")
            except Exception as e:
                logger.warning(f"Could not fetch related posts: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
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
        
        # System prompt - SEO content engine
        system_prompt = '''You are an SEO content engine generating high-conversion local service blog posts.

CRITICAL LOCATION RULES (MUST FOLLOW):
1. The PRIMARY KEYWORD may already contain a city or service area.
2. If the city name appears in the primary keyword, DO NOT repeat the city again in:
   - Headings
   - Titles
   - Introductions
   - H1/H2/H3
3. The city + state may appear ONCE for clarity only if it improves readability.
4. NEVER output patterns like:
   "Service City in City, State"
   "Keyword City for City Residents"

HEADLINE RULES:
- Convert ALL headlines to Proper Case (Title Case).
- Never leave headlines in lowercase.
- H1 must be human-readable, not keyword-stuffed.

OUTPUT FORMAT:
- Output ONLY valid JSON - no markdown, no code blocks, no explanations
- Follow the exact JSON structure requested

You are generating content for legitimate local service businesses (HVAC, plumbing, dental, etc.).'''
        
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
        """Build the blog generation prompt - Clean SEO-focused version"""
        
        # Helper function to convert to Title Case properly
        def to_title_case(text):
            if not text:
                return text
            lowercase_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 
                             'on', 'at', 'to', 'by', 'in', 'of', 'with', 'as'}
            words = text.split()
            result = []
            for i, word in enumerate(words):
                if i == 0 or word.lower() not in lowercase_words:
                    result.append(word.capitalize())
                else:
                    result.append(word.lower())
            return ' '.join(result)
        
        # Known Florida cities to detect in keyword
        known_cities = [
            'sarasota', 'port charlotte', 'fort myers', 'naples', 'tampa', 'orlando',
            'jacksonville', 'miami', 'bradenton', 'venice', 'punta gorda', 'north port',
            'cape coral', 'bonita springs', 'estero', 'lehigh acres', 'englewood',
            'arcadia', 'nokomis', 'osprey', 'lakewood ranch', 'palmetto', 'ellenton',
            'parrish', 'ruskin', 'sun city center', 'apollo beach', 'brandon', 'riverview'
        ]
        
        # Check if keyword already contains a city name
        keyword_lower = keyword.lower()
        keyword_city = None
        for test_city in known_cities:
            if test_city in keyword_lower:
                keyword_city = test_city.title()
                break
        
        # Parse geo from settings
        geo_parts = geo.split(',') if geo else ['', '']
        settings_city = geo_parts[0].strip() if len(geo_parts) > 0 else ''
        state = geo_parts[1].strip() if len(geo_parts) > 1 else 'FL'
        
        # USE THE CITY FROM KEYWORD if present, otherwise use settings
        if keyword_city:
            city = keyword_city
            logger.info(f"Using city from keyword: '{city}' (ignoring settings city '{settings_city}')")
        else:
            city = to_title_case(settings_city) if settings_city else ''
        
        state = state.upper() if len(state) == 2 else to_title_case(state)
        
        # Convert keyword to Title Case
        primary_keyword = to_title_case(keyword)
        
        # Build internal links section
        links_text = ""
        all_links = []
        
        if internal_links:
            for link in internal_links[:4]:
                url = link.get('url', '')
                title = link.get('title', link.get('keyword', ''))
                if url and title:
                    all_links.append({'url': url, 'title': title})
        
        if related_posts:
            for post in related_posts[:4]:
                url = post.get('url', post.get('published_url', ''))
                title = post.get('title', '')
                if url and title and not any(l['url'] == url for l in all_links):
                    all_links.append({'url': url, 'title': title})
        
        if all_links:
            links_text = "Internal Links to Include (2-4, naturally placed):\n"
            for link in all_links[:4]:
                links_text += f"- {link['title']}: {link['url']}\n"
        
        # Build contact info
        contact_info = f"Company Name: {business_name}\n"
        if contact_name:
            contact_info += f"Contact Name: {contact_name}\n"
        if phone:
            contact_info += f"Phone: {phone}\n"
        if email:
            contact_info += f"Email: {email}\n"
        
        logger.info(f"Building prompt: keyword='{primary_keyword}', city='{city}', state='{state}', links={len(all_links)}")

        # Build critical instruction about city
        city_instruction = ""
        if keyword_city:
            city_instruction = f"""
⚠️ CRITICAL CITY RULE: The keyword "{primary_keyword}" contains the city "{city}".
- Use ONLY "{city}" throughout the entire article
- Do NOT mention any other city (especially not from settings)
- Every location reference must be "{city}, {state}" or just "{city}"
"""

        return f"""Primary Keyword: {primary_keyword}
Service: {industry or 'Local Service'}
Target City: {city}
State: {state}
{contact_info}
{links_text}
{city_instruction}
WRITE A {word_count}-WORD BLOG ARTICLE with this structure:

<h1>[Title about {primary_keyword}]</h1>

<h2>Introduction</h2>
<p>200+ words introducing the service for {city} residents.</p>

<h2>Benefits of Professional {primary_keyword}</h2>
<h3>Benefit 1</h3><p>Explanation...</p>
<h3>Benefit 2</h3><p>Explanation...</p>
<h3>Benefit 3</h3><p>Explanation...</p>
<p>Total 250+ words for benefits section.</p>

<h2>The Process</h2>
<p>150+ words explaining how the service works.</p>

<h2>Cost Factors</h2>
<p>150+ words about pricing considerations.</p>

<h2>Why Choose {business_name}</h2>
<p>150+ words about company benefits. Include CTA here.</p>

<h2>Get Started Today</h2>
<p>100+ words with strong CTA including contact info.</p>

MANDATORY REQUIREMENTS:
1. Body MUST be {word_count}+ words - COUNT BEFORE RESPONDING
2. Include 1 <h1>, 5-6 <h2>, 3+ <h3> tags
3. Include 2-4 internal links naturally in paragraphs
4. Include keyword "{primary_keyword}" 8-12 times naturally
5. ONLY use city "{city}" - no other cities allowed

OUTPUT AS VALID JSON:
{{
    "meta_title": "{primary_keyword} | Expert Service | {business_name}",
    "meta_description": "Professional {primary_keyword.lower()} by {business_name}. Trusted {city} experts. Call today for a free estimate.",
    "h1": "{primary_keyword} - Professional Service by {business_name}",
    "body": "<h1>...</h1><h2>...</h2><p>...</p>... MUST BE {word_count}+ WORDS",
    "faq_items": [
        {{"question": "How much does {primary_keyword.lower()} cost?", "answer": "Costs vary based on your specific needs. Contact {business_name} for a free estimate tailored to your situation."}},
        {{"question": "How long does {primary_keyword.lower()} take?", "answer": "Most projects are completed within [timeframe]. {business_name} provides accurate timelines during your consultation."}},
        {{"question": "Why choose {business_name}?", "answer": "{business_name} offers professional service, quality workmanship, and customer satisfaction guaranteed."}},
        {{"question": "Do you serve {city}?", "answer": "Yes! {business_name} proudly serves {city} and surrounding areas. Call us today."}},
        {{"question": "Do you offer free estimates?", "answer": "Yes, {business_name} provides free, no-obligation estimates. Contact us to schedule yours."}}
    ],
    "faq_schema": {{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}},
    "cta": {{"contact_name": "{contact_name or ''}", "company_name": "{business_name}", "phone": "{phone or ''}", "email": "{email or ''}"}}
}}

⚠️ CRITICAL: Body must be {word_count}+ words. Use ONLY the city "{city}" - no other cities!"""
    
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
            
            # Helper to clean string content
            def clean_content(text):
                if not isinstance(text, str):
                    return text
                # Remove escaped newlines and backslashes
                text = text.replace('\\n', '\n')
                text = text.replace('\\r', '')
                text = text.replace('\\/', '/')
                text = text.replace('\\"', '"')
                text = text.replace("\\'", "'")
                # Remove stray backslashes that appear before tags
                text = re.sub(r'\\+([<>])', r'\1', text)
                # Remove backslashes before other chars
                text = re.sub(r'\\([^\\])', r'\1', text)
                # Remove any remaining stray backslashes
                text = text.replace('\\', '')
                return text.strip()
            
            # Clean body content
            if isinstance(body_content, str):
                body_content = clean_content(body_content)
            
            # Clean other text fields
            for field in ['h1', 'title', 'meta_title', 'meta_description']:
                if field in data and isinstance(data[field], str):
                    data[field] = clean_content(data[field])
            
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
            
            # POST-PROCESS: Fix duplicate city names in titles
            data = self._fix_duplicate_cities(data)
            
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
    
    def _fix_duplicate_cities(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process AI response to fix duplicate city names.
        E.g., "Heating Repair Port Charlotte Port Charlotte, FL" -> "Heating Repair Port Charlotte, FL"
        E.g., "in Port Charlotte? in Port Charlotte" -> "in Port Charlotte"
        """
        import re
        
        def fix_duplicate(text, pattern_city):
            """Remove duplicate city occurrences"""
            if not text or not pattern_city:
                return text
            
            original_text = text
            city_lower = pattern_city.lower()
            city_title = pattern_city.title()
            
            # Build regex-safe city name
            city_escaped = re.escape(city_title)
            city_escaped_lower = re.escape(city_lower)
            
            # Patterns to fix (order matters - most specific first):
            patterns = [
                # "in Port Charlotte? in Port Charlotte" or "in Port Charlotte? in Port"
                (rf'(in\s+{city_escaped}[?!.,]?)\s+in\s+{city_escaped}', r'\1', re.IGNORECASE),
                # "in Port Charlotte in Port Charlotte" -> "in Port Charlotte"  
                (rf'(in\s+{city_escaped})\s+in\s+{city_escaped}', r'\1', re.IGNORECASE),
                # "Port Charlotte? in Port" (partial at end)
                (rf'({city_escaped}[?!.,]?)\s+in\s+Port\b', r'\1', re.IGNORECASE),
                # "Port Charlotte Port Charlotte" -> "Port Charlotte"
                (rf'({city_escaped})\s+{city_escaped}', r'\1', re.IGNORECASE),
                # "Port Charlotte in Port Charlotte" -> "Port Charlotte"
                (rf'({city_escaped})\s+in\s+{city_escaped}', r'\1', re.IGNORECASE),
                # "Port Charlotte for Port Charlotte" -> "Port Charlotte"  
                (rf'({city_escaped})\s+for\s+{city_escaped}', r'\1', re.IGNORECASE),
                # "Port Charlotte, FL in Port Charlotte" -> "Port Charlotte, FL"
                (rf'({city_escaped},?\s*(?:FL|Florida)?)\s+in\s+{city_escaped}', r'\1', re.IGNORECASE),
                # "for Port Charlotte in Port Charlotte" -> "for Port Charlotte"
                (rf'(for\s+{city_escaped})\s+in\s+{city_escaped}', r'\1', re.IGNORECASE),
                # Handle truncated city at end: "in Port$" when city is "Port Charlotte"
                (rf'in\s+Port\s*$', '', re.IGNORECASE) if 'port' in city_lower else (r'$^', ''),
            ]
            
            for pattern, replacement, *flags in patterns:
                flag = flags[0] if flags else 0
                text = re.sub(pattern, replacement, text, flags=flag)
            
            # Clean up any trailing "in " at end of text
            text = re.sub(r'\s+in\s*$', '', text)
            
            # Clean up double spaces
            text = re.sub(r'\s{2,}', ' ', text)
            
            if original_text != text:
                logger.debug(f"Fixed duplicate: '{original_text[:60]}' -> '{text[:60]}'")
            
            return text.strip()
        
        # Try to extract city from the content
        city = None
        
        # Try to find city from meta_description or title
        for field in ['meta_description', 'title', 'meta_title', 'h1', 'body']:
            text = data.get(field, '')
            if text:
                # Look for "City, STATE" pattern
                match = re.search(r'in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),?\s*([A-Z]{2})?', text)
                if match:
                    city = match.group(1)
                    break
                # Look for just city name followed by state
                match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s*(?:FL|Florida|TX|Texas|CA|California|[A-Z]{2})', text)
                if match:
                    city = match.group(1)
                    break
        
        if not city:
            # Try extracting from common city names in the text
            common_cities = ['Port Charlotte', 'Sarasota', 'Fort Myers', 'Naples', 'Tampa', 'Orlando', 
                           'Jacksonville', 'Miami', 'Bradenton', 'Venice', 'Punta Gorda', 'North Port',
                           'Cape Coral', 'Bonita Springs', 'Estero', 'Lehigh Acres']
            for test_city in common_cities:
                if test_city.lower() in str(data).lower():
                    city = test_city
                    break
        
        if city:
            logger.info(f"Post-processing: fixing duplicate city '{city}' in titles")
            
            # Fix each text field
            for field in ['title', 'meta_title', 'meta_description', 'h1']:
                if field in data and data[field]:
                    original = data[field]
                    data[field] = fix_duplicate(data[field], city)
                    if original != data[field]:
                        logger.info(f"  Fixed {field}: '{original[:50]}' -> '{data[field][:50]}'")
            
            # Also fix H1 in body content
            if 'body' in data and data['body']:
                data['body'] = fix_duplicate(data['body'], city)
        
        return data
    
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
