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

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Enum as SQLEnum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import db


def safe_json_loads(value, default=None):
    """Safely parse JSON, returning default if None or invalid"""
    if default is None:
        default = []
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


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
        if not self.client_ids:
            return []
        try:
            return json.loads(self.client_ids)
        except (json.JSONDecodeError, TypeError):
            return []
    
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
    
    # Internal Linking - Service Pages (JSON array of {keyword, url, title})
    service_pages: Mapped[str] = mapped_column(Text, default='[]')
    
    tone: Mapped[str] = mapped_column(String(100), default='professional')
    
    # Integration credentials (stored as JSON)
    integrations: Mapped[str] = mapped_column(Text, default='{}')
    
    # WordPress Integration
    wordpress_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    wordpress_user: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wordpress_app_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Subscription
    subscription_tier: Mapped[str] = mapped_column(String(50), default='standard')
    monthly_content_limit: Mapped[int] = mapped_column(Integer, default=10)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # GBP Integration
    gbp_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gbp_location_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gbp_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Facebook Integration
    facebook_page_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    facebook_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    facebook_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Instagram Integration (via Facebook Graph API)
    instagram_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    instagram_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instagram_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # LinkedIn Integration
    linkedin_org_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    linkedin_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linkedin_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Lead notifications
    lead_notification_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lead_notification_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lead_notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # CallRail Integration
    callrail_company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    monthly_lead_target: Mapped[int] = mapped_column(Integer, default=10)
    
    # Google Analytics 4 Integration
    ga4_property_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Google Search Console Integration
    gsc_site_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationships
    leads: Mapped[List["DBLead"]] = relationship("DBLead", back_populates="client", lazy="dynamic")
    reviews: Mapped[List["DBReview"]] = relationship("DBReview", back_populates="client", lazy="dynamic")
    service_pages_rel: Mapped[List["DBServicePage"]] = relationship("DBServicePage", back_populates="client", lazy="dynamic")
    
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
        self.service_pages = json.dumps(kwargs.get('service_pages', []))
        self.tone = kwargs.get('tone', 'professional')
        self.integrations = json.dumps(kwargs.get('integrations', {}))
        self.subscription_tier = kwargs.get('subscription_tier', 'standard')
        self.monthly_content_limit = kwargs.get('monthly_content_limit', 10)
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def get_primary_keywords(self) -> List[str]:
        if not self.primary_keywords:
            return []
        try:
            return json.loads(self.primary_keywords)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_primary_keywords(self, keywords: List[str]):
        self.primary_keywords = json.dumps(keywords)
    
    def get_secondary_keywords(self) -> List[str]:
        if not self.secondary_keywords:
            return []
        try:
            return json.loads(self.secondary_keywords)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_competitors(self) -> List[str]:
        if not self.competitors:
            return []
        try:
            return json.loads(self.competitors)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_competitors(self, competitors: List[str]):
        """Set competitors list"""
        self.competitors = json.dumps(competitors)
    
    def get_service_areas(self) -> List[str]:
        if not self.service_areas:
            return []
        try:
            return json.loads(self.service_areas)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_service_areas(self, areas: List[str]):
        """Set service areas list"""
        self.service_areas = json.dumps(areas)
    
    def get_unique_selling_points(self) -> List[str]:
        if not self.unique_selling_points:
            return []
        try:
            return json.loads(self.unique_selling_points)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_unique_selling_points(self, usps: List[str]):
        """Set unique selling points list"""
        self.unique_selling_points = json.dumps(usps)
    
    def set_secondary_keywords(self, keywords: List[str]):
        """Set secondary keywords list"""
        self.secondary_keywords = json.dumps(keywords)
    
    def get_service_pages(self) -> List[dict]:
        """Get service pages for internal linking
        Returns: [{"keyword": "roof repair", "url": "/roof-repair/", "title": "Roof Repair Services"}]
        """
        if not self.service_pages:
            return []
        try:
            return json.loads(self.service_pages)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_service_pages(self, pages: List[dict]):
        """Set service pages for internal linking"""
        self.service_pages = json.dumps(pages)
    
    def get_integrations(self) -> dict:
        if not self.integrations:
            return {}
        try:
            return json.loads(self.integrations)
        except (json.JSONDecodeError, TypeError):
            return {}
    
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
            'service_pages': self.get_service_pages(),
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
            'service_pages': self.get_service_pages(),
            'tone': self.tone,
            'subscription_tier': self.subscription_tier,
            'monthly_content_limit': self.monthly_content_limit,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            # WordPress integration
            'wordpress_url': self.wordpress_url,
            'wordpress_user': self.wordpress_user,
            'wordpress_app_password': self.wordpress_app_password if self.wordpress_app_password else None,
            # Analytics & Tracking integrations
            'ga4_property_id': self.ga4_property_id,
            'gsc_site_url': self.gsc_site_url,
            'callrail_company_id': self.callrail_company_id,
            # Social connections (status only, no tokens)
            'social_connections': {
                'gbp': {
                    'connected': bool(self.gbp_location_id and self.gbp_access_token),
                    'location_id': self.gbp_location_id
                },
                'facebook': {
                    'connected': bool(self.facebook_page_id and self.facebook_access_token),
                    'page_id': self.facebook_page_id,
                    'connected_at': self.facebook_connected_at.isoformat() if self.facebook_connected_at else None
                },
                'instagram': {
                    'connected': bool(self.instagram_account_id and self.instagram_access_token),
                    'account_id': self.instagram_account_id,
                    'connected_at': self.instagram_connected_at.isoformat() if self.instagram_connected_at else None
                },
                'linkedin': {
                    'connected': bool(self.linkedin_org_id and self.linkedin_access_token),
                    'org_id': self.linkedin_org_id,
                    'connected_at': self.linkedin_connected_at.isoformat() if self.linkedin_connected_at else None
                }
            }
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
    
    # Scheduling
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # WordPress integration
    wordpress_post_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Approval workflow
    revision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
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
            'secondary_keywords': safe_json_loads(self.secondary_keywords, []),
            'word_count': self.word_count,
            'seo_score': self.seo_score,
            'internal_links': safe_json_loads(self.internal_links, []),
            'external_links': safe_json_loads(self.external_links, []),
            'schema_markup': safe_json_loads(self.schema_markup, None),
            'faq_content': safe_json_loads(self.faq_content, None),
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
    
    # Approval workflow
    revision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
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
            'hashtags': safe_json_loads(self.hashtags, []),
            'media_urls': safe_json_loads(self.media_urls, []),
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
            'content_ids': safe_json_loads(self.content_ids, []),
            'metrics': safe_json_loads(self.metrics, {}),
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
        return safe_json_loads(self.json_ld, {})
    
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


