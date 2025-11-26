"""
MCP Framework - Campaign Model
Marketing campaign tracking and management
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import secrets


class CampaignStatus(Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CampaignType(Enum):
    SEO = "seo"
    CONTENT = "content"
    SOCIAL = "social"
    PPC = "ppc"
    EMAIL = "email"
    FULL_SERVICE = "full_service"


@dataclass
class Campaign:
    """Marketing campaign model"""
    
    id: str
    client_id: str
    name: str
    campaign_type: CampaignType
    
    # Description
    description: str = ""
    goals: List[str] = field(default_factory=list)
    
    # Targeting
    target_keywords: List[str] = field(default_factory=list)
    target_locations: List[str] = field(default_factory=list)
    target_audience: str = ""
    
    # Status
    status: CampaignStatus = CampaignStatus.PLANNING
    
    # Timeline
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Budget
    monthly_budget: float = 0.0
    total_spent: float = 0.0
    
    # Content tracking
    content_ids: List[str] = field(default_factory=list)      # Associated blog posts
    schema_ids: List[str] = field(default_factory=list)       # Associated schemas
    social_post_ids: List[str] = field(default_factory=list)  # Associated social posts
    
    # Metrics
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if not self.id:
            self.id = f"campaign_{secrets.token_urlsafe(12)}"
    
    def add_content(self, content_id: str) -> None:
        """Add content to campaign"""
        if content_id not in self.content_ids:
            self.content_ids.append(content_id)
            self.updated_at = datetime.utcnow()
    
    def add_social_post(self, post_id: str) -> None:
        """Add social post to campaign"""
        if post_id not in self.social_post_ids:
            self.social_post_ids.append(post_id)
            self.updated_at = datetime.utcnow()
    
    def update_metrics(self, new_metrics: Dict[str, Any]) -> None:
        """Update campaign metrics"""
        self.metrics.update(new_metrics)
        self.updated_at = datetime.utcnow()
    
    def get_content_count(self) -> Dict[str, int]:
        """Get count of all associated content"""
        return {
            "blog_posts": len(self.content_ids),
            "schemas": len(self.schema_ids),
            "social_posts": len(self.social_post_ids),
            "total": len(self.content_ids) + len(self.schema_ids) + len(self.social_post_ids)
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "name": self.name,
            "campaign_type": self.campaign_type.value,
            "description": self.description,
            "goals": self.goals,
            "target_keywords": self.target_keywords,
            "target_locations": self.target_locations,
            "target_audience": self.target_audience,
            "status": self.status.value,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "monthly_budget": self.monthly_budget,
            "total_spent": self.total_spent,
            "content_ids": self.content_ids,
            "schema_ids": self.schema_ids,
            "social_post_ids": self.social_post_ids,
            "content_count": self.get_content_count(),
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Campaign":
        """Create Campaign from dictionary"""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        start_date = data.get('start_date')
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        
        end_date = data.get('end_date')
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        return cls(
            id=data.get('id', ''),
            client_id=data.get('client_id', ''),
            name=data.get('name', ''),
            campaign_type=CampaignType(data.get('campaign_type', 'seo')),
            description=data.get('description', ''),
            goals=data.get('goals', []),
            target_keywords=data.get('target_keywords', []),
            target_locations=data.get('target_locations', []),
            target_audience=data.get('target_audience', ''),
            status=CampaignStatus(data.get('status', 'planning')),
            start_date=start_date,
            end_date=end_date,
            monthly_budget=data.get('monthly_budget', 0.0),
            total_spent=data.get('total_spent', 0.0),
            content_ids=data.get('content_ids', []),
            schema_ids=data.get('schema_ids', []),
            social_post_ids=data.get('social_post_ids', []),
            metrics=data.get('metrics', {}),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow()
        )
    
    def activate(self) -> None:
        """Activate the campaign"""
        self.status = CampaignStatus.ACTIVE
        if not self.start_date:
            self.start_date = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def pause(self) -> None:
        """Pause the campaign"""
        self.status = CampaignStatus.PAUSED
        self.updated_at = datetime.utcnow()
    
    def complete(self) -> None:
        """Mark campaign as completed"""
        self.status = CampaignStatus.COMPLETED
        self.end_date = datetime.utcnow()
        self.updated_at = datetime.utcnow()


def create_seo_campaign(
    client_id: str,
    name: str,
    keywords: List[str],
    locations: List[str],
    monthly_budget: float = 0.0
) -> Campaign:
    """Factory for creating SEO campaigns"""
    return Campaign(
        id=f"campaign_{secrets.token_urlsafe(12)}",
        client_id=client_id,
        name=name,
        campaign_type=CampaignType.SEO,
        target_keywords=keywords,
        target_locations=locations,
        monthly_budget=monthly_budget,
        goals=[
            "Improve organic search rankings",
            "Increase organic traffic",
            "Generate qualified leads"
        ]
    )


def create_content_campaign(
    client_id: str,
    name: str,
    topics: List[str],
    content_count: int = 4
) -> Campaign:
    """Factory for creating content marketing campaigns"""
    return Campaign(
        id=f"campaign_{secrets.token_urlsafe(12)}",
        client_id=client_id,
        name=name,
        campaign_type=CampaignType.CONTENT,
        target_keywords=topics,
        goals=[
            f"Publish {content_count} blog posts per month",
            "Build topical authority",
            "Drive organic engagement"
        ]
    )
