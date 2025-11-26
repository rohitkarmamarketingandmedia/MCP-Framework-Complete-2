"""
MCP Framework - SQLAlchemy Database Models
PostgreSQL-backed models for production deployment
"""
from datetime import datetime
from typing import Optional, List
import uuid
import hashlib
import secrets
import json

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import db


# ============================================
# User Model
# ============================================

class UserRole:
    ADMIN = 'admin'
    MANAGER = 'manager'
    CLIENT = 'client'
    VIEWER = 'viewer'


class DBUser(db.Model):
    """User account for authentication and authorization"""
    __tablename__ = 'users'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER)
    api_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    client_ids: Mapped[str] = mapped_column(Text, default='[]')  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __init__(self, email: str, name: str, password: str, role: str = UserRole.VIEWER):
        self.id = f"user_{uuid.uuid4().hex[:12]}"
        self.email = email.lower()
        self.name = name
        self.role = role
        self.password_salt = secrets.token_hex(16)
        self.password_hash = self._hash_password(password, self.password_salt)
        self.api_key = f"mcp_{secrets.token_hex(16)}"
        self.client_ids = '[]'
        self.is_active = True
        self.created_at = datetime.utcnow()
    
    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    
    def verify_password(self, password: str) -> bool:
        return self.password_hash == self._hash_password(password, self.password_salt)
    
    def set_password(self, password: str):
        self.password_salt = secrets.token_hex(16)
        self.password_hash = self._hash_password(password, self.password_salt)
    
    def get_client_ids(self) -> List[str]:
        return json.loads(self.client_ids)
    
    def set_client_ids(self, ids: List[str]):
        self.client_ids = json.dumps(ids)
    
    def has_access_to_client(self, client_id: str) -> bool:
        if self.role in [UserRole.ADMIN, UserRole.MANAGER]:
            return True
        return client_id in self.get_client_ids()
    
    @property
    def can_generate_content(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.CLIENT]
    
    @property
    def can_manage_clients(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.MANAGER]
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'role': self.role,
            'client_ids': self.get_client_ids(),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


# ============================================
# Client Model
# ============================================

class DBClient(db.Model):
    """Client/business profile with SEO settings"""
    __tablename__ = 'clients'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), default='')
    geo: Mapped[str] = mapped_column(String(255), default='')
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # SEO Settings (stored as JSON)
    primary_keywords: Mapped[str] = mapped_column(Text, default='[]')
    secondary_keywords: Mapped[str] = mapped_column(Text, default='[]')
    competitors: Mapped[str] = mapped_column(Text, default='[]')
    service_areas: Mapped[str] = mapped_column(Text, default='[]')
    unique_selling_points: Mapped[str] = mapped_column(Text, default='[]')
    
    tone: Mapped[str] = mapped_column(String(100), default='professional')
    
    # Integration credentials (stored as JSON)
    integrations: Mapped[str] = mapped_column(Text, default='{}')
    
    # Subscription
    subscription_tier: Mapped[str] = mapped_column(String(50), default='standard')
    monthly_content_limit: Mapped[int] = mapped_column(Integer, default=10)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, business_name: str, **kwargs):
        self.id = f"client_{uuid.uuid4().hex[:12]}"
        self.business_name = business_name
        self.industry = kwargs.get('industry', '')
        self.geo = kwargs.get('geo', '')
        self.website_url = kwargs.get('website_url')
        self.phone = kwargs.get('phone')
        self.email = kwargs.get('email')
        self.primary_keywords = json.dumps(kwargs.get('primary_keywords', []))
        self.secondary_keywords = json.dumps(kwargs.get('secondary_keywords', []))
        self.competitors = json.dumps(kwargs.get('competitors', []))
        self.service_areas = json.dumps(kwargs.get('service_areas', []))
        self.unique_selling_points = json.dumps(kwargs.get('unique_selling_points', []))
        self.tone = kwargs.get('tone', 'professional')
        self.integrations = json.dumps(kwargs.get('integrations', {}))
        self.subscription_tier = kwargs.get('subscription_tier', 'standard')
        self.monthly_content_limit = kwargs.get('monthly_content_limit', 10)
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def get_primary_keywords(self) -> List[str]:
        return json.loads(self.primary_keywords)
    
    def set_primary_keywords(self, keywords: List[str]):
        self.primary_keywords = json.dumps(keywords)
    
    def get_secondary_keywords(self) -> List[str]:
        return json.loads(self.secondary_keywords)
    
    def get_competitors(self) -> List[str]:
        return json.loads(self.competitors)
    
    def get_service_areas(self) -> List[str]:
        return json.loads(self.service_areas)
    
    def get_unique_selling_points(self) -> List[str]:
        return json.loads(self.unique_selling_points)
    
    def get_integrations(self) -> dict:
        return json.loads(self.integrations)
    
    def get_seo_context(self) -> dict:
        return {
            'business_name': self.business_name,
            'industry': self.industry,
            'geo': self.geo,
            'primary_keywords': self.get_primary_keywords(),
            'secondary_keywords': self.get_secondary_keywords(),
            'competitors': self.get_competitors(),
            'service_areas': self.get_service_areas(),
            'usps': self.get_unique_selling_points(),
            'tone': self.tone
        }
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'business_name': self.business_name,
            'industry': self.industry,
            'geo': self.geo,
            'website_url': self.website_url,
            'phone': self.phone,
            'email': self.email,
            'primary_keywords': self.get_primary_keywords(),
            'secondary_keywords': self.get_secondary_keywords(),
            'competitors': self.get_competitors(),
            'service_areas': self.get_service_areas(),
            'unique_selling_points': self.get_unique_selling_points(),
            'tone': self.tone,
            'subscription_tier': self.subscription_tier,
            'monthly_content_limit': self.monthly_content_limit,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ============================================