# ============================================
# Competitor Monitoring Models
# ============================================

class DBCompetitor(db.Model):
    """Competitor website to monitor"""
    __tablename__ = 'competitors'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default='')
    
    # Monitoring settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    crawl_frequency: Mapped[str] = mapped_column(String(20), default='daily')  # daily, weekly
    last_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Stats
    known_pages_count: Mapped[int] = mapped_column(Integer, default=0)
    new_pages_detected: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, client_id: str, domain: str, **kwargs):
        self.id = f"comp_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.domain = domain.lower().strip()
        self.name = kwargs.get('name', domain)
        self.crawl_frequency = kwargs.get('crawl_frequency', 'daily')
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'domain': self.domain,
            'name': self.name,
            'is_active': self.is_active,
            'crawl_frequency': self.crawl_frequency,
            'last_crawl_at': self.last_crawl_at.isoformat() if self.last_crawl_at else None,
            'next_crawl_at': self.next_crawl_at.isoformat() if self.next_crawl_at else None,
            'known_pages_count': self.known_pages_count,
            'new_pages_detected': self.new_pages_detected,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DBCompetitorPage(db.Model):
    """Individual page discovered from competitor"""
    __tablename__ = 'competitor_pages'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    competitor_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default='')
    
    # Content snapshot
    content_hash: Mapped[str] = mapped_column(String(64), default='')  # MD5 of content
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    h1: Mapped[str] = mapped_column(String(500), default='')
    meta_description: Mapped[str] = mapped_column(Text, default='')
    
    # Status
    is_new: Mapped[bool] = mapped_column(Boolean, default=True)  # Newly discovered
    was_countered: Mapped[bool] = mapped_column(Boolean, default=False)  # We generated counter-content
    counter_content_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Our blog post ID
    
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __init__(self, competitor_id: str, client_id: str, url: str, **kwargs):
        self.id = f"cpage_{uuid.uuid4().hex[:12]}"
        self.competitor_id = competitor_id
        self.client_id = client_id
        self.url = url
        self.title = kwargs.get('title', '')
        self.content_hash = kwargs.get('content_hash', '')
        self.word_count = kwargs.get('word_count', 0)
        self.h1 = kwargs.get('h1', '')
        self.meta_description = kwargs.get('meta_description', '')
        self.is_new = True
        self.was_countered = False
        self.discovered_at = datetime.utcnow()
        self.last_checked_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'competitor_id': self.competitor_id,
            'client_id': self.client_id,
            'url': self.url,
            'title': self.title,
            'word_count': self.word_count,
            'h1': self.h1,
            'is_new': self.is_new,
            'was_countered': self.was_countered,
            'counter_content_id': self.counter_content_id,
            'discovered_at': self.discovered_at.isoformat() if self.discovered_at else None
        }


class DBRankHistory(db.Model):
    """Historical keyword ranking data"""
    __tablename__ = 'rank_history'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    previous_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    change: Mapped[int] = mapped_column(Integer, default=0)
    
    url: Mapped[str] = mapped_column(String(500), default='')  # URL that's ranking
    search_volume: Mapped[int] = mapped_column(Integer, default=0)
    cpc: Mapped[float] = mapped_column(Float, default=0.0)
    
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    def __init__(self, client_id: str, keyword: str, **kwargs):
        self.id = f"rank_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.keyword = keyword
        self.position = kwargs.get('position')
        self.previous_position = kwargs.get('previous_position')
        self.change = kwargs.get('change', 0)
        self.url = kwargs.get('url', '')
        self.search_volume = kwargs.get('search_volume', 0)
        self.cpc = kwargs.get('cpc', 0.0)
        self.checked_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'keyword': self.keyword,
            'position': self.position,
            'previous_position': self.previous_position,
            'change': self.change,
            'url': self.url,
            'search_volume': self.search_volume,
            'cpc': self.cpc,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None
        }


