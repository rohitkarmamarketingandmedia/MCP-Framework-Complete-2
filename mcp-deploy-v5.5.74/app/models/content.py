"""
MCP Framework - Content Models
Blog posts, schema markup, and social media content
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import secrets
import json


class ContentStatus(Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentType(Enum):
    BLOG_POST = "blog_post"
    LANDING_PAGE = "landing_page"
    SERVICE_PAGE = "service_page"
    LOCATION_PAGE = "location_page"
    EMAIL = "email"


@dataclass
class Content:
    """Base content model"""
    
    id: str
    client_id: str
    content_type: ContentType
    
    title: str = ""
    body: str = ""
    
    # SEO fields
    meta_title: str = ""
    meta_description: str = ""
    target_keyword: str = ""
    secondary_keywords: List[str] = field(default_factory=list)
    
    # Status tracking
    status: ContentStatus = ContentStatus.DRAFT
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None
    
    # Publishing info
    published_url: str = ""
    wordpress_post_id: Optional[int] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = f"content_{secrets.token_urlsafe(12)}"
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "content_type": self.content_type.value,
            "title": self.title,
            "body": self.body,
            "meta_title": self.meta_title,
            "meta_description": self.meta_description,
            "target_keyword": self.target_keyword,
            "secondary_keywords": self.secondary_keywords,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_url": self.published_url,
            "wordpress_post_id": self.wordpress_post_id,
            "h1": self.h1,
            "h2_headings": self.h2_headings,
            "h3_headings": self.h3_headings,
            "word_count": self.word_count,
            "reading_time_minutes": self.reading_time_minutes,
            "internal_links": self.internal_links,
            "external_links": self.external_links,
            "featured_image_url": self.featured_image_url,
            "featured_image_alt": self.featured_image_alt,
            "categories": self.categories,
            "tags": self.tags,
            "faq_items": self.faq_items
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "BlogPost":
        """Create BlogPost from dictionary"""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        published_at = data.get('published_at')
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        
        return cls(
            id=data.get('id', ''),
            client_id=data.get('client_id', ''),
            content_type=ContentType(data.get('content_type', 'blog_post')),
            title=data.get('title', ''),
            body=data.get('body', ''),
            meta_title=data.get('meta_title', ''),
            meta_description=data.get('meta_description', ''),
            target_keyword=data.get('target_keyword', ''),
            secondary_keywords=data.get('secondary_keywords', []),
            status=ContentStatus(data.get('status', 'draft')),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow(),
            published_at=published_at,
            published_url=data.get('published_url', ''),
            wordpress_post_id=data.get('wordpress_post_id'),
            h1=data.get('h1', ''),
            h2_headings=data.get('h2_headings', []),
            h3_headings=data.get('h3_headings', []),
            word_count=data.get('word_count', 0),
            reading_time_minutes=data.get('reading_time_minutes', 0),
            internal_links=data.get('internal_links', []),
            external_links=data.get('external_links', []),
            featured_image_url=data.get('featured_image_url', ''),
            featured_image_alt=data.get('featured_image_alt', ''),
            categories=data.get('categories', []),
            tags=data.get('tags', []),
            faq_items=data.get('faq_items', [])
        )


@dataclass
class BlogPost(Content):
    """Blog post content model with SEO optimization"""
    
    # Blog-specific fields
    word_count: int = 0
    reading_time_minutes: int = 0
    
    # Structure
    h1: str = ""
    h2_headings: List[str] = field(default_factory=list)
    h3_headings: List[str] = field(default_factory=list)
    
    # Internal linking
    internal_links: List[Dict[str, str]] = field(default_factory=list)  # [{"url": "", "anchor": ""}]
    external_links: List[Dict[str, str]] = field(default_factory=list)
    
    # Media
    featured_image_url: str = ""
    featured_image_alt: str = ""
    
    # Categories/Tags
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # FAQ section
    faq_items: List[Dict[str, str]] = field(default_factory=list)  # [{"question": "", "answer": ""}]
    
    def __post_init__(self):
        super().__post_init__()
        self.content_type = ContentType.BLOG_POST
        if self.body:
            self.word_count = len(self.body.split())
            self.reading_time_minutes = max(1, self.word_count // 200)
    
    def add_internal_link(self, url: str, anchor_text: str) -> None:
        """Add an internal link"""
        self.internal_links.append({"url": url, "anchor": anchor_text})
    
    def add_faq(self, question: str, answer: str) -> None:
        """Add FAQ item"""
        self.faq_items.append({"question": question, "answer": answer})
    
    def get_seo_score(self) -> Dict[str, Any]:
        """Calculate basic SEO score"""
        score = 0
        checks = {}
        
        # Title checks
        if self.meta_title:
            checks["meta_title_present"] = True
            score += 10
            if 50 <= len(self.meta_title) <= 60:
                checks["meta_title_length"] = True
                score += 10
        
        # Description checks
        if self.meta_description:
            checks["meta_description_present"] = True
            score += 10
            if 150 <= len(self.meta_description) <= 160:
                checks["meta_description_length"] = True
                score += 10
        
        # Keyword in title
        if self.target_keyword and self.target_keyword.lower() in self.h1.lower():
            checks["keyword_in_h1"] = True
            score += 15
        
        # Word count
        if self.word_count >= 1200:
            checks["word_count_sufficient"] = True
            score += 15
        
        # Internal links
        if len(self.internal_links) >= 3:
            checks["internal_links_sufficient"] = True
            score += 15
        
        # FAQ present
        if len(self.faq_items) >= 3:
            checks["faq_present"] = True
            score += 15
        
        return {
            "score": score,
            "max_score": 100,
            "checks": checks
        }


@dataclass
class SchemaMarkup:
    """JSON-LD Schema markup model"""
    
    id: str
    client_id: str
    schema_type: str              # LocalBusiness, Article, FAQ, Product, Service
    
    # The actual schema
    schema_json: Dict[str, Any] = field(default_factory=dict)
    
    # Associated content
    content_id: Optional[str] = None
    page_url: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if not self.id:
            self.id = f"schema_{secrets.token_urlsafe(12)}"
    
    def to_json_ld(self) -> str:
        """Return formatted JSON-LD string"""
        return json.dumps(self.schema_json, indent=2)
    
    def to_html_script(self) -> str:
        """Return HTML script tag with schema"""
        return f'<script type="application/ld+json">\n{self.to_json_ld()}\n</script>'
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "schema_type": self.schema_type,
            "schema_json": self.schema_json,
            "content_id": self.content_id,
            "page_url": self.page_url,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SchemaMarkup":
        """Create SchemaMarkup from dictionary"""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        return cls(
            id=data.get('id', ''),
            client_id=data.get('client_id', ''),
            schema_type=data.get('schema_type', ''),
            schema_json=data.get('schema_json', {}),
            content_id=data.get('content_id'),
            page_url=data.get('page_url', ''),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow()
        )
    
    @classmethod
    def create_local_business(
        cls,
        client_id: str,
        business_name: str,
        description: str,
        address: str,
        phone: str,
        geo: Dict[str, float],
        services: List[str],
        opening_hours: List[str] = None
    ) -> 'SchemaMarkup':
        """Factory for LocalBusiness schema"""
        schema = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": business_name,
            "description": description,
            "address": {
                "@type": "PostalAddress",
                "streetAddress": address
            },
            "telephone": phone,
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": geo.get("lat", 0),
                "longitude": geo.get("lng", 0)
            },
            "hasOfferCatalog": {
                "@type": "OfferCatalog",
                "name": "Services",
                "itemListElement": [
                    {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s}}
                    for s in services
                ]
            }
        }
        
        if opening_hours:
            schema["openingHours"] = opening_hours
        
        return cls(
            id=f"schema_{secrets.token_urlsafe(12)}",
            client_id=client_id,
            schema_type="LocalBusiness",
            schema_json=schema
        )
    
    @classmethod
    def create_faq(cls, client_id: str, faqs: List[Dict[str, str]]) -> 'SchemaMarkup':
        """Factory for FAQ schema"""
        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq["answer"]
                    }
                }
                for faq in faqs
            ]
        }
        
        return cls(
            id=f"schema_{secrets.token_urlsafe(12)}",
            client_id=client_id,
            schema_type="FAQ",
            schema_json=schema
        )


@dataclass
class SocialPost:
    """Social media post model"""
    
    id: str
    client_id: str
    platform: str                 # gbp, facebook, instagram, linkedin, twitter
    
    # Content
    text: str = ""
    hashtags: List[str] = field(default_factory=list)
    
    # Media
    image_url: str = ""
    image_alt: str = ""
    
    # Link
    link_url: str = ""
    cta: str = ""                 # Call to action text
    
    # Status
    status: ContentStatus = ContentStatus.DRAFT
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    
    # Platform-specific IDs
    platform_post_id: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if not self.id:
            self.id = f"social_{secrets.token_urlsafe(12)}"
    
    def get_formatted_text(self) -> str:
        """Return text with hashtags"""
        hashtag_str = " ".join([f"#{tag}" for tag in self.hashtags])
        return f"{self.text}\n\n{hashtag_str}".strip()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "platform": self.platform,
            "text": self.text,
            "hashtags": self.hashtags,
            "image_url": self.image_url,
            "image_alt": self.image_alt,
            "link_url": self.link_url,
            "cta": self.cta,
            "status": self.status.value,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "platform_post_id": self.platform_post_id,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SocialPost":
        """Create SocialPost from dictionary"""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        scheduled_at = data.get('scheduled_at')
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        
        published_at = data.get('published_at')
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        
        return cls(
            id=data.get('id', ''),
            client_id=data.get('client_id', ''),
            platform=data.get('platform', ''),
            text=data.get('text', ''),
            hashtags=data.get('hashtags', []),
            image_url=data.get('image_url', ''),
            image_alt=data.get('image_alt', ''),
            link_url=data.get('link_url', ''),
            cta=data.get('cta', ''),
            status=ContentStatus(data.get('status', 'draft')),
            scheduled_at=scheduled_at,
            published_at=published_at,
            platform_post_id=data.get('platform_post_id', ''),
            created_at=created_at or datetime.utcnow()
        )


def create_social_kit(
    client_id: str,
    topic: str,
    link_url: str,
    platforms: List[str] = None
) -> List[SocialPost]:
    """Generate social posts for multiple platforms"""
    if platforms is None:
        platforms = ["gbp", "facebook", "instagram"]
    
    posts = []
    for platform in platforms:
        posts.append(SocialPost(
            id=f"social_{secrets.token_urlsafe(12)}",
            client_id=client_id,
            platform=platform,
            text=f"[Placeholder text for {topic}]",
            link_url=link_url
        ))
    
    return posts
