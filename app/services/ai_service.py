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
        self.openai_key = os.environ.get('OPENAI_API_KEY', '')
        self.anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        self.default_model = os.environ.get('DEFAULT_AI_MODEL', 'gpt-4o-mini')
        self._last_call_time = 0
        self._min_call_interval = 2  # seconds between calls to avoid rate limits
    
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
        usps: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate SEO-optimized blog post using content_writer agent config
        
        Returns:
            {
                'title': str,
                'h1': str,
                'body': str,
                'meta_title': str,
                'meta_description': str,
                'h2_headings': List[str],
                'h3_headings': List[str],
                'faq_items': List[Dict],
                'secondary_keywords': List[str],
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
            usps=usps
        )
        
        # Enforce rate limiting
        self._rate_limit_delay()
        
        # Get agent settings or use defaults
        if agent_config:
            # Use agent's system prompt with variable substitution
            system_prompt = agent_config.system_prompt
            system_prompt = system_prompt.replace('{tone}', tone)
            system_prompt = system_prompt.replace('{industry}', industry)
            
            response = self._call_with_retry(
                prompt, 
                max_tokens=agent_config.max_tokens,
                system_prompt=system_prompt,
                model=agent_config.model,
                temperature=agent_config.temperature
            )
            logger.info(f"Used content_writer agent config (model={agent_config.model})")
        else:
            # Fallback to default behavior
            response = self._call_with_retry(prompt, max_tokens=4000)
        
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
        
        # Ensure we have meta fields - generate if missing
        if not result.get('meta_title'):
            result['meta_title'] = f"{keyword.title()} | {business_name or geo}"[:60]
            logger.warning(f"Generated fallback meta_title: {result['meta_title']}")
        
        if not result.get('meta_description'):
            result['meta_description'] = f"Expert {keyword} services in {geo}. {business_name or 'We'} provide professional {industry} solutions. Contact us today!"[:160]
            logger.warning(f"Generated fallback meta_description")
        
        logger.info(f"Blog generated successfully: {result.get('title', 'no title')[:50]}")
        return result
    
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
    "text": "post text without hashtags",
    "hashtags": ["hashtag1", "hashtag2"],
    "cta": "call to action text",
    "image_alt": "suggested image alt text"
}}

IMPORTANT: Return ONLY valid JSON, no markdown, no explanation."""

        # Enforce rate limiting
        self._rate_limit_delay()
        
        # Use agent config if available
        if agent_config:
            response = self._call_with_retry(
                prompt, 
                max_tokens=agent_config.max_tokens,
                system_prompt=agent_config.system_prompt,
                model=agent_config.model,
                temperature=agent_config.temperature
            )
            logger.info(f"Used social_writer agent config")
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
            logger.info(f"Social post generated: {len(result.get('text', ''))} chars")
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Social JSON parse failed: {e}, using raw content")
            # Generate a usable fallback
            raw_text = response.get('content', topic)
            return {
                'text': raw_text[:char_limit] if len(raw_text) > char_limit else raw_text,
                'hashtags': [f"#{industry.replace(' ', '')}", f"#{geo.split(',')[0].replace(' ', '')}", f"#{business_name.replace(' ', '')}"][:hashtag_count],
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
        usps: List[str]
    ) -> str:
        """Build the blog generation prompt"""
        
        links_instruction = ""
        if internal_links:
            links_instruction = f"""
Internal links to include (use natural anchor text):
{json.dumps(internal_links, indent=2)}
"""
        
        usp_instruction = ""
        if usps:
            usp_instruction = f"""
Unique selling points to weave in naturally:
- {chr(10).join('- ' + usp for usp in usps)}
"""
        
        faq_instruction = ""
        if include_faq:
            faq_instruction = f"""
Include {faq_count} FAQs at the end with questions real customers ask about {keyword} in {geo}.
"""
        
        return f"""Write a comprehensive, SEO-optimized blog post for a {industry} business{"called " + business_name if business_name else ""} in {geo}.

PRIMARY KEYWORD: {keyword}
TARGET WORD COUNT: {word_count} words
TONE: {tone}

SEO REQUIREMENTS (CRITICAL):
1. H1 must contain "{keyword}" and "{geo}"
2. All H2s must contain location reference ({geo} or nearby areas)
3. All H3s should include keyword variations
4. Meta title: 50-60 characters, keyword at start
5. Meta description: 150-160 characters, includes keyword and CTA
6. First paragraph must contain keyword within first 100 words
7. Keyword density: 1-2% naturally distributed
{links_instruction}
{usp_instruction}
{faq_instruction}

OUTPUT FORMAT (JSON):
{{
    "title": "SEO title for the page",
    "h1": "Main heading with keyword and location",
    "meta_title": "50-60 char meta title",
    "meta_description": "150-160 char meta description",
    "body": "Full HTML content with proper h2, h3, p tags",
    "h2_headings": ["list of h2 headings used"],
    "h3_headings": ["list of h3 headings used"],
    "secondary_keywords": ["related keywords used"],
    "faq_items": [
        {{"question": "FAQ question?", "answer": "Detailed answer"}}
    ]
}}

Write engaging, helpful content that serves the reader while optimizing for search.
IMPORTANT: Return ONLY valid JSON, no markdown code blocks, no explanation before or after.
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
            
            # Generate HTML if not present
            if 'html' not in data and 'body' in data:
                data['html'] = data['body']
            
            logger.debug(f"Parsed blog: title='{data.get('title', '')[:30]}', body_len={len(data.get('body', ''))}")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Failed content: {content[:500]}")
            
            # Try to extract any usable content
            return {
                'title': '',
                'h1': '',
                'body': original_content if '<' in original_content else f"<p>{original_content}</p>",
                'meta_title': '',
                'meta_description': '',
                'h2_headings': [],
                'h3_headings': [],
                'faq_items': [],
                'secondary_keywords': [],
                'html': original_content,
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
                timeout=120
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
                except:
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
                timeout=120
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
            return self._call_openai(user_input, max_tokens=2000)
        
        # Get system prompt with variable substitution
        system_prompt = agent.system_prompt
        if variables:
            for key, value in variables.items():
                system_prompt = system_prompt.replace(f'{{{key}}}', str(value))
        
        logger.info(f"Using agent '{agent_name}' with model {agent.model}")
        
        # Determine which API to call based on model
        model_lower = agent.model.lower()
        if 'claude' in model_lower or 'anthropic' in model_lower:
            return self._call_anthropic(
                prompt=user_input,
                max_tokens=agent.max_tokens,
                system_prompt=system_prompt,
                model=agent.model,
                temperature=agent.temperature
            )
        else:
            return self._call_openai(
                prompt=user_input,
                max_tokens=agent.max_tokens,
                system_prompt=system_prompt,
                model=agent.model,
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