class DBContentQueue(db.Model):
    """Auto-generated content waiting for approval"""
    __tablename__ = 'content_queue'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Trigger info
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)  # competitor_post, rank_drop, scheduled
    trigger_competitor_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    trigger_competitor_page_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    trigger_keyword: Mapped[str] = mapped_column(String(255), default='')
    
    # Content
    title: Mapped[str] = mapped_column(String(500), default='')
    body: Mapped[str] = mapped_column(Text, default='')
    meta_title: Mapped[str] = mapped_column(String(100), default='')
    meta_description: Mapped[str] = mapped_column(String(200), default='')
    primary_keyword: Mapped[str] = mapped_column(String(255), default='')
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # SEO scores
    our_seo_score: Mapped[int] = mapped_column(Integer, default=0)
    competitor_seo_score: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending, approved, rejected, published
    approved_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_blog_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # WordPress publishing
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    wordpress_post_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Notes
    client_notes: Mapped[str] = mapped_column(Text, default='')
    regenerate_count: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, client_id: str, trigger_type: str, **kwargs):
        self.id = f"queue_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.trigger_type = trigger_type
        self.trigger_competitor_id = kwargs.get('trigger_competitor_id')
        self.trigger_competitor_page_id = kwargs.get('trigger_competitor_page_id')
        self.trigger_keyword = kwargs.get('trigger_keyword', '')
        self.title = kwargs.get('title', '')
        self.body = kwargs.get('body', '')
        self.meta_title = kwargs.get('meta_title', '')
        self.meta_description = kwargs.get('meta_description', '')
        self.primary_keyword = kwargs.get('primary_keyword', '')
        self.word_count = kwargs.get('word_count', 0)
        self.our_seo_score = kwargs.get('our_seo_score', 0)
        self.competitor_seo_score = kwargs.get('competitor_seo_score', 0)
        self.status = 'pending'
        self.regenerate_count = 0
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'trigger_type': self.trigger_type,
            'trigger_competitor_id': self.trigger_competitor_id,
            'trigger_competitor_page_id': self.trigger_competitor_page_id,
            'trigger_keyword': self.trigger_keyword,
            'title': self.title,
            'meta_title': self.meta_title,
            'meta_description': self.meta_description,
            'primary_keyword': self.primary_keyword,
            'word_count': self.word_count,
            'our_seo_score': self.our_seo_score,
            'competitor_seo_score': self.competitor_seo_score,
            'status': self.status,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'published_blog_id': self.published_blog_id,
            'client_notes': self.client_notes,
            'regenerate_count': self.regenerate_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DBLead(db.Model):
    """Lead captured from forms, calls, or other sources"""
    __tablename__ = 'leads'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    # Contact info
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Lead details
    service_requested: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default='form')  # form, call, chat, gbp, referral
    source_detail: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # which form, campaign, etc
    landing_page: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    keyword: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # if we can attribute
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(50), default='new')  # new, contacted, qualified, converted, lost
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Value tracking
    estimated_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Notification tracking
    notified_email: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    client: Mapped["DBClient"] = relationship("DBClient", back_populates="leads")
    
    def __init__(self, client_id: str, source: str = 'form', **kwargs):
        self.id = f"lead_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.source = source
        self.name = kwargs.get('name', '')
        self.email = kwargs.get('email')
        self.phone = kwargs.get('phone')
        self.service_requested = kwargs.get('service_requested')
        self.message = kwargs.get('message')
        self.source_detail = kwargs.get('source_detail')
        self.landing_page = kwargs.get('landing_page')
        self.utm_source = kwargs.get('utm_source')
        self.utm_medium = kwargs.get('utm_medium')
        self.utm_campaign = kwargs.get('utm_campaign')
        self.keyword = kwargs.get('keyword')
        self.status = kwargs.get('status', 'new')
        self.notes = kwargs.get('notes')
        self.assigned_to = kwargs.get('assigned_to')
        self.estimated_value = kwargs.get('estimated_value')
        self.actual_value = kwargs.get('actual_value')
        self.notified_email = False
        self.notified_sms = False
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'service_requested': self.service_requested,
            'message': self.message,
            'source': self.source,
            'source_detail': self.source_detail,
            'landing_page': self.landing_page,
            'utm_source': self.utm_source,
            'utm_medium': self.utm_medium,
            'utm_campaign': self.utm_campaign,
            'keyword': self.keyword,
            'status': self.status,
            'notes': self.notes,
            'assigned_to': self.assigned_to,
            'estimated_value': self.estimated_value,
            'actual_value': self.actual_value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'contacted_at': self.contacted_at.isoformat() if self.contacted_at else None,
            'converted_at': self.converted_at.isoformat() if self.converted_at else None
        }