# Content Model
# ============================================

class ContentStatus:
    DRAFT = 'draft'
    REVIEW = 'review'
    APPROVED = 'approved'
    PUBLISHED = 'published'
    ARCHIVED = 'archived'


class DBBlogPost(db.Model):
    """Blog post content with SEO metadata"""
    __tablename__ = 'blog_posts'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), default='')
    meta_title: Mapped[str] = mapped_column(String(100), default='')
    meta_description: Mapped[str] = mapped_column(String(200), default='')
    
    body: Mapped[str] = mapped_column(Text, default='')
    excerpt: Mapped[str] = mapped_column(Text, default='')
    
    primary_keyword: Mapped[str] = mapped_column(String(255), default='')
    secondary_keywords: Mapped[str] = mapped_column(Text, default='[]')  # JSON
    
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    seo_score: Mapped[int] = mapped_column(Integer, default=0)
    
    internal_links: Mapped[str] = mapped_column(Text, default='[]')  # JSON
    external_links: Mapped[str] = mapped_column(Text, default='[]')  # JSON
    
    schema_markup: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    faq_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    featured_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default=ContentStatus.DRAFT)
    published_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, client_id: str, title: str, **kwargs):
        self.id = f"post_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.title = title
        self.slug = kwargs.get('slug', '')
        self.meta_title = kwargs.get('meta_title', '')
        self.meta_description = kwargs.get('meta_description', '')
        self.body = kwargs.get('body', '')
        self.excerpt = kwargs.get('excerpt', '')
        self.primary_keyword = kwargs.get('primary_keyword', '')
        self.secondary_keywords = json.dumps(kwargs.get('secondary_keywords', []))
        self.word_count = kwargs.get('word_count', 0)
        self.seo_score = kwargs.get('seo_score', 0)
        self.internal_links = json.dumps(kwargs.get('internal_links', []))
        self.external_links = json.dumps(kwargs.get('external_links', []))
        self.schema_markup = json.dumps(kwargs.get('schema_markup')) if kwargs.get('schema_markup') else None
        self.faq_content = json.dumps(kwargs.get('faq_content')) if kwargs.get('faq_content') else None
        self.featured_image_url = kwargs.get('featured_image_url')
        self.status = kwargs.get('status', ContentStatus.DRAFT)
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'title': self.title,
            'slug': self.slug,
            'meta_title': self.meta_title,
            'meta_description': self.meta_description,
            'body': self.body,
            'excerpt': self.excerpt,
            'primary_keyword': self.primary_keyword,
            'secondary_keywords': json.loads(self.secondary_keywords),
            'word_count': self.word_count,
            'seo_score': self.seo_score,
            'internal_links': json.loads(self.internal_links),
            'external_links': json.loads(self.external_links),
            'schema_markup': json.loads(self.schema_markup) if self.schema_markup else None,
            'faq_content': json.loads(self.faq_content) if self.faq_content else None,
            'featured_image_url': self.featured_image_url,
            'status': self.status,
            'published_url': self.published_url,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DBSocialPost(db.Model):
    """Social media post content"""
    __tablename__ = 'social_posts'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[str] = mapped_column(Text, default='[]')  # JSON
    
    media_urls: Mapped[str] = mapped_column(Text, default='[]')  # JSON
    link_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cta_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default=ContentStatus.DRAFT)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __init__(self, client_id: str, platform: str, content: str, **kwargs):
        self.id = f"social_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.platform = platform
        self.content = content
        self.hashtags = json.dumps(kwargs.get('hashtags', []))
        self.media_urls = json.dumps(kwargs.get('media_urls', []))
        self.link_url = kwargs.get('link_url')
        self.cta_type = kwargs.get('cta_type')
        self.status = kwargs.get('status', ContentStatus.DRAFT)
        self.scheduled_for = kwargs.get('scheduled_for')
        self.created_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'platform': self.platform,
            'content': self.content,
            'hashtags': json.loads(self.hashtags),
            'media_urls': json.loads(self.media_urls),
            'link_url': self.link_url,
            'cta_type': self.cta_type,
            'status': self.status,
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'published_id': self.published_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ============================================
# Campaign Model
# ============================================

