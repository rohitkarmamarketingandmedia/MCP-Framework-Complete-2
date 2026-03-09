"""
MCP Intelligence Automation — Auto-Migration
=============================================
Place at: app/models/intelligence_models.py

This file defines the new models AND auto-creates tables on import.
Import this in db_models.py at the bottom:

    from app.models.intelligence_models import DBClientInsight, DBAiSuggestion, DBRankAlert

OR import it in the routes file — the tables will create on first use.
"""
from app.database import db
from datetime import datetime
import uuid
import json


class DBClientInsight(db.Model):
    """Knowledge library entry — extracted from calls, forms, chat, reviews."""
    __tablename__ = 'client_insights'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = db.Column(db.String(36), db.ForeignKey('clients.id'), nullable=False, index=True)
    
    topic = db.Column(db.String(200), nullable=False)
    topic_type = db.Column(db.String(50), nullable=False)       # question, pain_point, service_request, praise, complaint, location
    category = db.Column(db.String(100))
    
    source = db.Column(db.String(50), nullable=False)           # callrail, wufoo, chat, review
    frequency = db.Column(db.Integer, default=1)
    frequency_7d = db.Column(db.Integer, default=0)
    frequency_30d = db.Column(db.Integer, default=0)
    
    sentiment_avg = db.Column(db.Float, default=0.0)
    business_value_score = db.Column(db.Float, default=5.0)
    example_quotes = db.Column(db.Text)                         # JSON array
    related_keywords = db.Column(db.Text)                       # JSON array
    
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    seasonal_peak = db.Column(db.String(20))
    
    is_trending = db.Column(db.Boolean, default=False)
    has_content = db.Column(db.Boolean, default=False)
    content_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'topic': self.topic,
            'topic_type': self.topic_type,
            'category': self.category,
            'source': self.source,
            'frequency': self.frequency,
            'frequency_7d': self.frequency_7d,
            'frequency_30d': self.frequency_30d,
            'sentiment_avg': self.sentiment_avg,
            'business_value_score': self.business_value_score,
            'example_quotes': json.loads(self.example_quotes) if self.example_quotes else [],
            'related_keywords': json.loads(self.related_keywords) if self.related_keywords else [],
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'seasonal_peak': self.seasonal_peak,
            'is_trending': self.is_trending,
            'has_content': self.has_content,
            'content_url': self.content_url,
        }


class DBAiSuggestion(db.Model):
    """AI-generated content suggestion with full lifecycle tracking."""
    __tablename__ = 'ai_suggestions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = db.Column(db.String(36), db.ForeignKey('clients.id'), nullable=False, index=True)
    
    suggestion_type = db.Column(db.String(50), nullable=False)  # blog_post, faq_page, location_page, service_page, refresh_post, recovery_post, counter_post, social_post
    
    title = db.Column(db.String(300))
    target_keyword = db.Column(db.String(200))
    outline = db.Column(db.Text)                                # JSON
    content_brief = db.Column(db.Text)
    
    trigger_type = db.Column(db.String(50))                     # trending_topic, service_gap, rank_drop, competitor_move, stale_content, review_theme, location_demand
    trigger_data = db.Column(db.Text)                           # JSON
    evidence_summary = db.Column(db.String(500))
    
    insight_ids = db.Column(db.Text)                            # JSON array
    source_breakdown = db.Column(db.Text)                       # JSON
    
    priority_score = db.Column(db.Float, default=5.0)
    urgency = db.Column(db.String(20), default='normal')        # low, normal, high, urgent
    
    status = db.Column(db.String(30), default='suggested', index=True)  # suggested, accepted, dismissed, generating, draft, published, effective
    
    blog_post_id = db.Column(db.String(36))
    published_url = db.Column(db.String(500))
    
    keyword_dropped = db.Column(db.String(200))
    old_position = db.Column(db.Integer)
    new_position = db.Column(db.Integer)
    recovery_status = db.Column(db.String(30))
    
    competitor_domain = db.Column(db.String(200))
    competitor_url = db.Column(db.String(500))
    
    outcome_data = db.Column(db.Text)                           # JSON
    
    dismissed_reason = db.Column(db.String(200))
    accepted_by = db.Column(db.String(36))
    accepted_at = db.Column(db.DateTime)
    published_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'suggestion_type': self.suggestion_type,
            'title': self.title,
            'target_keyword': self.target_keyword,
            'outline': json.loads(self.outline) if self.outline else None,
            'content_brief': self.content_brief,
            'trigger_type': self.trigger_type,
            'trigger_data': json.loads(self.trigger_data) if self.trigger_data else None,
            'evidence_summary': self.evidence_summary,
            'source_breakdown': json.loads(self.source_breakdown) if self.source_breakdown else None,
            'priority_score': self.priority_score,
            'urgency': self.urgency,
            'status': self.status,
            'blog_post_id': self.blog_post_id,
            'published_url': self.published_url,
            'keyword_dropped': self.keyword_dropped,
            'old_position': self.old_position,
            'new_position': self.new_position,
            'recovery_status': self.recovery_status,
            'competitor_domain': self.competitor_domain,
            'competitor_url': self.competitor_url,
            'dismissed_reason': self.dismissed_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }


class DBRankAlert(db.Model):
    """Rank drop/gain alert for a specific keyword."""
    __tablename__ = 'rank_alerts'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = db.Column(db.String(36), db.ForeignKey('clients.id'), nullable=False, index=True)
    
    keyword = db.Column(db.String(200), nullable=False)
    old_position = db.Column(db.Integer)
    new_position = db.Column(db.Integer)
    change = db.Column(db.Integer)
    ranking_url = db.Column(db.String(500))
    search_volume = db.Column(db.Integer, default=0)
    
    alert_type = db.Column(db.String(30))                       # rank_drop, rank_gain, lost_ranking, new_ranking
    severity = db.Column(db.String(20), default='medium')       # low, medium, high, critical
    
    recovery_suggestion_id = db.Column(db.String(36))
    recovery_status = db.Column(db.String(30), default='pending')
    recovered_at = db.Column(db.DateTime)
    recovered_position = db.Column(db.Integer)
    
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'keyword': self.keyword,
            'old_position': self.old_position,
            'new_position': self.new_position,
            'change': self.change,
            'ranking_url': self.ranking_url,
            'search_volume': self.search_volume,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'recovery_status': self.recovery_status,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
