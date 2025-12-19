"""
MCP Framework - CMS Service
WordPress and other CMS publishing
"""
import os
import base64
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime


class CMSService:
    """CMS publishing service (WordPress, Webflow, etc.)"""
    
    def __init__(self):
        self.wp_url = os.environ.get('WP_BASE_URL', '')
        self.wp_username = os.environ.get('WP_USERNAME', '')
        self.wp_password = os.environ.get('WP_APP_PASSWORD', '')
    
    def publish_to_wordpress(
        self,
        wp_url: str = None,
        wp_username: str = None,
        wp_password: str = None,
        title: str = '',
        body: str = '',
        meta_title: str = '',
        meta_description: str = '',
        status: str = 'draft',
        categories: List[str] = None,
        tags: List[str] = None,
        featured_image_url: str = None,
        slug: str = None
    ) -> Dict[str, Any]:
        """
        Publish content to WordPress via REST API
        
        Args:
            wp_url: WordPress site URL (e.g., https://example.com)
            wp_username: WordPress username
            wp_password: Application password
            title: Post title
            body: Post HTML content
            meta_title: SEO meta title (requires Yoast/RankMath)
            meta_description: SEO meta description
            status: 'draft', 'publish', 'pending', 'private'
            categories: List of category names
            tags: List of tag names
            featured_image_url: URL of featured image to upload
            slug: Custom URL slug
        
        Returns:
            {
                'success': bool,
                'post_id': int,
                'url': str,
                'edit_url': str
            }
        """
        wp_url = wp_url or self.wp_url
        wp_username = wp_username or self.wp_username
        wp_password = wp_password or self.wp_password
        
        if not all([wp_url, wp_username, wp_password]):
            return {'error': 'WordPress credentials not configured'}
        
        # Clean URL
        wp_url = wp_url.rstrip('/')
        api_url = f'{wp_url}/wp-json/wp/v2'
        
        # Create auth header
        credentials = f'{wp_username}:{wp_password}'
        token = base64.b64encode(credentials.encode()).decode()
        headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            # Prepare post data
            post_data = {
                'title': title,
                'content': body,
                'status': status
            }
            
            if slug:
                post_data['slug'] = slug
            
            # Handle categories
            if categories:
                category_ids = self._get_or_create_categories(api_url, headers, categories)
                if category_ids:
                    post_data['categories'] = category_ids
            
            # Handle tags
            if tags:
                tag_ids = self._get_or_create_tags(api_url, headers, tags)
                if tag_ids:
                    post_data['tags'] = tag_ids
            
            # Create post
            response = requests.post(
                f'{api_url}/posts',
                headers=headers,
                json=post_data,
                timeout=30
            )
            
            response.raise_for_status()
            post = response.json()
            
            post_id = post['id']
            post_url = post['link']
            
            # Upload featured image if provided
            if featured_image_url:
                media_id = self._upload_featured_image(
                    api_url, headers, featured_image_url, post_id
                )
                if media_id:
                    # Set as featured image
                    requests.post(
                        f'{api_url}/posts/{post_id}',
                        headers=headers,
                        json={'featured_media': media_id},
                        timeout=30
                    )
            
            # Update SEO meta if using Yoast
            if meta_title or meta_description:
                self._update_yoast_meta(
                    api_url, headers, post_id, meta_title, meta_description
                )
            
            return {
                'success': True,
                'post_id': post_id,
                'url': post_url,
                'edit_url': f'{wp_url}/wp-admin/post.php?post={post_id}&action=edit',
                'status': status
            }
            
        except requests.RequestException as e:
            return {'error': f'WordPress API error: {str(e)}'}
    
    def update_wordpress_post(
        self,
        post_id: int,
        wp_url: str = None,
        wp_username: str = None,
        wp_password: str = None,
        **updates
    ) -> Dict[str, Any]:
        """Update an existing WordPress post"""
        wp_url = wp_url or self.wp_url
        wp_username = wp_username or self.wp_username
        wp_password = wp_password or self.wp_password
        
        if not all([wp_url, wp_username, wp_password]):
            return {'error': 'WordPress credentials not configured'}
        
        wp_url = wp_url.rstrip('/')
        api_url = f'{wp_url}/wp-json/wp/v2'
        
        credentials = f'{wp_username}:{wp_password}'
        token = base64.b64encode(credentials.encode()).decode()
        headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f'{api_url}/posts/{post_id}',
                headers=headers,
                json=updates,
                timeout=30
            )
            
            response.raise_for_status()
            post = response.json()
            
            return {
                'success': True,
                'post_id': post_id,
                'url': post['link']
            }
            
        except requests.RequestException as e:
            return {'error': f'WordPress API error: {str(e)}'}
    
    def get_wordpress_posts(
        self,
        wp_url: str = None,
        wp_username: str = None,
        wp_password: str = None,
        per_page: int = 20,
        status: str = 'any'
    ) -> Dict[str, Any]:
        """Get list of WordPress posts"""
        wp_url = wp_url or self.wp_url
        wp_username = wp_username or self.wp_username
        wp_password = wp_password or self.wp_password
        
        wp_url = wp_url.rstrip('/')
        api_url = f'{wp_url}/wp-json/wp/v2'
        
        credentials = f'{wp_username}:{wp_password}'
        token = base64.b64encode(credentials.encode()).decode()
        headers = {'Authorization': f'Basic {token}'}
        
        try:
            response = requests.get(
                f'{api_url}/posts',
                headers=headers,
                params={'per_page': per_page, 'status': status},
                timeout=30
            )
            
            response.raise_for_status()
            posts = response.json()
            
            return {
                'posts': [
                    {
                        'id': p['id'],
                        'title': p['title']['rendered'],
                        'url': p['link'],
                        'status': p['status'],
                        'date': p['date']
                    }
                    for p in posts
                ]
            }
            
        except requests.RequestException as e:
            return {'error': f'WordPress API error: {str(e)}'}
    
    def _get_or_create_categories(
        self,
        api_url: str,
        headers: Dict,
        category_names: List[str]
    ) -> List[int]:
        """Get or create WordPress categories"""
        category_ids = []
        
        for name in category_names:
            # Search for existing
            response = requests.get(
                f'{api_url}/categories',
                headers=headers,
                params={'search': name},
                timeout=15
            )
            
            if response.ok:
                categories = response.json()
                if categories:
                    category_ids.append(categories[0]['id'])
                else:
                    # Create new category
                    create_response = requests.post(
                        f'{api_url}/categories',
                        headers=headers,
                        json={'name': name},
                        timeout=15
                    )
                    if create_response.ok:
                        category_ids.append(create_response.json()['id'])
        
        return category_ids
    
    def _get_or_create_tags(
        self,
        api_url: str,
        headers: Dict,
        tag_names: List[str]
    ) -> List[int]:
        """Get or create WordPress tags"""
        tag_ids = []
        
        for name in tag_names:
            response = requests.get(
                f'{api_url}/tags',
                headers=headers,
                params={'search': name},
                timeout=15
            )
            
            if response.ok:
                tags = response.json()
                if tags:
                    tag_ids.append(tags[0]['id'])
                else:
                    create_response = requests.post(
                        f'{api_url}/tags',
                        headers=headers,
                        json={'name': name},
                        timeout=15
                    )
                    if create_response.ok:
                        tag_ids.append(create_response.json()['id'])
        
        return tag_ids
    
    def _upload_featured_image(
        self,
        api_url: str,
        headers: Dict,
        image_url: str,
        post_id: int
    ) -> Optional[int]:
        """Upload image from URL and return media ID"""
        try:
            # Download image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            
            # Determine filename
            filename = image_url.split('/')[-1].split('?')[0]
            if '.' not in filename:
                filename = f'image_{post_id}.jpg'
            
            # Upload to WordPress
            upload_headers = headers.copy()
            upload_headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            upload_headers['Content-Type'] = img_response.headers.get('Content-Type', 'image/jpeg')
            
            upload_response = requests.post(
                f'{api_url}/media',
                headers=upload_headers,
                data=img_response.content,
                timeout=60
            )
            
            if upload_response.ok:
                return upload_response.json()['id']
            
        except Exception:
            pass
        
        return None
    
    def _update_yoast_meta(
        self,
        api_url: str,
        headers: Dict,
        post_id: int,
        meta_title: str,
        meta_description: str
    ) -> bool:
        """Update Yoast SEO meta fields"""
        try:
            # Yoast stores meta in post meta
            meta_update = {}
            
            if meta_title:
                meta_update['yoast_wpseo_title'] = meta_title
            if meta_description:
                meta_update['yoast_wpseo_metadesc'] = meta_description
            
            if meta_update:
                response = requests.post(
                    f'{api_url}/posts/{post_id}',
                    headers=headers,
                    json={'meta': meta_update},
                    timeout=15
                )
                return response.ok
            
        except Exception:
            pass
        
        return False
