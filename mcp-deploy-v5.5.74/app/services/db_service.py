"""
MCP Framework - Database Service
PostgreSQL-backed data operations
Replaces file-based DataService for production
"""
from typing import Optional, List
from datetime import datetime

from app.database import db
from app.models.db_models import (
    DBUser, DBClient, DBBlogPost, DBSocialPost, 
    DBCampaign, DBSchemaMarkup, UserRole
)


class DataService:
    """
    Database-backed data service
    Same interface as file-based DataService for compatibility
    """
    
    # ============================================
    # User Operations
    # ============================================
    
    def save_user(self, user: DBUser) -> DBUser:
        """Save or update a user"""
        existing = DBUser.query.get(user.id)
        if existing:
            # Update existing
            existing.email = user.email
            existing.name = user.name
            existing.role = user.role
            existing.is_active = user.is_active
            existing.client_ids = user.client_ids
        else:
            db.session.add(user)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e
        return user
    
    def get_user(self, user_id: str) -> Optional[DBUser]:
        """Get user by ID"""
        # Use filter_by instead of get() for more reliable results
        # query.get() can have issues with session state
        return DBUser.query.filter_by(id=user_id).first()
    
    def get_user_by_email(self, email: str) -> Optional[DBUser]:
        """Get user by email"""
        return DBUser.query.filter_by(email=email.lower()).first()
    
    def get_user_by_api_key(self, api_key: str) -> Optional[DBUser]:
        """Get user by API key"""
        return DBUser.query.filter_by(api_key=api_key, is_active=True).first()
    
    def get_all_users(self) -> List[DBUser]:
        """Get all users"""
        return DBUser.query.all()
    
    def delete_user(self, user_id: str) -> bool:
        """Delete a user"""
        user = DBUser.query.get(user_id)
        if user:
            try:
                db.session.delete(user)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise
                return True
            except Exception:
                db.session.rollback()
                return False
        return False
    
    def update_last_login(self, user_id: str):
        """Update user's last login timestamp"""
        user = DBUser.query.get(user_id)
        if user:
            try:
                user.last_login = datetime.utcnow()
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise
            except Exception:
                db.session.rollback()
    
    # ============================================
    # Client Operations
    # ============================================
    
    def save_client(self, client: DBClient) -> DBClient:
        """Save or update a client"""
        existing = DBClient.query.get(client.id)
        if existing:
            # Update existing
            existing.business_name = client.business_name
            existing.industry = client.industry
            existing.geo = client.geo
            existing.website_url = client.website_url
            existing.phone = client.phone
            existing.email = client.email
            existing.primary_keywords = client.primary_keywords
            existing.secondary_keywords = client.secondary_keywords
            existing.competitors = client.competitors
            existing.service_areas = client.service_areas
            existing.unique_selling_points = client.unique_selling_points
            existing.tone = client.tone
            existing.integrations = client.integrations
            existing.subscription_tier = client.subscription_tier
            existing.is_active = client.is_active
            # WordPress fields
            existing.wordpress_url = client.wordpress_url
            existing.wordpress_user = client.wordpress_user
            existing.wordpress_app_password = client.wordpress_app_password
            existing.updated_at = datetime.utcnow()
        else:
            db.session.add(client)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return client
    
    def get_client(self, client_id: str) -> Optional[DBClient]:
        """Get client by ID"""
        return DBClient.query.filter_by(id=client_id).first()
    
    def get_all_clients(self) -> List[DBClient]:
        """Get all clients"""
        return DBClient.query.filter_by(is_active=True).all()
    
    def delete_client(self, client_id: str) -> bool:
        """Soft delete a client"""
        client = DBClient.query.get(client_id)
        if client:
            try:
                client.is_active = False
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise
                return True
            except Exception:
                db.session.rollback()
                return False
        return False
    
    # ============================================
    # Blog Post Operations
    # ============================================
    
    def save_blog_post(self, post: DBBlogPost) -> DBBlogPost:
        """Save or update a blog post"""
        existing = DBBlogPost.query.get(post.id)
        if existing:
            # Update existing
            existing.title = post.title
            existing.slug = post.slug
            existing.meta_title = post.meta_title
            existing.meta_description = post.meta_description
            existing.body = post.body
            existing.excerpt = post.excerpt
            existing.primary_keyword = post.primary_keyword
            existing.secondary_keywords = post.secondary_keywords
            existing.word_count = post.word_count
            existing.seo_score = post.seo_score
            existing.internal_links = post.internal_links
            existing.external_links = post.external_links
            existing.schema_markup = post.schema_markup
            existing.faq_content = post.faq_content
            existing.status = post.status
            existing.updated_at = datetime.utcnow()
        else:
            db.session.add(post)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return post
    
    def get_blog_post(self, post_id: str) -> Optional[DBBlogPost]:
        """Get blog post by ID"""
        return DBBlogPost.query.get(post_id)
    
    def get_client_blog_posts(self, client_id: str) -> List[DBBlogPost]:
        """Get all blog posts for a client"""
        return DBBlogPost.query.filter_by(client_id=client_id).order_by(DBBlogPost.created_at.desc()).all()
    
    def delete_blog_post(self, post_id: str) -> bool:
        """Delete a blog post"""
        post = DBBlogPost.query.get(post_id)
        if post:
            db.session.delete(post)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return True
        return False
    
    # ============================================
    # Social Post Operations
    # ============================================
    
    def save_social_post(self, post: DBSocialPost) -> DBSocialPost:
        """Save or update a social post"""
        existing = DBSocialPost.query.get(post.id)
        if existing:
            existing.content = post.content
            existing.hashtags = post.hashtags
            existing.media_urls = post.media_urls
            existing.link_url = post.link_url
            existing.status = post.status
            existing.scheduled_for = post.scheduled_for
        else:
            db.session.add(post)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return post
    
    def get_social_post(self, post_id: str) -> Optional[DBSocialPost]:
        """Get social post by ID"""
        return DBSocialPost.query.get(post_id)
    
    def get_client_social_posts(self, client_id: str, platform: Optional[str] = None) -> List[DBSocialPost]:
        """Get social posts for a client"""
        query = DBSocialPost.query.filter_by(client_id=client_id)
        if platform:
            query = query.filter_by(platform=platform)
        return query.order_by(DBSocialPost.created_at.desc()).all()
    
    def delete_social_post(self, post_id: str) -> bool:
        """Delete a social post"""
        post = DBSocialPost.query.get(post_id)
        if post:
            db.session.delete(post)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return True
        return False
    
    # ============================================
    # Campaign Operations
    # ============================================
    
    def save_campaign(self, campaign: DBCampaign) -> DBCampaign:
        """Save or update a campaign"""
        existing = DBCampaign.query.get(campaign.id)
        if existing:
            existing.name = campaign.name
            existing.campaign_type = campaign.campaign_type
            existing.description = campaign.description
            existing.start_date = campaign.start_date
            existing.end_date = campaign.end_date
            existing.budget = campaign.budget
            existing.spent = campaign.spent
            existing.status = campaign.status
            existing.content_ids = campaign.content_ids
            existing.metrics = campaign.metrics
            existing.updated_at = datetime.utcnow()
        else:
            db.session.add(campaign)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return campaign
    
    def get_campaign(self, campaign_id: str) -> Optional[DBCampaign]:
        """Get campaign by ID"""
        return DBCampaign.query.get(campaign_id)
    
    def get_client_campaigns(self, client_id: str) -> List[DBCampaign]:
        """Get all campaigns for a client"""
        return DBCampaign.query.filter_by(client_id=client_id).order_by(DBCampaign.created_at.desc()).all()
    
    def delete_campaign(self, campaign_id: str) -> bool:
        """Delete a campaign"""
        campaign = DBCampaign.query.get(campaign_id)
        if campaign:
            db.session.delete(campaign)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return True
        return False
    
    # ============================================
    # Schema Markup Operations
    # ============================================
    
    def save_schema(self, schema: DBSchemaMarkup) -> DBSchemaMarkup:
        """Save or update a schema"""
        existing = DBSchemaMarkup.query.get(schema.id)
        if existing:
            existing.schema_type = schema.schema_type
            existing.name = schema.name
            existing.json_ld = schema.json_ld
            existing.is_active = schema.is_active
        else:
            db.session.add(schema)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return schema
    
    def get_schema(self, schema_id: str) -> Optional[DBSchemaMarkup]:
        """Get schema by ID"""
        return DBSchemaMarkup.query.get(schema_id)
    
    def get_client_schemas(self, client_id: str) -> List[DBSchemaMarkup]:
        """Get all schemas for a client"""
        return DBSchemaMarkup.query.filter_by(client_id=client_id, is_active=True).all()
    
    def delete_schema(self, schema_id: str) -> bool:
        """Delete a schema"""
        schema = DBSchemaMarkup.query.get(schema_id)
        if schema:
            db.session.delete(schema)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            return True
        return False


# ============================================
# Helper Functions
# ============================================

def create_admin_user(email: str, name: str, password: str) -> DBUser:
    """Create an admin user"""
    user = DBUser(
        email=email,
        name=name,
        password=password,
        role=UserRole.ADMIN
    )
    return user