class DBReview(db.Model):
    """Reviews from Google, Yelp, Facebook, etc."""
    __tablename__ = 'reviews'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    # Review info
    platform: Mapped[str] = mapped_column(String(50))  # google, yelp, facebook
    platform_review_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reviewer_name: Mapped[str] = mapped_column(String(200))
    reviewer_avatar: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    review_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_date: Mapped[datetime] = mapped_column(DateTime)
    
    # Response
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    suggested_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default='pending')  # pending, responded, flagged
    sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # positive, neutral, negative
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    client: Mapped["DBClient"] = relationship("DBClient", back_populates="reviews")
    
    def __init__(self, client_id: str, platform: str, reviewer_name: str, rating: int, review_date: datetime, **kwargs):
        self.id = f"review_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.platform = platform
        self.reviewer_name = reviewer_name
        self.rating = rating
        self.review_date = review_date
        self.platform_review_id = kwargs.get('platform_review_id')
        self.reviewer_avatar = kwargs.get('reviewer_avatar')
        self.review_text = kwargs.get('review_text')
        self.response_text = kwargs.get('response_text')
        self.response_date = kwargs.get('response_date')
        self.suggested_response = kwargs.get('suggested_response')
        self.status = kwargs.get('status', 'pending')
        self.sentiment = kwargs.get('sentiment')
        self.created_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'platform': self.platform,
            'reviewer_name': self.reviewer_name,
            'rating': self.rating,
            'review_text': self.review_text,
            'review_date': self.review_date.isoformat() if self.review_date else None,
            'response_text': self.response_text,
            'response_date': self.response_date.isoformat() if self.response_date else None,
            'suggested_response': self.suggested_response,
            'status': self.status,
            'sentiment': self.sentiment
        }


class DBServicePage(db.Model):
    """Service and location landing pages"""
    __tablename__ = 'service_pages'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    # Page info
    page_type: Mapped[str] = mapped_column(String(50))  # service, location, service_location
    title: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(200))
    
    # Targeting
    service: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    primary_keyword: Mapped[str] = mapped_column(String(200))
    secondary_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    
    # Content
    hero_headline: Mapped[str] = mapped_column(String(300))
    hero_subheadline: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    intro_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_content: Mapped[str] = mapped_column(Text)
    
    # Conversion elements
    cta_headline: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cta_button_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    form_headline: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    trust_badges: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ["Licensed", "Insured", "5-Star"]
    
    # SEO
    meta_title: Mapped[Optional[str]] = mapped_column(String(70), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    schema_markup: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Publishing
    status: Mapped[str] = mapped_column(String(50), default='draft')  # draft, published
    wordpress_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    published_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    client: Mapped["DBClient"] = relationship("DBClient", back_populates="service_pages_rel")
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'page_type': self.page_type,
            'title': self.title,
            'slug': self.slug,
            'service': self.service,
            'location': self.location,
            'primary_keyword': self.primary_keyword,
            'hero_headline': self.hero_headline,
            'meta_title': self.meta_title,
            'meta_description': self.meta_description,
            'status': self.status,
            'published_url': self.published_url,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DBAlert(db.Model):
    """Alerts and notifications"""
    __tablename__ = 'alerts'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # new_competitor_content, rank_change, content_ready
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, default='')
    
    # Related entities
    related_competitor_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    related_page_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    related_content_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    related_keyword: Mapped[str] = mapped_column(String(255), default='')
    
    # Status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    
    priority: Mapped[str] = mapped_column(String(20), default='normal')  # low, normal, high, urgent
    
    # Notification tracking
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    def __init__(self, client_id: str, alert_type: str, title: str, **kwargs):
        self.id = f"alert_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.alert_type = alert_type
        self.title = title
        self.message = kwargs.get('message', '')
        self.related_competitor_id = kwargs.get('related_competitor_id')
        self.related_page_id = kwargs.get('related_page_id')
        self.related_content_id = kwargs.get('related_content_id')
        self.related_keyword = kwargs.get('related_keyword', '')
        self.priority = kwargs.get('priority', 'normal')
        self.is_read = False
        self.is_emailed = False
        self.is_sms_sent = False
        self.created_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'alert_type': self.alert_type,
            'title': self.title,
            'message': self.message,
            'related_competitor_id': self.related_competitor_id,
            'related_page_id': self.related_page_id,
            'related_content_id': self.related_content_id,
            'related_keyword': self.related_keyword,
            'is_read': self.is_read,
            'priority': self.priority,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# AUDIT LOG MODEL
# ==========================================

