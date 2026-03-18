"""
MCP Framework - Content Schedule & Comment Models
Auto-generation scheduling and client review comments
"""
from datetime import datetime, timedelta
from typing import Optional, List
import uuid
import json

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import db


class DBContentSchedule(db.Model):
    """Per-client blog auto-generation schedule"""
    __tablename__ = 'content_schedules'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), unique=True, index=True)
    
    # Schedule settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    blogs_per_week: Mapped[int] = mapped_column(Integer, default=2)  # 1-7
    
    # Preferred generation days (JSON array of 0-6, Mon=0)
    # e.g., [0, 3] = Monday and Thursday for 2/week
    preferred_days: Mapped[str] = mapped_column(Text, default='[0, 3]')
    
    # Preferred hour to generate (UTC, 0-23)
    preferred_hour: Mapped[int] = mapped_column(Integer, default=9)
    
    # Keyword rotation tracking
    # Index into the client's primary_keywords × service_cities matrix
    keyword_index: Mapped[int] = mapped_column(Integer, default=0)
    city_index: Mapped[int] = mapped_column(Integer, default=0)
    
    # Custom keyword queue (optional override - JSON array)
    # If set, these are used instead of rotating through client keywords
    keyword_queue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of strings
    
    # Generation settings
    target_word_count: Mapped[int] = mapped_column(Integer, default=1800)
    include_faq: Mapped[bool] = mapped_column(Boolean, default=True)
    faq_count: Mapped[int] = mapped_column(Integer, default=5)
    verify_content: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Email settings
    send_to_client: Mapped[bool] = mapped_column(Boolean, default=True)
    client_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Override client.email
    cc_emails: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Comma-separated
    
    # Tracking
    total_generated: Mapped[int] = mapped_column(Integer, default=0)
    last_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_generation_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_keyword_used: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, client_id: str, **kwargs):
        self.id = f"sched_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        if not self.next_generation_at:
            self.next_generation_at = self._calculate_next_run()
    
    def get_preferred_days(self) -> List[int]:
        try:
            return json.loads(self.preferred_days) if self.preferred_days else [0, 3]
        except (json.JSONDecodeError, TypeError):
            return [0, 3]
    
    def set_preferred_days(self, days: List[int]):
        self.preferred_days = json.dumps(days)
    
    def get_keyword_queue(self) -> List[str]:
        if not self.keyword_queue:
            return []
        try:
            return json.loads(self.keyword_queue)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def _calculate_next_run(self) -> Optional[datetime]:
        """Calculate the next generation time based on schedule"""
        if not self.is_active:
            return None
        
        now = datetime.utcnow()
        days = self.get_preferred_days()
        if not days:
            return None
        
        # Find the next preferred day
        for days_ahead in range(1, 8):
            candidate = now + timedelta(days=days_ahead)
            if candidate.weekday() in days:
                return candidate.replace(
                    hour=self.preferred_hour, minute=0, second=0, microsecond=0
                )
        
        return now + timedelta(days=3)  # Fallback
    
    def advance_schedule(self):
        """Move to next generation time after a successful run"""
        self.last_generated_at = datetime.utcnow()
        self.total_generated += 1
        self.next_generation_at = self._calculate_next_run()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'is_active': self.is_active,
            'blogs_per_week': self.blogs_per_week,
            'preferred_days': self.get_preferred_days(),
            'preferred_hour': self.preferred_hour,
            'keyword_index': self.keyword_index,
            'city_index': self.city_index,
            'keyword_queue': self.get_keyword_queue(),
            'target_word_count': self.target_word_count,
            'include_faq': self.include_faq,
            'faq_count': self.faq_count,
            'verify_content': self.verify_content,
            'send_to_client': self.send_to_client,
            'client_email': self.client_email,
            'cc_emails': self.cc_emails,
            'total_generated': self.total_generated,
            'last_generated_at': self.last_generated_at.isoformat() if self.last_generated_at else None,
            'next_generation_at': self.next_generation_at.isoformat() if self.next_generation_at else None,
            'last_keyword_used': self.last_keyword_used,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class DBContentComment(db.Model):
    """Comments on blog posts — from clients or internal team"""
    __tablename__ = 'content_comments'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    blog_id: Mapped[str] = mapped_column(String(50), ForeignKey('blog_posts.id', ondelete='CASCADE'), index=True)
    
    # Who commented — either a logged-in user or a client via review token
    author_type: Mapped[str] = mapped_column(String(20), default='client')  # 'client', 'team', 'system'
    author_name: Mapped[str] = mapped_column(String(200), default='')
    author_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # If logged-in team member
    
    # Comment content
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Threading (optional)
    parent_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Reply to another comment
    
    # Status
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __init__(self, blog_id: str, comment: str, **kwargs):
        self.id = f"cmt_{uuid.uuid4().hex[:12]}"
        self.blog_id = blog_id
        self.comment = comment
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'blog_id': self.blog_id,
            'author_type': self.author_type,
            'author_name': self.author_name,
            'author_email': self.author_email,
            'user_id': self.user_id,
            'comment': self.comment,
            'parent_id': self.parent_id,
            'is_resolved': self.is_resolved,
            'resolved_by': self.resolved_by,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
