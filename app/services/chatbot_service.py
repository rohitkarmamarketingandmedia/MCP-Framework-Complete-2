"""
MCP Framework - Chatbot Service
Handles AI-powered chat conversations for client websites
"""
import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class ChatbotService:
    """Service for managing chatbot conversations and AI responses"""
    
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.model = os.getenv('CHATBOT_MODEL', 'gpt-4o-mini')
    
    def build_system_prompt(self, client_data: Dict, chatbot_config: Dict) -> str:
        """
        Build a comprehensive system prompt based on client data
        """
        # Use override if provided
        if chatbot_config.get('system_prompt_override'):
            return chatbot_config['system_prompt_override']
        
        business_name = client_data.get('business_name', 'the business')
        industry = client_data.get('industry', 'service')
        geo = client_data.get('geo', '')
        phone = client_data.get('phone', '')
        email = client_data.get('email', '')
        website = client_data.get('website_url', '')
        
        # Get services
        services = client_data.get('services', [])
        if isinstance(services, str):
            services = json.loads(services) if services else []
        services_text = ', '.join(services[:10]) if services else 'various services'
        
        # Get service areas
        service_areas = client_data.get('service_areas', [])
        if isinstance(service_areas, str):
            service_areas = json.loads(service_areas) if service_areas else []
        areas_text = ', '.join(service_areas[:10]) if service_areas else geo
        
        # Get USPs
        usps = client_data.get('unique_selling_points', [])
        if isinstance(usps, str):
            usps = json.loads(usps) if usps else []
        usps_text = '\n'.join([f"- {u}" for u in usps[:5]]) if usps else ''
        
        # Get FAQs if available
        faqs = client_data.get('faqs', [])
        faqs_text = ''
        if faqs:
            faqs_text = '\n\nCommon Questions:\n'
            for faq in faqs[:10]:
                if isinstance(faq, dict):
                    faqs_text += f"Q: {faq.get('question', '')}\nA: {faq.get('answer', '')}\n\n"
        
        # Get business hours
        hours = client_data.get('business_hours', '')
        hours_text = f"\nBusiness Hours: {hours}" if hours else ''
        
        prompt = f"""You are a friendly and helpful customer service assistant for {business_name}, a {industry} company located in {geo}.

ABOUT THE BUSINESS:
- Company: {business_name}
- Industry: {industry}
- Location: {geo}
- Service Areas: {areas_text}
- Services Offered: {services_text}
{hours_text}

CONTACT INFORMATION:
- Phone: {phone or 'Ask to leave contact info'}
- Email: {email or 'Ask to leave contact info'}
- Website: {website}

{f'WHAT MAKES US SPECIAL:{chr(10)}{usps_text}' if usps_text else ''}
{faqs_text}

YOUR ROLE:
1. Warmly greet visitors and help answer their questions about our services
2. Provide accurate information about what we offer and service areas
3. Encourage visitors to schedule a consultation or request a quote
4. Collect contact information (name, email, phone) when appropriate
5. If you don't know something specific, offer to have a team member follow up

GUIDELINES:
- Be friendly, professional, and concise
- Keep responses under 150 words unless more detail is needed
- Use the business name naturally in conversation
- If asked about pricing, explain that quotes are customized and offer to schedule a consultation
- If asked about availability, offer to check and ask for their preferred times
- For emergency services, provide the phone number immediately
- Never make up information - if unsure, say you'll have someone follow up
- Don't discuss competitors or make comparisons
- Stay focused on helping the visitor with their needs

Remember: Your goal is to be helpful, capture leads, and create a positive impression of {business_name}."""

        return prompt
    
    def build_mcp_support_prompt(self) -> str:
        """
        Build system prompt for the internal MCP support chatbot
        """
        return """You are the MCP Framework Support Assistant, helping users navigate and use the Marketing Control Platform effectively.

ABOUT MCP FRAMEWORK:
MCP (Marketing Control Platform) is an AI-powered SEO and content automation system for digital marketing agencies. It helps agencies manage multiple clients, generate SEO content, track rankings, monitor competitors, and capture leads.

KEY FEATURES YOU CAN HELP WITH:

1. DASHBOARDS:
   - Admin Dashboard: User management, settings, branding
   - Agency Dashboard: Overview of all clients, pending tasks
   - Client Dashboard: Content generation, blogs, social posts
   - Elite Dashboard: Advanced competitor monitoring, rank tracking
   - Intake Dashboard: New client onboarding
   - Portal Dashboard: Lead tracking and analytics

2. CONTENT GENERATION:
   - Blog posts (1500+ words, SEO-optimized)
   - Social media content (GBP, Facebook, Instagram)
   - Service pages
   - FAQ schema

3. SEO FEATURES:
   - Keyword research and tracking
   - Competitor monitoring
   - Rank history charts
   - Content gap analysis
   - Internal linking suggestions

4. LEAD MANAGEMENT:
   - Embeddable lead forms
   - Lead tracking dashboard
   - Email/SMS notifications
   - Conversion analytics

5. INTEGRATIONS:
   - WordPress publishing
   - SEMRush API
   - SendGrid email
   - Google Business Profile

COMMON QUESTIONS:
- "How do I generate a blog?" → Go to Client Dashboard > Blogs tab > Click Generate Blog
- "Where are my leads?" → Portal Dashboard shows all leads, or Client Dashboard > Overview
- "How do I add a client?" → Intake Dashboard for full setup, or Admin Dashboard > Clients
- "How do I publish to WordPress?" → Client Dashboard > Blogs > Select blog > Publish to WP

YOUR ROLE:
- Help users find features and navigate dashboards
- Explain how to use different tools
- Troubleshoot common issues
- Provide tips for better results
- Keep responses concise and actionable

If asked about something outside MCP, politely redirect to MCP-related help or suggest contacting support."""
    
    async def get_ai_response(
        self,
        messages: List[Dict],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> Dict:
        """
        Get AI response from OpenAI
        """
        if not self.openai_api_key:
            return {
                'content': "I'm having trouble connecting right now. Please leave your contact info and we'll get back to you shortly!",
                'tokens_used': 0,
                'response_time_ms': 0,
                'error': 'No API key configured'
            }
        
        try:
            import httpx
            
            start_time = time.time()
            
            # Build messages with system prompt
            full_messages = [
                {"role": "system", "content": system_prompt}
            ] + messages
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': self.model,
                        'messages': full_messages,
                        'temperature': temperature,
                        'max_tokens': max_tokens
                    }
                )
                
                response_time = int((time.time() - start_time) * 1000)
                
                if response.status_code != 200:
                    logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                    return {
                        'content': "I'm experiencing some technical difficulties. Please try again or leave your contact info!",
                        'tokens_used': 0,
                        'response_time_ms': response_time,
                        'error': f'API error: {response.status_code}'
                    }
                
                data = response.json()
                content = data['choices'][0]['message']['content']
                tokens = data.get('usage', {}).get('total_tokens', 0)
                
                return {
                    'content': content,
                    'tokens_used': tokens,
                    'response_time_ms': response_time
                }
                
        except Exception as e:
            logger.error(f"Chatbot AI error: {str(e)}")
            return {
                'content': "I'm having trouble responding right now. Please leave your contact info and someone will reach out soon!",
                'tokens_used': 0,
                'response_time_ms': 0,
                'error': str(e)
            }
    
    def get_ai_response_sync(
        self,
        messages: List[Dict],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> Dict:
        """
        Synchronous version of get_ai_response
        """
        if not self.openai_api_key:
            return {
                'content': "I'm having trouble connecting right now. Please leave your contact info and we'll get back to you shortly!",
                'tokens_used': 0,
                'response_time_ms': 0,
                'error': 'No API key configured'
            }
        
        try:
            import requests
            
            start_time = time.time()
            
            # Build messages with system prompt
            full_messages = [
                {"role": "system", "content": system_prompt}
            ] + messages
            
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.openai_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.model,
                    'messages': full_messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens
                },
                timeout=30
            )
            
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return {
                    'content': "I'm experiencing some technical difficulties. Please try again or leave your contact info!",
                    'tokens_used': 0,
                    'response_time_ms': response_time,
                    'error': f'API error: {response.status_code}'
                }
            
            data = response.json()
            content = data['choices'][0]['message']['content']
            tokens = data.get('usage', {}).get('total_tokens', 0)
            
            return {
                'content': content,
                'tokens_used': tokens,
                'response_time_ms': response_time
            }
            
        except Exception as e:
            logger.error(f"Chatbot AI error: {str(e)}")
            return {
                'content': "I'm having trouble responding right now. Please leave your contact info and someone will reach out soon!",
                'tokens_used': 0,
                'response_time_ms': 0,
                'error': str(e)
            }
    
    def check_faq_match(self, message: str, faqs: List[Dict]) -> Optional[str]:
        """
        Check if message matches any FAQ keywords
        Returns the FAQ answer if matched
        """
        message_lower = message.lower()
        
        for faq in faqs:
            keywords = faq.get('keywords', [])
            if isinstance(keywords, str):
                keywords = json.loads(keywords) if keywords else []
            
            # Check if any keyword is in the message
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    return faq.get('answer')
            
            # Also check question similarity
            question = faq.get('question', '').lower()
            # Simple word overlap check
            question_words = set(question.split())
            message_words = set(message_lower.split())
            overlap = len(question_words.intersection(message_words))
            if overlap >= 3:  # At least 3 words in common
                return faq.get('answer')
        
        return None
    
    def should_capture_lead(self, message_count: int, trigger: str) -> bool:
        """
        Determine if we should prompt for lead capture
        """
        if trigger == 'after_3_messages':
            return message_count >= 3
        elif trigger == 'after_5_messages':
            return message_count >= 5
        elif trigger == 'after_1_message':
            return message_count >= 1
        elif trigger == 'never':
            return False
        else:
            return message_count >= 3
    
    def get_lead_capture_message(self, collect_name: bool, collect_email: bool, collect_phone: bool) -> str:
        """
        Generate a natural lead capture prompt
        """
        fields = []
        if collect_name:
            fields.append("your name")
        if collect_email:
            fields.append("email")
        if collect_phone:
            fields.append("phone number")
        
        if not fields:
            return ""
        
        fields_text = ', '.join(fields[:-1])
        if len(fields) > 1:
            fields_text += f" and {fields[-1]}"
        else:
            fields_text = fields[0]
        
        return f"I'd love to help you further! Could you share {fields_text} so we can follow up with more details?"
    
    def format_conversation_for_ai(self, messages: List[Dict]) -> List[Dict]:
        """
        Format conversation messages for OpenAI API
        """
        formatted = []
        for msg in messages:
            role = msg.get('role', 'user')
            if role not in ['user', 'assistant', 'system']:
                role = 'user'
            formatted.append({
                'role': role,
                'content': msg.get('content', '')
            })
        return formatted
    
    def generate_embed_code(self, chatbot_id: str, base_url: str) -> str:
        """
        Generate the JavaScript embed code for client websites
        """
        return f'''<!-- MCP Chatbot Widget -->
<script>
(function() {{
    var script = document.createElement('script');
    script.src = '{base_url}/static/chatbot-widget.js';
    script.async = true;
    script.onload = function() {{
        MCPChatbot.init({{
            chatbotId: '{chatbot_id}',
            apiUrl: '{base_url}'
        }});
    }};
    document.head.appendChild(script);
}})();
</script>
<!-- End MCP Chatbot Widget -->'''


# Singleton instance
chatbot_service = ChatbotService()