class DBAuditLog(db.Model):
    """Audit log for tracking all system actions"""
    __tablename__ = 'audit_logs'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Who did it
    user_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey('users.id'), nullable=True, index=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # What they did
    action: Mapped[str] = mapped_column(String(50), index=True)  # create, update, delete, login, logout, view, export
    resource_type: Mapped[str] = mapped_column(String(50), index=True)  # client, user, lead, content, campaign, etc
    resource_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Details
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON of old state
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON of new state
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Additional JSON data
    
    # Context
    client_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    http_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default='success')  # success, failure, error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_email': self.user_email,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'resource_name': self.resource_name,
            'description': self.description,
            'client_id': self.client_id,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# WEBHOOK MODEL
# ==========================================

class DBWebhook(db.Model):
    """Outbound webhooks for external integrations"""
    __tablename__ = 'webhooks'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey('clients.id'), nullable=True, index=True)
    
    # Configuration
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # For signing payloads
    
    # Events to trigger on
    events: Mapped[str] = mapped_column(Text, default='[]')  # JSON array: ["lead.created", "content.generated", "ranking.changed"]
    
    # Settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    
    # Stats
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_failed: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_events(self) -> list:
        try:
            return json.loads(self.events) if self.events else []
        except Exception as e:
            return []
    
    def set_events(self, events: list):
        self.events = json.dumps(events)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'name': self.name,
            'url': self.url,
            'events': self.get_events(),
            'is_active': self.is_active,
            'total_sent': self.total_sent,
            'total_failed': self.total_failed,
            'last_triggered_at': self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            'last_status': self.last_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# SETTINGS MODEL
# ==========================================

