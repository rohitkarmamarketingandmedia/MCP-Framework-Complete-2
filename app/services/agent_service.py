"""
Karma Marketing + Media - Agent Service
Manages AI agent configurations, allowing prompt editing without code changes
"""
import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from app.database import db
from app.models.db_models import DBAgentConfig, DBAgentVersion

logger = logging.getLogger(__name__)


# ==========================================
# DEFAULT AGENT DEFINITIONS
# ==========================================

DEFAULT_AGENTS = [
    {
        'id': 'agent_content_writer',
        'name': 'content_writer',
        'display_name': 'Content Writer',
        'description': 'Writes SEO-optimized blog posts and articles',
        'category': 'content',
        'system_prompt': '''You are an expert SEO content writer for a digital marketing agency.

Your task is to write high-quality, SEO-optimized blog posts that:
1. Start every H1, H2, and H3 heading with the primary keyword + location
2. Include the primary keyword naturally 5-7 times throughout the content
3. Use secondary keywords where they fit naturally
4. Write in a {tone} tone appropriate for the {industry} industry
5. Include a compelling meta description (150-160 characters)
6. Structure content with clear sections and subheadings
7. End with a strong call-to-action mentioning the business name and location

Format your response as JSON:
{
    "title": "SEO-optimized title",
    "meta_description": "Compelling 150-160 char description",
    "content": "Full HTML content with h2, h3, p tags",
    "word_count": number,
    "keywords_used": ["list", "of", "keywords"]
}''',
        'output_format': '{"title": "string", "meta_description": "string", "content": "string (HTML)", "word_count": "number", "keywords_used": "array"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.7,
        'max_tokens': 4000,
        'tools_allowed': '[]'
    },
    {
        'id': 'agent_review_responder',
        'name': 'review_responder',
        'display_name': 'Review Responder',
        'description': 'Generates professional responses to customer reviews',
        'category': 'reviews',
        'system_prompt': '''You are a professional customer service representative responding to online reviews.

Guidelines:
1. Always thank the reviewer by name (if provided)
2. For positive reviews (4-5 stars): Express genuine gratitude, highlight specific praise they mentioned, invite them back
3. For negative reviews (1-2 stars): Apologize sincerely, acknowledge their concerns specifically, offer to make it right, provide contact info
4. For neutral reviews (3 stars): Thank them, address any concerns, highlight positives, invite them to return
5. Keep responses concise (2-4 sentences for positive, 3-5 for negative)
6. Include the business name naturally
7. Never be defensive or argumentative
8. Sign with a name and title

Tone: Professional, warm, and genuine. Match the formality of the original review.

Format your response as JSON:
{
    "response": "Your response text",
    "sentiment": "positive|negative|neutral",
    "tone_used": "description of tone",
    "follow_up_recommended": true/false
}''',
        'output_format': '{"response": "string", "sentiment": "positive|negative|neutral", "tone_used": "string", "follow_up_recommended": "boolean"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.6,
        'max_tokens': 500,
        'tools_allowed': '[]'
    },
    {
        'id': 'agent_seo_analyzer',
        'name': 'seo_analyzer',
        'display_name': 'SEO Analyzer',
        'description': 'Analyzes keyword opportunities and gaps',
        'category': 'seo',
        'system_prompt': '''You are an expert SEO analyst specializing in local search optimization.

Your task is to analyze keyword data and identify:
1. High-opportunity keywords (good volume, low competition, high relevance)
2. Quick wins (keywords where the client ranks 11-20 that could be pushed to page 1)
3. Content gaps (keywords competitors rank for but client doesn't)
4. Local keyword opportunities (service + location combinations)

Scoring criteria for keyword opportunity (0-100):
- Search volume: 0-30 points (higher = better)
- Competition: 0-30 points (lower = better)
- Relevance to business: 0-25 points
- Local intent: 0-15 points

Format your response as JSON:
{
    "top_opportunities": [
        {"keyword": "string", "score": number, "reason": "string", "recommended_action": "string"}
    ],
    "quick_wins": [
        {"keyword": "string", "current_position": number, "potential": "string"}
    ],
    "content_gaps": [
        {"keyword": "string", "competitor": "string", "priority": "high|medium|low"}
    ],
    "summary": "Overall analysis summary"
}''',
        'output_format': '{"top_opportunities": "array", "quick_wins": "array", "content_gaps": "array", "summary": "string"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.3,
        'max_tokens': 2000,
        'tools_allowed': '[]'
    },
    {
        'id': 'agent_competitor_analyzer',
        'name': 'competitor_analyzer',
        'display_name': 'Competitor Analyzer',
        'description': 'Analyzes competitor websites and strategies',
        'category': 'seo',
        'system_prompt': '''You are a competitive intelligence analyst specializing in digital marketing.

Your task is to analyze competitor data and identify:
1. Competitor strengths (what they do well)
2. Competitor weaknesses (opportunities for the client)
3. Content strategies (what topics/formats they focus on)
4. Keyword gaps (what they rank for that client doesn't)
5. Actionable recommendations

Focus on practical, implementable insights that can improve the client's competitive position.

Format your response as JSON:
{
    "competitors_analyzed": ["list of competitors"],
    "key_insights": [
        {"insight": "string", "impact": "high|medium|low", "action": "string"}
    ],
    "content_opportunities": [
        {"topic": "string", "competitor_coverage": "string", "recommendation": "string"}
    ],
    "competitive_advantages": ["client strengths to leverage"],
    "threats": ["competitive threats to address"],
    "priority_actions": ["top 3-5 recommended actions"]
}''',
        'output_format': '{"competitors_analyzed": "array", "key_insights": "array", "content_opportunities": "array", "competitive_advantages": "array", "threats": "array", "priority_actions": "array"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.4,
        'max_tokens': 2500,
        'tools_allowed': '[]'
    },
    {
        'id': 'agent_social_writer',
        'name': 'social_writer',
        'display_name': 'Social Media Writer',
        'description': 'Creates engaging social media posts',
        'category': 'social',
        'system_prompt': '''You are a social media marketing expert creating engaging posts for local businesses.

Guidelines by platform:
- Facebook: 1-2 paragraphs, can be longer, include call-to-action
- Instagram: Shorter, emoji-friendly, hashtag-focused
- LinkedIn: Professional tone, industry insights, thought leadership
- Twitter/X: Concise, punchy, under 280 characters

All posts should:
1. Be relevant to the business's industry and location
2. Include a clear call-to-action when appropriate
3. Feel authentic and human (not corporate/robotic)
4. Encourage engagement (questions, polls, opinions)

Format your response as JSON:
{
    "post": "The main post content",
    "hashtags": ["relevant", "hashtags"],
    "call_to_action": "CTA if applicable",
    "best_posting_time": "recommended time/day",
    "engagement_hook": "what makes this engaging"
}''',
        'output_format': '{"post": "string", "hashtags": "array", "call_to_action": "string", "best_posting_time": "string", "engagement_hook": "string"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.8,
        'max_tokens': 800,
        'tools_allowed': '[]'
    },
    {
        'id': 'agent_service_page_writer',
        'name': 'service_page_writer',
        'display_name': 'Service Page Writer',
        'description': 'Creates location/service landing pages',
        'category': 'content',
        'system_prompt': '''You are an expert at creating high-converting service area pages for local businesses.

Your task is to write SEO-optimized service pages that:
1. Target a specific service + location combination
2. Start EVERY heading (H1, H2, H3) with the keyword + location
3. Include local landmarks, neighborhoods, or references when possible
4. Address common customer pain points and questions
5. Include trust signals (experience, certifications, guarantees)
6. Have a strong, location-specific call-to-action
7. Be 800-1200 words for optimal SEO

Structure:
- H1: [Keyword] in [Location] - [Benefit]
- Intro paragraph with keyword + location in first sentence
- H2: Why Choose [Business] for [Keyword] in [Location]
- H2: Our [Keyword] Services in [Location]
- H2: [Location] [Keyword] FAQ (3-5 questions)
- H2: Get [Keyword] in [Location] Today (CTA section)

Format your response as JSON:
{
    "title": "Page title",
    "meta_description": "150-160 character description",
    "h1": "Main heading",
    "content": "Full HTML content",
    "faqs": [{"question": "string", "answer": "string"}],
    "schema_data": {"@type": "Service", ...}
}''',
        'output_format': '{"title": "string", "meta_description": "string", "h1": "string", "content": "string (HTML)", "faqs": "array", "schema_data": "object"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.6,
        'max_tokens': 3000,
        'tools_allowed': '[]'
    },
    {
        'id': 'agent_intake_analyzer',
        'name': 'intake_analyzer',
        'display_name': 'Intake Analyzer',
        'description': 'Analyzes new client intake data and generates recommendations',
        'category': 'intake',
        'system_prompt': '''You are a digital marketing strategist analyzing a new client's business for SEO and content opportunities.

Given information about a business, analyze and provide:
1. Initial keyword opportunities based on their industry and location
2. Competitor identification and analysis
3. Content strategy recommendations
4. Quick wins they can implement immediately
5. Long-term growth opportunities

Be specific and actionable. Avoid generic advice.

Format your response as JSON:
{
    "business_summary": "1-2 sentence summary of their business",
    "primary_keywords": ["top 5-10 keyword recommendations"],
    "secondary_keywords": ["supporting keywords"],
    "competitors": ["likely competitors to track"],
    "content_priorities": [
        {"type": "blog|service_page|social", "topic": "string", "priority": "high|medium|low", "reason": "string"}
    ],
    "quick_wins": ["immediate actions"],
    "strategy_notes": "Overall strategic recommendations"
}''',
        'output_format': '{"business_summary": "string", "primary_keywords": "array", "secondary_keywords": "array", "competitors": "array", "content_priorities": "array", "quick_wins": "array", "strategy_notes": "string"}',
        'model': 'gpt-4o-mini',
        'temperature': 0.5,
        'max_tokens': 2000,
        'tools_allowed': '[]'
    }
]


