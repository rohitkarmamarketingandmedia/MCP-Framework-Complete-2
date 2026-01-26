"""
MCP Framework - WordPress Publishing Service
Publishes content to client WordPress sites via REST API
"""
import os
import re
import time
import logging
import requests
import base64
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def retry_request(func, max_retries=3, delay=1):
    """Retry a request with exponential backoff"""
    last_error = None
    for attempt in range(max_retries):
        try:
            result = func()
            return result
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Request failed, retrying in {wait_time}s... ({e})")
                time.sleep(wait_time)
    raise last_error


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
        self.username = username.strip()
        # WordPress app passwords can have spaces - that's OK, but trim leading/trailing
        self.app_password = app_password.strip() if app_password else ''
        
        # Create session with persistent headers and cookies
        self.session = requests.Session()
        credentials = f"{self.username}:{self.app_password}"
        token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
        
        self.session.headers.update({
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': self.site_url,
            'Origin': self.site_url,
            'Connection': 'keep-alive',
            'X-Requested-With': 'XMLHttpRequest',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"'
        })

    def _handle_response(self, response: requests.Response) -> requests.Response:
        """Centralized response handling to detect captchas and errors"""
        # Check for SiteGround captcha specific signatures
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type and 'application/json' not in content_type:
                text = response.text.lower()
                if 'sgcaptcha' in text or 'checking your browser' in text or 'cf-browser-verification' in text:
                    logger.error(f"Captcha detected on {response.url}")
                    raise requests.exceptions.ConnectionError("SiteGround Captcha Challenge detected. Please whitelist server IP.")
        
        return response
    
    def test_connection(self) -> Dict[str, Any]:
        """Test the WordPress connection using multiple methods"""
        try:
            # Method 1: Try /users/me endpoint (best for auth testing)
            response = self.session.get(
                f"{self.api_url}/users/me",
                timeout=15
            )
            self._handle_response(response)
            
            # Check for captcha/challenge page
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type and 'application/json' not in content_type:
                text = response.text.lower()
                if 'checking your browser' in text or 'cf-browser-verification' in text:
                    return {
                        'success': False,
                        'error': 'Security challenge detected',
                        'message': 'Cloudflare or similar protection is blocking access. Try whitelisting the server IP.',
                        'response_preview': response.text[:300]
                    }
            
            if response.status_code == 200:
                # Successfully authenticated!
                try:
                    user_data = response.json()
                    user_name = user_data.get('name', self.username)
                    user_roles = user_data.get('roles', [])
                    capabilities = user_data.get('capabilities', {})
                    
                    can_publish = (
                        'administrator' in user_roles or 
                        'editor' in user_roles or
                        'author' in user_roles or
                        capabilities.get('publish_posts', False)
                    )
                    
                    return {
                        'success': True,
                        'user': user_name,
                        'roles': user_roles,
                        'can_publish': can_publish,
                        'connected_as': user_name,
                        'site': self.site_url,
                        'message': f"Connected as {user_name}" + (" (can publish)" if can_publish else " (limited permissions)")
                    }
                except Exception:
                    return {
                        'success': True,
                        'connected_as': self.username,
                        'site': self.site_url,
                        'message': 'Connected successfully'
                    }
            
            elif response.status_code == 401:
                # Get more details about the 401 error
                try:
                    error_data = response.json()
                    error_code = error_data.get('code', '')
                    error_msg = error_data.get('message', '')
                except Exception:
                    error_code = ''
                    error_msg = response.text[:200]
                
                if 'invalid_username' in str(error_code).lower() or 'invalid_username' in error_msg.lower():
                    return {
                        'success': False,
                        'error': 'Invalid username',
                        'message': f'The username "{self.username}" was not found. Check your WordPress username.'
                    }
                elif 'incorrect_password' in str(error_code).lower() or 'incorrect_password' in error_msg.lower():
                    return {
                        'success': False,
                        'error': 'Invalid password',
                        'message': 'The Application Password is incorrect. Generate a new one at: WordPress Admin → Users → Profile → Application Passwords'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Authentication failed',
                        'message': f'Invalid credentials. Make sure you are using an Application Password (not your regular WordPress password). Error: {error_msg}'
                    }
            
            elif response.status_code == 403:
                # 403 on /users/me - try fallback to /posts with context=edit
                return self._test_connection_fallback()
                
            elif response.status_code == 404:
                # /users/me not available, try fallback
                return self._test_connection_fallback()
            else:
                return {
                    'success': False,
                    'error': f'Unexpected response: {response.status_code}',
                    'message': response.text[:300]
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Connection timeout',
                'message': 'The WordPress site took too long to respond. Check the URL and try again.'
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'success': False,
                'error': 'Connection failed',
                'message': f'Could not connect to {self.site_url}. Check the URL is correct and the site is accessible.'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Connection test failed: {str(e)}'
            }
    
    def _test_connection_fallback(self) -> Dict[str, Any]:
        """Fallback connection test using posts endpoint with edit context"""
        try:
            # Try to access posts with edit context (requires auth)
            response = self.session.get(
                f"{self.api_url}/posts",
                params={'per_page': 1, 'context': 'edit'},
                timeout=15
            )
            self._handle_response(response)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'connected_as': self.username,
                    'site': self.site_url,
                    'can_publish': True,
                    'message': f'Connected as {self.username}'
                }
            elif response.status_code == 401:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', response.text[:200])
                except:
                    error_msg = response.text[:200]
                return {
                    'success': False,
                    'error': 'Authentication failed',
                    'message': f'Invalid credentials. {error_msg}'
                }
            elif response.status_code == 403:
                # Check if public API works
                public_check = requests.get(
                    f"{self.site_url}/wp-json/wp/v2/posts",
                    params={'per_page': 1},
                    timeout=10
                )
                if public_check.status_code == 200:
                    # API works but auth fails
                    return {
                        'success': False,
                        'error': 'Authentication rejected',
                        'message': 'REST API is accessible but authentication failed. Please check: 1) Application Password is correct (not regular password), 2) Username is correct, 3) No security plugin blocking REST API auth'
                    }
                return {
                    'success': False,
                    'error': 'Access forbidden',
                    'message': 'WordPress is blocking REST API access. Check security plugins like Wordfence or iThemes Security.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Connection test failed ({response.status_code})',
                    'message': response.text[:300]
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Fallback test failed: {str(e)}'
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
        author_id: int = None,
        excerpt: str = None,
        date: str = None,
        meta: dict = None,
        meta_title: str = None,
        focus_keyword: str = None
    ) -> Dict[str, Any]:
        """
        Create a new WordPress post
        
        Args:
            title: Post title
            content: Post content (HTML)
            status: 'draft', 'publish', 'pending', 'private', 'future'
            categories: List of category IDs or names
            tags: List of tag IDs or names
            featured_image_url: URL of image to set as featured
            meta_description: SEO meta description (Yoast/RankMath)
            meta_title: SEO meta title (Yoast/RankMath) - different from post title
            slug: URL slug (auto-generated if not provided)
            author_id: WordPress user ID for author
            excerpt: Post excerpt/summary
            date: Scheduled date for future posts (ISO format)
            meta: Additional meta fields for SEO plugins
        
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
            
            if excerpt:
                post_data['excerpt'] = excerpt
            
            if date and status == 'future':
                post_data['date'] = date.isoformat() if hasattr(date, 'isoformat') else date
            
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
            response = self.session.post(
                f"{self.api_url}/posts",
                json=post_data,
                timeout=30
            )
            self._handle_response(response)
            
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
            
            # Set SEO meta if plugin available (Yoast or RankMath)
            if (meta_title or meta_description or focus_keyword) and post_id:
                seo_result = self._set_seo_meta(
                    post_id, 
                    meta_title=meta_title, 
                    meta_description=meta_description,
                    focus_keyword=focus_keyword
                )
                if seo_result.get('success'):
                    logger.info(f"SEO meta set for post {post_id}")
            
            return {
                'success': True,
                'post_id': post_id,
                'post_url': post.get('link'),
                'url': post.get('link'),
                'edit_url': f"{self.site_url}/wp-admin/post.php?post={post_id}&action=edit",
                'status': post.get('status'),
                'message': f'Published to WordPress successfully'
            }
            
        except Exception as e:
            logger.error(f"WordPress publish error: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'WordPress publish failed: {str(e)}'
            }
    
    def update_post(self, post_id: int, **kwargs) -> Dict[str, Any]:
        """Update an existing post"""
        try:
            response = self.session.post(
                f"{self.api_url}/posts/{post_id}",
                json=kwargs,
                timeout=30
            )
            self._handle_response(response)
            
            if response.status_code == 200:
                post = response.json()
                return {
                    'success': True,
                    'post_id': post_id,
                    'post_url': post.get('link'),
                    'url': post.get('link'),
                    'message': 'WordPress post updated successfully'
                }
            else:
                return {
                    'success': False,
                    'error': f"Update failed: {response.status_code}",
                    'message': f'WordPress update failed with status {response.status_code}'
                }
        except Exception as e:
            return {'success': False, 'error': str(e), 'message': f'WordPress update failed: {str(e)}'}
    
    def _resolve_categories(self, categories: list) -> list:
        """Convert category names to IDs, creating if needed"""
        category_ids = []
        
        for cat in categories:
            if isinstance(cat, int):
                category_ids.append(cat)
            else:
                # Search for category by name
                response = self.session.get(
                    f"{self.api_url}/categories",
                    params={'search': cat},
                    timeout=10
                )
                self._handle_response(response)
                
                if response.status_code == 200:
                    results = response.json()
                    if results:
                        category_ids.append(results[0]['id'])
                    else:
                        # Create category
                        create_response = self.session.post(
                            f"{self.api_url}/categories",
                            json={'name': cat},
                            timeout=10
                        )
                        self._handle_response(create_response)
                        if create_response.status_code in [200, 201]:
                            category_ids.append(create_response.json()['id'])
        
        return category_ids
    
    def _resolve_tags(self, tags: list) -> list:
        """Convert tag names to IDs, creating if needed. Always use Title Case."""
        tag_ids = []
        
        def to_title_case(text):
            """Convert to Title Case, preserving acronyms"""
            if not text:
                return text
            words = text.split()
            result = []
            lowercase_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'by', 'in', 'of'}
            acronyms = {'hvac', 'ac', 'seo', 'usa', 'llc', 'inc'}
            
            for i, word in enumerate(words):
                word_lower = word.lower()
                if word_lower in acronyms:
                    result.append(word.upper())
                elif i == 0 or word_lower not in lowercase_words:
                    result.append(word.capitalize())
                else:
                    result.append(word_lower)
            return ' '.join(result)
        
        for tag in tags:
            if isinstance(tag, int):
                tag_ids.append(tag)
            else:
                # Always use Title Case
                tag_title = to_title_case(tag.strip())
                
                # Search for existing tag
                response = self.session.get(
                    f"{self.api_url}/tags",
                    params={'search': tag_title},
                    timeout=10
                )
                self._handle_response(response)
                
                if response.status_code == 200:
                    results = response.json()
                    # Find exact match (case-insensitive)
                    existing_tag = None
                    for r in results:
                        if r.get('name', '').lower() == tag_title.lower():
                            existing_tag = r
                            break
                    
                    if existing_tag:
                        # If existing tag has wrong case, update it
                        if existing_tag['name'] != tag_title:
                            try:
                                update_resp = self.session.post(
                                    f"{self.api_url}/tags/{existing_tag['id']}",
                                    json={'name': tag_title},
                                    timeout=10
                                )
                                self._handle_response(update_resp)
                                if update_resp.status_code == 200:
                                    logger.info(f"Updated tag case: '{existing_tag['name']}' -> '{tag_title}'")
                            except Exception:
                                pass  # Ignore update errors
                        tag_ids.append(existing_tag['id'])
                    else:
                        # Create new tag with Title Case
                        create_response = self.session.post(
                            f"{self.api_url}/tags",
                            json={'name': tag_title},
                            timeout=10
                        )
                        self._handle_response(create_response)
                        if create_response.status_code in [200, 201]:
                            tag_ids.append(create_response.json()['id'])
                            logger.info(f"Created tag: '{tag_title}'")
        
        return tag_ids
    
    def _set_featured_image(self, post_id: int, image_url: str) -> Dict[str, Any]:
        """Download image and set as featured image"""
        try:
            logger.info(f"Setting featured image for post {post_id} from URL: {image_url}")
            
            if not image_url:
                return {'success': False, 'error': 'No image URL provided'}
            
            # Download image
            img_response = requests.get(image_url, timeout=30)
            if img_response.status_code != 200:
                logger.error(f"Failed to download image: HTTP {img_response.status_code}")
                return {'success': False, 'error': f'Failed to download image: HTTP {img_response.status_code}'}
            
            logger.info(f"Downloaded image: {len(img_response.content)} bytes")
            
            # Determine filename and content type
            filename = image_url.split('/')[-1].split('?')[0]
            if not filename or '.' not in filename:
                filename = 'featured-image.jpg'
            
            content_type = img_response.headers.get('Content-Type', 'image/jpeg')
            
            # Upload to WordPress media library
            # Need fresh headers for binary upload (don't use session JSON headers)
            upload_headers = self.session.headers.copy()
            upload_headers.update({
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': content_type
            })
            # Remove JSON content type if present
            # upload_headers.pop('Content-Type', None) # Actually we set it above
            
            logger.info(f"Uploading image to WordPress: {filename} ({content_type})")
            
            logger.info(f"Uploading image to WordPress: {filename} ({content_type})")
            
            # Use requests.post directly for binary upload to avoid session JSON defaults interfering
            upload_response = self.session.post(
                f"{self.api_url}/media",
                headers=upload_headers,
                data=img_response.content,
                timeout=60
            )
            self._handle_response(upload_response)
            
            if upload_response.status_code not in [200, 201]:
                logger.error(f"Upload failed: HTTP {upload_response.status_code} - {upload_response.text[:200]}")
                return {'success': False, 'error': f'Upload failed: {upload_response.status_code} - {upload_response.text[:100]}'}
            
            media_id = upload_response.json().get('id')
            logger.info(f"Image uploaded, media_id: {media_id}")
            
            # Set as featured image
            update_response = self.session.post(
                f"{self.api_url}/posts/{post_id}",
                json={'featured_media': media_id},
                timeout=10
            )
            self._handle_response(update_response)
            
            if update_response.status_code == 200:
                logger.info(f"Featured image set successfully for post {post_id}")
                return {'success': True, 'media_id': media_id}
            else:
                logger.error(f"Failed to set featured image: HTTP {update_response.status_code}")
                return {'success': False, 'error': f'Failed to set featured image: {update_response.status_code}'}
                
        except Exception as e:
            logger.error(f"Featured image error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _set_seo_meta(self, post_id: int, meta_title: str = None, meta_description: str = None, focus_keyword: str = None) -> Dict[str, Any]:
        """
        Set SEO meta fields for Yoast SEO, RankMath, and All in One SEO
        
        Yoast SEO meta keys:
            _yoast_wpseo_title - SEO Title
            _yoast_wpseo_metadesc - Meta Description
            _yoast_wpseo_focuskw - Focus Keyword
            
        RankMath meta keys:
            rank_math_title - SEO Title
            rank_math_description - Meta Description
            rank_math_focus_keyword - Focus Keyword
            
        All in One SEO meta keys:
            _aioseo_title - SEO Title
            _aioseo_description - Meta Description
        """
        result = {'success': False, 'yoast': False, 'rankmath': False, 'aioseo': False}
        
        try:
            logger.info(f"Setting SEO meta for post {post_id}")
            logger.info(f"  - meta_title: {meta_title[:50] if meta_title else 'None'}...")
            logger.info(f"  - meta_description: {meta_description[:50] if meta_description else 'None'}...")
            logger.info(f"  - focus_keyword: {focus_keyword}")
            
            # Strategy 1: Set via WordPress REST API meta endpoint
            all_meta_fields = {}
            
            # Yoast SEO fields
            if meta_title:
                all_meta_fields['_yoast_wpseo_title'] = meta_title
            if meta_description:
                all_meta_fields['_yoast_wpseo_metadesc'] = meta_description
            if focus_keyword:
                all_meta_fields['_yoast_wpseo_focuskw'] = focus_keyword
            
            # RankMath fields
            if meta_title:
                all_meta_fields['rank_math_title'] = meta_title
            if meta_description:
                all_meta_fields['rank_math_description'] = meta_description
            if focus_keyword:
                all_meta_fields['rank_math_focus_keyword'] = focus_keyword
            
            # All in One SEO fields
            if meta_title:
                all_meta_fields['_aioseo_title'] = meta_title
            if meta_description:
                all_meta_fields['_aioseo_description'] = meta_description
            
            if all_meta_fields:
                logger.info(f"Setting SEO meta fields: {list(all_meta_fields.keys())}")
                
                # Try setting via post meta
                response = self.session.post(
                    f"{self.api_url}/posts/{post_id}",
                    json={'meta': all_meta_fields},
                    timeout=15
                )
                self._handle_response(response)
                
                if response.status_code == 200:
                    result['yoast'] = True
                    result['rankmath'] = True
                    result['aioseo'] = True
                    result['success'] = True
                    logger.info(f"SEO meta set successfully via REST API")
                else:
                    logger.warning(f"SEO meta via REST API failed: {response.status_code}")
                    logger.warning(f"Response: {response.text[:300]}")
                    
                    # Strategy 2: Try setting each field individually
                    for field_name, field_value in all_meta_fields.items():
                        try:
                            individual_response = self.session.post(
                                f"{self.api_url}/posts/{post_id}",
                                json={'meta': {field_name: field_value}},
                                timeout=10
                            )
                            self._handle_response(individual_response)
                            if individual_response.status_code == 200:
                                logger.info(f"Set {field_name} individually")
                                result['success'] = True
                        except Exception as e:
                            logger.warning(f"Failed to set {field_name}: {e}")
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to set SEO meta for post {post_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _set_schema(self, post_id: int, schema_json: str) -> Dict[str, Any]:
        """
        Set schema for 'Schema & Structured Data for WP & AMP' plugin
        
        The plugin uses the meta key: 'saswp_custom_schema_field'
        """
        result = {'success': False}
        
        try:
            if not schema_json:
                return {'success': False, 'error': 'No schema provided'}
            
            # Clean the schema - remove script tags if present
            schema_clean = schema_json
            if '<script' in schema_clean.lower():
                # Extract just the JSON part
                import re
                match = re.search(r'<script[^>]*>(.*?)</script>', schema_clean, re.DOTALL | re.IGNORECASE)
                if match:
                    schema_clean = match.group(1).strip()
            
            # Schema & Structured Data for WP & AMP plugin uses this meta key
            meta_fields = {
                'saswp_custom_schema_field': schema_clean,
                # Also try alternate field names the plugin might use
                '_schema_json': schema_clean,
                'schema_json_ld': schema_clean,
            }
            
            logger.info(f"Setting schema for post {post_id}: {len(schema_clean)} chars")
            
            response = self.session.post(
                f"{self.api_url}/posts/{post_id}",
                json={'meta': meta_fields},
                timeout=15
            )
            self._handle_response(response)
            
            if response.status_code == 200:
                result['success'] = True
                logger.info(f"Schema set for post {post_id}")
            else:
                logger.warning(f"Schema response: {response.status_code} - {response.text[:200]}")
                result['error'] = f"HTTP {response.status_code}"
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to set schema for post {post_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_categories(self) -> list:
        """Get all categories"""
        try:
            response = self.session.get(
                f"{self.api_url}/categories",
                params={'per_page': 100},
                timeout=10
            )
            self._handle_response(response)
            if response.status_code == 200:
                return [{'id': c['id'], 'name': c['name'], 'slug': c['slug']} 
                        for c in response.json()]
            return []
        except Exception as e:
            return []
    
    def get_posts(self, status: str = 'publish', per_page: int = 10) -> list:
        """Get recent posts"""
        try:
            response = self.session.get(
                f"{self.api_url}/posts",
                params={'status': status, 'per_page': per_page},
                timeout=10
            )
            self._handle_response(response)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
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
        
        # Build tags - prefer content tags if available
        tags = []
        if hasattr(content, 'tags') and content.tags:
            # If tags are stored as JSON/list
            tags = content.tags if isinstance(content.tags, list) else json.loads(content.tags)
        
        # Fallback to generating from keyword/location if no tags
        if not tags and content.primary_keyword:
            tags.append(content.primary_keyword.title())
            
        if not tags and client.geo:
            # Extract city from "City, State" string
            city_str = client.geo.split(',')[0].strip()
            if city_str:
                tags.append(city_str.title())
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
            logger.info(f"Sending WordPress publish notifications...")
            email = get_email_service()
            from app.models.db_models import DBUser
            admins = DBUser.query.filter_by(role='admin').all()
            logger.info(f"Found {len(admins)} admin users")
            for admin in admins:
                if admin.email:
                    logger.info(f"Sending WordPress publish email to {admin.email}")
                    try:
                        result_email = email.send_wordpress_published(
                            admin.email,
                            client.business_name,
                            content.title,
                            result.get('url')
                        )
                        logger.info(f"Email result: {result_email}")
                    except Exception as e:
                        logger.error(f"Failed to send WordPress publish email: {e}")
                        import traceback
                        traceback.print_exc()
            
            logger.info(f"Published to WordPress: {content.title} -> {result.get('url')}")
        
        return result


# Singleton
_wp_manager = None

def get_wordpress_manager() -> WordPressManager:
    global _wp_manager
    if _wp_manager is None:
        _wp_manager = WordPressManager()
    return _wp_manager
