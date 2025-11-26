"""
MCP Framework - Model Tests
"""
import pytest
from datetime import datetime

from app.models.user import User, UserRole, create_admin_user, create_client_user
from app.models.client import Client, create_client
from app.models.content import BlogPost, SchemaMarkup, SocialPost, ContentStatus, ContentType
from app.models.campaign import Campaign, CampaignType, CampaignStatus, create_seo_campaign


class TestUserModel:
    """Test User model"""
    
    def test_create_admin_user(self):
        user = create_admin_user("admin@test.com", "Test Admin", "password123")
        
        assert user.email == "admin@test.com"
        assert user.name == "Test Admin"
        assert user.role == UserRole.ADMIN
        assert user.can_generate_content == True
        assert user.can_publish == True
        assert user.is_active == True
    
    def test_password_verification(self):
        user = create_admin_user("admin@test.com", "Test Admin", "password123")
        
        assert user.verify_password("password123") == True
        assert user.verify_password("wrongpassword") == False
    
    def test_api_key_generation(self):
        user = create_admin_user("admin@test.com", "Test Admin", "password123")
        
        assert user.api_key.startswith("mcp_")
        assert len(user.api_key) > 20
    
    def test_user_to_dict(self):
        user = create_admin_user("admin@test.com", "Test Admin", "password123")
        data = user.to_dict()
        
        assert data['email'] == "admin@test.com"
        assert data['role'] == "admin"
        assert 'password_hash' not in data  # Should not expose password
    
    def test_user_from_dict(self):
        original = create_admin_user("admin@test.com", "Test Admin", "password123")
        data = original.to_dict(include_sensitive=True)
        
        restored = User.from_dict(data)
        
        assert restored.email == original.email
        assert restored.role == original.role
    
    def test_client_access(self):
        admin = create_admin_user("admin@test.com", "Admin", "pass")
        client_user = create_client_user("client@test.com", "Client", "pass", ["client_123"])
        
        assert admin.has_access_to_client("client_123") == True
        assert admin.has_access_to_client("any_client") == True
        assert client_user.has_access_to_client("client_123") == True
        assert client_user.has_access_to_client("other_client") == False


class TestClientModel:
    """Test Client model"""
    
    def test_create_client(self):
        client = create_client(
            business_name="Test Roofing",
            industry="roofing",
            geo="Sarasota, FL",
            website_url="https://testroofing.com",
            keywords=["roof repair", "roofing company"]
        )
        
        assert client.business_name == "Test Roofing"
        assert client.industry == "roofing"
        assert client.geo == "Sarasota, FL"
        assert client.id.startswith("client_")
    
    def test_client_to_dict_from_dict(self):
        original = Client(
            id="client_test123",
            business_name="Test Business",
            industry="hvac",
            geo="Tampa, FL",
            primary_keywords=["hvac repair", "ac installation"]
        )
        
        data = original.to_dict()
        restored = Client.from_dict(data)
        
        assert restored.id == original.id
        assert restored.business_name == original.business_name
        assert restored.primary_keywords == original.primary_keywords
    
    def test_seo_context(self):
        client = Client(
            id="client_test",
            business_name="Test Business",
            industry="roofing",
            geo="Sarasota, FL",
            primary_keywords=["roof repair"],
            unique_selling_points=["24/7 emergency service"]
        )
        
        context = client.get_seo_context()
        
        assert context['business_name'] == "Test Business"
        assert context['location'] == "Sarasota, FL"
        assert "roof repair" in context['keywords']


class TestBlogPostModel:
    """Test BlogPost model"""
    
    def test_create_blog_post(self):
        post = BlogPost(
            id="",
            client_id="client_123",
            content_type=ContentType.BLOG_POST,
            title="Test Blog Post",
            body="This is a test blog post with some content. " * 100,
            h1="Test Blog Post | Sarasota, FL",
            target_keyword="roof repair sarasota"
        )
        
        assert post.id.startswith("content_")
        assert post.word_count > 0
        assert post.reading_time_minutes >= 1
    
    def test_seo_score(self):
        post = BlogPost(
            id="content_test",
            client_id="client_123",
            content_type=ContentType.BLOG_POST,
            title="Roof Repair Sarasota",
            body="Content " * 600,  # 1200 words
            h1="Roof Repair Sarasota - Expert Services",
            meta_title="Roof Repair Sarasota | 55 chars here123456",
            meta_description="Professional roof repair in Sarasota FL. Call now for expert service. We offer 24/7 emergency repairs. Free estimates available today. Contact us!",
            target_keyword="roof repair sarasota",
            internal_links=[{"url": "/a", "anchor": "a"}, {"url": "/b", "anchor": "b"}, {"url": "/c", "anchor": "c"}],
            faq_items=[{"q": "1", "a": "1"}, {"q": "2", "a": "2"}, {"q": "3", "a": "3"}]
        )
        
        score = post.get_seo_score()
        
        assert score['score'] > 50
        assert score['checks'].get('keyword_in_h1') == True
    
    def test_blog_post_from_dict(self):
        original = BlogPost(
            id="content_test",
            client_id="client_123",
            content_type=ContentType.BLOG_POST,
            title="Test Title",
            body="Test body content",
            h1="Test H1",
            faq_items=[{"question": "Q1?", "answer": "A1"}]
        )
        
        data = original.to_dict()
        restored = BlogPost.from_dict(data)
        
        assert restored.id == original.id
        assert restored.title == original.title
        assert len(restored.faq_items) == 1