class AgentService:
    """Service for managing AI agent configurations"""
    
    def __init__(self):
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    
    def initialize_default_agents(self) -> int:
        """Create default agents if they don't exist"""
        created = 0
        for agent_def in DEFAULT_AGENTS:
            existing = DBAgentConfig.query.filter_by(name=agent_def['name']).first()
            if not existing:
                agent = DBAgentConfig(
                    id=agent_def['id'],
                    name=agent_def['name'],
                    display_name=agent_def['display_name'],
                    description=agent_def['description'],
                    category=agent_def['category'],
                    system_prompt=agent_def['system_prompt'],
                    output_format=agent_def['output_format'],
                    model=agent_def['model'],
                    temperature=agent_def['temperature'],
                    max_tokens=agent_def['max_tokens'],
                    tools_allowed=agent_def['tools_allowed'],
                    is_active=True,
                    version=1,
                    created_at=datetime.utcnow()
                )
                db.session.add(agent)
                created += 1
        
        if created > 0:
            try:
                db.session.commit()
                logger.info(f"Initialized {created} default agents")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to initialize agents: {e}")
                raise
        
        return created
    
    def get_agent(self, name: str) -> Optional[DBAgentConfig]:
        """Get agent config by name"""
        return DBAgentConfig.query.filter_by(name=name, is_active=True).first()
    
    def get_agent_by_id(self, agent_id: str) -> Optional[DBAgentConfig]:
        """Get agent config by ID"""
        return DBAgentConfig.query.get(agent_id)
    
    def get_all_agents(self, category: str = None) -> List[DBAgentConfig]:
        """Get all agents, optionally filtered by category"""
        query = DBAgentConfig.query
        if category:
            query = query.filter_by(category=category)
        return query.order_by(DBAgentConfig.category, DBAgentConfig.name).all()
    
    def get_prompt(self, agent_name: str, **variables) -> Optional[str]:
        """
        Get an agent's system prompt with variable substitution
        
        Args:
            agent_name: Name of the agent
            **variables: Variables to substitute (e.g., tone='professional', industry='HVAC')
            
        Returns:
            Formatted system prompt or None if agent not found
        """
        agent = self.get_agent(agent_name)
        if not agent:
            logger.warning(f"Agent not found: {agent_name}")
            return None
        
        prompt = agent.system_prompt
        
        # Substitute variables like {tone}, {industry}, etc.
        for key, value in variables.items():
            prompt = prompt.replace(f'{{{key}}}', str(value))
        
        return prompt
    
    def update_agent(
        self,
        agent_id: str,
        updates: Dict[str, Any],
        changed_by: str = None,
        change_note: str = None
    ) -> Dict:
        """
        Update an agent's configuration
        
        Args:
            agent_id: Agent ID
            updates: Dict of fields to update
            changed_by: Email of user making change
            change_note: Note about what changed
            
        Returns:
            Updated agent or error
        """
        agent = DBAgentConfig.query.get(agent_id)
        if not agent:
            return {'error': 'Agent not found'}
        
        # Save version history before updating
        version = DBAgentVersion(
            agent_id=agent.id,
            version=agent.version,
            system_prompt=agent.system_prompt,
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            output_format=agent.output_format,
            changed_by=changed_by,
            change_note=change_note or 'Configuration updated',
            created_at=datetime.utcnow()
        )
        db.session.add(version)
        
        # Apply updates
        allowed_fields = [
            'display_name', 'description', 'system_prompt', 'output_format',
            'output_example', 'model', 'temperature', 'max_tokens', 'is_active'
        ]
        
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(agent, field, value)
        
        if 'tools_allowed' in updates:
            if isinstance(updates['tools_allowed'], list):
                agent.set_tools(updates['tools_allowed'])
            else:
                agent.tools_allowed = updates['tools_allowed']
        
        agent.version += 1
        agent.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
            logger.info(f"Updated agent {agent.name} to version {agent.version}")
            return {'agent': agent.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update agent: {e}")
            return {'error': str(e)}
    
    def get_version_history(self, agent_id: str, limit: int = 10) -> List[DBAgentVersion]:
        """Get version history for an agent"""
        return DBAgentVersion.query.filter_by(agent_id=agent_id)\
            .order_by(DBAgentVersion.version.desc())\
            .limit(limit).all()
    
    def rollback_to_version(self, agent_id: str, version_id: int, changed_by: str = None) -> Dict:
        """Rollback an agent to a previous version"""
        agent = DBAgentConfig.query.get(agent_id)
        if not agent:
            return {'error': 'Agent not found'}
        
        version = DBAgentVersion.query.get(version_id)
        if not version or version.agent_id != agent_id:
            return {'error': 'Version not found'}
        
        # Save current state as new version before rollback
        current_version = DBAgentVersion(
            agent_id=agent.id,
            version=agent.version,
            system_prompt=agent.system_prompt,
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            output_format=agent.output_format,
            changed_by=changed_by,
            change_note=f'Before rollback to version {version.version}',
            created_at=datetime.utcnow()
        )
        db.session.add(current_version)
        
        # Apply rollback
        agent.system_prompt = version.system_prompt
        agent.model = version.model
        agent.temperature = version.temperature
        agent.max_tokens = version.max_tokens
        agent.output_format = version.output_format
        agent.version += 1
        agent.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
            logger.info(f"Rolled back agent {agent.name} to version {version.version}")
            return {'agent': agent.to_dict(), 'rolled_back_to': version.version}
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}
    
    def test_agent(
        self,
        agent_id: str,
        test_input: str,
        variables: Dict[str, str] = None
    ) -> Dict:
        """
        Test an agent with sample input
        
        Args:
            agent_id: Agent ID to test
            test_input: Sample input to send to the agent
            variables: Variables to substitute in the prompt
            
        Returns:
            Agent output or error
        """
        agent = DBAgentConfig.query.get(agent_id)
        if not agent:
            return {'error': 'Agent not found'}
        
        # Get the prompt with variable substitution
        prompt = agent.system_prompt
        if variables:
            for key, value in variables.items():
                prompt = prompt.replace(f'{{{key}}}', str(value))
        
        # Determine which API to use based on model
        model = agent.model.lower()
        
        try:
            if 'claude' in model or 'anthropic' in model:
                result = self._call_anthropic(
                    prompt=prompt,
                    user_input=test_input,
                    model=agent.model,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens
                )
            else:
                result = self._call_openai(
                    prompt=prompt,
                    user_input=test_input,
                    model=agent.model,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens
                )
            
            # Try to parse as JSON
            output = result
            is_valid_json = False
            try:
                parsed = json.loads(result)
                output = parsed
                is_valid_json = True
            except Exception as e:
                pass
            
            return {
                'success': True,
                'agent': agent.name,
                'model': agent.model,
                'output': output,
                'is_valid_json': is_valid_json,
                'raw_output': result,
                'tokens_used': len(result.split()) * 1.3  # Rough estimate
            }
            
        except Exception as e:
            logger.error(f"Agent test failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'agent': agent.name
            }
    
    def _call_openai(
        self,
        prompt: str,
        user_input: str,
        model: str = 'gpt-4o-mini',
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """Call OpenAI API"""
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY not configured")
        
        import openai
        client = openai.OpenAI(api_key=self.openai_key)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content
    
    def _call_anthropic(
        self,
        prompt: str,
        user_input: str,
        model: str = 'claude-3-haiku-20240307',
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """Call Anthropic API"""
        if not self.anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        
        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=prompt,
            messages=[
                {"role": "user", "content": user_input}
            ]
        )
        
        return response.content[0].text
    
    def duplicate_agent(self, agent_id: str, new_name: str, new_display_name: str) -> Dict:
        """Create a copy of an agent (for A/B testing)"""
        agent = DBAgentConfig.query.get(agent_id)
        if not agent:
            return {'error': 'Agent not found'}
        
        # Check if name already exists
        if DBAgentConfig.query.filter_by(name=new_name).first():
            return {'error': f'Agent with name {new_name} already exists'}
        
        new_agent = DBAgentConfig(
            id=f'agent_{uuid.uuid4().hex[:12]}',
            name=new_name,
            display_name=new_display_name,
            description=f'Copy of {agent.display_name}',
            category=agent.category,
            system_prompt=agent.system_prompt,
            output_format=agent.output_format,
            output_example=agent.output_example,
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            tools_allowed=agent.tools_allowed,
            is_active=True,
            version=1,
            created_at=datetime.utcnow()
        )
        
        try:
            db.session.add(new_agent)
            db.session.commit()
            return {'agent': new_agent.to_dict()}
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}


# Singleton instance
agent_service = AgentService()
