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
    
    # Generic phrases to EXCLUDE from questions (agent/greeting phrases, intake questions)
    # These are NOT customer questions - they are AGENT questions for data collection
    EXCLUDED_QUESTION_PHRASES = [
        # Greetings and small talk
        'how can i help',
        'how may i help',
        'how are you',
        'are you there',
        'can you hear me',
        'hello',
        'hi there',
        'good morning',
        'good afternoon',
        'good evening',
        'thank you for calling',
        'thanks for calling',
        
        # Personal info collection (AGENT asking CUSTOMER)
        'what is your name',
        'what\'s your name',
        'can i get your name',
        'may i have your name',
        'who am i speaking',
        'spell your',
        'how do you spell',
        'first and last name',
        'your first name',
        'your last name',
        'last name please',
        'first name please',
        'and your name',
        'name on the account',
        'name for the',
        'what name',
        
        # Phone number collection
        'what is your phone',
        'what\'s your phone',
        'what is your number',
        'what\'s your number',
        'what is the best phone',
        'what\'s the best phone',
        'best number to reach',
        'call you back at',
        'contact number',
        'phone number for',
        
        # Address collection
        'what is your address',
        'what\'s your address',
        'what is the address',
        'what\'s the address',
        'where are you located',
        'service address',
        'property address',
        
        # Email collection
        'what is your email',
        'what\'s your email',
        'email address',
        
        # Personal details (spouse, DOB, etc.)
        'what is your husband',
        'what\'s your husband',
        'what is your wife',
        'what\'s your wife',
        'what is his',
        'what\'s his',
        'what is her',
        'what\'s her',
        'date of birth',
        'birth date',
        'when were you born',
        'social security',
        'last four',
        
        # Insurance/billing questions (agent asking)
        'do you have insurance',
        'what insurance',
        'insurance company',
        'insurance card',
        'verify the benefits',
        'insurance information',
        'policy number',
        'member id',
        'group number',
        
        # Scheduling logistics (agent questions)
        'do you have a pen',
        'do you have something to write',
        'let me get you scheduled',
        'when would you like',
        'what time works',
        'does that work for you',
        'how does that sound',
        'would you prefer',
        'morning or afternoon',
        'do you have two o\'clock',
        'does that time work',
        'can you come in',
        'would you be able to come',
        'looking at a time',
        'get you scheduled',
        
        # Clarification (agent)
        'can i get your',
        'can i have your',
        'may i have your',
        'is this the',
        'is this cliff',
        'one moment',
        'hold on',
        'please hold',
        'let me check',
        'let me see',
        'what was that',
        'can you repeat',
        'sorry what',
        'excuse me',
        'i didn\'t catch',
        'you said',
        'did you say',
        
        # Generic agent phrases
        'caller:',
        'agent:',
        'representative:',
        'how long she\'ll take',
        'how long will it take',
        'we\'ll check what\'s going on',
        'and then we\'ll',
        
        # Legal/court unrelated content (if showing up)
        'the courts are',
        'court date',
        'properly notified',
        'other explanation',
        'why you were absent',
        'trouble getting in contact',
        'in trouble or anything',
        
        # Payment logistics
        'form of payment',
        'credit card',
        'do you want to pay',
        
        # Verification
        'verify your',
        'confirm your',
        'is that correct',
        'did i get that right',
        
        # Casual/conversational questions (not service-related)
        'who is this',
        'who are you',
        'who am i talking',
        'who am i speaking',
        'who\'s this',
        'is there someone you could recommend',
        'could you recommend',
        'can you recommend someone',
        'you could recommend',
        'they got somebody',
        'is there one or two',
        'part of the fam',
        'does that for them',
        'is this the right number',
        'did i call the right',
        'am i calling the right',
        'are you still open',
        'are you guys open',
        'what are your hours',
        'when do you open',
        'when do you close',
        'are you open on',
        'do you accept',
        'do you take',
        'where are you guys',
        'how far are you',
        'are you still in business',
        'is this still',
        'do you still do',
        'do you guys still',
        'what area do you serve',
        'are you busy',
        'how\'s it going',
        'what\'s going on',
        'how have you been',
        'you know what i mean',
        'know what i\'m saying',
        'you there',
        'can you hear',
        'i\'m sorry',
        'sorry to bother',
        'i apologize',
        'no worries',
        'right right',
        'exactly exactly',
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
        r'\b(stopped working|quit working|won\'t start|won\'t turn on)\b',
        r'\b(leaking|leak|water damage|flooding)\b',
        r'\b(no heat|no cooling|no air|not cooling|not heating)\b',
        r'\b(loud noise|strange noise|making noise)\b',
    ]
    
    # Service-related keywords by industry
    # This is used to filter questions for relevance to the business
    INDUSTRY_KEYWORDS = {
        # Home Services
        'hvac': [
            'air conditioning', 'ac', 'heating', 'furnace', 'heat pump',
            'thermostat', 'ductwork', 'refrigerant', 'freon', 'compressor',
            'maintenance', 'tune-up', 'filter', 'installation', 'repair',
            'replacement', 'efficiency', 'seer', 'humidity', 'ventilation',
            'cooling', 'not cooling', 'not heating', 'frozen', 'freeze'
        ],
        'plumbing': [
            'leak', 'drain', 'clog', 'clogged', 'pipe', 'pipes', 'water heater', 
            'toilet', 'faucet', 'sewer', 'septic', 'garbage disposal', 'water pressure',
            'backup', 'flooding', 'burst pipe', 'tankless', 'repiping', 'plumber',
            'sink', 'shower', 'bathtub', 'water line', 'gas line', 'sump pump'
        ],
        'electrical': [
            'outlet', 'circuit', 'breaker', 'panel', 'wiring', 'lighting',
            'generator', 'surge protector', 'electrical fire', 'flickering',
            'power outage', 'rewiring', 'code', 'inspection', 'ev charger',
            'electrician', 'switch', 'dimmer', 'ceiling fan', 'electrical'
        ],
        'roofing': [
            'roof', 'roofing', 'shingle', 'shingles', 'leak', 'leaking',
            'gutter', 'gutters', 'flashing', 'soffit', 'fascia', 'skylight',
            'storm damage', 'hail damage', 'wind damage', 'replacement', 'repair',
            'inspection', 'estimate', 'insurance claim', 'tile', 'metal roof'
        ],
        'landscaping': [
            'lawn', 'grass', 'mowing', 'tree', 'trees', 'shrub', 'shrubs',
            'mulch', 'fertilizer', 'irrigation', 'sprinkler', 'landscape',
            'hardscape', 'patio', 'pavers', 'sod', 'planting', 'trimming',
            'removal', 'stump', 'hedge', 'garden', 'drainage'
        ],
        'pest_control': [
            'pest', 'pests', 'bug', 'bugs', 'insect', 'insects', 'termite',
            'termites', 'ant', 'ants', 'roach', 'roaches', 'rodent', 'mouse',
            'mice', 'rat', 'rats', 'bed bug', 'spider', 'wasp', 'bee',
            'exterminator', 'infestation', 'treatment', 'spray', 'fumigation'
        ],
        'cleaning': [
            'clean', 'cleaning', 'maid', 'housekeeping', 'deep clean',
            'carpet', 'carpet cleaning', 'upholstery', 'window', 'windows',
            'pressure wash', 'power wash', 'janitorial', 'sanitize', 'disinfect',
            'move out', 'move in', 'recurring', 'one time', 'weekly', 'monthly'
        ],
        'garage_door': [
            'garage', 'garage door', 'opener', 'spring', 'springs', 'track',
            'remote', 'sensor', 'stuck', 'won\'t open', 'won\'t close',
            'noisy', 'installation', 'replacement', 'repair', 'maintenance'
        ],
        'appliance_repair': [
            'appliance', 'refrigerator', 'fridge', 'washer', 'dryer', 'dishwasher',
            'oven', 'stove', 'range', 'microwave', 'freezer', 'ice maker',
            'not working', 'broken', 'repair', 'fix', 'service', 'warranty'
        ],
        
        # Healthcare
        'dental': [
            'teeth', 'tooth', 'crown', 'filling', 'root canal', 'extraction',
            'cleaning', 'whitening', 'implant', 'dentures', 'braces', 'invisalign',
            'cavity', 'cavities', 'gum', 'gums', 'periodontal', 'periodontist',
            'oral', 'dental', 'dentist', 'hygienist', 'orthodontist',
            'toothache', 'tooth pain', 'sensitive', 'sensitivity', 'bleeding gums',
            'bad breath', 'halitosis', 'swelling', 'abscess', 'infection',
            'chipped', 'cracked', 'broken tooth', 'missing tooth', 'loose tooth',
            'veneer', 'veneers', 'bonding', 'bridge', 'dental bridge',
            'deep cleaning', 'scaling', 'fluoride', 'sealant', 'x-ray', 'xray',
            'sedation', 'nitrous', 'numbing', 'anesthesia', 'novocaine',
            'smile', 'cosmetic', 'teeth whitening', 'bleaching',
            'dental insurance', 'dental plan', 'dental coverage',
            'emergency', 'urgent', 'pain', 'same day'
        ],
        'medical': [
            'appointment', 'consultation', 'treatment', 'diagnosis', 'symptoms',
            'insurance', 'coverage', 'specialist', 'referral', 'prescription',
            'follow-up', 'test', 'results', 'procedure', 'surgery', 'recovery',
            'doctor', 'physician', 'nurse', 'clinic', 'patient', 'health',
            'checkup', 'physical', 'lab', 'blood work', 'medication'
        ],
        'chiropractic': [
            'back', 'back pain', 'spine', 'spinal', 'neck', 'neck pain',
            'adjustment', 'alignment', 'chiropractor', 'chiropractic',
            'posture', 'sciatica', 'disc', 'herniated', 'pinched nerve',
            'headache', 'migraine', 'joint', 'muscle', 'therapy', 'x-ray'
        ],
        'optometry': [
            'eye', 'eyes', 'vision', 'glasses', 'contacts', 'contact lenses',
            'exam', 'eye exam', 'prescription', 'optometrist', 'ophthalmologist',
            'frames', 'lenses', 'bifocal', 'progressive', 'sunglasses',
            'dry eye', 'glaucoma', 'cataract', 'lasik', 'blurry'
        ],
        'veterinary': [
            'pet', 'dog', 'cat', 'puppy', 'kitten', 'animal', 'vet',
            'veterinarian', 'vaccine', 'vaccination', 'shots', 'checkup',
            'spay', 'neuter', 'surgery', 'sick', 'injury', 'emergency',
            'grooming', 'boarding', 'dental', 'teeth cleaning'
        ],
        'physical_therapy': [
            'therapy', 'physical therapy', 'pt', 'rehab', 'rehabilitation',
            'exercise', 'stretching', 'strength', 'mobility', 'flexibility',
            'injury', 'recovery', 'pain', 'sports', 'post surgery',
            'knee', 'shoulder', 'hip', 'ankle', 'back', 'neck'
        ],
        'mental_health': [
            'therapy', 'therapist', 'counseling', 'counselor', 'psychologist',
            'psychiatrist', 'mental health', 'anxiety', 'depression', 'stress',
            'appointment', 'session', 'insurance', 'sliding scale', 'telehealth',
            'couples', 'family', 'individual', 'group'
        ],
        
        # Professional Services
        'legal': [
            'lawyer', 'attorney', 'legal', 'case', 'lawsuit', 'consultation',
            'settlement', 'court', 'trial', 'deposition', 'discovery',
            'representation', 'fees', 'retainer', 'contract', 'liability',
            'damages', 'defense', 'prosecution', 'divorce', 'custody',
            'personal injury', 'criminal', 'civil', 'estate', 'will', 'trust'
        ],
        'accounting': [
            'tax', 'taxes', 'accountant', 'cpa', 'bookkeeping', 'payroll',
            'filing', 'return', 'refund', 'audit', 'irs', 'deduction',
            'business', 'personal', 'quarterly', 'annual', 'financial',
            'statement', 'balance sheet', 'income', 'expense'
        ],
        'real_estate': [
            'listing', 'showing', 'offer', 'closing', 'inspection', 'appraisal',
            'mortgage', 'pre-approval', 'commission', 'contract', 'escrow',
            'contingency', 'negotiation', 'market', 'price', 'neighborhood',
            'buy', 'sell', 'rent', 'lease', 'property', 'home', 'house',
            'condo', 'townhouse', 'realtor', 'agent', 'broker'
        ],
        'insurance': [
            'policy', 'coverage', 'premium', 'deductible', 'claim', 'quote',
            'auto', 'home', 'life', 'health', 'business', 'liability',
            'umbrella', 'agent', 'broker', 'renew', 'cancel', 'add', 'remove'
        ],
        'financial': [
            'investment', 'retirement', 'portfolio', 'stocks', 'bonds', 'mutual fund',
            '401k', 'ira', 'roth', 'advisor', 'planner', 'wealth', 'estate',
            'loan', 'mortgage', 'refinance', 'credit', 'debt', 'savings'
        ],
        
        # Automotive
        'automotive': [
            'car', 'vehicle', 'auto', 'truck', 'suv', 'repair', 'service',
            'oil change', 'brake', 'brakes', 'tire', 'tires', 'transmission',
            'engine', 'battery', 'alignment', 'inspection', 'diagnostic',
            'check engine', 'maintenance', 'tune up', 'warranty', 'recall'
        ],
        'auto_body': [
            'body', 'collision', 'accident', 'dent', 'scratch', 'paint',
            'bumper', 'fender', 'frame', 'insurance', 'claim', 'estimate',
            'repair', 'restoration', 'custom', 'detail', 'detailing'
        ],
        
        # Beauty & Wellness
        'salon': [
            'hair', 'haircut', 'color', 'highlight', 'balayage', 'perm',
            'straightening', 'keratin', 'stylist', 'appointment', 'walk-in',
            'blowout', 'trim', 'style', 'updo', 'extensions', 'treatment'
        ],
        'spa': [
            'massage', 'facial', 'spa', 'relaxation', 'treatment', 'body',
            'skin', 'skincare', 'wax', 'waxing', 'nail', 'manicure', 'pedicure',
            'appointment', 'package', 'gift card', 'couples', 'prenatal'
        ],
        'fitness': [
            'gym', 'membership', 'class', 'classes', 'trainer', 'training',
            'workout', 'exercise', 'fitness', 'weight', 'cardio', 'strength',
            'yoga', 'pilates', 'spin', 'crossfit', 'schedule', 'cancel'
        ],
        
        # Food & Hospitality
        'restaurant': [
            'reservation', 'table', 'menu', 'order', 'delivery', 'takeout',
            'catering', 'private event', 'party', 'hours', 'location',
            'allergy', 'vegetarian', 'vegan', 'gluten free', 'special'
        ],
        'catering': [
            'catering', 'event', 'wedding', 'corporate', 'party', 'menu',
            'quote', 'tasting', 'headcount', 'dietary', 'setup', 'delivery',
            'buffet', 'plated', 'appetizer', 'dessert', 'beverage'
        ],
        
        # Education
        'tutoring': [
            'tutor', 'tutoring', 'lesson', 'lessons', 'subject', 'math',
            'reading', 'writing', 'science', 'test prep', 'sat', 'act',
            'homework', 'grade', 'schedule', 'online', 'in person', 'rates'
        ],
        'music_lessons': [
            'lesson', 'lessons', 'music', 'piano', 'guitar', 'violin', 'drums',
            'voice', 'singing', 'instrument', 'teacher', 'instructor',
            'beginner', 'intermediate', 'advanced', 'recital', 'schedule'
        ],
        
        # Construction & Trades
        'construction': [
            'build', 'building', 'construction', 'contractor', 'remodel',
            'renovation', 'addition', 'permit', 'estimate', 'bid', 'project',
            'timeline', 'materials', 'labor', 'commercial', 'residential'
        ],
        'painting': [
            'paint', 'painting', 'painter', 'interior', 'exterior', 'color',
            'estimate', 'quote', 'prep', 'primer', 'coat', 'finish',
            'cabinet', 'trim', 'ceiling', 'wall', 'deck', 'stain'
        ],
        'flooring': [
            'floor', 'flooring', 'hardwood', 'laminate', 'tile', 'carpet',
            'vinyl', 'installation', 'refinish', 'repair', 'estimate',
            'measurement', 'material', 'labor', 'subfloor', 'transition'
        ],
        
        # Technology
        'it_services': [
            'computer', 'laptop', 'desktop', 'server', 'network', 'wifi',
            'internet', 'email', 'software', 'hardware', 'virus', 'malware',
            'backup', 'recovery', 'support', 'repair', 'upgrade', 'install'
        ],
        'web_design': [
            'website', 'web', 'design', 'development', 'hosting', 'domain',
            'seo', 'mobile', 'responsive', 'ecommerce', 'update', 'maintenance',
            'redesign', 'quote', 'portfolio', 'cms', 'wordpress'
        ],
    }
    
    # Universal keywords that apply to ALL industries
    UNIVERSAL_KEYWORDS = [
        # Pricing & Cost
        'cost', 'price', 'pricing', 'rate', 'rates', 'fee', 'fees',
        'charge', 'charges', 'estimate', 'quote', 'afford', 'budget',
        'payment', 'financing', 'deposit', 'discount', 'special', 'deal',
        
        # Scheduling & Time
        'appointment', 'schedule', 'available', 'availability', 'book',
        'reschedule', 'cancel', 'time', 'when', 'how long', 'how soon',
        'wait', 'waiting', 'urgent', 'emergency', 'asap', 'same day',
        'next day', 'weekend', 'evening', 'morning', 'afternoon',
        
        # Service Actions
        'repair', 'fix', 'replace', 'install', 'service', 'maintain',
        'maintenance', 'inspect', 'inspection', 'diagnose', 'assess',
        
        # Quality & Warranty
        'warranty', 'guarantee', 'insured', 'licensed', 'certified',
        'experience', 'years', 'reviews', 'rating', 'recommend',
        
        # Process & Procedure
        'how do', 'how does', 'what happens', 'process', 'steps',
        'what should', 'what do', 'need to', 'have to', 'required',
        
        # Location & Coverage
        'area', 'location', 'travel', 'service area', 'come to', 'on site'
    ]
    
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
        
        # Extract questions (pass client_id for relevance filtering)
        questions = self._extract_questions(transcript, client_id)
        
        # Identify pain points (pass client_id for relevance filtering)
        pain_points = self._extract_pain_points(transcript, client_id)
        
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
    
    def _extract_questions(self, text: str, client_id: str = None) -> List[str]:
        """Extract meaningful CUSTOMER questions from text (excludes agent/generic questions)
        
        This method filters aggressively to only return questions that:
        1. Are asked by the CUSTOMER (not agent intake questions)
        2. Are relevant to the business services
        3. Would make good FAQ or blog content
        
        Uses UNIVERSAL_KEYWORDS (apply to all industries) + industry-specific keywords
        """
        questions = []
        
        # Industry aliases - map common variations to our standard keys
        INDUSTRY_ALIASES = {
            'dentist': 'dental',
            'dentistry': 'dental',
            'dental office': 'dental',
            'dental clinic': 'dental',
            'orthodontist': 'dental',
            'hvac contractor': 'hvac',
            'air conditioning': 'hvac',
            'heating and cooling': 'hvac',
            'plumber': 'plumbing',
            'electrician': 'electrical',
            'roofer': 'roofing',
            'lawyer': 'legal',
            'attorney': 'legal',
            'law firm': 'legal',
            'accountant': 'accounting',
            'cpa': 'accounting',
            'tax preparer': 'accounting',
            'realtor': 'real_estate',
            'real estate agent': 'real_estate',
            'realty': 'real_estate',
            'auto repair': 'automotive',
            'mechanic': 'automotive',
            'car repair': 'automotive',
            'hair salon': 'salon',
            'barber': 'salon',
            'beauty salon': 'salon',
            'massage': 'spa',
            'wellness': 'spa',
            'gym': 'fitness',
            'personal trainer': 'fitness',
            'vet': 'veterinary',
            'animal hospital': 'veterinary',
            'pet clinic': 'veterinary',
            'chiropractor': 'chiropractic',
            'eye doctor': 'optometry',
            'optician': 'optometry',
            'therapist': 'mental_health',
            'counselor': 'mental_health',
            'psychologist': 'mental_health',
            'pest': 'pest_control',
            'exterminator': 'pest_control',
            'maid service': 'cleaning',
            'house cleaning': 'cleaning',
            'janitorial': 'cleaning',
            'contractor': 'construction',
            'builder': 'construction',
            'remodeling': 'construction',
            'painter': 'painting',
            'flooring': 'flooring',
            'carpet': 'flooring',
            'computer repair': 'it_services',
            'tech support': 'it_services',
            'web developer': 'web_design',
            'website design': 'web_design',
        }
        
        # Get client's industry for relevance filtering
        industry = None
        if client_id:
            try:
                client = DBClient.query.get(client_id)
                if client:
                    industry = client.industry.lower() if client.industry else None
            except:
                pass
        
        # Normalize industry using aliases
        if industry:
            # Check aliases first
            if industry in INDUSTRY_ALIASES:
                industry = INDUSTRY_ALIASES[industry]
            else:
                # Try partial match on aliases
                for alias, standard in INDUSTRY_ALIASES.items():
                    if alias in industry or industry in alias:
                        industry = standard
                        break
        
        # Build relevance keywords: UNIVERSAL + industry-specific
        relevance_keywords = set(self.UNIVERSAL_KEYWORDS)
        
        # Add industry-specific keywords if industry is known
        if industry:
            # Try exact match first
            if industry in self.INDUSTRY_KEYWORDS:
                relevance_keywords.update(self.INDUSTRY_KEYWORDS[industry])
            else:
                # Try partial match (e.g., "dental clinic" matches "dental")
                for ind_key, ind_keywords in self.INDUSTRY_KEYWORDS.items():
                    if ind_key in industry or industry in ind_key:
                        relevance_keywords.update(ind_keywords)
                        break
        
        # If still no industry match, add keywords from ALL industries
        # This ensures we catch relevant questions even if industry isn't set
        if not industry or industry not in self.INDUSTRY_KEYWORDS:
            for ind_keywords in self.INDUSTRY_KEYWORDS.values():
                relevance_keywords.update(ind_keywords)
        
        # Split into sentences
        sentences = re.split(r'[.!?\n]', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 15:  # Minimum length for meaningful question
                continue
            
            sentence_lower = sentence.lower()
            
            # Skip if it contains excluded phrases (agent questions, greetings, etc.)
            is_excluded = False
            for excluded in self.EXCLUDED_QUESTION_PHRASES:
                if excluded in sentence_lower:
                    is_excluded = True
                    break
            
            if is_excluded:
                continue
            
            # Check if it's a question
            is_question = False
            for pattern in self.QUESTION_PATTERNS:
                if re.search(pattern, sentence_lower):
                    is_question = True
                    break
            
            if is_question:
                # Clean up the question - remove speaker labels
                question = re.sub(r'^(caller|agent|customer|rep|representative):\s*', '', sentence, flags=re.IGNORECASE)
                question = question.strip()
                
                # Skip very short questions after cleanup
                if len(question) < 15:  # Reduced back to 15
                    continue
                
                # Skip incomplete/cut-off questions
                # These typically end with "or", "and", "the", "a", "to", etc.
                trailing_words = ['or', 'and', 'the', 'a', 'to', 'for', 'with', 'at', 'in', 'on']
                words = question.lower().split()
                if words and words[-1].rstrip('?') in trailing_words:
                    logger.debug(f"Skipping incomplete question: {question[:50]}...")
                    continue
                
                # Skip questions that are too generic/vague
                vague_patterns = [
                    r'^(what|how|is|are|do|does|can|could|will|would)\s+(it|that|this)$',  # Only if it's the WHOLE question
                    r'^is (it|that|this)\?$',
                ]
                is_vague = False
                question_lower = question.lower()
                for vp in vague_patterns:
                    if re.search(vp, question_lower):
                        is_vague = True
                        break
                if is_vague:
                    logger.debug(f"Skipping vague question: {question[:50]}...")
                    continue
                
                # REMOVED: strict keyword relevance check
                # Now we accept all questions that pass the above filters
                # The industry-specific filtering happens at display time
                
                # SERVICE-RELEVANCE CHECK: Only keep questions that relate to the business
                # Must contain at least one service/business keyword OR be a clear service inquiry
                question_lower = question.lower()
                
                # Service inquiry patterns (questions about pricing, scheduling, process, etc.)
                service_inquiry_patterns = [
                    r'\b(how much|what.{0,5}cost|price|pricing|fee|charge|rate|estimate|quote)\b',
                    r'\b(how long|when can|how soon|how fast|time.{0,5}take|turnaround)\b',
                    r'\b(do you (do|offer|provide|handle|service|fix|repair|install|replace))\b',
                    r'\b(can you (do|fix|repair|install|replace|come|help|check|look))\b',
                    r'\b(need.{0,10}(repair|replace|install|fix|service|inspect|clean|maintain))\b',
                    r'\b(warranty|guarantee|covered|insurance)\b',
                    r'\b(what.{0,5}(process|procedure|steps|involved|required|needed|happen))\b',
                    r'\b(is there.{0,10}(way|option|chance|possibility))\b',
                    r'\b(should i|do i need|will i need|would i need)\b',
                    r'\b(difference between|which.{0,5}(better|best|recommend))\b',
                    r'\b(problem|issue|broken|not working|stopped|won\'t|doesn\'t)\b',
                    r'\b(brand|model|type|kind|size|unit|system|equipment)\b',
                    r'\b(new|old|replacement|upgrade|install)\b',
                    r'\b(disconnect|swap|remove|add|put in)\b',
                    r'\b(package|unit|high voltage|low voltage|wire|wiring)\b',
                ]
                
                has_service_relevance = False
                
                # Check against service inquiry patterns
                for pattern in service_inquiry_patterns:
                    if re.search(pattern, question_lower):
                        has_service_relevance = True
                        break
                
                # Check against industry/universal keywords
                if not has_service_relevance:
                    for keyword in relevance_keywords:
                        if keyword.lower() in question_lower:
                            has_service_relevance = True
                            break
                
                if not has_service_relevance:
                    logger.debug(f"Skipping non-service question: {question[:60]}...")
                    continue
                    
                if not question.endswith('?'):
                    question += '?'
                questions.append(question)
        
        return questions
    
    def _extract_pain_points(self, text: str, client_id: str = None) -> List[str]:
        """Extract customer pain points and concerns from text
        
        Filters out:
        - Agent statements
        - Non-business related concerns (legal, personal issues unrelated to service)
        """
        pain_points = []
        text_lower = text.lower()
        
        # Phrases that indicate non-relevant content (legal issues, personal drama, conversational)
        irrelevant_phrases = [
            'court date', 'judge', 'custody', 'divorce', 'hearing',
            'police', 'arrested', 'jail', 'probation',
            'notified about that', 'absent from',
            # Conversational/filler phrases — not real pain points
            'hopefully it doesn\'t bug you',
            'hope that\'s okay',
            'sorry to bother',
            'i apologize for',
            'don\'t want to be a bother',
            'hope you don\'t mind',
            'if that\'s alright',
            'and then there was a call for',
            'and then we\'ll',
            'i appreciate',
            'thank you so much',
            'thanks so much',
            'have a good',
            'have a great',
            'god bless',
            'take care',
        ]
        
        # Split into sentences
        sentences = re.split(r'[.!?\n]', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 20:
                continue
            
            sentence_lower = sentence.lower()
            
            # Skip agent statements - we want CALLER pain points
            if sentence_lower.startswith('agent:') or 'thank you for calling' in sentence_lower:
                continue
            
            # Skip irrelevant content (legal issues unrelated to service)
            is_irrelevant = False
            for phrase in irrelevant_phrases:
                if phrase in sentence_lower:
                    is_irrelevant = True
                    break
            if is_irrelevant:
                continue
            
            # Check for pain indicators
            for pattern in self.PAIN_INDICATORS:
                if re.search(pattern, sentence_lower):
                    # Clean up - remove speaker labels
                    pain_point = re.sub(r'^(caller|agent|customer):\s*', '', sentence, flags=re.IGNORECASE)
                    pain_point = pain_point.strip()
                    
                    # Skip pain points that are too vague or just conversational filler
                    pp_lower = pain_point.lower()
                    is_filler = (
                        pp_lower.startswith('and then') or
                        pp_lower.startswith('and hopefully') or
                        pp_lower.startswith('and so') or
                        pp_lower.startswith('i\'m not sure if') or
                        pp_lower.startswith('i don\'t know if') or
                        pp_lower.startswith('i don\'t think') or
                        pp_lower.startswith('i\'m not sure who') or
                        pp_lower.startswith('i was wondering') or
                        (pp_lower.startswith('but ') and len(pain_point) < 40) or
                        (pp_lower.startswith('so ') and len(pain_point) < 40)
                    )
                    if is_filler:
                        break
                    
                    # Pain point must reference something tangible — skip vague conversational mentions
                    # Must contain a service/problem keyword, not just "not sure" or "confused"
                    has_substance = bool(re.search(
                        r'\b(broke|broken|leak|not working|stopped|won\'t|doesn\'t|damaged|failing|failed|'
                        r'noise|smell|expensive|wait|delay|hot|cold|froze|frozen|flood|'
                        r'install|repair|replace|service|unit|system|house|home|office|building|'
                        r'pipe|wire|light|heat|cool|air|water|electric|gas|drain|roof|floor|wall|'
                        r'tooth|teeth|pain|hurt|ache|bleed|crack|chip|cavity|crown|'
                        r'mold|rust|rot|stain|crack|dent|scratch)\b',
                        pp_lower
                    ))
                    
                    if not has_substance:
                        break
                    
                    # Only add if it's meaningful
                    if len(pain_point) >= 25 and len(pain_point) <= 250:
                        pain_points.append(pain_point)
                    break
        
        return pain_points
    
    def _extract_keywords(self, text: str, industry: str = None) -> List[str]:
        """Extract relevant keywords from text (filters out generic/common words)"""
        keywords = []
        text_lower = text.lower()
        
        # Industry aliases - map common variations to standard keys
        INDUSTRY_ALIASES = {
            'dentist': 'dental',
            'dentistry': 'dental',
            'dental office': 'dental',
            'dental clinic': 'dental',
            'orthodontist': 'dental',
            'hvac contractor': 'hvac',
            'air conditioning': 'hvac',
            'heating and cooling': 'hvac',
            'plumber': 'plumbing',
            'electrician': 'electrical',
            'roofer': 'roofing',
            'lawyer': 'legal',
            'attorney': 'legal',
        }
        
        # Common words to ALWAYS exclude - these are never relevant
        GLOBAL_STOP_WORDS = {
            'about', 'would', 'could', 'should', 'there', 'their', 'where', 'which', 
            'these', 'those', 'going', 'trying', 'thing', 'think', 'things', 'getting',
            'really', 'actually', 'basically', 'probably', 'maybe', 'might', 'right',
            'please', 'thank', 'thanks', 'hello', 'okay', 'alright', 'yeah', 'yes',
            'know', 'just', 'like', 'well', 'good', 'great', 'want', 'need',
            'today', 'tomorrow', 'yesterday', 'morning', 'afternoon', 'evening',
            'number', 'phone', 'email', 'address', 'name', 'called', 'calling',
            'office', 'company', 'customer', 'agent', 'caller',
            'something', 'anything', 'nothing', 'everything', 'someone', 'anyone',
            'here', 'come', 'coming', 'going', 'make', 'made', 'have',
            'because', 'since', 'while', 'after', 'before', 'during', 'between',
            'include', 'included', 'excuse', 'sorry', 'happy', 'support', 'needs',
            'captured', 'chatbot', 'widget', 'spelled', 'checked', 'decided',
            'extension', 'another', 'kings', 'will', 'body', 'car', 'rent', 
            'lease', 'irs', 'event', 'build', 'building', 'cat', 'act',
        }
        
        # Words to filter UNLESS they match the specific industry
        INDUSTRY_SPECIFIC_FILTER = {
            'pest_control': {'ant', 'ants', 'bee', 'bees', 'bug', 'bugs', 'mouse', 'mice', 'rat', 'rats', 'roach', 'spider'},
            'legal': {'attorney', 'lawyer', 'court', 'judge'},
        }
        
        # Minimum keyword length to avoid noise
        MIN_KEYWORD_LENGTH = 3
        
        # Normalize industry using aliases
        normalized_industry = None
        if industry:
            industry_lower = industry.lower()
            if industry_lower in INDUSTRY_ALIASES:
                normalized_industry = INDUSTRY_ALIASES[industry_lower]
            elif industry_lower in self.INDUSTRY_KEYWORDS:
                normalized_industry = industry_lower
            else:
                # Try fuzzy match
                for alias, standard in INDUSTRY_ALIASES.items():
                    if alias in industry_lower or industry_lower in alias:
                        normalized_industry = standard
                        break
                if not normalized_industry:
                    for ind_key in self.INDUSTRY_KEYWORDS.keys():
                        if ind_key in industry_lower or industry_lower in ind_key:
                            normalized_industry = ind_key
                            break
        
        # Build keyword list to search for
        industry_kws = []
        
        # 1. Always include universal keywords
        industry_kws.extend(self.UNIVERSAL_KEYWORDS)
        
        # 2. If we have a specific industry, add those keywords
        if normalized_industry and normalized_industry in self.INDUSTRY_KEYWORDS:
            industry_kws.extend(self.INDUSTRY_KEYWORDS[normalized_industry])
        else:
            # No specific industry - add keywords from ALL industries
            # But we'll filter out problematic ones below
            for ind_kws in self.INDUSTRY_KEYWORDS.values():
                industry_kws.extend(ind_kws)
        
        # Build dynamic stop words based on industry
        stop_words = set(GLOBAL_STOP_WORDS)
        
        # Add industry-specific filtered words for NON-matching industries
        for ind, words_to_filter in INDUSTRY_SPECIFIC_FILTER.items():
            if normalized_industry != ind:
                stop_words.update(words_to_filter)
        
        # Find keywords in text
        for kw in industry_kws:
            kw_lower = kw.lower()
            
            # Skip very short keywords unless they're known industry-specific
            if len(kw_lower) < MIN_KEYWORD_LENGTH:
                if normalized_industry == 'hvac' and kw_lower in ['ac']:
                    pass  # Allow "ac" for HVAC
                else:
                    continue
            
            # Skip stop words
            if kw_lower in stop_words:
                continue
                
            if kw_lower in text_lower:
                keywords.append(kw)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique_keywords.append(kw)
        
        return unique_keywords
    
    def _extract_services(self, text: str, industry: str = None) -> List[str]:
        """Extract service mentions from text based on industry"""
        services = []
        text_lower = text.lower()
        
        # Industry-specific service patterns
        SERVICE_PATTERNS = {
            'dental': [
                r'\b(teeth?\s*cleaning|dental\s*cleaning|prophylaxis)',
                r'\b(teeth?\s*whitening|bleaching|zoom\s*whitening)',
                r'\b(root\s*canal|endodontic)',
                r'\b(crown|dental\s*crown|cap)',
                r'\b(filling|cavity\s*filling|composite)',
                r'\b(extraction|tooth\s*extraction|pull\s*(?:a\s*)?tooth)',
                r'\b(implant|dental\s*implant)',
                r'\b(veneers?|dental\s*veneers?)',
                r'\b(bridge|dental\s*bridge)',
                r'\b(dentures?|partial\s*dentures?|full\s*dentures?)',
                r'\b(braces|invisalign|orthodontic)',
                r'\b(deep\s*cleaning|scaling|root\s*planing)',
                r'\b(exam|dental\s*exam|check.?up|checkup)',
                r'\b(x.?ray|dental\s*x.?ray)',
                r'\b(emergency\s*dental|dental\s*emergency|tooth\s*pain)',
                r'\b(cosmetic\s*dentistry|smile\s*makeover)',
                r'\b(gum\s*treatment|periodontal|gum\s*disease)',
                r'\b(night\s*guard|mouth\s*guard|bite\s*guard)',
                r'\b(sedation\s*dentistry|sleep\s*dentistry)',
            ],
            'hvac': [
                r'\b(ac|air conditioner|air conditioning)\s*(repair|service|installation|replacement|maintenance|tune.?up)',
                r'\b(heating|furnace|heat pump)\s*(repair|service|installation|replacement|maintenance)',
                r'\b(thermostat)\s*(repair|replacement|installation|programming)',
                r'\b(duct|ductwork)\s*(cleaning|repair|installation)',
                r'\b(freon|refrigerant)\s*(recharge|leak|check)',
                r'\bnew\s+(ac|air conditioner|unit|system|furnace)',
                r'\b(not cooling|not heating|won\'t turn on|stopped working)',
                r'\b(emergency|same.?day|urgent)\s*(hvac|ac|heating)',
            ],
            'plumbing': [
                r'\b(drain)\s*(cleaning|unclog|repair)',
                r'\b(pipe)\s*(repair|replacement|leak)',
                r'\b(water heater)\s*(repair|replacement|installation)',
                r'\b(toilet)\s*(repair|replacement|installation|unclog)',
                r'\b(faucet)\s*(repair|replacement|installation)',
                r'\b(garbage disposal)\s*(repair|replacement|installation)',
                r'\b(sewer)\s*(line|cleaning|repair)',
                r'\b(leak)\s*(detection|repair)',
                r'\b(emergency)\s*(plumbing|plumber)',
            ],
            'electrical': [
                r'\b(electrical)\s*(repair|service|installation|inspection)',
                r'\b(outlet)\s*(repair|replacement|installation)',
                r'\b(panel)\s*(upgrade|repair|replacement)',
                r'\b(wiring)\s*(repair|replacement|installation)',
                r'\b(lighting)\s*(installation|repair)',
                r'\b(generator)\s*(installation|repair|service)',
                r'\b(ev charger)\s*(installation)',
                r'\b(circuit breaker)\s*(repair|replacement)',
            ],
            'roofing': [
                r'\b(roof)\s*(repair|replacement|inspection|installation)',
                r'\b(shingle)\s*(repair|replacement)',
                r'\b(gutter)\s*(cleaning|repair|installation)',
                r'\b(leak)\s*(repair|detection)',
                r'\b(storm damage)\s*(repair)',
                r'\b(roof)\s*(estimate|inspection)',
            ],
            'legal': [
                r'\b(legal)\s*(consultation|advice|representation)',
                r'\b(case)\s*(review|evaluation)',
                r'\b(personal injury)\s*(case|claim)',
                r'\b(divorce)\s*(consultation|filing)',
                r'\b(estate)\s*(planning|will|trust)',
                r'\b(contract)\s*(review|drafting)',
                r'\b(criminal)\s*(defense)',
            ],
            'automotive': [
                r'\b(oil)\s*(change)',
                r'\b(brake)\s*(repair|replacement|service)',
                r'\b(tire)\s*(rotation|replacement|repair)',
                r'\b(transmission)\s*(repair|service)',
                r'\b(engine)\s*(repair|diagnostic)',
                r'\b(check engine)\s*(light|diagnostic)',
                r'\b(ac)\s*(repair|recharge)',
                r'\b(alignment)',
            ],
            'salon': [
                r'\b(haircut|hair\s*cut)',
                r'\b(hair)\s*(color|coloring|dye)',
                r'\b(highlights?|balayage)',
                r'\b(blowout|blow\s*dry)',
                r'\b(trim)',
                r'\b(perm|straightening|keratin)',
                r'\b(extensions)',
            ],
            'spa': [
                r'\b(massage)\s*(therapy|treatment)?',
                r'\b(facial)\s*(treatment)?',
                r'\b(manicure|pedicure)',
                r'\b(wax|waxing)',
                r'\b(body)\s*(treatment|wrap)',
            ],
            'real_estate': [
                r'\b(home)\s*(buying|selling|valuation)',
                r'\b(listing)\s*(consultation)?',
                r'\b(market)\s*(analysis)',
                r'\b(property)\s*(search|showing)',
            ],
            'cleaning': [
                r'\b(house|home)\s*(cleaning)',
                r'\b(deep)\s*(clean|cleaning)',
                r'\b(carpet)\s*(cleaning)',
                r'\b(window)\s*(cleaning)',
                r'\b(move.?in|move.?out)\s*(cleaning)?',
            ],
            'veterinary': [
                r'\b(pet|dog|cat)\s*(checkup|exam|vaccination|surgery)',
                r'\b(spay|neuter)',
                r'\b(dental)\s*(cleaning)',
                r'\b(emergency)\s*(vet|animal)',
            ],
            'fitness': [
                r'\b(gym)\s*(membership)',
                r'\b(personal)\s*(training|trainer)',
                r'\b(fitness)\s*(class|assessment)',
                r'\b(yoga|pilates|crossfit)\s*(class)?',
            ],
        }
        
        # Industry aliases - map common variations to standard keys
        INDUSTRY_ALIASES = {
            'dentist': 'dental', 'dentistry': 'dental', 'orthodontist': 'dental',
            'hvac contractor': 'hvac', 'air conditioning': 'hvac',
            'plumber': 'plumbing', 'electrician': 'electrical', 'roofer': 'roofing',
            'lawyer': 'legal', 'attorney': 'legal', 'law firm': 'legal',
            'accountant': 'accounting', 'cpa': 'accounting',
            'realtor': 'real_estate', 'realty': 'real_estate',
            'auto repair': 'automotive', 'mechanic': 'automotive',
            'hair salon': 'salon', 'barber': 'salon',
            'vet': 'veterinary', 'animal hospital': 'veterinary',
            'gym': 'fitness', 'trainer': 'fitness',
            'maid service': 'cleaning', 'janitorial': 'cleaning',
        }
        
        # Normalize industry using aliases
        normalized_industry = industry
        if industry:
            if industry in INDUSTRY_ALIASES:
                normalized_industry = INDUSTRY_ALIASES[industry]
            else:
                for alias, standard in INDUSTRY_ALIASES.items():
                    if alias in industry or industry in alias:
                        normalized_industry = standard
                        break
        
        # Choose patterns based on industry
        patterns_to_use = []
        if normalized_industry and normalized_industry in SERVICE_PATTERNS:
            patterns_to_use = SERVICE_PATTERNS[normalized_industry]
        else:
            # Try partial match
            for ind_key, patterns in SERVICE_PATTERNS.items():
                if normalized_industry and (ind_key in normalized_industry or normalized_industry in ind_key):
                    patterns_to_use = patterns
                    break
        
        # If no industry match, use all patterns
        if not patterns_to_use:
            for patterns in SERVICE_PATTERNS.values():
                patterns_to_use.extend(patterns)
        
        for pattern in patterns_to_use:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if isinstance(match, tuple):
                    service = ' '.join(m for m in match if m).strip()
                else:
                    service = match.strip()
                if service and len(service) > 3:
                    # Capitalize for display
                    services.append(service.title())
        
        # Generic service patterns as fallback
        generic_patterns = [
            r'(?:need|want|looking for|interested in)\s+(?:a|an|to)?\s*(?:get\s+)?(?:my|the|our)?\s*(\w+(?:\s+\w+)?)\s*(?:repaired|fixed|replaced|installed|serviced)',
        ]
        
        for pattern in generic_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if match and len(match) > 3:
                    services.append(match.strip().title())
        
        # Filter out garbage/non-service words
        BLACKLISTED_SERVICES = {
            'stuff', 'thing', 'things', 'something', 'anything', 'everything',
            'it', 'that', 'this', 'them', 'there', 'here', 'what', 'which',
            'some', 'other', 'more', 'less', 'much', 'many', 'any', 'all',
            'like', 'just', 'also', 'really', 'actually', 'basically',
            'okay', 'alright', 'sure', 'yeah', 'yes', 'no', 'not',
            'good', 'bad', 'nice', 'fine', 'great', 'well',
            'about', 'around', 'back', 'over', 'done', 'going',
        }
        services = [s for s in services if s.lower().strip() not in BLACKLISTED_SERVICES]
        
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