class DBSetting(db.Model):
    """System and client settings storage"""
    __tablename__ = 'settings'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Scope
    scope: Mapped[str] = mapped_column(String(20), default='global', index=True)  # global, client, user
    scope_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # client_id or user_id
    
    # Setting
    category: Mapped[str] = mapped_column(String(50), index=True)  # branding, content, notifications, integrations, seo
    key: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), default='string')  # string, int, float, bool, json
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)  # API keys, passwords
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('scope', 'scope_id', 'category', 'key', name='unique_setting'),
    )
    
    def get_typed_value(self):
        """Get value with proper type conversion"""
        if self.value is None:
            return None
        
        if self.value_type == 'int':
            return int(self.value)
        elif self.value_type == 'float':
            return float(self.value)
        elif self.value_type == 'bool':
            return self.value.lower() in ('true', '1', 'yes')
        elif self.value_type == 'json':
            try:
                return json.loads(self.value)
            except Exception as e:
                return self.value
        return self.value
    
    def to_dict(self, include_secret=False) -> dict:
        return {
            'id': self.id,
            'scope': self.scope,
            'scope_id': self.scope_id,
            'category': self.category,
            'key': self.key,
            'value': '***' if self.is_secret and not include_secret else self.get_typed_value(),
            'value_type': self.value_type,
            'is_secret': self.is_secret,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==========================================
# AGENT CONFIG MODEL
# ==========================================

class DBAgentConfig(db.Model):
    """
    AI Agent configurations - stores system prompts and settings
    Allows modifying agent behavior without code changes
    """
    __tablename__ = 'agent_configs'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    
    # Identity
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # e.g., content_writer
    display_name: Mapped[str] = mapped_column(String(200))  # e.g., "Content Writer Agent"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default='general', index=True)  # content, seo, social, etc.
    
    # The prompt
    system_prompt: Mapped[str] = mapped_column(Text)  # The actual system prompt
    
    # Output expectations
    output_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON schema or description
    output_example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Example output
    
    # Model settings
    model: Mapped[str] = mapped_column(String(100), default='gpt-4o-mini')
    temperature: Mapped[float] = mapped_column(db.Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2000)
    
    # Tools/capabilities this agent can use
    tools_allowed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tool names
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_tools(self) -> list:
        """Get list of allowed tools"""
        if not self.tools_allowed:
            return []
        try:
            return json.loads(self.tools_allowed)
        except Exception as e:
            return []
    
    def set_tools(self, tools: list):
        """Set allowed tools"""
        self.tools_allowed = json.dumps(tools)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'category': self.category,
            'system_prompt': self.system_prompt,
            'output_format': self.output_format,
            'output_example': self.output_example,
            'model': self.model,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'tools_allowed': self.get_tools(),
            'is_active': self.is_active,
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DBAgentVersion(db.Model):
    """Version history for agent configs - allows rollback"""
    __tablename__ = 'agent_versions'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(50), ForeignKey('agent_configs.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    
    # Snapshot of the config at this version
    system_prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    temperature: Mapped[float] = mapped_column(db.Float)
    max_tokens: Mapped[int] = mapped_column(Integer)
    output_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Who made the change
    changed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    change_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'version': self.version,
            'system_prompt': self.system_prompt[:200] + '...' if len(self.system_prompt) > 200 else self.system_prompt,
            'model': self.model,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'changed_by': self.changed_by,
            'change_note': self.change_note,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ============================================
# Chatbot Models
# ============================================

class DBChatbotConfig(db.Model):
    """Configuration for client website chatbots"""
    __tablename__ = 'chatbot_configs'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    # Branding
    name: Mapped[str] = mapped_column(String(100), default='Support Assistant')
    welcome_message: Mapped[str] = mapped_column(Text, default='Hi! How can I help you today?')
    placeholder_text: Mapped[str] = mapped_column(String(200), default='Type your message...')
    
    # Appearance
    primary_color: Mapped[str] = mapped_column(String(20), default='#3b82f6')
    secondary_color: Mapped[str] = mapped_column(String(20), default='#1e40af')
    position: Mapped[str] = mapped_column(String(20), default='bottom-right')  # bottom-right, bottom-left
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Behavior
    auto_open_delay: Mapped[int] = mapped_column(Integer, default=0)  # 0 = don't auto open
    show_on_mobile: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_email: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_phone: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_name: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # AI Configuration
    system_prompt_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    temperature: Mapped[float] = mapped_column(db.Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=500)
    
    # Lead capture
    lead_capture_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    lead_capture_trigger: Mapped[str] = mapped_column(String(50), default='after_3_messages')
    
    # Notifications
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sms_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Business hours
    business_hours_only: Mapped[bool] = mapped_column(Boolean, default=False)
    business_hours_start: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # "09:00"
    business_hours_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)    # "17:00"
    timezone: Mapped[str] = mapped_column(String(50), default='America/New_York')
    offline_message: Mapped[str] = mapped_column(Text, default="We're currently offline. Leave your info and we'll get back to you!")
    
    # Analytics
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    total_leads_captured: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_rating: Mapped[Optional[float]] = mapped_column(db.Float, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    conversations = relationship('DBChatConversation', backref='chatbot', lazy='dynamic')
    
    def __init__(self, client_id: str, **kwargs):
        self.id = f"chatbot_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'name': self.name,
            'welcome_message': self.welcome_message,
            'placeholder_text': self.placeholder_text,
            'primary_color': self.primary_color,
            'secondary_color': self.secondary_color,
            'position': self.position,
            'avatar_url': self.avatar_url,
            'auto_open_delay': self.auto_open_delay,
            'show_on_mobile': self.show_on_mobile,
            'collect_email': self.collect_email,
            'collect_phone': self.collect_phone,
            'collect_name': self.collect_name,
            'lead_capture_enabled': self.lead_capture_enabled,
            'lead_capture_trigger': self.lead_capture_trigger,
            'email_notifications': self.email_notifications,
            'notification_email': self.notification_email,
            'sms_notifications': self.sms_notifications,
            'business_hours_only': self.business_hours_only,
            'business_hours_start': self.business_hours_start,
            'business_hours_end': self.business_hours_end,
            'timezone': self.timezone,
            'offline_message': self.offline_message,
            'total_conversations': self.total_conversations,
            'total_leads_captured': self.total_leads_captured,
            'avg_response_rating': self.avg_response_rating,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DBChatConversation(db.Model):
    """Individual chat conversation with a website visitor"""
    __tablename__ = 'chat_conversations'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    chatbot_id: Mapped[str] = mapped_column(String(50), ForeignKey('chatbot_configs.id'), index=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    # Visitor info
    visitor_id: Mapped[str] = mapped_column(String(100), index=True)  # Browser fingerprint/cookie
    visitor_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    visitor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    visitor_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    # Context
    page_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    page_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Conversation metadata
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_lead_captured: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), default='active')  # active, closed, escalated
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 stars
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    messages = relationship('DBChatMessage', backref='conversation', lazy='dynamic', order_by='DBChatMessage.created_at')
    
    def __init__(self, chatbot_id: str, client_id: str, visitor_id: str, **kwargs):
        self.id = f"conv_{uuid.uuid4().hex[:12]}"
        self.chatbot_id = chatbot_id
        self.client_id = client_id
        self.visitor_id = visitor_id
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self, include_messages: bool = False) -> dict:
        result = {
            'id': self.id,
            'chatbot_id': self.chatbot_id,
            'client_id': self.client_id,
            'visitor_id': self.visitor_id,
            'visitor_name': self.visitor_name,
            'visitor_email': self.visitor_email,
            'visitor_phone': self.visitor_phone,
            'page_url': self.page_url,
            'page_title': self.page_title,
            'message_count': self.message_count,
            'is_lead_captured': self.is_lead_captured,
            'lead_id': self.lead_id,
            'status': self.status,
            'rating': self.rating,
            'feedback': self.feedback,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None
        }
        if include_messages:
            result['messages'] = [m.to_dict() for m in self.messages.all()]
        return result


