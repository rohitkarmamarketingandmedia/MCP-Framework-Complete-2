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
        word_count: int = 400,
        tone: str = 'professional',
        business_name: str = '',
        include_faq: bool = True,  # Changed default to True for 100% SEO
        faq_count: int = 5,  # Changed to 5-7 FAQs for SEO
        internal_links: List[Dict] = None,
        usps: List[str] = None,
        contact_name: str = None,
        phone: str = None,
        email: str = None
    ) -> Dict[str, Any]:
        """
        Generate 100% SEO-optimized blog post
        
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
                'secondary_keywords': List[str],
                'cta': Dict,
                'html': str
            }
        """
        internal_links = internal_links or []
        usps = usps or []
        
        logger.info(f"Generating blog: '{keyword}' for {geo}")
        
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
            email=email
        )
        
        # Enforce rate limiting
        self._rate_limit_delay()
        
        # Get agent settings or use defaults
        if agent_config:
            # Use agent's system prompt with variable substitution
            system_prompt = agent_config.system_prompt
            system_prompt = system_prompt.replace('{tone}', tone)
            system_prompt = system_prompt.replace('{industry}', industry)
            
            # Calculate tokens needed: ~2 tokens per word + overhead for JSON structure
            # Minimum 2000 tokens for proper blog with real content, max 3500 for longer
            estimated_tokens = max(2000, min(3500, int(word_count * 2) + 800))
            
            fast_model = self.default_model  # gpt-3.5-turbo
            
            response = self._call_with_retry(
                prompt, 
                max_tokens=estimated_tokens,
                system_prompt=system_prompt,
                model=fast_model,
                temperature=agent_config.temperature
            )
            logger.info(f"Used content_writer agent config (model={fast_model}, tokens={estimated_tokens})")
        else:
            # Fallback to default behavior
            estimated_tokens = max(2000, min(3500, int(word_count * 2) + 800))
            response = self._call_with_retry(prompt, max_tokens=estimated_tokens)
        
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
        
        # ===== POST-PROCESSING FOR SEO QUALITY =====
        body_content = result.get('body', '')
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
        email: str = None
    ) -> str:
        """Build the blog generation prompt - optimized for 100% SEO score"""
        
        from datetime import datetime
        current_year = datetime.utcnow().year
        
        # Build internal links section
        links_section = ""
        if internal_links:
            links_section = """
INTERNAL LINKING (MANDATORY):
Include these internal links naturally within your content using <a href="URL">anchor text</a> format:
"""
            for link in internal_links[:8]:
                kw = link.get('keyword', link.get('title', ''))
                url = link.get('url', '')
                if kw and url:
                    links_section += f'- Link to "{url}" for: {kw}\n'
        
        # Build USP section
        usp_section = ""
        if usps:
            usp_section = "\nUNIQUE SELLING POINTS (weave naturally into content):\n"
            for usp in usps[:5]:
                usp_section += f"- {usp}\n"
        
        # Build CTA contact info
        cta_contact = contact_name or business_name or f"our {industry} team"
        cta_company = business_name or f"our {industry} company"
        cta_phone = f"call {phone}" if phone else ""
        cta_email = f"email {email}" if email else ""
        cta_methods = " or ".join(filter(None, [cta_phone, cta_email])) or "contact us"
        
        return f"""You are an expert SEO content writer creating a blog post for a real client website.

BUSINESS INFO:
- Company: {business_name or f'A {industry} company'}
- Contact: {contact_name or 'Not provided'}
- Phone: {phone or 'Not provided'}
- Email: {email or 'Not provided'}
- Location: {geo}
- Industry: {industry}

TARGET KEYWORD: "{keyword}"
WORD COUNT: {word_count} words minimum
TONE: {tone}
CURRENT YEAR: {current_year}

===== REQUIRED BLOG STRUCTURE =====

1. INTRO (120-180 words) - MANDATORY FORMAT:
   - Paragraph 1: What this topic is (no sales language)
   - Paragraph 2: Who this information is for
   - Paragraph 3: Why this matters to the reader
   - Include "{keyword}" naturally in first 100 words
   - Mention "{geo}" in intro

2. CONTEXT/BACKGROUND SECTION (100-150 words):
   - What this service/topic actually is
   - Who it applies to in {geo}
   - Local context if relevant
   - NO assumptions or hype

3. PRIMARY INFORMATIONAL SECTIONS (3-5 H2 sections, each 150-200 words):
   Each section must:
   - Answer a real question a human would ask
   - Use varied, natural headings (avoid repeating "{keyword}" verbatim)
   - Include H3 subheadings for detail
   - Good H2 examples:
     * "What to Consider Before [Action] in {geo}"
     * "How {geo} [Professionals] Approach This"
     * "Comparing Options for {geo} [Customers]"

4. PRACTICAL CONSIDERATIONS (include 2-3 that apply):
   - Cost breakdown or pricing factors
   - Step-by-step process
   - Pros and cons
   - Who this is NOT for
   - Common mistakes to avoid

5. FAQ SECTION (MANDATORY - exactly 5-7 FAQs):
   - Questions must be specific and natural
   - Each answer: 40-70 words
   - No fluff or marketing language
   - Answer-first format (start with the actual answer)
   - Format: <h3>Question?</h3><p>Answer...</p>

6. CTA SECTION (MANDATORY - appears twice):
   First CTA: Mid-content (subtle, helpful)
   Final CTA: End of article (direct but not salesy)
   
   CTA must include:
   - Contact name: {cta_contact}
   - Company: {cta_company}
   - Contact method: {cta_methods}
   
   CTA Example tone: "If you have questions about this or want guidance specific to your situation, reach out to {cta_contact} at {cta_company}. You can {cta_methods} to get straightforward, no-pressure advice."
{links_section}
{usp_section}
===== SEO REQUIREMENTS =====
✓ "{keyword}" appears 8-15 times naturally throughout
✓ "{geo}" appears 10+ times
✓ Keyword in first 100 words
✓ Keyword in last 100 words  
✓ Meta title: 55-60 chars, keyword at START
✓ Meta description: 150-160 chars with keyword
✓ Use <ul>/<li> for lists, <strong> for emphasis
✓ Include specific numbers/stats where relevant

===== OUTPUT FORMAT (MANDATORY JSON) =====
Return ONLY this JSON structure - no markdown, no code blocks:

{{
    "title": "SEO title with {keyword} and {geo}",
    "h1": "H1 with {keyword} and {geo}",
    "meta_title": "55-60 char title starting with {keyword}",
    "meta_description": "150-160 char description with {keyword}",
    "summary": "2-3 sentence summary for AI/chat responses",
    "body": "<p>Full HTML content with all sections...</p>",
    "h2_headings": ["list", "of", "h2", "headings"],
    "h3_headings": ["list", "of", "h3", "headings"],
    "secondary_keywords": ["related", "keywords"],
    "key_takeaways": [
        "Takeaway 1 - actionable insight",
        "Takeaway 2 - key fact",
        "Takeaway 3 - important consideration"
    ],
    "faq_items": [
        {{"question": "Specific question about {keyword}?", "answer": "40-70 word answer starting with the actual answer, not fluff."}},
        {{"question": "Another real question?", "answer": "Direct answer with useful information."}},
        {{"question": "Third question?", "answer": "Helpful response."}},
        {{"question": "Fourth question?", "answer": "Practical answer."}},
        {{"question": "Fifth question?", "answer": "Clear response."}}
    ],
    "cta": {{
        "contact_name": "{contact_name or ''}",
        "company_name": "{business_name or ''}",
        "phone": "{phone or ''}",
        "email": "{email or ''}",
        "cta_text": "Natural CTA text for the article"
    }},
    "word_count": {word_count}
}}

CRITICAL RULES:
1. Body MUST be {word_count}+ words of REAL content
2. NEVER use placeholder text ("Content...", "Details here...")
3. Write complete, helpful, authoritative content
4. FAQs are MANDATORY with 5-7 specific questions
5. CTA appears twice in body content
6. Return ONLY valid JSON
"""
    
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
                timeout=90
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
            return {'error': 'Request timed out after 120 seconds'}
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
