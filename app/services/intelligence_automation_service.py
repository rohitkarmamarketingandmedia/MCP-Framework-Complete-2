"""
MCP Intelligence Automation Service
====================================
The brain that connects all data sources (CallRail, Wufoo, Chat, Reviews)
into a unified intelligence engine that auto-suggests content.

Place at: app/services/intelligence_automation_service.py
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


class IntelligenceAutomationService:
    """
    Orchestrates intelligence gathering from all sources and generates
    actionable content suggestions.
    """
    
    # Minimum mentions to be considered a valid topic
    MIN_FREQUENCY_FOR_SUGGESTION = 3
    # Spike detection: 7d frequency must be N times the weekly average from 30d
    SPIKE_MULTIPLIER = 3.0
    # Rank drop threshold
    RANK_DROP_THRESHOLD = 5
    # Content staleness threshold (days)
    STALE_CONTENT_DAYS = 180
    
    # Topic normalization: common variations → canonical form
    TOPIC_NORMALIZATIONS = {
        'ac': 'air conditioning',
        'a/c': 'air conditioning',
        'hvac': 'heating and cooling',
        'ev charger': 'electric vehicle charger',
        'ev charging': 'electric vehicle charger',
        'mini split': 'ductless mini-split',
        'minisplit': 'ductless mini-split',
    }
    
    def __init__(self):
        self.ai_service = None  # Lazy-loaded
    
    def _get_ai_service(self):
        if not self.ai_service:
            try:
                from app.services.ai_service import ai_service
                self.ai_service = ai_service
            except ImportError:
                logger.warning("AI service not available")
        return self.ai_service
    
    # ==========================================
    # PHASE 1: MULTI-SOURCE DATA INGESTION
    # ==========================================
    
    def ingest_from_calls(self, client_id: str, interactions_data: dict):
        """
        Process Call Intelligence data and extract insights.
        Called after interaction_intelligence_service processes calls.
        
        interactions_data: output from interaction_intelligence_service.analyze_interactions()
        """
        insights = []
        
        # Extract questions as topics
        for q in interactions_data.get('top_questions', []):
            question = q.get('question', '') if isinstance(q, dict) else str(q)
            if question and len(question) > 10:
                insights.append({
                    'topic': self._normalize_topic(question),
                    'topic_type': 'question',
                    'source': 'callrail',
                    'raw_text': question,
                    'frequency': q.get('count', 1) if isinstance(q, dict) else 1,
                })
        
        # Extract pain points
        for pp in interactions_data.get('top_pain_points', []):
            pain = pp.get('pain_point', '') if isinstance(pp, dict) else str(pp)
            if pain and len(pain) > 10:
                insights.append({
                    'topic': self._normalize_topic(pain),
                    'topic_type': 'pain_point',
                    'source': 'callrail',
                    'raw_text': pain,
                    'frequency': pp.get('count', 1) if isinstance(pp, dict) else 1,
                })
        
        # Extract services
        for svc in interactions_data.get('top_services', []):
            service = svc.get('service', '') if isinstance(svc, dict) else str(svc)
            if service and len(service) > 3:
                insights.append({
                    'topic': self._normalize_topic(service),
                    'topic_type': 'service_request',
                    'source': 'callrail',
                    'raw_text': service,
                    'frequency': svc.get('count', 1) if isinstance(svc, dict) else 1,
                })
        
        # Extract locations from caller data
        for call in interactions_data.get('calls', []):
            caller_city = call.get('caller_city') or call.get('city')
            if caller_city and len(caller_city) > 2:
                insights.append({
                    'topic': caller_city.strip().title(),
                    'topic_type': 'location',
                    'source': 'callrail',
                    'raw_text': f"Call from {caller_city}",
                    'frequency': 1,
                })
        
        return self._store_insights(client_id, insights)
    
    def ingest_from_wufoo(self, client_id: str, submissions: list):
        """
        Process Wufoo form submissions and extract insights.
        submissions: list of form submission dicts
        """
        insights = []
        
        for sub in submissions:
            # Extract service requests from form fields
            for key, value in sub.items():
                if not value or not isinstance(value, str) or len(value) < 5:
                    continue
                
                key_lower = key.lower()
                
                # Service-related fields
                if any(term in key_lower for term in ['service', 'type of', 'what do you need', 'project', 'work needed', 'request']):
                    insights.append({
                        'topic': self._normalize_topic(value),
                        'topic_type': 'service_request',
                        'source': 'wufoo',
                        'raw_text': value,
                        'frequency': 1,
                    })
                
                # Location fields
                if any(term in key_lower for term in ['city', 'zip', 'location', 'address', 'area']):
                    # Try to extract city from address
                    city = self._extract_city(value)
                    if city:
                        insights.append({
                            'topic': city,
                            'topic_type': 'location',
                            'source': 'wufoo',
                            'raw_text': value,
                            'frequency': 1,
                        })
                
                # Problem/description fields
                if any(term in key_lower for term in ['describe', 'problem', 'issue', 'details', 'message', 'comment', 'notes']):
                    # Extract pain points from description
                    pain_topics = self._extract_topics_from_text(value)
                    for topic in pain_topics:
                        insights.append({
                            'topic': topic,
                            'topic_type': 'pain_point',
                            'source': 'wufoo',
                            'raw_text': value[:200],
                            'frequency': 1,
                        })
        
        return self._store_insights(client_id, insights)
    
    def ingest_from_chat(self, client_id: str, conversations: list):
        """
        Process chatbot conversations and extract insights.
        conversations: list of conversation dicts with messages
        """
        insights = []
        
        for conv in conversations:
            messages = conv.get('messages', [])
            
            for msg in messages:
                # Only process user messages (not bot responses)
                if msg.get('role') != 'user' or msg.get('sender') == 'bot':
                    continue
                
                text = msg.get('content', '') or msg.get('text', '')
                if not text or len(text) < 10:
                    continue
                
                # Check if it's a question
                if '?' in text or text.lower().startswith(('how', 'what', 'when', 'where', 'do you', 'can you', 'is there')):
                    insights.append({
                        'topic': self._normalize_topic(text),
                        'topic_type': 'question',
                        'source': 'chat',
                        'raw_text': text,
                        'frequency': 1,
                    })
                else:
                    # General topic extraction
                    topics = self._extract_topics_from_text(text)
                    for topic in topics:
                        insights.append({
                            'topic': topic,
                            'topic_type': 'service_request',
                            'source': 'chat',
                            'raw_text': text[:200],
                            'frequency': 1,
                        })
        
        return self._store_insights(client_id, insights)
    
    def ingest_from_reviews(self, client_id: str, reviews: list):
        """
        Process Google Reviews and extract insights.
        reviews: list of review dicts
        """
        insights = []
        
        for review in reviews:
            text = review.get('text', '') or review.get('comment', '')
            rating = review.get('rating', 0) or review.get('star_rating', 0)
            
            if not text or len(text) < 20:
                continue
            
            # Determine if praise or complaint based on rating
            topic_type = 'praise' if rating >= 4 else 'complaint' if rating <= 2 else 'service_request'
            sentiment = (rating - 3) / 2.0 if rating else 0  # Normalize to -1 to 1
            
            # Extract topics from review text
            topics = self._extract_topics_from_text(text)
            
            for topic in topics:
                insights.append({
                    'topic': topic,
                    'topic_type': topic_type,
                    'source': 'review',
                    'raw_text': text[:300],
                    'frequency': 1,
                    'sentiment': sentiment,
                })
            
            # Extract location mentions
            locations = self._extract_locations_from_text(text)
            for loc in locations:
                insights.append({
                    'topic': loc,
                    'topic_type': 'location',
                    'source': 'review',
                    'raw_text': text[:200],
                    'frequency': 1,
                })
        
        return self._store_insights(client_id, insights)
    
    # ==========================================
    # PHASE 1: STORAGE & DEDUPLICATION
    # ==========================================
    
    def _store_insights(self, client_id: str, insights: list) -> dict:
        """Store/update insights in the knowledge library, deduplicating by topic."""
        from app.database import db
        from app.models.intelligence_models import DBClientInsight
        
        stored = 0
        updated = 0
        
        for insight in insights:
            topic = insight.get('topic', '').strip()
            if not topic or len(topic) < 3:
                continue
            
            # Try to find existing insight with similar topic
            existing = DBClientInsight.query.filter(
                DBClientInsight.client_id == client_id,
                DBClientInsight.topic == topic,
                DBClientInsight.topic_type == insight['topic_type'],
            ).first()
            
            if existing:
                # Update frequency and metadata
                existing.frequency = (existing.frequency or 0) + insight.get('frequency', 1)
                existing.last_seen = datetime.utcnow()
                
                # Update sentiment (rolling average)
                if 'sentiment' in insight:
                    old_sentiment = existing.sentiment_avg or 0
                    new_sentiment = insight['sentiment']
                    existing.sentiment_avg = (old_sentiment * 0.7) + (new_sentiment * 0.3)
                
                # Append example quote
                try:
                    quotes = json.loads(existing.example_quotes or '[]')
                    raw = insight.get('raw_text', '')
                    if raw and raw not in quotes and len(quotes) < 10:
                        quotes.append(raw)
                        existing.example_quotes = json.dumps(quotes)
                except (json.JSONDecodeError, TypeError):
                    pass
                
                updated += 1
            else:
                # Create new insight
                new_insight = DBClientInsight(
                    client_id=client_id,
                    topic=topic,
                    topic_type=insight['topic_type'],
                    source=insight['source'],
                    frequency=insight.get('frequency', 1),
                    sentiment_avg=insight.get('sentiment', 0),
                    example_quotes=json.dumps([insight.get('raw_text', '')]) if insight.get('raw_text') else '[]',
                    business_value_score=self._score_business_value(topic, insight['topic_type']),
                )
                db.session.add(new_insight)
                stored += 1
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error storing insights: {e}")
        
        return {'stored': stored, 'updated': updated, 'total_processed': len(insights)}
    
    def _normalize_topic(self, text: str) -> str:
        """Normalize a topic string for deduplication."""
        text = text.strip().lower()
        # Remove question marks and trailing punctuation
        text = re.sub(r'[?!.]+$', '', text).strip()
        # Remove common prefixes
        text = re.sub(r'^(do you|can you|how do i|what is|i need|i want|looking for|interested in)\s+', '', text)
        # Apply known normalizations
        for variant, canonical in self.TOPIC_NORMALIZATIONS.items():
            if variant in text:
                text = text.replace(variant, canonical)
        # Capitalize first letter
        return text[:200].strip().capitalize() if text else ''
    
    def _extract_topics_from_text(self, text: str) -> list:
        """Extract meaningful topics/noun phrases from free text."""
        topics = []
        text_lower = text.lower()
        
        # Service-related pattern matching
        service_patterns = [
            r'(?:need|want|looking for|interested in|asking about|inquiring about)\s+(?:a\s+)?(.{5,60}?)(?:\.|,|$)',
            r'(?:repair|install|replace|fix|service|clean|maintain)\s+(?:my\s+|the\s+|our\s+)?(.{3,40}?)(?:\.|,|$)',
            r'(?:my|our|the)\s+(.{3,30}?)\s+(?:is|are|isn\'t|aren\'t|was|were)\s+(?:broken|not working|leaking|making noise|damaged)',
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                topic = match.strip()
                if len(topic) > 3 and len(topic) < 60:
                    topics.append(self._normalize_topic(topic))
        
        # If no specific patterns found, use the whole text as a topic (truncated)
        if not topics and len(text) > 20:
            topics.append(self._normalize_topic(text[:100]))
        
        return topics[:3]  # Max 3 topics per text
    
    def _extract_city(self, text: str) -> Optional[str]:
        """Extract city name from address/location text."""
        # Simple heuristic: take the first non-numeric word(s) that look like a city
        text = text.strip()
        # If it's just a zip code, skip
        if re.match(r'^\d{5}(-\d{4})?$', text):
            return None
        # Remove zip codes and state abbreviations
        text = re.sub(r'\d{5}(-\d{4})?', '', text)
        text = re.sub(r'\b[A-Z]{2}\b', '', text)
        # Take the remaining meaningful part
        parts = [p.strip() for p in text.split(',') if p.strip() and len(p.strip()) > 2]
        if parts:
            return parts[0].title()
        return None
    
    def _extract_locations_from_text(self, text: str) -> list:
        """Extract location mentions from review/description text."""
        # Common patterns: "in [City]", "near [City]", "[City] area"
        locations = []
        patterns = [
            r'(?:in|near|around|from|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:area|location|office|branch)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) > 2 and match.lower() not in ('the', 'this', 'that', 'our', 'their', 'your'):
                    locations.append(match.strip())
        return locations[:2]
    
    def _score_business_value(self, topic: str, topic_type: str) -> float:
        """Score a topic's business value (1-10)."""
        score = 5.0
        topic_lower = topic.lower()
        
        # High-value indicators
        high_value = ['install', 'repair', 'replace', 'emergency', 'cost', 'price', 'quote', 'financing', 'warranty']
        for hv in high_value:
            if hv in topic_lower:
                score += 1.5
                break
        
        # Service requests are high value
        if topic_type == 'service_request':
            score += 1.0
        elif topic_type == 'question':
            score += 0.5
        elif topic_type == 'complaint':
            score += 1.0  # Complaints are opportunities
        
        return min(10.0, max(1.0, score))
    
    # ==========================================
    # PHASE 1: TRENDING & SPIKE DETECTION
    # ==========================================
    
    def detect_trending_topics(self, client_id: str) -> list:
        """
        Detect topics that are spiking in frequency.
        Compares 7-day vs 30-day averages.
        """
        from app.models.intelligence_models import DBClientInsight
        
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)
        
        # Get all recent insights
        insights = DBClientInsight.query.filter(
            DBClientInsight.client_id == client_id,
            DBClientInsight.last_seen >= thirty_days_ago,
        ).all()
        
        trending = []
        for insight in insights:
            weekly_avg = (insight.frequency_30d or 0) / 4.3  # ~4.3 weeks in 30 days
            if weekly_avg == 0:
                weekly_avg = 0.5  # Avoid division by zero
            
            recent_rate = insight.frequency_7d or 0
            spike_ratio = recent_rate / weekly_avg
            
            if spike_ratio >= self.SPIKE_MULTIPLIER and recent_rate >= 2:
                insight.is_trending = True
                trending.append({
                    'topic': insight.topic,
                    'type': insight.topic_type,
                    'source': insight.source,
                    'frequency_7d': insight.frequency_7d,
                    'frequency_30d': insight.frequency_30d,
                    'spike_ratio': round(spike_ratio, 1),
                    'business_value': insight.business_value_score,
                })
        
        from app.database import db
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        return sorted(trending, key=lambda x: x['spike_ratio'] * x.get('business_value', 5), reverse=True)
    
    def update_frequency_windows(self, client_id: str):
        """
        Update the 7-day and 30-day frequency windows for all insights.
        Should be called daily by a scheduler.
        """
        from app.database import db
        from app.models.intelligence_models import DBClientInsight
        
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)
        
        insights = DBClientInsight.query.filter_by(client_id=client_id).all()
        
        for insight in insights:
            # Count mentions in last 7 days (from example_quotes timestamps or approximation)
            # Simplified: if last_seen is within 7 days, use frequency as proxy
            if insight.last_seen and insight.last_seen >= seven_days_ago:
                insight.frequency_7d = max(1, insight.frequency_7d or 0)
            else:
                insight.frequency_7d = max(0, (insight.frequency_7d or 0) - 1)
            
            if insight.last_seen and insight.last_seen >= thirty_days_ago:
                insight.frequency_30d = insight.frequency or 0
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    
    # ==========================================
    # PHASE 2: CONTENT SUGGESTION GENERATION
    # ==========================================
    
    def generate_suggestions(self, client_id: str) -> dict:
        """
        Main method: analyze all insights and generate content suggestions.
        Returns dict with suggestions by type.
        """
        from app.models.intelligence_models import DBClientInsight, DBAiSuggestion
        from app.models.db_models import DBClient, DBBlogPost
        
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        results = {
            'blog_suggestions': [],
            'faq_suggestions': [],
            'location_page_suggestions': [],
            'service_page_suggestions': [],
            'refresh_suggestions': [],
            'total_generated': 0,
        }
        
        # Get existing suggestions to avoid duplicates
        existing = DBAiSuggestion.query.filter(
            DBAiSuggestion.client_id == client_id,
            DBAiSuggestion.status.in_(['suggested', 'accepted', 'generating', 'draft'])
        ).all()
        existing_topics = set(s.target_keyword.lower() for s in existing if s.target_keyword)
        
        # Get existing blog posts
        blogs = DBBlogPost.query.filter_by(client_id=client_id).all()
        blog_topics = set()
        for blog in blogs:
            if blog.title:
                blog_topics.add(blog.title.lower())
            if blog.primary_keyword:
                blog_topics.add(blog.primary_keyword.lower())
        
        # Get all insights sorted by value
        insights = DBClientInsight.query.filter(
            DBClientInsight.client_id == client_id,
            DBClientInsight.frequency >= self.MIN_FREQUENCY_FOR_SUGGESTION,
            DBClientInsight.business_value_score >= 5.0,
        ).order_by(DBClientInsight.business_value_score.desc()).all()
        
        # --- BLOG POST SUGGESTIONS ---
        blog_candidates = [i for i in insights if i.topic_type in ('question', 'pain_point', 'service_request') and i.is_trending]
        for insight in blog_candidates[:10]:
            if insight.topic.lower() in existing_topics:
                continue
            if any(insight.topic.lower() in bt for bt in blog_topics):
                insight.has_content = True
                continue
            
            suggestion = self._create_blog_suggestion(client, insight)
            if suggestion:
                results['blog_suggestions'].append(suggestion)
                results['total_generated'] += 1
        
        # --- FAQ PAGE SUGGESTIONS ---
        questions = [i for i in insights if i.topic_type == 'question']
        if len(questions) >= 5:
            faq_suggestion = self._create_faq_suggestion(client, questions[:30])
            if faq_suggestion:
                results['faq_suggestions'].append(faq_suggestion)
                results['total_generated'] += 1
        
        # --- LOCATION PAGE SUGGESTIONS ---
        locations = DBClientInsight.query.filter(
            DBClientInsight.client_id == client_id,
            DBClientInsight.topic_type == 'location',
            DBClientInsight.frequency >= 3,
        ).order_by(DBClientInsight.frequency.desc()).limit(10).all()
        
        for loc in locations:
            if loc.topic.lower() in existing_topics:
                continue
            suggestion = self._create_location_suggestion(client, loc)
            if suggestion:
                results['location_page_suggestions'].append(suggestion)
                results['total_generated'] += 1
        
        # --- SERVICE PAGE SUGGESTIONS ---
        services = [i for i in insights if i.topic_type == 'service_request' and not i.has_content]
        for svc in services[:5]:
            if svc.topic.lower() in existing_topics:
                continue
            suggestion = self._create_service_page_suggestion(client, svc)
            if suggestion:
                results['service_page_suggestions'].append(suggestion)
                results['total_generated'] += 1
        
        # --- STALE CONTENT REFRESH ---
        stale_threshold = datetime.utcnow() - timedelta(days=self.STALE_CONTENT_DAYS)
        stale_blogs = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'published',
            DBBlogPost.created_at < stale_threshold,
        ).order_by(DBBlogPost.created_at.asc()).limit(10).all()
        
        for blog in stale_blogs:
            suggestion = self._create_refresh_suggestion(client, blog)
            if suggestion:
                results['refresh_suggestions'].append(suggestion)
                results['total_generated'] += 1
        
        return results
    
    def _create_blog_suggestion(self, client, insight) -> Optional[dict]:
        """Create a blog post suggestion from an insight."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        # Build evidence
        try:
            quotes = json.loads(insight.example_quotes or '[]')
        except (json.JSONDecodeError, TypeError):
            quotes = []
        
        evidence = f"{insight.frequency} mentions across {insight.source}"
        if insight.is_trending:
            evidence += " (TRENDING)"
        
        title = self._generate_blog_title(client, insight.topic)
        
        suggestion = DBAiSuggestion(
            client_id=client.id,
            suggestion_type='blog_post',
            title=title,
            target_keyword=insight.topic,
            content_brief=f"Customers are asking about '{insight.topic}'. Write a comprehensive blog post addressing this topic using the language customers actually use.",
            trigger_type='trending_topic' if insight.is_trending else 'frequent_topic',
            trigger_data=json.dumps({
                'insight_id': insight.id,
                'frequency': insight.frequency,
                'frequency_7d': insight.frequency_7d,
                'source': insight.source,
                'example_quotes': quotes[:5],
            }),
            evidence_summary=evidence,
            source_breakdown=json.dumps({insight.source: insight.frequency}),
            priority_score=insight.business_value_score,
            urgency='high' if insight.is_trending else 'normal',
            status='suggested',
            insight_ids=json.dumps([insight.id]),
        )
        
        db.session.add(suggestion)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating blog suggestion: {e}")
            return None
        
        return suggestion.to_dict()
    
    def _create_faq_suggestion(self, client, questions) -> Optional[dict]:
        """Create an FAQ page suggestion from accumulated questions."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        faq_items = []
        source_counts = defaultdict(int)
        
        for q in questions:
            faq_items.append({
                'question': q.topic,
                'frequency': q.frequency,
                'source': q.source,
            })
            source_counts[q.source] += q.frequency
        
        evidence = f"{len(questions)} unique questions from " + ", ".join(f"{src} ({cnt})" for src, cnt in source_counts.items())
        
        suggestion = DBAiSuggestion(
            client_id=client.id,
            suggestion_type='faq_page',
            title=f"Frequently Asked Questions - {client.business_name}",
            target_keyword=f"{client.industry or 'service'} FAQ",
            content_brief=f"Generate a comprehensive FAQ page with {len(questions)} questions based on real customer inquiries. Include schema markup for rich snippets.",
            outline=json.dumps(faq_items[:30]),
            trigger_type='accumulated_questions',
            evidence_summary=evidence,
            source_breakdown=json.dumps(dict(source_counts)),
            priority_score=7.0,
            urgency='normal',
            status='suggested',
            insight_ids=json.dumps([q.id for q in questions]),
        )
        
        db.session.add(suggestion)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return None
        
        return suggestion.to_dict()
    
    def _create_location_suggestion(self, client, location_insight) -> Optional[dict]:
        """Create a location page suggestion."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        city = location_insight.topic
        industry = client.industry or 'services'
        
        suggestion = DBAiSuggestion(
            client_id=client.id,
            suggestion_type='location_page',
            title=f"{industry.title()} in {city}",
            target_keyword=f"{industry.lower()} {city.lower()}",
            content_brief=f"Generate a location-specific service page for {city}. {location_insight.frequency} customers from this area have contacted us. Include local references, service area details, and a clear CTA.",
            trigger_type='location_demand',
            trigger_data=json.dumps({
                'city': city,
                'frequency': location_insight.frequency,
                'source': location_insight.source,
            }),
            evidence_summary=f"{location_insight.frequency} customer contacts from {city}",
            source_breakdown=json.dumps({location_insight.source: location_insight.frequency}),
            priority_score=min(10, 5 + location_insight.frequency * 0.5),
            urgency='normal',
            status='suggested',
        )
        
        db.session.add(suggestion)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return None
        
        return suggestion.to_dict()
    
    def _create_service_page_suggestion(self, client, service_insight) -> Optional[dict]:
        """Create a service page suggestion for a gap."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        suggestion = DBAiSuggestion(
            client_id=client.id,
            suggestion_type='service_page',
            title=f"{service_insight.topic.title()} Services",
            target_keyword=service_insight.topic.lower(),
            content_brief=f"Customers are requesting '{service_insight.topic}' but we don't have a dedicated page. Create a service page with: service description, benefits, process, FAQ section, and strong CTA.",
            trigger_type='service_gap',
            trigger_data=json.dumps({
                'service': service_insight.topic,
                'frequency': service_insight.frequency,
                'source': service_insight.source,
            }),
            evidence_summary=f"{service_insight.frequency} requests for '{service_insight.topic}' — no existing page",
            source_breakdown=json.dumps({service_insight.source: service_insight.frequency}),
            priority_score=service_insight.business_value_score,
            urgency='high' if service_insight.frequency >= 10 else 'normal',
            status='suggested',
        )
        
        db.session.add(suggestion)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return None
        
        return suggestion.to_dict()
    
    def _create_refresh_suggestion(self, client, blog) -> Optional[dict]:
        """Create a content refresh suggestion for stale blog post."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        days_old = (datetime.utcnow() - blog.created_at).days if blog.created_at else 0
        
        suggestion = DBAiSuggestion(
            client_id=client.id,
            suggestion_type='refresh_post',
            title=f"Refresh: {blog.title}",
            target_keyword=blog.primary_keyword or '',
            content_brief=f"This post is {days_old} days old. Refresh with: updated stats/info, add 300+ new words, improve headings, add new FAQ section if applicable.",
            trigger_type='stale_content',
            trigger_data=json.dumps({
                'blog_id': blog.id,
                'blog_title': blog.title,
                'created_at': blog.created_at.isoformat() if blog.created_at else None,
                'days_old': days_old,
                'word_count': blog.word_count,
            }),
            evidence_summary=f"Published {days_old} days ago — needs refresh",
            blog_post_id=blog.id,
            priority_score=min(10, 5 + (days_old / 90)),
            urgency='high' if days_old > 365 else 'normal',
            status='suggested',
        )
        
        db.session.add(suggestion)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return None
        
        return suggestion.to_dict()
    
    def _generate_blog_title(self, client, topic: str) -> str:
        """Generate a compelling blog title for a topic."""
        industry = client.industry or 'Service'
        geo = ''
        try:
            if client.geo:
                geo = client.geo.split(',')[0].strip()
        except Exception:
            pass
        
        # Simple title generation (AI can enhance later)
        templates = [
            f"Everything You Need to Know About {topic.title()}",
            f"{topic.title()}: A Complete Guide" + (f" for {geo} Homeowners" if geo else ""),
            f"Top Questions About {topic.title()} — Answered by Experts",
            f"Why {topic.title()} Matters" + (f" in {geo}" if geo else ""),
        ]
        
        import random
        return random.choice(templates)
    
    # ==========================================
    # PHASE 3: RANK DROP DETECTION
    # ==========================================
    
    def check_rank_drops(self, client_id: str) -> list:
        """
        Check for significant rank drops and create alerts + recovery suggestions.
        Call this after rankings are updated.
        """
        from app.database import db
        from app.models.db_models import DBRankHistory, DBClient
        from app.models.intelligence_models import DBRankAlert, DBAiSuggestion
        from sqlalchemy import func
        
        client = DBClient.query.get(client_id)
        if not client:
            return []
        
        now = datetime.utcnow()
        one_day_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        
        alerts = []
        
        # Get the latest ranking for each keyword
        subq = db.session.query(
            DBRankHistory.keyword,
            func.max(DBRankHistory.checked_at).label('latest')
        ).filter(
            DBRankHistory.client_id == client_id,
        ).group_by(DBRankHistory.keyword).subquery()
        
        latest = db.session.query(DBRankHistory).join(
            subq,
            db.and_(
                DBRankHistory.keyword == subq.c.keyword,
                DBRankHistory.checked_at == subq.c.latest,
                DBRankHistory.client_id == client_id
            )
        ).all()
        
        for rank in latest:
            change = rank.change or 0
            
            # Check for significant drops
            if change <= -self.RANK_DROP_THRESHOLD:
                # Check if we already have an alert for this keyword recently
                existing_alert = DBRankAlert.query.filter(
                    DBRankAlert.client_id == client_id,
                    DBRankAlert.keyword == rank.keyword,
                    DBRankAlert.created_at >= seven_days_ago,
                ).first()
                
                if existing_alert:
                    continue
                
                severity = 'critical' if change <= -15 else 'high' if change <= -10 else 'medium'
                
                alert = DBRankAlert(
                    client_id=client_id,
                    keyword=rank.keyword,
                    old_position=rank.previous_position,
                    new_position=rank.position,
                    change=change,
                    ranking_url=rank.url or '',
                    search_volume=rank.search_volume or 0,
                    alert_type='rank_drop',
                    severity=severity,
                )
                db.session.add(alert)
                
                # Auto-create recovery suggestion
                recovery = DBAiSuggestion(
                    client_id=client_id,
                    suggestion_type='recovery_post',
                    title=f"Recovery: '{rank.keyword}' dropped {abs(change)} positions",
                    target_keyword=rank.keyword,
                    content_brief=f"Keyword '{rank.keyword}' dropped from position {rank.previous_position or '?'} to {rank.position}. Create supporting content to recover ranking.",
                    trigger_type='rank_drop',
                    trigger_data=json.dumps({
                        'keyword': rank.keyword,
                        'old_position': rank.previous_position,
                        'new_position': rank.position,
                        'change': change,
                        'url': rank.url or '',
                        'search_volume': rank.search_volume or 0,
                    }),
                    evidence_summary=f"Dropped {abs(change)} positions (#{rank.previous_position or '?'} → #{rank.position})",
                    keyword_dropped=rank.keyword,
                    old_position=rank.previous_position,
                    new_position=rank.position,
                    priority_score=min(10, 6 + abs(change) * 0.3),
                    urgency='urgent' if severity == 'critical' else 'high',
                    status='suggested',
                )
                db.session.add(recovery)
                
                alerts.append(alert)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating rank alerts: {e}")
        
        return [a.to_dict() for a in alerts]
    
    # ==========================================
    # PHASE 4: COMPETITOR RESPONSE
    # ==========================================
    
    def check_competitor_opportunities(self, client_id: str, competitor_data: list) -> list:
        """
        Analyze competitor data for steal opportunities and counter-post suggestions.
        competitor_data: from competitor-dashboard endpoint
        """
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        from app.models.db_models import DBClient, DBRankHistory
        from sqlalchemy import func
        
        client = DBClient.query.get(client_id)
        if not client:
            return []
        
        suggestions = []
        
        # Get client's ranked keywords
        subq = db.session.query(
            DBRankHistory.keyword,
            func.max(DBRankHistory.checked_at).label('latest')
        ).filter(
            DBRankHistory.client_id == client_id,
        ).group_by(DBRankHistory.keyword).subquery()
        
        client_keywords = set()
        latest_ranks = db.session.query(DBRankHistory).join(
            subq, db.and_(
                DBRankHistory.keyword == subq.c.keyword,
                DBRankHistory.checked_at == subq.c.latest,
                DBRankHistory.client_id == client_id
            )
        ).all()
        
        for r in latest_ranks:
            if r.position and r.position <= 100:
                client_keywords.add(r.keyword.lower())
        
        # Find steal opportunities across competitors
        for comp in competitor_data:
            comp_rankings = comp.get('rankings', {})
            comp_domain = comp.get('domain', '')
            
            for kw, position in comp_rankings.items():
                kw_lower = kw.lower()
                
                # Steal opportunity: competitor ranks 4-10, client doesn't rank
                if 4 <= position <= 10 and kw_lower not in client_keywords:
                    suggestion = DBAiSuggestion(
                        client_id=client_id,
                        suggestion_type='blog_post',
                        title=f"Target: '{kw}' (competitor ranks #{position})",
                        target_keyword=kw,
                        content_brief=f"Competitor {comp_domain} ranks #{position} for '{kw}' but you don't rank. A strong, comprehensive post could win this keyword.",
                        trigger_type='competitor_steal',
                        trigger_data=json.dumps({
                            'competitor': comp_domain,
                            'competitor_position': position,
                            'keyword': kw,
                        }),
                        evidence_summary=f"Steal opportunity: {comp_domain} has weak position #{position}",
                        competitor_domain=comp_domain,
                        priority_score=min(10, 5 + (11 - position) * 0.5),
                        urgency='normal',
                        status='suggested',
                    )
                    db.session.add(suggestion)
                    suggestions.append(suggestion)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating competitor suggestions: {e}")
        
        return [s.to_dict() for s in suggestions[:10]]
    
    # ==========================================
    # PHASE 5: DAILY BRIEFING
    # ==========================================
    
    def get_daily_briefing(self, client_id: str) -> dict:
        """
        Generate the daily AI briefing for a client.
        Aggregates all alerts, suggestions, and insights.
        """
        from app.models.intelligence_models import DBClientInsight, DBAiSuggestion, DBRankAlert
        from app.models.db_models import (
            DBClientInsight, DBAiSuggestion, DBRankAlert,
            DBBlogPost, DBClient
        )
        
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)
        
        # Pending suggestions
        suggestions = DBAiSuggestion.query.filter(
            DBAiSuggestion.client_id == client_id,
            DBAiSuggestion.status == 'suggested',
        ).order_by(DBAiSuggestion.priority_score.desc()).limit(20).all()
        
        # Rank alerts
        rank_alerts = DBRankAlert.query.filter(
            DBRankAlert.client_id == client_id,
            DBRankAlert.created_at >= seven_days_ago,
        ).order_by(DBRankAlert.created_at.desc()).limit(10).all()
        
        # Trending topics
        trending = DBClientInsight.query.filter(
            DBClientInsight.client_id == client_id,
            DBClientInsight.is_trending == True,
        ).order_by(DBClientInsight.frequency_7d.desc()).limit(10).all()
        
        # Stale content
        stale_threshold = now - timedelta(days=self.STALE_CONTENT_DAYS)
        stale_count = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'published',
            DBBlogPost.created_at < stale_threshold,
        ).count()
        
        # Knowledge library stats
        total_insights = DBClientInsight.query.filter_by(client_id=client_id).count()
        recent_insights = DBClientInsight.query.filter(
            DBClientInsight.client_id == client_id,
            DBClientInsight.last_seen >= seven_days_ago,
        ).count()
        
        # Suggestion stats
        suggestion_stats = {
            'pending': DBAiSuggestion.query.filter_by(client_id=client_id, status='suggested').count(),
            'accepted': DBAiSuggestion.query.filter_by(client_id=client_id, status='accepted').count(),
            'published': DBAiSuggestion.query.filter(
                DBAiSuggestion.client_id == client_id,
                DBAiSuggestion.status == 'published',
                DBAiSuggestion.published_at >= thirty_days_ago,
            ).count(),
            'dismissed': DBAiSuggestion.query.filter(
                DBAiSuggestion.client_id == client_id,
                DBAiSuggestion.status == 'dismissed',
                DBAiSuggestion.updated_at >= thirty_days_ago,
            ).count(),
        }
        
        # Build priority action items
        actions = []
        
        for alert in rank_alerts:
            if not alert.is_read:
                actions.append({
                    'type': 'rank_drop',
                    'urgency': alert.severity,
                    'title': f"'{alert.keyword}' dropped {abs(alert.change)} positions",
                    'detail': f"Was #{alert.old_position}, now #{alert.new_position}",
                    'action': 'create_recovery',
                    'action_data': {'alert_id': alert.id, 'keyword': alert.keyword},
                })
        
        for s in suggestions[:10]:
            actions.append({
                'type': s.suggestion_type,
                'urgency': s.urgency,
                'title': s.title,
                'detail': s.evidence_summary,
                'action': 'review_suggestion',
                'action_data': {'suggestion_id': s.id},
            })
        
        # Sort by urgency
        urgency_order = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}
        actions.sort(key=lambda x: urgency_order.get(x['urgency'], 2))
        
        return {
            'client_name': client.business_name,
            'generated_at': now.isoformat(),
            'summary': {
                'action_items': len(actions),
                'rank_alerts': len(rank_alerts),
                'trending_topics': len(trending),
                'stale_content': stale_count,
                'knowledge_library_size': total_insights,
                'new_insights_7d': recent_insights,
            },
            'actions': actions[:15],
            'suggestions': [s.to_dict() for s in suggestions],
            'rank_alerts': [a.to_dict() for a in rank_alerts],
            'trending_topics': [t.to_dict() for t in trending],
            'suggestion_stats': suggestion_stats,
        }
    
    # ==========================================
    # SUGGESTION LIFECYCLE
    # ==========================================
    
    def accept_suggestion(self, suggestion_id: str, user_id: str) -> dict:
        """Accept a suggestion and move it to 'accepted' status."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        suggestion = DBAiSuggestion.query.get(suggestion_id)
        if not suggestion:
            return {'error': 'Suggestion not found'}
        
        suggestion.status = 'accepted'
        suggestion.accepted_by = user_id
        suggestion.accepted_at = datetime.utcnow()
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return {'error': 'Database error'}
        
        return suggestion.to_dict()
    
    def dismiss_suggestion(self, suggestion_id: str, reason: str = '') -> dict:
        """Dismiss a suggestion."""
        from app.database import db
        from app.models.intelligence_models import DBAiSuggestion
        
        suggestion = DBAiSuggestion.query.get(suggestion_id)
        if not suggestion:
            return {'error': 'Suggestion not found'}
        
        suggestion.status = 'dismissed'
        suggestion.dismissed_reason = reason
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return {'error': 'Database error'}
        
        return suggestion.to_dict()
    
    def execute_suggestion(self, suggestion_id: str) -> dict:
        """Execute a suggestion — generate the actual content."""
        from app.models.intelligence_models import DBAiSuggestion
        
        suggestion = DBAiSuggestion.query.get(suggestion_id)
        if not suggestion:
            return {'error': 'Suggestion not found'}
        
        # Route to appropriate content generator based on type
        generators = {
            'blog_post': self._execute_blog_suggestion,
            'recovery_post': self._execute_blog_suggestion,
            'faq_page': self._execute_faq_suggestion,
            'location_page': self._execute_location_suggestion,
            'service_page': self._execute_service_suggestion,
            'refresh_post': self._execute_refresh_suggestion,
        }
        
        generator = generators.get(suggestion.suggestion_type)
        if generator:
            return generator(suggestion)
        
        return {'error': f'No generator for type: {suggestion.suggestion_type}'}
    
    def _execute_blog_suggestion(self, suggestion) -> dict:
        """Generate a blog post from a suggestion. Returns data for the content API."""
        return {
            'action': 'generate_blog',
            'keyword': suggestion.target_keyword,
            'title': suggestion.title,
            'brief': suggestion.content_brief,
            'suggestion_id': suggestion.id,
            'client_id': suggestion.client_id,
        }
    
    def _execute_faq_suggestion(self, suggestion) -> dict:
        """Generate FAQ content from a suggestion."""
        try:
            questions = json.loads(suggestion.outline or '[]')
        except (json.JSONDecodeError, TypeError):
            questions = []
        
        return {
            'action': 'generate_faq',
            'questions': questions,
            'title': suggestion.title,
            'suggestion_id': suggestion.id,
            'client_id': suggestion.client_id,
        }
    
    def _execute_location_suggestion(self, suggestion) -> dict:
        """Generate location page from a suggestion."""
        return {
            'action': 'generate_location_page',
            'keyword': suggestion.target_keyword,
            'title': suggestion.title,
            'brief': suggestion.content_brief,
            'suggestion_id': suggestion.id,
            'client_id': suggestion.client_id,
        }
    
    def _execute_service_suggestion(self, suggestion) -> dict:
        """Generate service page from a suggestion."""
        return {
            'action': 'generate_service_page',
            'keyword': suggestion.target_keyword,
            'title': suggestion.title,
            'brief': suggestion.content_brief,
            'suggestion_id': suggestion.id,
            'client_id': suggestion.client_id,
        }
    
    def _execute_refresh_suggestion(self, suggestion) -> dict:
        """Generate refresh recommendations for a blog post."""
        return {
            'action': 'refresh_blog',
            'blog_id': suggestion.blog_post_id,
            'keyword': suggestion.target_keyword,
            'brief': suggestion.content_brief,
            'suggestion_id': suggestion.id,
            'client_id': suggestion.client_id,
        }


# Singleton instance
intelligence_automation = IntelligenceAutomationService()