class DBChatMessage(db.Model):
    """Individual message in a chat conversation"""
    __tablename__ = 'chat_messages'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(50), ForeignKey('chat_conversations.id'), index=True)
    
    # Message content
    role: Mapped[str] = mapped_column(String(20))  # 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(Text)
    
    # AI metadata
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'tokens_used': self.tokens_used,
            'response_time_ms': self.response_time_ms,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DBChatbotFAQ(db.Model):
    """Pre-defined FAQ responses for chatbot"""
    __tablename__ = 'chatbot_faqs'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(Text, default='[]')  # JSON array for matching
    
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def get_keywords(self) -> list:
        return safe_json_loads(self.keywords, [])
    
    def set_keywords(self, kws: list):
        self.keywords = json.dumps(kws)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'question': self.question,
            'answer': self.answer,
            'keywords': self.get_keywords(),
            'category': self.category,
            'is_active': self.is_active,
            'times_used': self.times_used,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DBContentFeedback(db.Model):
    """Content feedback and change requests from clients"""
    __tablename__ = 'content_feedback'
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    
    feedback_type: Mapped[str] = mapped_column(String(50), default='comment')  # change_request, approval, comment
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending, addressed, dismissed
    addressed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    addressed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    response_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'content_id': self.content_id,
            'client_id': self.client_id,
            'user_id': self.user_id,
            'feedback_type': self.feedback_type,
            'feedback_text': self.feedback_text,
            'status': self.status,
            'addressed_by': self.addressed_by,
            'addressed_at': self.addressed_at.isoformat() if self.addressed_at else None,
            'response_notes': self.response_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ============================================
# Notification System Models
# ============================================

class NotificationType:
    """Notification type constants"""
    # Content lifecycle
    CONTENT_SCHEDULED = 'content_scheduled'
    CONTENT_DUE_TODAY = 'content_due_today'
    CONTENT_PUBLISHED = 'content_published'
    CONTENT_APPROVAL_NEEDED = 'content_approval_needed'
    CONTENT_APPROVED = 'content_approved'
    CONTENT_FEEDBACK = 'content_feedback'
    
    # Competitor & Rankings
    COMPETITOR_NEW_CONTENT = 'competitor_new_content'
    RANKING_IMPROVED = 'ranking_improved'
    RANKING_DROPPED = 'ranking_dropped'
    
    # System
    WEEKLY_DIGEST = 'weekly_digest'
    DAILY_SUMMARY = 'daily_summary'
    ALERT_DIGEST = 'alert_digest'
    
    # WordPress
    WORDPRESS_PUBLISHED = 'wordpress_published'
    WORDPRESS_FAILED = 'wordpress_failed'
    
    # Social
    SOCIAL_PUBLISHED = 'social_published'
    SOCIAL_FAILED = 'social_failed'


class DBNotificationPreferences(db.Model):
    """User notification preferences"""
    __tablename__ = 'notification_preferences'
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # Null = global prefs
    
    # Content notifications
    content_scheduled: Mapped[bool] = mapped_column(Boolean, default=True)
    content_due_today: Mapped[bool] = mapped_column(Boolean, default=True)
    content_published: Mapped[bool] = mapped_column(Boolean, default=True)
    content_approval_needed: Mapped[bool] = mapped_column(Boolean, default=True)
    content_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    content_feedback: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Competitor & Ranking notifications
    competitor_new_content: Mapped[bool] = mapped_column(Boolean, default=True)
    ranking_improved: Mapped[bool] = mapped_column(Boolean, default=True)
    ranking_dropped: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # System notifications
    weekly_digest: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_summary: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_digest: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # WordPress/Social notifications
    wordpress_published: Mapped[bool] = mapped_column(Boolean, default=True)
    wordpress_failed: Mapped[bool] = mapped_column(Boolean, default=True)
    social_published: Mapped[bool] = mapped_column(Boolean, default=False)  # Off by default (could be noisy)
    social_failed: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Delivery preferences
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_frequency: Mapped[str] = mapped_column(String(20), default='instant')  # instant, daily, weekly
    digest_time: Mapped[str] = mapped_column(String(10), default='08:00')  # HH:MM for daily/weekly
    digest_day: Mapped[int] = mapped_column(Integer, default=1)  # 0=Mon, 6=Sun for weekly
    
    # Quiet hours
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_start: Mapped[str] = mapped_column(String(10), default='22:00')
    quiet_end: Mapped[str] = mapped_column(String(10), default='07:00')
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, user_id: str, **kwargs):
        self.id = str(uuid4())
        self.user_id = user_id
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def is_enabled(self, notification_type: str) -> bool:
        """Check if a notification type is enabled"""
        if not self.email_enabled:
            return False
        return getattr(self, notification_type, True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'client_id': self.client_id,
            'content': {
                'scheduled': self.content_scheduled,
                'due_today': self.content_due_today,
                'published': self.content_published,
                'approval_needed': self.content_approval_needed,
                'approved': self.content_approved,
                'feedback': self.content_feedback
            },
            'competitor': {
                'new_content': self.competitor_new_content,
                'ranking_improved': self.ranking_improved,
                'ranking_dropped': self.ranking_dropped
            },
            'system': {
                'weekly_digest': self.weekly_digest,
                'daily_summary': self.daily_summary,
                'alert_digest': self.alert_digest
            },
            'publishing': {
                'wordpress_published': self.wordpress_published,
                'wordpress_failed': self.wordpress_failed,
                'social_published': self.social_published,
                'social_failed': self.social_failed
            },
            'delivery': {
                'email_enabled': self.email_enabled,
                'digest_frequency': self.digest_frequency,
                'digest_time': self.digest_time,
                'digest_day': self.digest_day
            },
            'quiet_hours': {
                'enabled': self.quiet_hours_enabled,
                'start': self.quiet_start,
                'end': self.quiet_end
            },
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DBNotificationLog(db.Model):
    """Log of sent notifications for tracking and debugging"""
    __tablename__ = 'notification_log'
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending, sent, failed, queued
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Related content
    related_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # blog_id, social_id, etc
    related_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # blog, social, competitor
    
    # Metadata
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON for extra data
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __init__(self, user_id: str, notification_type: str, subject: str, recipient_email: str, **kwargs):
        self.id = str(uuid4())
        self.user_id = user_id
        self.notification_type = notification_type
        self.subject = subject
        self.recipient_email = recipient_email
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'client_id': self.client_id,
            'notification_type': self.notification_type,
            'subject': self.subject,
            'recipient_email': self.recipient_email,
            'status': self.status,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'related_id': self.related_id,
            'related_type': self.related_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None
        }


