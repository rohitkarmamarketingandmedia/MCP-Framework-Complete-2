"""
MCP Framework - WordPress Publishing Service
Publishes content to client WordPress sites via REST API
"""
import os
import re
import logging
import requests
import base64
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class WordPressService:
    """Handles publishing content to WordPress sites"""
    
    def __init__(self, site_url: str, username: str, app_password: str):
        """
        Initialize WordPress connection
        
        Args:
            site_url: WordPress site URL (e.g., https://example.com)
            username: WordPress username
            app_password: Application password (not regular password)
                         Generate at: WordPress Admin > Users > Profile > Application Passwords
        """
        self.site_url = site_url.rstrip('/')
        self.api_url = f"{self.site_url}/wp-json/wp/v2"
        self.username = username
        self.app_password = app_password
        
        # Create auth header
        credentials = f"{username}:{app_password}"
        token = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json'
        }
    
    def test_connection(self) -> Dict[str, Any]:
        """Test the WordPress connection"""
        try:
            # Try to get user info
            response = requests.get(
                f"{self.api_url}/users/me",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                user = response.json()
                return {
                    'success': True,
                    'connected_as': user.get('name'),
                    'site': self.site_url
                }
            else:
                return {
                    'success': False,
                    'error': f"Auth failed: {response.status_code}",
                    'message': response.text[:200]
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_post(
        self,
        title: str,
        content: str,
        status: str = 'draft',
        categories: list = None,
        tags: list = None,
        featured_image_url: str = None,
        meta_description: str = None,
        slug: str = None,
        author_id: int = None
    ) -> Dict[str, Any]:
        """
        Create a new WordPress post
        
        Args:
            title: Post title
            content: Post content (HTML)
            status: 'draft', 'publish', 'pending', 'private'
            categories: List of category IDs or names
            tags: List of tag IDs or names
            featured_image_url: URL of image to set as featured
            meta_description: SEO meta description (requires Yoast/RankMath)
            slug: URL slug (auto-generated if not provided)
            author_id: WordPress user ID for author
        
        Returns:
            Dict with success status and post details
        """
        try:
            # Prepare post data
            post_data = {
                'title': title,
                'content': content,
                'status': status
            }
            
            if slug:
                post_data['slug'] = slug
            
            if author_id:
                post_data['author'] = author_id
            
            # Handle categories
            if categories:
                category_ids = self._resolve_categories(categories)
                if category_ids:
                    post_data['categories'] = category_ids
            
            # Handle tags
            if tags:
                tag_ids = self._resolve_tags(tags)
                if tag_ids:
                    post_data['tags'] = tag_ids
            
            # Create the post
            response = requests.post(
                f"{self.api_url}/posts",
                headers=self.headers,
                json=post_data,
                timeout=30
            )
            
            if response.status_code not in [200, 201]:
                return {
                    'success': False,
                    'error': f"Failed to create post: {response.status_code}",
                    'message': response.text[:500]
                }
            
            post = response.json()
            post_id = post.get('id')
            
            # Upload and set featured image if provided
            if featured_image_url and post_id:
                image_result = self._set_featured_image(post_id, featured_image_url)
                if not image_result.get('success'):
                    logger.warning(f"Failed to set featured image: {image_result.get('error')}")
            
            # Set SEO meta if plugin available
            if meta_description and post_id:
                self._set_seo_meta(post_id, meta_description)
            
            return {
                'success': True,
                'post_id': post_id,
                'url': post.get('link'),
                'edit_url': f"{self.site_url}/wp-admin/post.php?post={post_id}&action=edit",
                'status': post.get('status')
            }
            
        except Exception as e:
            logger.error(f"WordPress publish error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_post(self, post_id: int, **kwargs) -> Dict[str, Any]:
        """Update an existing post"""
        try:
            response = requests.post(
                f"{self.api_url}/posts/{post_id}",
                headers=self.headers,
                json=kwargs,
                timeout=30
            )
            
            if response.status_code == 200:
                post = response.json()
                return {
                    'success': True,
                    'post_id': post_id,
                    'url': post.get('link')
                }
            else:
                return {
                    'success': False,
                    'error': f"Update failed: {response.status_code}"
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _resolve_categories(self, categories: list) -> list:
        """Convert category names to IDs, creating if needed"""
        category_ids = []
        
        for cat in categories:
            if isinstance(cat, int):
                category_ids.append(cat)
            else:
                # Search for category by name
                response = requests.get(
                    f"{self.api_url}/categories",
                    headers=self.headers,
                    params={'search': cat},
                    timeout=10
                )
                
                if response.status_code == 200:
                    results = response.json()
                    if results:
                        category_ids.append(results[0]['id'])
                    else:
                        # Create category
                        create_response = requests.post(
                            f"{self.api_url}/categories",
                            headers=self.headers,
                            json={'name': cat},
                            timeout=10
                        )
                        if create_response.status_code in [200, 201]:
                            category_ids.append(create_response.json()['id'])
        
        return category_ids
    
    def _resolve_tags(self, tags: list) -> list:
        """Convert tag names to IDs, creating if needed"""
        tag_ids = []
        
        for tag in tags:
            if isinstance(tag, int):
                tag_ids.append(tag)
            else:
                # Search for tag by name
                response = requests.get(
                    f"{self.api_url}/tags",
                    headers=self.headers,
                    params={'search': tag},
                    timeout=10
                )
                
                if response.status_code == 200:
                    results = response.json()
                    if results:
                        tag_ids.append(results[0]['id'])
                    else:
                        # Create tag
                        create_response = requests.post(
                            f"{self.api_url}/tags",
                            headers=self.headers,
                            json={'name': tag},
                            timeout=10
                        )
                        if create_response.status_code in [200, 201]:
                            tag_ids.append(create_response.json()['id'])
        
        return tag_ids
    
    def _set_featured_image(self, post_id: int, image_url: str) -> Dict[str, Any]:
        """Download image and set as featured image"""
        try:
            # Download image
            img_response = requests.get(image_url, timeout=30)
            if img_response.status_code != 200:
                return {'success': False, 'error': 'Failed to download image'}
            
            # Determine filename and content type
            filename = image_url.split('/')[-1].split('?')[0]
            if not filename or '.' not in filename:
                filename = 'featured-image.jpg'
            
            content_type = img_response.headers.get('Content-Type', 'image/jpeg')
            
            # Upload to WordPress media library
            upload_headers = {
                'Authorization': self.headers['Authorization'],
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': content_type
            }
            
            upload_response = requests.post(
                f"{self.api_url}/media",
                headers=upload_headers,
                data=img_response.content,
                timeout=60
            )
            
            if upload_response.status_code not in [200, 201]:
                return {'success': False, 'error': f'Upload failed: {upload_response.status_code}'}
            
            media_id = upload_response.json().get('id')
            
            # Set as featured image
            update_response = requests.post(
                f"{self.api_url}/posts/{post_id}",
                headers=self.headers,
                json={'featured_media': media_id},
                timeout=10
            )
            
            if update_response.status_code == 200:
                return {'success': True, 'media_id': media_id}
            else:
                return {'success': False, 'error': 'Failed to set featured image'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _set_seo_meta(self, post_id: int, meta_description: str) -> bool:
        """Try to set SEO meta description (Yoast or RankMath)"""
        try:
            # Try Yoast format
            requests.post(
                f"{self.api_url}/posts/{post_id}",
                headers=self.headers,
                json={
                    'meta': {
                        '_yoast_wpseo_metadesc': meta_description
                    }
                },
                timeout=10
            )
            return True
        except:
            return False
    
    def get_categories(self) -> list:
        """Get all categories"""
        try:
            response = requests.get(
                f"{self.api_url}/categories",
                headers=self.headers,
                params={'per_page': 100},
                timeout=10
            )
            if response.status_code == 200:
                return [{'id': c['id'], 'name': c['name'], 'slug': c['slug']} 
                        for c in response.json()]
            return []
        except:
            return []
    
    def get_posts(self, status: str = 'publish', per_page: int = 10) -> list:
        """Get recent posts"""
        try:
            response = requests.get(
                f"{self.api_url}/posts",
                headers=self.headers,
                params={'status': status, 'per_page': per_page},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []


class WordPressManager:
    """Manages WordPress connections for multiple clients"""
    
    def __init__(self):
        self._connections = {}
    
    def get_client_wordpress(self, client_id: int) -> Optional[WordPressService]:
        """Get WordPress service for a client"""
        from app.models.db_models import DBClient
        
        client = DBClient.query.get(client_id)
        if not client:
            return None
        
        # Check if we have WordPress credentials
        wp_url = client.wordpress_url
        wp_user = client.wordpress_user
        wp_pass = client.wordpress_app_password
        
        if not all([wp_url, wp_user, wp_pass]):
            return None
        
        # Cache connection
        cache_key = f"{client_id}:{wp_url}"
        if cache_key not in self._connections:
            self._connections[cache_key] = WordPressService(wp_url, wp_user, wp_pass)
        
        return self._connections[cache_key]
    
    def publish_content(self, client_id: int, content_queue_id: int) -> Dict[str, Any]:
        """Publish content from queue to client's WordPress"""
        from app.models.db_models import DBClient, DBContentQueue, DBBlogPost
        from app.database import db
        from app.services.email_service import get_email_service
        import re
        
        # Get content
        content = DBContentQueue.query.get(content_queue_id)
        if not content:
            return {'success': False, 'error': 'Content not found'}
        
        if content.status != 'approved':
            return {'success': False, 'error': 'Content not approved'}
        
        # Get WordPress connection
        wp = self.get_client_wordpress(client_id)
        if not wp:
            return {'success': False, 'error': 'WordPress not configured for this client'}
        
        # Get client for category info
        client = DBClient.query.get(client_id)
        
        # Build categories from industry
        categories = []
        if client.industry:
            categories.append(client.industry.title())
        
        # Build tags from keyword and location
        tags = []
        if content.primary_keyword:
            # Add the keyword and its parts as tags
            tags.append(content.primary_keyword)
            # Add individual meaningful words from keyword
            for word in content.primary_keyword.split():
                if len(word) > 3 and word.lower() not in ['with', 'from', 'that', 'this', 'your']:
                    tags.append(word.lower())
        
        if client.geo:
            # Add location as tag
            city = client.geo.split(',')[0].strip()
            tags.append(city)
        
        # Limit tags
        tags = list(set(tags))[:10]
        
        # Use body field (DBContentQueue uses 'body' not 'content')
        post_body = content.body or ''
        
        # Generate SEO-friendly slug from keyword
        slug = None
        if content.primary_keyword:
            slug = re.sub(r'[^a-z0-9]+', '-', content.primary_keyword.lower()).strip('-')[:60]
        
        # Publish with full SEO data
        result = wp.create_post(
            title=content.title,
            content=post_body,
            status='publish',
            categories=categories if categories else None,
            tags=tags if tags else None,
            meta_description=content.meta_description,
            slug=slug
        )
        
        if result.get('success'):
            # Update content queue
            content.status = 'published'
            content.published_at = datetime.utcnow()
            content.published_url = result.get('url')
            content.wordpress_post_id = result.get('post_id')
            
            # Also save as blog post (use 'body' not 'content')
            blog = DBBlogPost(
                client_id=client_id,
                title=content.title,
                primary_keyword=content.primary_keyword,
                body=post_body,
                meta_title=content.meta_title,
                meta_description=content.meta_description,
                status='published',
                word_count=content.word_count,
                seo_score=content.our_seo_score
            )
            db.session.add(blog)
            db.session.commit()
            
            # Send notification
            email = get_email_service()
            from app.models.db_models import DBUser
            admins = DBUser.query.filter_by(role='admin').all()
            for admin in admins:
                if admin.email:
                    email.send_wordpress_published(
                        admin.email,
                        client.business_name,
                        content.title,
                        result.get('url')
                    )
            
            logger.info(f"Published to WordPress: {content.title} -> {result.get('url')}")
        
        return result


# Singleton
_wp_manager = None

def get_wordpress_manager() -> WordPressManager:
    global _wp_manager
    if _wp_manager is None:
        _wp_manager = WordPressManager()
    return _wp_manager
