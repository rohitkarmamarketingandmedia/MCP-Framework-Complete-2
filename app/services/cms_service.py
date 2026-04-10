"""
MCP Framework - CMS Service
WordPress and other CMS publishing
"""
import os
import re
import base64
import logging
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Import shared browser headers and SGCaptcha handler from wordpress_service
try:
    from app.services.wordpress_service import BROWSER_HEADERS, handle_sgcaptcha, is_sgcaptcha_response
except ImportError:
    # Fallback if wordpress_service not available
    BROWSER_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/html, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Ch-Ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
    }
    handle_sgcaptcha = None
    is_sgcaptcha_response = lambda r: 'sgcaptcha' in (r.text or '').lower()


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

        # Use a Session for cookie persistence (required for SGCaptcha bypass)
        session = self._create_wp_session(wp_username, wp_password)

        try:
            # Final SEO sanitization before publishing — safety net
            from app.services.html_sanitizer import sanitize_html_for_seo, ensure_h1
            body = sanitize_html_for_seo(body)
            if title:
                body = ensure_h1(body, title)

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
                category_ids = self._get_or_create_categories_session(api_url, session, categories)
                if category_ids:
                    post_data['categories'] = category_ids

            # Handle tags
            if tags:
                tag_ids = self._get_or_create_tags_session(api_url, session, tags)
                if tag_ids:
                    post_data['tags'] = tag_ids

            # Create post (with SGCaptcha handling)
            response = self._wp_request(session, 'POST', f'{api_url}/posts', wp_url, json=post_data)

            # Check for non-JSON responses (WAF, CAPTCHA, empty body, server errors)
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                text = (response.text or '').lower()
                if 'sgcaptcha' in text or '.well-known/sgcaptcha' in text:
                    return {
                        'error': 'SiteGround CAPTCHA is blocking the WordPress API. '
                                 'Whitelist the server IP in SiteGround Site Tools > Security > Access Control, '
                                 'or temporarily disable SG Security Bot Protection.'
                    }
                if 'cloudflare' in text and ('challenge' in text or 'checking your browser' in text):
                    return {
                        'error': 'Cloudflare is blocking the WordPress API. '
                                 'Add the server IP to the Cloudflare firewall allowlist.'
                    }
                return {
                    'error': f'WordPress returned non-JSON response (HTTP {response.status_code}). '
                             f'Content-Type: {content_type}. '
                             f'This usually means a security plugin, firewall, or server error is intercepting the request. '
                             f'Response preview: {(response.text or "")[:300]}'
                }

            response.raise_for_status()

            # Guard against empty JSON body
            if not response.text or not response.text.strip():
                return {
                    'error': f'WordPress returned an empty response (HTTP {response.status_code}). '
                             'The server accepted the request but returned no data. '
                             'Check server error logs and ensure no security plugin is stripping response bodies.'
                }

            try:
                post = response.json()
            except ValueError as json_err:
                return {
                    'error': f'WordPress returned invalid JSON (HTTP {response.status_code}): {json_err}. '
                             f'Response preview: {response.text[:300]}'
                }
            
            post_id = post['id']
            post_url = post['link']
            
            # Upload featured image if provided
            if featured_image_url:
                media_id = self._upload_featured_image_session(
                    api_url, session, featured_image_url, post_id
                )
                if media_id:
                    # Set as featured image
                    self._wp_request(session, 'POST',
                        f'{api_url}/posts/{post_id}', wp_url,
                        json={'featured_media': media_id})

            # Update SEO meta if using Yoast
            if meta_title or meta_description:
                self._update_yoast_meta_session(
                    api_url, session, post_id, meta_title, meta_description, wp_url
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
    
    # ---- Session / SGCaptcha helpers ----

    def _create_wp_session(self, wp_username, wp_password):
        """Create a requests.Session with full browser headers + auth for WordPress"""
        credentials = f'{wp_username}:{wp_password}'
        token = base64.b64encode(credentials.encode()).decode()
        session = requests.Session()
        session.headers.update({
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            **BROWSER_HEADERS,
        })
        return session

    def _wp_request(self, session, method, url, site_url, **kwargs):
        """
        Make a WordPress request with automatic SGCaptcha bypass.
        If SiteGround returns a CAPTCHA challenge, follow it to get the
        cookie, then retry the original request.
        """
        kwargs.setdefault('timeout', 30)
        response = session.request(method, url, **kwargs)

        # Log response details for debugging publish failures
        logger.info(
            f"CMS WP request: {method} {url} -> "
            f"HTTP {response.status_code}, "
            f"Content-Type: {response.headers.get('Content-Type', 'N/A')}, "
            f"Body length: {len(response.text) if response.text else 0}"
        )

        # Check for SGCaptcha and handle it
        if is_sgcaptcha_response(response) and handle_sgcaptcha:
            logger.info("CMS: SGCaptcha detected — attempting bypass")
            result = handle_sgcaptcha(session, response, site_url)
            if result:
                logger.info("CMS: Retrying request after SGCaptcha bypass")
                response = session.request(method, url, **kwargs)
                if is_sgcaptcha_response(response):
                    logger.error("CMS: SGCaptcha still blocking after bypass")
            else:
                logger.error("CMS: SGCaptcha bypass failed")

        return response

    # ---- CRUD methods ----

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
        session = self._create_wp_session(wp_username, wp_password)

        try:
            response = self._wp_request(session, 'POST',
                f'{api_url}/posts/{post_id}', wp_url, json=updates)

            # Validate response before parsing JSON
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                return {
                    'error': f'WordPress returned non-JSON response (HTTP {response.status_code}). '
                             f'A security plugin or firewall may be blocking the request. '
                             f'Response preview: {(response.text or "")[:300]}'
                }

            response.raise_for_status()

            if not response.text or not response.text.strip():
                return {'error': f'WordPress returned an empty response (HTTP {response.status_code}).'}

            try:
                post = response.json()
            except ValueError as json_err:
                return {'error': f'WordPress returned invalid JSON: {json_err}. Preview: {response.text[:300]}'}

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
        session = self._create_wp_session(wp_username, wp_password)

        try:
            response = self._wp_request(session, 'GET',
                f'{api_url}/posts', wp_url,
                params={'per_page': per_page, 'status': status})

            # Validate response before parsing JSON
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                return {
                    'error': f'WordPress returned non-JSON response (HTTP {response.status_code}). '
                             f'A security plugin or firewall may be blocking the request. '
                             f'Response preview: {(response.text or "")[:300]}'
                }

            response.raise_for_status()

            if not response.text or not response.text.strip():
                return {'error': f'WordPress returned an empty response (HTTP {response.status_code}).'}

            try:
                posts = response.json()
            except ValueError as json_err:
                return {'error': f'WordPress returned invalid JSON: {json_err}. Preview: {response.text[:300]}'}

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

    # ---- Session-based helpers (used by publish_to_wordpress) ----

    def _get_or_create_categories_session(self, api_url, session, category_names):
        """Get or create WordPress categories using a session"""
        category_ids = []
        for name in category_names:
            response = session.get(f'{api_url}/categories', params={'search': name}, timeout=15)
            if response.ok:
                categories = response.json()
                if categories:
                    category_ids.append(categories[0]['id'])
                else:
                    create_response = session.post(f'{api_url}/categories', json={'name': name}, timeout=15)
                    if create_response.ok:
                        category_ids.append(create_response.json()['id'])
        return category_ids

    def _get_or_create_tags_session(self, api_url, session, tag_names):
        """Get or create WordPress tags using a session"""
        tag_ids = []
        for name in tag_names:
            response = session.get(f'{api_url}/tags', params={'search': name}, timeout=15)
            if response.ok:
                tags = response.json()
                if tags:
                    tag_ids.append(tags[0]['id'])
                else:
                    create_response = session.post(f'{api_url}/tags', json={'name': name}, timeout=15)
                    if create_response.ok:
                        tag_ids.append(create_response.json()['id'])
        return tag_ids

    def _upload_featured_image_session(self, api_url, session, image_url, post_id):
        """Upload image from URL and return media ID, using a session"""
        try:
            img_response = requests.get(image_url, headers={'User-Agent': BROWSER_HEADERS['User-Agent']}, timeout=30)
            img_response.raise_for_status()

            filename = image_url.split('/')[-1].split('?')[0]
            if '.' not in filename:
                filename = f'image_{post_id}.jpg'

            # For media upload, override Content-Type
            upload_headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': img_response.headers.get('Content-Type', 'image/jpeg'),
            }
            upload_response = session.post(
                f'{api_url}/media',
                headers=upload_headers,
                data=img_response.content,
                timeout=60
            )
            if upload_response.ok:
                return upload_response.json()['id']
        except Exception as e:
            logger.error(f"Featured image upload failed: {e}")
        return None

    def _update_yoast_meta_session(self, api_url, session, post_id, meta_title, meta_description, wp_url):
        """Update Yoast SEO meta fields using a session"""
        try:
            meta_update = {}
            if meta_title:
                meta_update['yoast_wpseo_title'] = meta_title
            if meta_description:
                meta_update['yoast_wpseo_metadesc'] = meta_description
            if meta_update:
                response = self._wp_request(session, 'POST',
                    f'{api_url}/posts/{post_id}', wp_url,
                    json={'meta': meta_update})
                return response.ok
        except Exception:
            pass
        return False

    # ---- Legacy helpers (kept for backward compatibility) ----

    def _get_or_create_categories(self, api_url, headers, category_names):
        """Legacy: Get or create categories with raw headers"""
        session = requests.Session()
        session.headers.update(headers)
        return self._get_or_create_categories_session(api_url, session, category_names)

    def _get_or_create_tags(self, api_url, headers, tag_names):
        """Legacy: Get or create tags with raw headers"""
        session = requests.Session()
        session.headers.update(headers)
        return self._get_or_create_tags_session(api_url, session, tag_names)

    def _upload_featured_image(self, api_url, headers, image_url, post_id):
        """Legacy: Upload featured image with raw headers"""
        session = requests.Session()
        session.headers.update(headers)
        return self._upload_featured_image_session(api_url, session, image_url, post_id)

    def _update_yoast_meta(self, api_url, headers, post_id, meta_title, meta_description):
        """Legacy: Update Yoast meta with raw headers"""
        session = requests.Session()
        session.headers.update(headers)
        return self._update_yoast_meta_session(api_url, session, post_id, meta_title, meta_description, '')