class TestSchemaMarkupModel:
    """Test SchemaMarkup model"""
    
    def test_create_local_business_schema(self):
        schema = SchemaMarkup.create_local_business(
            client_id="client_123",
            business_name="Test Roofing",
            description="Professional roofing services",
            address="123 Main St, Sarasota, FL",
            phone="(941) 555-1234",
            geo={"lat": 27.3364, "lng": -82.5306},
            services=["Roof Repair", "Roof Replacement"]
        )
        
        assert schema.schema_type == "LocalBusiness"
        assert schema.schema_json["@type"] == "LocalBusiness"
        assert schema.schema_json["name"] == "Test Roofing"
    
    def test_create_faq_schema(self):
        faqs = [
            {"question": "How much does roof repair cost?", "answer": "Costs vary based on damage."},
            {"question": "Do you offer warranties?", "answer": "Yes, we offer 10-year warranties."}
        ]
        
        schema = SchemaMarkup.create_faq("client_123", faqs)
        
        assert schema.schema_type == "FAQ"
        assert schema.schema_json["@type"] == "FAQPage"
        assert len(schema.schema_json["mainEntity"]) == 2
    
    def test_to_html_script(self):
        schema = SchemaMarkup.create_faq("client_123", [{"question": "Q?", "answer": "A."}])
        html = schema.to_html_script()
        
        assert '<script type="application/ld+json">' in html
        assert '</script>' in html


class TestSocialPostModel:
    """Test SocialPost model"""
    
    def test_create_social_post(self):
        post = SocialPost(
            id="",
            client_id="client_123",
            platform="facebook",
            text="Check out our latest blog post!",
            hashtags=["roofing", "sarasota", "homeimprovement"]
        )
        
        assert post.id.startswith("social_")
        assert post.platform == "facebook"
    
    def test_formatted_text(self):
        post = SocialPost(
            id="social_test",
            client_id="client_123",
            platform="instagram",
            text="Great roofing tips!",
            hashtags=["roofing", "tips"]
        )
        
        formatted = post.get_formatted_text()
        
        assert "#roofing" in formatted
        assert "#tips" in formatted
    
    def test_social_post_from_dict(self):
        original = SocialPost(
            id="social_test",
            client_id="client_123",
            platform="gbp",
            text="Test post",
            hashtags=["test"]
        )
        
        data = original.to_dict()
        restored = SocialPost.from_dict(data)
        
        assert restored.id == original.id
        assert restored.platform == original.platform


class TestCampaignModel:
    """Test Campaign model"""
    
    def test_create_seo_campaign(self):
        campaign = create_seo_campaign(
            client_id="client_123",
            name="Q1 SEO Campaign",
            keywords=["roof repair", "roofing company"],
            locations=["Sarasota, FL", "Bradenton, FL"],
            monthly_budget=2500.0
        )
        
        assert campaign.campaign_type == CampaignType.SEO
        assert campaign.status == CampaignStatus.PLANNING
        assert len(campaign.goals) > 0
    
    def test_campaign_lifecycle(self):
        campaign = create_seo_campaign(
            client_id="client_123",
            name="Test Campaign",
            keywords=["test"],
            locations=["Test, FL"]
        )
        
        # Start campaign
        campaign.activate()
        assert campaign.status == CampaignStatus.ACTIVE
        assert campaign.start_date is not None
        
        # Pause
        campaign.pause()
        assert campaign.status == CampaignStatus.PAUSED
        
        # Complete
        campaign.complete()
        assert campaign.status == CampaignStatus.COMPLETED
        assert campaign.end_date is not None
    
    def test_add_content(self):
        campaign = create_seo_campaign(
            client_id="client_123",
            name="Test",
            keywords=[],
            locations=[]
        )
        
        campaign.add_content("content_abc")
        campaign.add_content("content_xyz")
        campaign.add_social_post("social_123")
        
        counts = campaign.get_content_count()
        
        assert counts['blog_posts'] == 2
        assert counts['social_posts'] == 1
        assert counts['total'] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
