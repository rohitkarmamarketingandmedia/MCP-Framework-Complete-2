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
        
        # For long-form content, we need a model with higher token limits
        # GPT-3.5-turbo is limited to 4096 tokens - not enough for 1000+ word blogs
        # Use GPT-4-turbo or GPT-4 for better results
        content_model = os.environ.get('BLOG_AI_MODEL', 'gpt-4-turbo-preview')
        
        # Calculate tokens: ~1.3 tokens per word for output + JSON overhead
        # For 1000 words, we need at least 2500-3000 tokens
        # Add buffer for JSON structure, headings, FAQs, schema
        min_tokens_for_content = int(word_count * 1.5) + 1500  # Extra for JSON/HTML
        estimated_tokens = max(3500, min(8000, min_tokens_for_content))
        
        logger.info(f"Blog generation: word_count={word_count}, estimated_tokens={estimated_tokens}, model={content_model}")
        
        # Get agent settings or use defaults
        if agent_config:
            # Use agent's system prompt with variable substitution
            system_prompt = agent_config.system_prompt
            system_prompt = system_prompt.replace('{tone}', tone)
            system_prompt = system_prompt.replace('{industry}', industry)
            
            response = self._call_with_retry(
                prompt, 
                max_tokens=estimated_tokens,
                system_prompt=system_prompt,
                model=content_model,
                temperature=0.7
            )
            logger.info(f"Used content_writer agent config (model={content_model}, tokens={estimated_tokens})")
        else:
            response = self._call_with_retry(prompt, max_tokens=estimated_tokens, model=content_model)
        
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
        
        # Check if word count is too low (less than 70% of requested)
        min_acceptable = int(word_count * 0.7)
        if actual_word_count < min_acceptable:
            logger.warning(f"Blog word count too low: {actual_word_count} < {min_acceptable} (70% of {word_count})")
            # Don't fail, but log warning - the content might still be usable
        
        # Check if body is too short in characters (likely truncated)
        min_chars = word_count * 5  # Average 5 chars per word
        if len(body_content) < min_chars:
            logger.error(f"Blog body too short: {len(body_content)} chars (expected {min_chars}+)")
            return {
                'error': f'AI returned incomplete content ({actual_word_count} words instead of {word_count}). Please try again.',
                'raw_response': response.get('content', '')[:500],
                'actual_word_count': actual_word_count
            }
        
        # ===== PLACEHOLDER DETECTION =====
        # Check for placeholder text in body and FAQs
        placeholder_patterns = [
            'Response...', 'Insight...', 'Explanation...', 'Advice...', 
            'Information...', 'Clarification...', 'CTA section...', 
            'Content...', 'Details...', 'Details here', 'Content here',
            'Full HTML content with all sections', 'WRITE', 'DO NOT put placeholder',
            '[specific symptom', '[factor 1]', '[qualification 1]', '[shorter time]',
            'MANDATORY:', '[COUNT YOUR WORDS', '[60-80 word'
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
            usp_text = "\nUnique Selling Points to weave in:\n"
            for usp in usps[:5]:
                usp_text += f"• {usp}\n"

        return f"""You are an expert SEO content writer. Generate a blog post that will score 100% on SEO analysis tools.

####################################################################
#                    CRITICAL: WORD COUNT REQUIREMENT              #
####################################################################
#                                                                  #
#   MINIMUM WORD COUNT: {word_count} WORDS                         #
#                                                                  #
#   Your body content MUST contain AT LEAST {word_count} words.    #
#   This is NON-NEGOTIABLE. Content under {word_count} words       #
#   will be REJECTED.                                              #
#                                                                  #
#   To achieve {word_count}+ words:                                #
#   - Write 5-6 detailed H2 sections (180-220 words each)          #
#   - Include 2-3 H3 subsections per H2                            #
#   - Write comprehensive FAQ answers (60-80 words each)           #
#   - Include detailed intro (120+ words) and conclusion (100+)    #
#                                                                  #
####################################################################

====================================================================
                    100% SEO SCORE REQUIREMENTS
====================================================================

PRIMARY KEYWORD: "{keyword}"
LOCATION: {location}
BUSINESS: {business_name}
INDUSTRY: {industry}
MINIMUM WORD COUNT: {word_count} words (MANDATORY - will be verified)
TONE: {tone}
YEAR: {current_year}

====================================================================
                    CRITICAL SEO CHECKLIST (ALL REQUIRED)
====================================================================

TITLE & META (Score: 20 points)
✓ Meta title: EXACTLY 55-60 characters, "{keyword}" at the START
✓ Meta description: EXACTLY 150-155 characters, includes "{keyword}" and "{location}"
✓ H1: Contains "{keyword}" AND "{location}"

KEYWORD DENSITY (Score: 25 points)  
✓ "{keyword}" appears 12-18 times throughout the content (1.5-2% density)
✓ "{keyword}" in first paragraph (first 100 words)
✓ "{keyword}" in last paragraph (last 100 words)
✓ "{keyword}" in at least 3 H2 headings
✓ "{location}" or "{city}" appears 8-12 times

CONTENT STRUCTURE (Score: 25 points)
✓ Minimum 5 H2 sections (each 150-200 words)
✓ At least 2 H3 subheadings per H2 section
✓ Bullet points or numbered lists in at least 2 sections
✓ Short paragraphs (3-4 sentences max)
✓ Transition words between sections

INTERNAL LINKING (Score: 15 points)
{link_instructions if internal_links else "✓ No internal links provided - skip this section"}
✓ Links placed naturally within paragraph text
✓ Varied anchor text (not repetitive)
{related_posts_html}

FAQ SCHEMA (Score: 10 points)
✓ Exactly 5-6 FAQs at the end
✓ Questions are realistic buyer questions
✓ Answers are 50-80 words each with specific information
✓ FAQ formatted with <h3> for questions, <p> for answers

CTA (Score: 5 points)
✓ 2 CTAs: one mid-article, one at end
✓ Include contact: {cta_name}
✓ Include method: {contact_str}
✓ Include location: {location}
{internal_links_html}
{usp_text}
====================================================================
                    EXACT OUTPUT STRUCTURE
====================================================================

Your response must have this EXACT HTML structure in the body:

<p>[Opening paragraph - mention {keyword} and {location} in first 2 sentences. 80-100 words.]</p>

<h2>{keyword} in {location}: [Benefit or Question]</h2>
<p>[Paragraph with internal link if available]</p>
<h3>[Subtopic 1]</h3>
<p>[Detailed explanation]</p>
<h3>[Subtopic 2]</h3>
<p>[Detailed explanation]</p>

<h2>Why {location} [Residents/Businesses] Choose {keyword}</h2>
<p>[Content with bullet points]</p>
<ul>
<li><strong>Benefit 1:</strong> Explanation</li>
<li><strong>Benefit 2:</strong> Explanation</li>
<li><strong>Benefit 3:</strong> Explanation</li>
</ul>

<p><strong>Ready to discuss your {keyword} needs?</strong> Contact {cta_name} at {business_name}. You can {contact_str}.</p>

<h2>What to Expect from {keyword} Services in {location}</h2>
<p>[Process or timeline content with internal link]</p>
<h3>[Step or Phase 1]</h3>
<p>[Details]</p>
<h3>[Step or Phase 2]</h3>
<p>[Details]</p>

<h2>{keyword} Costs in {location}: What You Should Know</h2>
<p>[Pricing factors - be specific but don't make up numbers]</p>
<ol>
<li>Factor 1</li>
<li>Factor 2</li>
<li>Factor 3</li>
</ol>

<h2>Choosing the Right {keyword} Provider in {location}</h2>
<p>[Selection criteria with internal link]</p>

<h2>Frequently Asked Questions About {keyword} in {location}</h2>

<h3>Question 1 about {keyword}?</h3>
<p>[50-80 word answer with specific information]</p>

<h3>Question 2 about {keyword} in {location}?</h3>
<p>[50-80 word answer]</p>

<h3>Question 3?</h3>
<p>[50-80 word answer]</p>

<h3>Question 4?</h3>
<p>[50-80 word answer]</p>

<h3>Question 5?</h3>
<p>[50-80 word answer]</p>

<h2>Get Started with {keyword} in {location}</h2>
<p>[Final CTA paragraph] Contact {cta_name} at {business_name} today. {contact_str} for a free consultation. We're proud to serve {location} and surrounding areas.</p>

====================================================================
                    JSON OUTPUT FORMAT
====================================================================

Return ONLY this JSON (no markdown code blocks):

{{
    "title": "{keyword} in {location} | {business_name}",
    "h1": "{keyword} Services in {location} - Expert Solutions",
    "meta_title": "[EXACTLY 55-60 characters, {keyword} at START]",
    "meta_description": "[EXACTLY 150-155 characters with {keyword} and {location}]",
    "body": "[MANDATORY: Write {word_count}+ WORDS of HTML content. Include: 120+ word intro, 5-6 H2 sections (180+ words each), H3 subsections, bullet lists, 2 CTAs, FAQ section. This field must be LONG and DETAILED.]",
    "h2_headings": ["H2 1", "H2 2", "H2 3", "H2 4", "H2 5", "H2 6"],
    "h3_headings": ["H3 1", "H3 2", "H3 3", "H3 4", "H3 5", "H3 6", "H3 7", "H3 8"],
    "word_count": {word_count},
    "actual_word_count": "[COUNT YOUR WORDS - must be {word_count}+]",
    "keyword_count": 15,
    "internal_links_used": ["url1", "url2", "url3"],
    "faq_items": [
        {{"question": "Detailed question 1 about {keyword}?", "answer": "[60-80 word comprehensive answer with specific details]"}},
        {{"question": "Detailed question 2 about {keyword} in {location}?", "answer": "[60-80 word comprehensive answer]"}},
        {{"question": "Detailed question 3 about cost/pricing?", "answer": "[60-80 word comprehensive answer]"}},
        {{"question": "Detailed question 4 about process/timeline?", "answer": "[60-80 word comprehensive answer]"}},
        {{"question": "Detailed question 5 about choosing provider?", "answer": "[60-80 word comprehensive answer]"}}
    ],
    "faq_schema": {{
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {{"@type": "Question", "name": "Q1?", "acceptedAnswer": {{"@type": "Answer", "text": "Full answer 1"}}}},
            {{"@type": "Question", "name": "Q2?", "acceptedAnswer": {{"@type": "Answer", "text": "Full answer 2"}}}},
            {{"@type": "Question", "name": "Q3?", "acceptedAnswer": {{"@type": "Answer", "text": "Full answer 3"}}}},
            {{"@type": "Question", "name": "Q4?", "acceptedAnswer": {{"@type": "Answer", "text": "Full answer 4"}}}},
            {{"@type": "Question", "name": "Q5?", "acceptedAnswer": {{"@type": "Answer", "text": "Full answer 5"}}}}
        ]
    }},
    "cta": {{
        "contact_name": "{cta_name}",
        "company_name": "{business_name}",
        "phone": "{phone or ''}",
        "email": "{email or ''}",
        "location": "{location}"
    }},
    "seo_score": 100
}}

####################################################################
#                    FINAL VERIFICATION CHECKLIST                  #
####################################################################

BEFORE OUTPUTTING, YOU MUST VERIFY:

□ WORD COUNT: Body contains {word_count}+ words (COUNT THEM!)
□ META TITLE: Exactly 55-60 characters, keyword "{keyword}" at start
□ META DESC: Exactly 150-155 characters with keyword and location
□ H2 SECTIONS: At least 5-6 H2 headings (each section 180+ words)
□ H3 SECTIONS: At least 2 H3 per H2 section (10+ total H3s)
□ KEYWORD DENSITY: "{keyword}" appears 12-18 times
□ LOCATION: "{location}" appears 8-12 times
□ INTERNAL LINKS: ALL links from the list above are included
□ FAQs: 5-6 FAQs with 60-80 word answers each
□ CTAs: 2 CTAs with contact info (mid-article + end)
□ OUTPUT: Valid JSON only, no markdown code blocks

REMEMBER: Content under {word_count} words will be REJECTED!
Write DETAILED, COMPREHENSIVE content for each section.
"""
    
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
