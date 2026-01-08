"""
MCP Framework - Customer Interaction Intelligence Service
Analyzes CallRail transcripts, chatbot conversations, and lead forms
to extract questions, pain points, keywords, and content opportunities

This is the GOLDMINE - turning every customer interaction into content
"""
import os
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
from dataclasses import dataclass, field

from app.database import db
from app.models.db_models import DBClient, DBLead, DBBlogPost

logger = logging.getLogger(__name__)


@dataclass
class ExtractedQuestion:
    """A question extracted from customer interaction"""
    question: str
    source: str  # 'call', 'chat', 'form'
    source_id: str
    timestamp: datetime
    context: str = ""
    frequency: int = 1
    keywords: List[str] = field(default_factory=list)


@dataclass
class PainPoint:
    """A pain point/concern identified from interactions"""
    description: str
    source: str
    frequency: int = 1
    sentiment: str = "neutral"  # negative, neutral, concerned
    related_service: str = ""


@dataclass
class ContentOpportunity:
    """A content opportunity identified from interactions"""
    topic: str
    content_type: str  # 'blog', 'faq', 'service_page', 'video'
    source_questions: List[str]
    keywords: List[str]
    priority: int  # 1-10 based on frequency and relevance
    suggested_title: str
    outline: List[str]


class InteractionIntelligenceService:
    """
    Analyze customer interactions to extract valuable content opportunities
    
    Sources:
    - CallRail transcripts (phone calls)
    - Chatbot conversations
    - Lead form submissions
    - Email inquiries (future)
    
    Outputs:
    - Common questions asked
    - Pain points and concerns
    - Keywords customers actually use
    - Content topics that matter
    - FAQ content from real Q&A
    - Service page enhancements
    """
    
    # Question indicators
    QUESTION_PATTERNS = [
        r'\b(how much|how long|how do|how can|how does)\b',
        r'\b(what is|what are|what does|what do|what\'s)\b',
        r'\b(when do|when can|when will|when should)\b',
        r'\b(where do|where can|where is)\b',
        r'\b(why do|why does|why is|why should)\b',
        r'\b(can you|can i|could you|could i|will you)\b',
        r'\b(do you|does it|is it|is there|are there)\b',
        r'\b(should i|would you|is this)\b',
        r'\?',  # Direct questions
    ]
    
    # Pain point indicators
    PAIN_INDICATORS = [
        r'\b(problem|issue|trouble|broken|not working|failed|failing)\b',
        r'\b(frustrated|annoyed|upset|worried|concerned|scared)\b',
        r'\b(expensive|costly|too much|afford|budget)\b',
        r'\b(emergency|urgent|asap|immediately|right away)\b',
        r'\b(bad|terrible|awful|horrible|worst)\b',
        r'\b(don\'t understand|confused|unsure|not sure)\b',
        r'\b(waited|waiting|delayed|slow)\b',
        r'\b(scam|rip off|overcharged|dishonest)\b',
    ]
    
    # Service-related keywords by industry
    INDUSTRY_KEYWORDS = {
        'hvac': [
            'air conditioning', 'ac', 'heating', 'furnace', 'heat pump',
            'thermostat', 'ductwork', 'refrigerant', 'freon', 'compressor',
            'maintenance', 'tune-up', 'filter', 'installation', 'repair',
            'replacement', 'efficiency', 'seer', 'humidity', 'ventilation'
        ],
        'plumbing': [
            'leak', 'drain', 'clog', 'pipe', 'water heater', 'toilet',
            'faucet', 'sewer', 'septic', 'garbage disposal', 'water pressure',
            'backup', 'flooding', 'burst pipe', 'tankless', 'repiping'
        ],
        'electrical': [
            'outlet', 'circuit', 'breaker', 'panel', 'wiring', 'lighting',
            'generator', 'surge protector', 'electrical fire', 'flickering',
            'power outage', 'rewiring', 'code', 'inspection', 'ev charger'
        ],
        'dental': [
            'teeth', 'tooth', 'crown', 'filling', 'root canal', 'extraction',
            'cleaning', 'whitening', 'implant', 'dentures', 'braces', 'invisalign',
            'cavity', 'gum', 'periodontal', 'emergency', 'pain', 'sensitivity'
        ],
        'medical': [
            'appointment', 'consultation', 'treatment', 'diagnosis', 'symptoms',
            'insurance', 'coverage', 'specialist', 'referral', 'prescription',
            'follow-up', 'test', 'results', 'procedure', 'surgery', 'recovery'
        ],
        'real_estate': [
            'listing', 'showing', 'offer', 'closing', 'inspection', 'appraisal',
            'mortgage', 'pre-approval', 'commission', 'contract', 'escrow',
            'contingency', 'negotiation', 'market', 'price', 'neighborhood'
        ],
        'legal': [
            'consultation', 'case', 'lawsuit', 'settlement', 'court', 'trial',
            'deposition', 'discovery', 'representation', 'fees', 'retainer',
            'contract', 'liability', 'damages', 'defense', 'prosecution'
        ]
    }
    
    def __init__(self):
        pass  # API key read at runtime via property
    
    @property
    def openai_api_key(self):
        return os.environ.get('OPENAI_API_KEY', '')
    
    # ==========================================
    # CALL TRANSCRIPT ANALYSIS
    # ==========================================
    
    def analyze_call_transcript(self, transcript: str, client_id: str = None) -> Dict[str, Any]:
        """
        Analyze a single call transcript to extract intelligence
        
        Returns:
            {
                'questions': [...],
                'pain_points': [...],
                'keywords': [...],
                'services_mentioned': [...],
                'sentiment': 'positive/negative/neutral',
                'summary': '...',
                'content_opportunities': [...]
            }
        """
        if not transcript:
            return {'error': 'No transcript provided'}
        
        # Get client's industry for keyword matching
        industry = None
        if client_id:
            client = DBClient.query.get(client_id)
            if client:
                industry = client.industry.lower() if client.industry else None
        
        # Extract questions
        questions = self._extract_questions(transcript)
        
        # Identify pain points
        pain_points = self._extract_pain_points(transcript)
        
        # Extract keywords
        keywords = self._extract_keywords(transcript, industry)
        
        # Identify services mentioned
        services = self._extract_services(transcript, industry)
        
        # Analyze sentiment
        sentiment = self._analyze_sentiment(transcript)
        
        # Generate summary using AI if available
        summary = self._generate_call_summary(transcript)
        
        return {
            'questions': questions,
            'pain_points': pain_points,
            'keywords': keywords,
            'services_mentioned': services,
            'sentiment': sentiment,
            'summary': summary,
            'word_count': len(transcript.split())
        }
    
    def analyze_multiple_calls(self, transcripts: List[Dict], client_id: str) -> Dict[str, Any]:
        """
        Analyze multiple call transcripts to find patterns
        
        Args:
            transcripts: List of {'id': str, 'transcript': str, 'date': datetime}
            client_id: Client ID
        
        Returns:
            Aggregated analysis with top questions, common pain points, trending keywords
        """
        all_questions = []
        all_pain_points = []
        all_keywords = []
        all_services = []
        
        for call in transcripts:
            if not call.get('transcript'):
                continue
            
            analysis = self.analyze_call_transcript(call['transcript'], client_id)
            
            for q in analysis.get('questions', []):
                all_questions.append({
                    'question': q,
                    'source': 'call',
                    'source_id': call.get('id'),
                    'date': call.get('date')
                })
            
            all_pain_points.extend(analysis.get('pain_points', []))
            all_keywords.extend(analysis.get('keywords', []))
            all_services.extend(analysis.get('services_mentioned', []))
        
        # Aggregate and rank
        question_counts = Counter([q['question'].lower() for q in all_questions])
        pain_counts = Counter(all_pain_points)
        keyword_counts = Counter(all_keywords)
        service_counts = Counter(all_services)
        
        return {
            'total_calls_analyzed': len(transcripts),
            'top_questions': [
                {'question': q, 'count': c} 
                for q, c in question_counts.most_common(20)
            ],
            'top_pain_points': [
                {'pain_point': p, 'count': c}
                for p, c in pain_counts.most_common(10)
            ],
            'top_keywords': [
                {'keyword': k, 'count': c}
                for k, c in keyword_counts.most_common(30)
            ],
            'services_requested': [
                {'service': s, 'count': c}
                for s, c in service_counts.most_common(15)
            ],
            'all_questions': all_questions
        }
    
    # ==========================================
    # CHATBOT CONVERSATION ANALYSIS
    # ==========================================
    
    def analyze_chatbot_conversations(self, client_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Analyze chatbot conversations to extract questions and topics
        """
        from app.models.db_models import DBChatConversation, DBChatMessage
        
        period_start = datetime.utcnow() - timedelta(days=days)
        
        conversations = DBChatConversation.query.filter(
            DBChatConversation.client_id == client_id,
            DBChatConversation.started_at >= period_start
        ).all()
        
        all_questions = []
        all_topics = []
        all_keywords = []
        
        for conv in conversations:
            # Get messages for this conversation
            messages = DBChatMessage.query.filter(
                DBChatMessage.conversation_id == conv.id,
                DBChatMessage.role == 'user'
            ).all()
            
            for msg in messages:
                content = msg.content or ''
                
                # Extract questions
                questions = self._extract_questions(content)
                for q in questions:
                    all_questions.append({
                        'question': q,
                        'source': 'chatbot',
                        'source_id': conv.id,
                        'date': conv.started_at
                    })
                
                # Extract keywords
                client = DBClient.query.get(client_id)
                industry = client.industry.lower() if client and client.industry else None
                keywords = self._extract_keywords(content, industry)
                all_keywords.extend(keywords)
        
        # Aggregate
        question_counts = Counter([q['question'].lower() for q in all_questions])
        keyword_counts = Counter(all_keywords)
        
        return {
            'total_conversations': len(conversations),
            'top_questions': [
                {'question': q, 'count': c}
                for q, c in question_counts.most_common(20)
            ],
            'top_keywords': [
                {'keyword': k, 'count': c}
                for k, c in keyword_counts.most_common(30)
            ],
            'all_questions': all_questions
        }
    
    # ==========================================
    # LEAD FORM ANALYSIS
    # ==========================================
    
    def analyze_lead_forms(self, client_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Analyze lead form submissions to extract service requests and questions
        """
        period_start = datetime.utcnow() - timedelta(days=days)
        
        leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= period_start
        ).all()
        
        all_services = []
        all_questions = []
        all_keywords = []
        sources = []
        
        for lead in leads:
            # Service requested
            if lead.service_requested:
                all_services.append(lead.service_requested)
            
            # Analyze message/notes for questions
            message = lead.notes or lead.message if hasattr(lead, 'message') else ''
            if message:
                questions = self._extract_questions(message)
                for q in questions:
                    all_questions.append({
                        'question': q,
                        'source': 'form',
                        'source_id': lead.id,
                        'date': lead.created_at
                    })
                
                # Extract keywords
                client = DBClient.query.get(client_id)
                industry = client.industry.lower() if client and client.industry else None
                keywords = self._extract_keywords(message, industry)
                all_keywords.extend(keywords)
            
            # Track source
            if lead.source:
                sources.append(lead.source)
        
        # Aggregate
        service_counts = Counter(all_services)
        question_counts = Counter([q['question'].lower() for q in all_questions])
        keyword_counts = Counter(all_keywords)
        source_counts = Counter(sources)
        
        return {
            'total_leads': len(leads),
            'services_requested': [
                {'service': s, 'count': c}
                for s, c in service_counts.most_common(15)
            ],
            'questions_from_forms': [
                {'question': q, 'count': c}
                for q, c in question_counts.most_common(15)
            ],
            'top_keywords': [
                {'keyword': k, 'count': c}
                for k, c in keyword_counts.most_common(20)
            ],
            'lead_sources': dict(source_counts),
            'all_questions': all_questions
        }
    
    # ==========================================
    # COMBINED ANALYSIS
    # ==========================================
    
    def get_full_intelligence_report(
        self,
        client_id: str,
        call_transcripts: List[Dict] = None,
        days: int = 30,
        all_calls: List[Dict] = None  # Add all calls for metadata analysis
    ) -> Dict[str, Any]:
        """
        Get comprehensive intelligence report from all sources
        
        Combines:
        - Call transcript analysis
        - Call metadata analysis (when no transcripts)
        - Chatbot conversations
        - Lead form submissions
        
        Returns unified insights and content opportunities
        """
        report = {
            'client_id': client_id,
            'period_days': days,
            'generated_at': datetime.utcnow().isoformat(),
            'sources': {},
            'combined_insights': {},
            'content_opportunities': [],
            'transcript_status': 'none'  # none, partial, full
        }
        
        all_questions = []
        all_keywords = []
        all_pain_points = []
        all_services = []
        
        # Analyze calls if provided
        if call_transcripts:
            call_analysis = self.analyze_multiple_calls(call_transcripts, client_id)
            report['sources']['calls'] = {
                'count': call_analysis['total_calls_analyzed'],
                'top_questions': call_analysis['top_questions'][:10],
                'top_pain_points': call_analysis['top_pain_points'][:5]
            }
            all_questions.extend(call_analysis.get('all_questions', []))
            all_keywords.extend([k['keyword'] for k in call_analysis.get('top_keywords', [])])
            all_pain_points.extend([p['pain_point'] for p in call_analysis.get('top_pain_points', [])])
            all_services.extend([s['service'] for s in call_analysis.get('services_requested', [])])
            report['transcript_status'] = 'full' if len(call_transcripts) > 5 else 'partial'
        
        # Analyze chatbot
        try:
            chat_analysis = self.analyze_chatbot_conversations(client_id, days)
            report['sources']['chatbot'] = {
                'count': chat_analysis['total_conversations'],
                'top_questions': chat_analysis['top_questions'][:10]
            }
            all_questions.extend(chat_analysis.get('all_questions', []))
            all_keywords.extend([k['keyword'] for k in chat_analysis.get('top_keywords', [])])
        except Exception as e:
            logger.warning(f"Could not analyze chatbot: {e}")
        
        # Analyze lead forms
        try:
            form_analysis = self.analyze_lead_forms(client_id, days)
            report['sources']['forms'] = {
                'count': form_analysis['total_leads'],
                'services_requested': form_analysis['services_requested'][:10],
                'questions': form_analysis['questions_from_forms'][:10]
            }
            all_questions.extend(form_analysis.get('all_questions', []))
            all_keywords.extend([k['keyword'] for k in form_analysis.get('top_keywords', [])])
            all_services.extend([s['service'] for s in form_analysis.get('services_requested', [])])
        except Exception as e:
            logger.warning(f"Could not analyze forms: {e}")
        
        # Combine and rank everything
        question_counts = Counter([q['question'].lower() for q in all_questions])
        keyword_counts = Counter(all_keywords)
        service_counts = Counter(all_services)
        pain_counts = Counter(all_pain_points)
        
        report['combined_insights'] = {
            'top_questions': [
                {'question': q, 'count': c, 'sources': self._get_question_sources(q, all_questions)}
                for q, c in question_counts.most_common(25)
            ],
            'top_keywords': [
                {'keyword': k, 'count': c}
                for k, c in keyword_counts.most_common(40)
            ],
            'top_services': [
                {'service': s, 'count': c}
                for s, c in service_counts.most_common(15)
            ],
            'top_pain_points': [
                {'pain_point': p, 'count': c}
                for p, c in pain_counts.most_common(10)
            ],
            'total_interactions': (
                report['sources'].get('calls', {}).get('count', 0) +
                report['sources'].get('chatbot', {}).get('count', 0) +
                report['sources'].get('forms', {}).get('count', 0)
            )
        }
        
        # Generate content opportunities
        report['content_opportunities'] = self._generate_content_opportunities(
            report['combined_insights'],
            client_id
        )
        
        return report
    
    def _get_question_sources(self, question: str, all_questions: List[Dict]) -> List[str]:
        """Get which sources a question came from"""
        sources = set()
        for q in all_questions:
            if q['question'].lower() == question.lower():
                sources.add(q['source'])
        return list(sources)
    
    # ==========================================
    # EXTRACTION HELPERS
    # ==========================================
    
    def _extract_questions(self, text: str) -> List[str]:
        """Extract questions from text"""
        questions = []
        
        # Split into sentences
        sentences = re.split(r'[.!?\n]', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 10:
                continue
            
            # Check if it's a question
            is_question = False
            for pattern in self.QUESTION_PATTERNS:
                if re.search(pattern, sentence.lower()):
                    is_question = True
                    break
            
            if is_question:
                # Clean up the question
                question = sentence.strip()
                if not question.endswith('?'):
                    question += '?'
                questions.append(question)
        
        return questions
    
    def _extract_pain_points(self, text: str) -> List[str]:
        """Extract pain points and concerns from text"""
        pain_points = []
        text_lower = text.lower()
        
        # Split into sentences
        sentences = re.split(r'[.!?\n]', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Check for pain indicators
            for pattern in self.PAIN_INDICATORS:
                if re.search(pattern, sentence.lower()):
                    # Extract the pain point context
                    pain_points.append(sentence[:100])  # Limit length
                    break
        
        return pain_points
    
    def _extract_keywords(self, text: str, industry: str = None) -> List[str]:
        """Extract relevant keywords from text"""
        keywords = []
        text_lower = text.lower()
        
        # Get industry-specific keywords
        industry_kws = []
        if industry and industry in self.INDUSTRY_KEYWORDS:
            industry_kws = self.INDUSTRY_KEYWORDS[industry]
        else:
            # Use all industry keywords if no specific industry
            for kws in self.INDUSTRY_KEYWORDS.values():
                industry_kws.extend(kws)
        
        # Find industry keywords in text
        for kw in industry_kws:
            if kw.lower() in text_lower:
                keywords.append(kw)
        
        # Extract noun phrases (simple approach)
        # In production, would use NLP library like spaCy
        words = text_lower.split()
        for i, word in enumerate(words):
            if len(word) > 4 and word.isalpha():
                # Check if it's a meaningful word
                if word not in ['about', 'would', 'could', 'should', 'there', 'their', 'where', 'which', 'these', 'those']:
                    keywords.append(word)
        
        return keywords
    
    def _extract_services(self, text: str, industry: str = None) -> List[str]:
        """Extract service mentions from text"""
        services = []
        text_lower = text.lower()
        
        # Common service patterns
        service_patterns = [
            r'\b(repair|fix|replace|install|maintenance|service|check|inspect)\s+(?:my|the|a|an)?\s*(\w+)',
            r'\b(need|want|looking for|interested in)\s+(?:a|an)?\s*(\w+\s*\w*)\s*(repair|service|installation|replacement)?',
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if isinstance(match, tuple):
                    service = ' '.join(m for m in match if m).strip()
                else:
                    service = match.strip()
                if service and len(service) > 3:
                    services.append(service)
        
        return services
    
    def _analyze_sentiment(self, text: str) -> str:
        """Simple sentiment analysis"""
        text_lower = text.lower()
        
        positive_words = ['thank', 'great', 'excellent', 'happy', 'satisfied', 'recommend', 'best', 'wonderful', 'appreciate']
        negative_words = ['problem', 'issue', 'terrible', 'awful', 'worst', 'frustrated', 'angry', 'disappointed', 'horrible']
        
        positive_count = sum(1 for w in positive_words if w in text_lower)
        negative_count = sum(1 for w in negative_words if w in text_lower)
        
        if positive_count > negative_count + 1:
            return 'positive'
        elif negative_count > positive_count + 1:
            return 'negative'
        else:
            return 'neutral'
    
    def _generate_call_summary(self, transcript: str) -> str:
        """Generate a brief summary of the call"""
        # Simple extractive summary - first 2-3 meaningful sentences
        sentences = re.split(r'[.!?]', transcript)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 30]
        
        if meaningful:
            return '. '.join(meaningful[:3]) + '.'
        return ""
    
    # ==========================================
    # CONTENT OPPORTUNITY GENERATION
    # ==========================================
    
    def _generate_content_opportunities(
        self,
        insights: Dict[str, Any],
        client_id: str
    ) -> List[Dict[str, Any]]:
        """
        Generate content opportunities from insights
        
        Types of content:
        1. FAQ page from top questions
        2. Blog posts addressing common concerns
        3. Service page enhancements
        4. "What Customers Ask" sections
        """
        opportunities = []
        
        top_questions = insights.get('top_questions', [])
        top_pain_points = insights.get('top_pain_points', [])
        top_services = insights.get('top_services', [])
        
        # Get client for context
        client = DBClient.query.get(client_id)
        business_name = client.business_name if client else "Your Business"
        geo = client.geo if client else ""
        
        # Opportunity 1: FAQ Page from Real Questions
        if len(top_questions) >= 5:
            opportunities.append({
                'type': 'faq_page',
                'priority': 10,
                'title': f"Frequently Asked Questions | {business_name}",
                'description': f"FAQ page with {len(top_questions)} real questions from customers",
                'questions': [q['question'] for q in top_questions[:15]],
                'estimated_words': 1500,
                'seo_value': 'high',
                'source': 'customer_interactions'
            })
        
        # Opportunity 2: Blog Posts from Question Clusters
        # Group similar questions into blog topics
        question_clusters = self._cluster_questions(top_questions)
        for i, cluster in enumerate(question_clusters[:5]):
            opportunities.append({
                'type': 'blog_post',
                'priority': 9 - i,
                'title': cluster['suggested_title'],
                'description': f"Blog answering {len(cluster['questions'])} related customer questions",
                'questions': cluster['questions'],
                'keywords': cluster['keywords'],
                'estimated_words': 1800,
                'seo_value': 'high',
                'outline': cluster['outline']
            })
        
        # Opportunity 3: Pain Point Solution Posts
        for i, pain in enumerate(top_pain_points[:3]):
            opportunities.append({
                'type': 'blog_post',
                'priority': 7 - i,
                'title': f"How to Solve {pain['pain_point'].title()} {geo}",
                'description': f"Address common customer pain point: {pain['pain_point']}",
                'pain_point': pain['pain_point'],
                'frequency': pain['count'],
                'estimated_words': 1500,
                'seo_value': 'medium'
            })
        
        # Opportunity 4: Service Page Enhancements
        for service in top_services[:5]:
            opportunities.append({
                'type': 'service_page',
                'priority': 6,
                'title': f"{service['service'].title()} Services {geo}",
                'description': f"Enhance service page with customer Q&A section",
                'service': service['service'],
                'add_sections': [
                    'What Customers Ask',
                    'Common Concerns',
                    'What to Expect',
                    'Pricing FAQ'
                ],
                'frequency': service['count']
            })
        
        # Opportunity 5: "Real Questions" Content Series
        if len(top_questions) >= 10:
            opportunities.append({
                'type': 'content_series',
                'priority': 8,
                'title': f"Real Questions from {geo} Customers",
                'description': "Monthly blog series answering real customer questions",
                'format': 'weekly_qa_post',
                'questions_per_post': 5,
                'total_posts': min(len(top_questions) // 5, 12),
                'seo_value': 'very_high'
            })
        
        # Sort by priority
        opportunities.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        return opportunities
    
    def _cluster_questions(self, questions: List[Dict]) -> List[Dict]:
        """Group similar questions into topic clusters"""
        clusters = []
        
        # Simple keyword-based clustering
        topic_keywords = {
            'cost': ['cost', 'price', 'how much', 'charge', 'fee', 'expensive', 'afford'],
            'time': ['how long', 'when', 'time', 'duration', 'wait', 'schedule'],
            'process': ['how do', 'how does', 'process', 'steps', 'what happens'],
            'comparison': ['difference', 'better', 'vs', 'compare', 'should i'],
            'emergency': ['emergency', 'urgent', 'asap', 'immediately', 'broken'],
            'warranty': ['warranty', 'guarantee', 'coverage', 'insurance'],
            'maintenance': ['maintenance', 'prevent', 'avoid', 'care', 'last'],
        }
        
        clustered = {topic: [] for topic in topic_keywords}
        unclustered = []
        
        for q in questions:
            question_lower = q['question'].lower()
            matched = False
            
            for topic, keywords in topic_keywords.items():
                if any(kw in question_lower for kw in keywords):
                    clustered[topic].append(q)
                    matched = True
                    break
            
            if not matched:
                unclustered.append(q)
        
        # Create cluster objects for non-empty clusters
        for topic, qs in clustered.items():
            if len(qs) >= 2:
                clusters.append({
                    'topic': topic,
                    'questions': [q['question'] for q in qs],
                    'keywords': topic_keywords[topic],
                    'suggested_title': self._generate_cluster_title(topic, qs),
                    'outline': self._generate_cluster_outline(topic, qs)
                })
        
        return clusters
    
    def _generate_cluster_title(self, topic: str, questions: List[Dict]) -> str:
        """Generate a blog title for a question cluster"""
        titles = {
            'cost': "How Much Does {service} Cost? Complete Pricing Guide",
            'time': "How Long Does {service} Take? Timeline & What to Expect",
            'process': "How {service} Works: Step-by-Step Guide",
            'comparison': "{service} Options Compared: Which Is Right for You?",
            'emergency': "Emergency {service}: What to Do When Things Go Wrong",
            'warranty': "{service} Warranty Guide: What's Covered & What's Not",
            'maintenance': "{service} Maintenance Tips to Save Money & Extend Lifespan",
        }
        
        base_title = titles.get(topic, f"Common Questions About {topic.title()}")
        
        # Try to extract service from questions
        service = "Service"  # Default
        for q in questions:
            # Simple extraction - in production would use NLP
            words = q['question'].split()
            for word in words:
                if len(word) > 4 and word.lower() not in ['about', 'would', 'could', 'should']:
                    service = word.title()
                    break
        
        return base_title.format(service=service)
    
    def _generate_cluster_outline(self, topic: str, questions: List[Dict]) -> List[str]:
        """Generate a blog outline from clustered questions"""
        outline = [
            f"Introduction: Why {topic.title()} Questions Matter",
        ]
        
        # Add each question as a section
        for i, q in enumerate(questions[:7], 1):
            outline.append(f"H2: {q['question']}")
        
        outline.extend([
            "H2: Key Takeaways",
            "H2: When to Call a Professional",
            "Conclusion & Call to Action"
        ])
        
        return outline


# Singleton
_intelligence_service = None

def get_interaction_intelligence_service() -> InteractionIntelligenceService:
    """Get or create intelligence service singleton"""
    global _intelligence_service
    if _intelligence_service is None:
        _intelligence_service = InteractionIntelligenceService()
    return _intelligence_service