class DBNotificationQueue(db.Model):
    """Queue for digest notifications (batched instead of instant)"""
    __tablename__ = 'notification_queue'
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default='normal')  # low, normal, high
    
    # Related content
    related_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    related_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    action_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Processing
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __init__(self, user_id: str, notification_type: str, title: str, message: str, **kwargs):
        self.id = str(uuid4())
        self.user_id = user_id
        self.notification_type = notification_type
        self.title = title
        self.message = message
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'client_id': self.client_id,
            'notification_type': self.notification_type,
            'title': self.title,
            'message': self.message,
            'priority': self.priority,
            'related_id': self.related_id,
            'action_url': self.action_url,
            'processed': self.processed,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DBWebhookLog(db.Model):
    """Log of webhook events sent and received"""
    __tablename__ = 'webhook_logs'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    direction: Mapped[str] = mapped_column(String(20), default='outbound')  # inbound, outbound
    
    # Request details
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Response details
    status: Mapped[str] = mapped_column(String(30), default='queued')  # queued, sent, delivered, failed
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Related entities
    client_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    
    def __init__(self, event_id: str, event_type: str, **kwargs):
        self.event_id = event_id
        self.event_type = event_type
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'event_id': self.event_id,
            'event_type': self.event_type,
            'direction': self.direction,
            'url': self.url,
            'status': self.status,
            'response_code': self.response_code,
            'error_message': self.error_message,
            'client_id': self.client_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None
        }


class DBWebhookEndpoint(db.Model):
    """Configured webhook endpoints for external system integration"""
    __tablename__ = 'webhook_endpoints'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(500))
    
    # What events trigger this webhook
    event_types: Mapped[str] = mapped_column(Text)  # JSON array of event types
    
    # Optional filtering
    client_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # None = all clients
    
    # Authentication
    secret: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    auth_header: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, name: str, url: str, event_types: List[str], **kwargs):
        self.id = f"wh_{uuid.uuid4().hex[:12]}"
        self.name = name
        self.url = url
        self.event_types = json.dumps(event_types)
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def get_event_types(self) -> List[str]:
        return safe_json_loads(self.event_types, [])
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'event_types': self.get_event_types(),
            'client_id': self.client_id,
            'is_active': self.is_active,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ============================================
# Client Image Library
# ============================================

class DBClientImage(db.Model):
    """Images uploaded by clients for use in content"""
    __tablename__ = 'client_images'
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey('clients.id'), index=True)
    
    # Image info
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))  # Local storage path
    file_url: Mapped[str] = mapped_column(String(500))   # Public URL
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), default='image/jpeg')
    
    # Dimensions
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    alt_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[str] = mapped_column(Text, default='[]')  # JSON array
    category: Mapped[str] = mapped_column(String(100), default='general')  # hero, team, work, logo, etc.
    
    # Usage tracking
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    def __init__(self, client_id: str, filename: str, file_path: str, **kwargs):
        self.id = f"img_{uuid.uuid4().hex[:12]}"
        self.client_id = client_id
        self.filename = filename
        self.original_filename = kwargs.get('original_filename', filename)
        self.file_path = file_path
        self.file_url = kwargs.get('file_url', '')
        self.file_size = kwargs.get('file_size', 0)
        self.mime_type = kwargs.get('mime_type', 'image/jpeg')
        self.width = kwargs.get('width', 0)
        self.height = kwargs.get('height', 0)
        self.title = kwargs.get('title')
        self.alt_text = kwargs.get('alt_text')
        self.description = kwargs.get('description')
        self.tags = json.dumps(kwargs.get('tags', []))
        self.category = kwargs.get('category', 'general')
        self.uploaded_by = kwargs.get('uploaded_by')
    
    def get_tags(self) -> List[str]:
        return safe_json_loads(self.tags, [])
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'client_id': self.client_id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_path': self.file_path,
            'file_url': self.file_url,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'width': self.width,
            'height': self.height,
            'title': self.title,
            'alt_text': self.alt_text,
            'description': self.description,
            'tags': self.get_tags(),
            'category': self.category,
            'use_count': self.use_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# Alias for backward compatibility
DBContent = DBBlogPost