class CampaignStatus:
    DRAFT = 'draft'
    ACTIVE = 'active'
    PAUSED = 'paused'
    COMPLETED = 'completed'


class DBCampaign(db.Model):
    """Marketing campaign tracking"""
    __tablename__ = 'campaigns'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(50), default='content')
    description: Mapped[str] = mapped_column(Text, default='')
    
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    budget: Mapped[float] = mapped_column(Float, default=0.0)
    spent: Mapped[float] = mapped_column(Float, default=0.0)
    
    status: Mapped[str] = mapped_column(String(20), default=CampaignStatus.DRAFT)
    
    content_ids: Mapped[str] = mapped_column(Text, default='[]')  # JSON
    metrics: Mapped[str] = mapped_column(Text, default='{}')  # JSON
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, client_id: str, name: str, **kwargs):
        self.id = f"campaign_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.name = name
        self.campaign_type = kwargs.get('campaign_type', 'content')
        self.description = kwargs.get('description', '')
        self.start_date = kwargs.get('start_date')
        self.end_date = kwargs.get('end_date')
        self.budget = kwargs.get('budget', 0.0)
        self.spent = kwargs.get('spent', 0.0)
        self.status = kwargs.get('status', CampaignStatus.DRAFT)
        self.content_ids = json.dumps(kwargs.get('content_ids', []))
        self.metrics = json.dumps(kwargs.get('metrics', {}))
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'name': self.name,
            'campaign_type': self.campaign_type,
            'description': self.description,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'budget': self.budget,
            'spent': self.spent,
            'status': self.status,
            'content_ids': json.loads(self.content_ids),
            'metrics': json.loads(self.metrics),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ============================================
# Schema Markup Model
# ============================================

class DBSchemaMarkup(db.Model):
    """JSON-LD schema markup storage"""
    __tablename__ = 'schema_markups'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    schema_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default='')
    json_ld: Mapped[str] = mapped_column(Text, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __init__(self, client_id: str, schema_type: str, json_ld: dict, **kwargs):
        self.id = f"schema_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.schema_type = schema_type
        self.name = kwargs.get('name', '')
        self.json_ld = json.dumps(json_ld)
        self.is_active = True
        self.created_at = datetime.utcnow()
    
    def get_json_ld(self) -> dict:
        return json.loads(self.json_ld)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'schema_type': self.schema_type,
            'name': self.name,
            'json_ld': self.get_json_ld(),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
