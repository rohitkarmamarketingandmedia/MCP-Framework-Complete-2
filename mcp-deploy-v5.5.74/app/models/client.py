"""
MCP Framework - Client Model
Represents a marketing client/business
"""
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field
import secrets


@dataclass
class Client:
    """Client/Business model for MCP campaigns"""
    
    id: str
    business_name: str
    industry: str                    # roofing, hvac, electrical, dental, etc.
    
    # Location targeting
    geo: str = ""                    # Primary location (city, state)
    service_areas: List[str] = field(default_factory=list)
    
    # Contact info
    website_url: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    
    # SEO settings
    primary_keywords: List[str] = field(default_factory=list)
    secondary_keywords: List[str] = field(default_factory=list)
    competitors: List[str] = field(default_factory=list)
    
    # Content settings
    tone: str = "professional"       # professional, casual, technical, friendly
    brand_voice: str = ""
    unique_selling_points: List[str] = field(default_factory=list)
    
    # Integration credentials (encrypted in production)
    wordpress_url: str = ""
    wordpress_api_key: str = ""
    gbp_location_id: str = ""
    ga4_property_id: str = ""
    
    # Subscription
    plan_tier: str = "standard"      # standard, premium, enterprise
    monthly_budget: float = 0.0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    def __post_init__(self):
        if not self.id:
            self.id = f"client_{secrets.token_urlsafe(12)}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "business_name": self.business_name,
            "industry": self.industry,
            "geo": self.geo,
            "service_areas": self.service_areas,
            "website_url": self.website_url,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "primary_keywords": self.primary_keywords,
            "secondary_keywords": self.secondary_keywords,
            "competitors": self.competitors,
            "tone": self.tone,
            "brand_voice": self.brand_voice,
            "unique_selling_points": self.unique_selling_points,
            "wordpress_url": self.wordpress_url,
            "wordpress_api_key": self.wordpress_api_key,
            "gbp_location_id": self.gbp_location_id,
            "ga4_property_id": self.ga4_property_id,
            "plan_tier": self.plan_tier,
            "monthly_budget": self.monthly_budget,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Client":
        """Create Client from dictionary"""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        return cls(
            id=data.get('id', ''),
            business_name=data.get('business_name', ''),
            industry=data.get('industry', ''),
            geo=data.get('geo', ''),
            service_areas=data.get('service_areas', []),
            website_url=data.get('website_url', ''),
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            address=data.get('address', ''),
            primary_keywords=data.get('primary_keywords', []),
            secondary_keywords=data.get('secondary_keywords', []),
            competitors=data.get('competitors', []),
            tone=data.get('tone', 'professional'),
            brand_voice=data.get('brand_voice', ''),
            unique_selling_points=data.get('unique_selling_points', []),
            wordpress_url=data.get('wordpress_url', ''),
            wordpress_api_key=data.get('wordpress_api_key', ''),
            gbp_location_id=data.get('gbp_location_id', ''),
            ga4_property_id=data.get('ga4_property_id', ''),
            plan_tier=data.get('plan_tier', 'standard'),
            monthly_budget=data.get('monthly_budget', 0.0),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow(),
            is_active=data.get('is_active', True)
        )
    
    def get_seo_context(self) -> Dict:
        """Return SEO-relevant context for content generation"""
        return {
            "business_name": self.business_name,
            "industry": self.industry,
            "location": self.geo,
            "service_areas": self.service_areas,
            "keywords": self.primary_keywords + self.secondary_keywords,
            "tone": self.tone,
            "usps": self.unique_selling_points
        }


def create_client(
    business_name: str,
    industry: str,
    geo: str,
    website_url: str = "",
    keywords: List[str] = None
) -> Client:
    """Factory function to create a new client"""
    return Client(
        id=f"client_{secrets.token_urlsafe(12)}",
        business_name=business_name,
        industry=industry,
        geo=geo,
        website_url=website_url,
        primary_keywords=keywords or []
    )
