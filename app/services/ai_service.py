"""
MCP Framework - AI Service
OpenAI and Anthropic API integration for content generation
"""
import os
import json
from typing import Dict, List, Any, Optional
import requests


class AIService:
    """AI content generation service"""
    
    def __init__(self):
        self.openai_key = os.environ.get('OPENAI_API_KEY', '')
        self.anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        self.default_model = os.environ.get('DEFAULT_AI_MODEL', 'gpt-4o-mini')
    
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
        Generate SEO-optimized blog post
        
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
        
        # Build the prompt
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
        
        # Call AI
        response = self._call_openai(prompt, max_tokens=4000)
        
        if response.get('error'):
            return response
        
        # Parse the response
        return self._parse_blog_response(response.get('content', ''))
    
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
        """Generate social media post for specific platform"""
        
        platform_limits = {
            'gbp': 1500,
            'facebook': 500,
            'instagram': 2200,
            'linkedin': 700,
            'twitter': 280
        }
        
        char_limit = platform_limits.get(platform, 500)
        
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
}}"""

        response = self._call_openai(prompt, max_tokens=500)
        
        if response.get('error'):
            return response
        
        try:
            content = response.get('content', '{}')
            # Clean markdown code blocks if present
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
            return json.loads(content.strip())
        except json.JSONDecodeError:
            return {
                'text': response.get('content', ''),
                'hashtags': [],
                'cta': '',
                'image_alt': ''
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
"""
    
    def _parse_blog_response(self, content: str) -> Dict[str, Any]:
        """Parse AI response into structured blog data"""
        try:
            # Clean markdown if present
            if '```' in content:
                parts = content.split('```')
                for part in parts:
                    if part.strip().startswith('json') or part.strip().startswith('{'):
                        content = part.replace('json', '', 1).strip()
                        break
            
            data = json.loads(content)
            
            # Generate HTML if not present
            if 'html' not in data and 'body' in data:
                data['html'] = data['body']
            
            return data
            
        except json.JSONDecodeError:
            # Return raw content if JSON parsing fails
            return {
                'title': '',
                'h1': '',
                'body': content,
                'meta_title': '',
                'meta_description': '',
                'h2_headings': [],
                'h3_headings': [],
                'faq_items': [],
                'secondary_keywords': [],
                'html': content
            }
    
    def _call_openai(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """Call OpenAI API"""
        if not self.openai_key:
            return {'error': 'OpenAI API key not configured'}
        
        try:
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.openai_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.default_model,
                    'messages': [
                        {'role': 'system', 'content': 'You are an expert SEO content writer. Always respond with valid JSON when requested.'},
                        {'role': 'user', 'content': prompt}
                    ],
                    'max_tokens': max_tokens,
                    'temperature': 0.7
                },
                timeout=120
            )
            
            response.raise_for_status()
            data = response.json()
            
            return {
                'content': data['choices'][0]['message']['content'],
                'usage': data.get('usage', {})
            }
            
        except requests.RequestException as e:
            return {'error': f'OpenAI API error: {str(e)}'}
    
    def _call_anthropic(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """Call Anthropic Claude API (fallback)"""
        if not self.anthropic_key:
            return {'error': 'Anthropic API key not configured'}
        
        try:
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': self.anthropic_key,
                    'Content-Type': 'application/json',
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': 'claude-3-sonnet-20240229',
                    'max_tokens': max_tokens,
                    'messages': [
                        {'role': 'user', 'content': prompt}
                    ]
                },
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
