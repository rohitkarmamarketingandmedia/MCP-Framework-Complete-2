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

# Modern User-Agent to avoid bot detection by security services (SiteGround, Cloudflare, etc.)
# Must be kept up-to-date — hosting providers block outdated browser versions via ModSecurity rules.
# Updated April 2026 to Chrome 136 (current stable).
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'

# Full set of browser-like headers to pass SiteGround/Cloudflare bot detection.
# Missing headers like Accept-Language, Sec-Fetch-* are a common reason for blocks.
BROWSER_HEADERS = {
    'User-Agent': DEFAULT_USER_AGENT,
    'Accept': 'application/json, text/html, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Ch-Ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
}


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


def handle_sgcaptcha(session, response, site_url):
    """
    Handle SiteGround's SGCaptcha challenge.

    SiteGround uses a meta-refresh redirect to /.well-known/sgcaptcha/ which
    sets a cookie upon "visit" and then redirects back. This simulates what a
    real browser does when hitting the challenge.

    Returns the cookie-enriched session (or None if bypass failed).
    """
    try:
        text = response.text

        # Extract the sgcaptcha URL from meta refresh
        # Pattern: content="0;/.well-known/sgcaptcha/?r=...&y=..."
        import re
        match = re.search(r'content="0;(/\.well-known/sgcaptcha/[^"]+)"', text)
        if not match:
            # Try alternate pattern
            match = re.search(r'url=(/\.well-known/sgcaptcha/[^"\'>\s]+)', text, re.IGNORECASE)

        if not match:
            logger.warning("SGCaptcha detected but could not extract challenge URL")
            return None

        captcha_path = match.group(1)
        captcha_url = f"{site_url.rstrip('/')}{captcha_path}"

        logger.info(f"Following SGCaptcha challenge: {captcha_url}")

        # Visit the captcha URL — this should set a cookie
        captcha_response = session.get(
            captcha_url,
            timeout=10,
            allow_redirects=True
        )

        logger.info(f"SGCaptcha response: {captcha_response.status_code}, cookies: {dict(session.cookies)}")

        # Check if we got cookies set
        if session.cookies:
            logger.info(f"SGCaptcha bypass successful — got {len(session.cookies)} cookies")
            return session
        else:
            # Some SG setups return a second redirect or set cookies via headers
            # Check Set-Cookie in response
            if 'Set-Cookie' in captcha_response.headers:
                logger.info("SGCaptcha set cookies via header")
                return session

            logger.warning("SGCaptcha challenge did not set any cookies")
            return None

    except Exception as e:
        logger.error(f"SGCaptcha bypass error: {e}")
        return None


def is_sgcaptcha_response(response):
    """Check if a response is a SiteGround CAPTCHA challenge page"""
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        return False

    text = response.text.lower() if response.text else ''
    return 'sgcaptcha' in text or '.well-known/sgcaptcha' in text


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

        # Create auth header - WordPress uses Basic auth with base64
        credentials = f"{self.username}:{self.app_password}"
        token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')

        # Use a Session to ensure headers are applied to ALL requests
        # The session persists cookies across requests, which is critical for
        # SiteGround's SGCaptcha — it sets a cookie on the challenge page that
        # must be present on subsequent requests.
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            **BROWSER_HEADERS,
        })

        # Track whether we've passed the SGCaptcha challenge
        self._sgcaptcha_resolved = False

        # Keep headers dict for backward compatibility
        self.headers = dict(self.session.headers)

    def _request(self, method, url, **kwargs):
        """
        Make a request with automatic SGCaptcha handling.
        If SiteGround returns a CAPTCHA challenge, we follow it to get the
        cookie, then retry the original request.
        """
        # Set a default timeout
        kwargs.setdefault('timeout', 30)

        logger.info(f"WP _request: {method} {url}")
        response = self.session.request(method, url, **kwargs)
        logger.info(
            f"WP _request response: {method} {url} -> "
            f"HTTP {response.status_code}, "
            f"Content-Type: {response.headers.get('Content-Type', 'N/A')}, "
            f"Body length: {len(response.text) if response.text else 0}"
        )

        # Check for SGCaptcha and handle it
        if is_sgcaptcha_response(response) and not self._sgcaptcha_resolved:
            logger.info("SGCaptcha detected on request — attempting bypass")
            result = handle_sgcaptcha(self.session, response, self.site_url)

            if result:
                self._sgcaptcha_resolved = True
                # Retry the original request with the new cookies
                logger.info(f"Retrying original request after SGCaptcha bypass: {method} {url}")
                response = self.session.request(method, url, **kwargs)

                if is_sgcaptcha_response(response):
                    logger.error("SGCaptcha still blocking after bypass attempt")
                else:
                    logger.info(f"Post-bypass response: {response.status_code}")
            else:
                logger.error("SGCaptcha bypass failed")

        return response

    def _safe_json(self, response, context=''):
        """
        Safely parse JSON from a WordPress response.
        Returns (parsed_data, None) on success, or (None, error_string) on failure.
        Handles empty bodies, HTML responses (WAF/CAPTCHA), and malformed JSON.
        """
        content_type = response.headers.get('Content-Type', '')

        # Check for non-JSON Content-Type (WAF, CAPTCHA, server error page)
        if response.text and 'application/json' not in content_type:
            text_lower = response.text.lower()
            if 'sgcaptcha' in text_lower or '.well-known/sgcaptcha' in text_lower:
                return None, (
                    'SiteGround CAPTCHA is blocking the WordPress API. '
                    'Whitelist the server IP in SiteGround Site Tools > Security > Access Control.'
                )
            if 'cloudflare' in text_lower and ('challenge' in text_lower or 'checking your browser' in text_lower):
                return None, (
                    'Cloudflare is blocking the WordPress API. '
                    'Add the server IP to the Cloudflare firewall allowlist.'
                )
            preview = response.text[:300]
            return None, (
                f'WordPress returned non-JSON response (HTTP {response.status_code}, '
                f'Content-Type: {content_type}). '
                f'A security plugin or firewall may be intercepting. '
                f'Preview: {preview}'
            )

        # Empty body
        if not response.text or not response.text.strip():
            return None, (
                f'WordPress returned an empty response body (HTTP {response.status_code}). '
                f'Context: {context}. '
                'Check server error logs — a security plugin may be stripping responses.'
            )

        # Try to parse
        try:
            return response.json(), None
        except (ValueError, Exception) as e:
            return None, (
                f'WordPress returned invalid JSON (HTTP {response.status_code}): {e}. '
                f'Context: {context}. '
                f'Preview: {response.text[:300]}'
            )

    def test_connection(self) -> Dict[str, Any]:
        """Test the WordPress connection using multiple methods"""
        try:
            # Method 1: Try /users/me endpoint (best for auth testing)
            response = self._request('GET',
                f"{self.api_url}/users/me",
                
                timeout=15
            )
            
            # Check for captcha/challenge page (SiteGround, Cloudflare, etc.)
            content_type = response.headers.get('Content-Type', '')
            
            # Only check for CAPTCHA if we got HTML instead of JSON
            if 'text/html' in content_type and 'application/json' not in content_type:
                text = response.text.lower()
                
                # SiteGround CAPTCHA detection - check for sgcaptcha patterns
                is_sg_captcha = (
                    'sgcaptcha' in text or
                    'sg-captcha-form' in text or
                    '.well-known/sgcaptcha' in text
                )

                if is_sg_captcha:
                    # The _request() method already tried to bypass SGCaptcha,
                    # so if we're still here it means the bypass failed.
                    return {
                        'success': False,
                        'error': 'SiteGround CAPTCHA detected',
                        'message': 'SiteGround security is blocking API access. Please whitelist the server IP in SiteGround Site Tools > Security > Access Control > Allow IP, or temporarily disable SG Security plugin Bot Protection.',
                        'response_preview': response.text[:500]
                    }
                
                # Cloudflare challenge detection - specific patterns
                is_cloudflare = (
                    'checking your browser' in text or 
                    'cf-browser-verification' in text or
                    'cloudflare' in text and 'challenge' in text
                )
                
                if is_cloudflare:
                    return {
                        'success': False,
                        'error': 'Cloudflare security blocking API access',
                        'message': 'Cloudflare protection is blocking access. Add the server IP to Cloudflare firewall allowlist or create a WAF rule to allow API access.',
                        'response_preview': response.text[:500]
                    }
                
                # If we got HTML but no specific CAPTCHA detected, it might be another issue
                # Log it for debugging but don't assume CAPTCHA
                if response.status_code != 200:
                    logger.warning(f"Received HTML response (status {response.status_code}) instead of JSON. Preview: {response.text[:300]}")
            
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
    
    def diagnose_connection(self) -> Dict[str, Any]:
        """
        Detailed diagnostic of WordPress connection - useful for debugging
        Returns raw response info to help identify blocking issues
        """
        results = {
            'site_url': self.site_url,
            'api_url': self.api_url,
            'tests': []
        }
        
        # Create a separate session for no-auth tests (full browser headers but no Authorization)
        noauth_session = requests.Session()
        noauth_session.headers.update(BROWSER_HEADERS)
        
        # Test 1: Basic site access (no auth)
        try:
            response = noauth_session.get(self.site_url, timeout=10, allow_redirects=True)
            results['tests'].append({
                'name': 'Site Access (no auth)',
                'url': self.site_url,
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'final_url': response.url,
                'response_preview': response.text[:300] if response.text else None
            })
        except Exception as e:
            results['tests'].append({
                'name': 'Site Access (no auth)',
                'error': str(e)
            })
        
        # Test 2: REST API discovery (no auth)
        try:
            response = noauth_session.get(f"{self.site_url}/wp-json/", timeout=10)
            results['tests'].append({
                'name': 'REST API Discovery (no auth)',
                'url': f"{self.site_url}/wp-json/",
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'is_json': 'application/json' in response.headers.get('Content-Type', ''),
                'response_preview': response.text[:300] if response.text else None
            })
        except Exception as e:
            results['tests'].append({
                'name': 'REST API Discovery (no auth)',
                'error': str(e)
            })
        
        # Test 3: Posts endpoint (no auth)
        try:
            response = noauth_session.get(f"{self.api_url}/posts", params={'per_page': 1}, timeout=10)
            results['tests'].append({
                'name': 'Posts Endpoint (no auth)',
                'url': f"{self.api_url}/posts",
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'is_json': 'application/json' in response.headers.get('Content-Type', ''),
                'response_preview': response.text[:300] if response.text else None
            })
        except Exception as e:
            results['tests'].append({
                'name': 'Posts Endpoint (no auth)',
                'error': str(e)
            })
        
        # Test 4: Users/me endpoint (with auth)
        try:
            response = self._request('GET',
                f"{self.api_url}/users/me",
                
                timeout=10
            )
            results['tests'].append({
                'name': 'Users/Me Endpoint (with auth)',
                'url': f"{self.api_url}/users/me",
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'is_json': 'application/json' in response.headers.get('Content-Type', ''),
                'response_preview': response.text[:500] if response.text else None,
                'headers_sent': {k: v for k, v in self.headers.items() if k != 'Authorization'}
            })
        except Exception as e:
            results['tests'].append({
                'name': 'Users/Me Endpoint (with auth)',
                'error': str(e)
            })
        
        # Test 5: POST to posts endpoint (with auth) - dry run check
        try:
            response = self._request('POST',
                f"{self.api_url}/posts",
                
                json={'title': 'Connection Test - DELETE ME', 'content': 'Test', 'status': 'draft'},
                timeout=15
            )
            results['tests'].append({
                'name': 'POST to Posts (with auth)',
                'url': f"{self.api_url}/posts",
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'is_json': 'application/json' in response.headers.get('Content-Type', ''),
                'response_preview': response.text[:500] if response.text else None
            })
            
            # If we created a test post, delete it
            if response.status_code == 201:
                try:
                    post_data = response.json()
                    post_id = post_data.get('id')
                    if post_id:
                        delete_response = self._request('DELETE',
                            f"{self.api_url}/posts/{post_id}",
                            
                            params={'force': True},
                            timeout=10
                        )
                        results['tests'][-1]['cleanup'] = f"Deleted test post {post_id}"
                except:
                    pass
                    
        except Exception as e:
            results['tests'].append({
                'name': 'POST to Posts (with auth)',
                'error': str(e)
            })
        
        # Analyze results
        results['diagnosis'] = self._analyze_diagnostic_results(results['tests'])
        
        return results
    
    def _analyze_diagnostic_results(self, tests: list) -> str:
        """Analyze diagnostic test results and provide recommendations"""
        issues = []
        
        for test in tests:
            if 'error' in test:
                issues.append(f"- {test['name']}: Connection error - {test['error']}")
                continue
                
            status = test.get('status_code')
            content_type = test.get('content_type', '')
            is_json = test.get('is_json', False)
            preview = test.get('response_preview', '').lower()
            
            # Check for HTML when JSON expected
            if 'with auth' in test['name'] and not is_json and status != 200:
                if 'sgcaptcha' in preview or 'sg-captcha' in preview:
                    issues.append(f"- {test['name']}: SiteGround CAPTCHA detected in response")
                elif 'cloudflare' in preview:
                    issues.append(f"- {test['name']}: Cloudflare protection detected")
                elif 'text/html' in content_type:
                    issues.append(f"- {test['name']}: Got HTML instead of JSON (possible error page or WAF)")
            
            if status == 401:
                issues.append(f"- {test['name']}: Authentication failed (401)")
            elif status == 403:
                issues.append(f"- {test['name']}: Access forbidden (403) - check security plugins")
            elif status == 404:
                issues.append(f"- {test['name']}: Endpoint not found (404) - REST API may be disabled")
            elif status == 500:
                issues.append(f"- {test['name']}: Server error (500)")
        
        if not issues:
            return "All tests passed. Connection should work."
        
        return "Issues found:\n" + "\n".join(issues)
    
    def _test_connection_fallback(self) -> Dict[str, Any]:
        """Fallback connection test using posts endpoint with edit context"""
        try:
            # Try to access posts with edit context (requires auth)
            response = self._request('GET',
                f"{self.api_url}/posts",
                
                params={'per_page': 1, 'context': 'edit'},
                timeout=15
            )
            
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
                public_check = self._request('GET',
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
            response = self._request('POST',
                f"{self.api_url}/posts",
                
                json=post_data,
                timeout=30
            )
            
            # Log response details for debugging
            logger.info(
                f"WP create_post response: HTTP {response.status_code}, "
                f"Content-Type: {response.headers.get('Content-Type', 'N/A')}, "
                f"Body length: {len(response.text) if response.text else 0}"
            )

            # Use safe JSON parsing — handles empty body, HTML/CAPTCHA, malformed JSON
            post, json_err = self._safe_json(response, 'create_post')
            if json_err:
                # If we also got an error status code, include it
                if response.status_code not in [200, 201]:
                    return {
                        'success': False,
                        'error': f'Failed to create post (HTTP {response.status_code})',
                        'message': json_err
                    }
                return {
                    'success': False,
                    'error': 'Invalid response from WordPress',
                    'message': json_err
                }

            # Check HTTP status for JSON error responses
            if response.status_code not in [200, 201]:
                error_msg = post.get('message', str(post)) if isinstance(post, dict) else str(post)
                return {
                    'success': False,
                    'error': f"Failed to create post: {response.status_code}",
                    'message': error_msg
                }
            
            post_id = post.get('id')
            
            # Upload and set featured image if provided
            if featured_image_url and post_id:
                logger.info(f"Attempting to set featured image for post {post_id}")
                logger.info(f"Featured image URL: {featured_image_url}")
                image_result = self._set_featured_image(post_id, featured_image_url)
                if not image_result.get('success'):
                    logger.warning(f"Failed to set featured image: {image_result.get('error')}")
                else:
                    logger.info(f"Featured image set successfully: media_id={image_result.get('media_id')}")
            elif not featured_image_url:
                logger.info(f"No featured_image_url provided for post {post_id}")
            
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
            response = self._request('POST',
                f"{self.api_url}/posts/{post_id}",
                
                json=kwargs,
                timeout=30
            )
            
            # Check for CAPTCHA/WAF response - only on error status
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type and 'application/json' not in content_type and response.status_code != 200:
                text = response.text.lower()
                if 'sgcaptcha' in text and 'form' in text:
                    return {
                        'success': False,
                        'error': 'SiteGround CAPTCHA blocking API',
                        'message': 'SiteGround security is blocking the request. Whitelist the server IP in SiteGround Site Tools > Security.'
                    }
            
            # Safe JSON parsing for update response
            data, json_err = self._safe_json(response, 'update_post')

            if response.status_code == 200:
                if json_err:
                    return {
                        'success': False,
                        'error': 'Invalid response',
                        'message': json_err
                    }
                return {
                    'success': True,
                    'post_id': post_id,
                    'post_url': data.get('link'),
                    'url': data.get('link'),
                    'message': 'WordPress post updated successfully'
                }
            else:
                error_msg = data.get('message', str(data)) if isinstance(data, dict) else (json_err or f'HTTP {response.status_code}')
                return {
                    'success': False,
                    'error': f"Update failed: {response.status_code}",
                    'message': error_msg
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
                try:
                    # Search for category by name
                    response = self._request('GET',
                        f"{self.api_url}/categories",
                        params={'search': cat},
                        timeout=10
                    )

                    if response.status_code == 200:
                        results, err = self._safe_json(response, f'search category "{cat}"')
                        if err:
                            logger.warning(f"Failed to search category '{cat}': {err}")
                            continue
                        if results:
                            category_ids.append(results[0]['id'])
                        else:
                            # Create category
                            create_response = self._request('POST',
                                f"{self.api_url}/categories",
                                json={'name': cat},
                                timeout=10
                            )
                            if create_response.status_code in [200, 201]:
                                data, err = self._safe_json(create_response, f'create category "{cat}"')
                                if data:
                                    category_ids.append(data['id'])
                                else:
                                    logger.warning(f"Failed to create category '{cat}': {err}")
                except Exception as e:
                    logger.warning(f"Failed to resolve category '{cat}': {e}")

        return category_ids
    
    def _resolve_tags(self, tags: list) -> list:
        """Convert tag names to IDs, creating if needed"""
        tag_ids = []

        for tag in tags:
            if isinstance(tag, int):
                tag_ids.append(tag)
            else:
                try:
                    response = self._request('GET',
                        f"{self.api_url}/tags",
                        params={'search': tag},
                        timeout=10
                    )

                    if response.status_code == 200:
                        results, err = self._safe_json(response, f'search tag "{tag}"')
                        if err:
                            logger.warning(f"Failed to search tag '{tag}': {err}")
                            continue
                        if results:
                            tag_ids.append(results[0]['id'])
                        else:
                            # Create tag
                            create_response = self._request('POST',
                                f"{self.api_url}/tags",
                                json={'name': tag},
                                timeout=10
                            )
                            if create_response.status_code in [200, 201]:
                                data, err = self._safe_json(create_response, f'create tag "{tag}"')
                                if data:
                                    tag_ids.append(data['id'])
                                else:
                                    logger.warning(f"Failed to create tag '{tag}': {err}")
                except Exception as e:
                    logger.warning(f"Failed to resolve tag '{tag}': {e}")

        return tag_ids
    
    def _set_featured_image(self, post_id: int, image_url: str) -> Dict[str, Any]:
        """Download image and set as featured image"""
        try:
            logger.info(f"Setting featured image for post {post_id} from URL: {image_url}")
            
            if not image_url:
                return {'success': False, 'error': 'No image URL provided'}
            
            # Determine filename from URL
            filename = image_url.split('/')[-1].split('?')[0]
            if not filename or '.' not in filename:
                filename = 'featured-image.jpg'
            
            # Download image with Chrome 145 User-Agent (required by SiteGround)
            headers = {
                'User-Agent': DEFAULT_USER_AGENT,
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            logger.info(f"Downloading image with Chrome 145 User-Agent...")
            img_response = requests.get(image_url, headers=headers, timeout=30)
            
            logger.info(f"Response: HTTP {img_response.status_code}, {len(img_response.content)} bytes")
            
            if img_response.status_code != 200:
                logger.error(f"Failed to download image: HTTP {img_response.status_code}")
                # Check if it's a SiteGround CAPTCHA
                if 'sgcaptcha' in img_response.text.lower() or img_response.headers.get('SG-Captcha'):
                    logger.error("SiteGround CAPTCHA still blocking - User-Agent may need update")
                return {'success': False, 'error': f'Failed to download image: HTTP {img_response.status_code}'}
            
            if len(img_response.content) < 5000:
                logger.error(f"Downloaded content too small: {len(img_response.content)} bytes")
                return {'success': False, 'error': f'Downloaded content too small: {len(img_response.content)} bytes'}
            
            image_content = img_response.content
            content_type = img_response.headers.get('Content-Type', 'image/jpeg')
            
            logger.info(f"Downloaded image: {len(image_content)} bytes")
            
            # Ensure content type is valid
            if not content_type or not content_type.startswith('image/'):
                content_type = 'image/jpeg'
            
            # Upload to WordPress media library
            upload_headers = {
                'Authorization': self.headers['Authorization'],
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': content_type
            }
            
            logger.info(f"Uploading image to WordPress: {filename} ({content_type}, {len(image_content)} bytes)")
            
            upload_response = requests.post(
                f"{self.api_url}/media",
                headers=upload_headers,
                data=image_content,
                timeout=60
            )
            
            if upload_response.status_code not in [200, 201]:
                logger.error(f"Upload failed: HTTP {upload_response.status_code} - {upload_response.text[:200]}")
                return {'success': False, 'error': f'Upload failed: {upload_response.status_code} - {upload_response.text[:100]}'}
            
            media_data, img_json_err = self._safe_json(upload_response, 'upload featured image')
            if img_json_err:
                logger.error(f"Featured image upload returned invalid JSON: {img_json_err}")
                return {'success': False, 'error': f'Featured image upload failed: {img_json_err}'}
            media_id = media_data.get('id')
            logger.info(f"Image uploaded, media_id: {media_id}")
            
            # Set as featured image
            update_response = requests.post(
                f"{self.api_url}/posts/{post_id}",
                headers=self.headers,
                json={'featured_media': media_id},
                timeout=10
            )
            
            if update_response.status_code == 200:
                logger.info(f"Featured image set successfully for post {post_id}")
                return {'success': True, 'media_id': media_id}
            else:
                logger.error(f"Failed to set featured image: HTTP {update_response.status_code}")
                return {'success': False, 'error': f'Failed to set featured image: {update_response.status_code}'}
                
        except Exception as e:
            logger.error(f"Featured image error: {str(e)}")
            import traceback
            traceback.print_exc()
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
            
            # Build meta fields for all SEO plugins
            yoast_meta = {}
            if meta_title:
                yoast_meta['_yoast_wpseo_title'] = meta_title
            if meta_description:
                yoast_meta['_yoast_wpseo_metadesc'] = meta_description
            if focus_keyword:
                yoast_meta['_yoast_wpseo_focuskw'] = focus_keyword
            
            rankmath_meta = {}
            if meta_title:
                rankmath_meta['rank_math_title'] = meta_title
            if meta_description:
                rankmath_meta['rank_math_description'] = meta_description
            if focus_keyword:
                rankmath_meta['rank_math_focus_keyword'] = focus_keyword
            
            aioseo_meta = {}
            if meta_title:
                aioseo_meta['_aioseo_title'] = meta_title
            if meta_description:
                aioseo_meta['_aioseo_description'] = meta_description
            
            # Combine all meta fields
            all_meta = {**yoast_meta, **rankmath_meta, **aioseo_meta}
            
            if not all_meta:
                logger.info("No SEO meta fields to set")
                return result
            
            logger.info(f"Setting SEO meta fields: {list(all_meta.keys())}")
            
            # APPROACH 1: Try Yoast REST API endpoint (if available)
            # Yoast Premium and some versions expose /wp-json/yoast/v1/
            try:
                yoast_data = {}
                if meta_title:
                    yoast_data['title'] = meta_title
                if meta_description:
                    yoast_data['description'] = meta_description
                if focus_keyword:
                    yoast_data['focuskw'] = focus_keyword
                
                if yoast_data:
                    yoast_response = self._request('POST',
                        f"{self.site_url}/wp-json/yoast/v1/posts/{post_id}",
                        json=yoast_data,
                        timeout=10
                    )
                    if yoast_response.status_code == 200:
                        result['yoast'] = True
                        result['success'] = True
                        logger.info("Yoast meta set via Yoast REST API")
            except Exception as e:
                logger.debug(f"Yoast REST API not available: {e}")
            
            # APPROACH 2: Try setting via WordPress post meta endpoint
            try:
                response = self._request('POST',
                    f"{self.api_url}/posts/{post_id}",
                    json={'meta': all_meta},
                    timeout=15
                )
                
                if response.status_code == 200:
                    result['success'] = True
                    logger.info(f"SEO meta set via REST API meta field")
                    
                    # Verify the meta was actually set
                    verify_response = self._request('GET',
                        f"{self.api_url}/posts/{post_id}",
                        params={'context': 'edit'},
                        timeout=10
                    )
                    if verify_response.status_code == 200:
                        post_data = verify_response.json()
                        post_meta = post_data.get('meta', {})
                        if post_meta.get('_yoast_wpseo_focuskw') or post_meta.get('_yoast_wpseo_metadesc'):
                            result['yoast'] = True
                            logger.info("Verified: Yoast meta fields are set")
                        else:
                            logger.warning("Meta fields sent but not visible in response - Yoast may not expose them via REST")
                else:
                    logger.warning(f"SEO meta via REST API failed: {response.status_code}")
                    logger.warning(f"Response: {response.text[:300]}")
            except Exception as e:
                logger.warning(f"REST API meta approach failed: {e}")
            
            # APPROACH 3: Try custom REST fields (if yoast-rest-api-fix.php is installed)
            if not result.get('yoast'):
                try:
                    custom_fields = {}
                    if meta_title:
                        custom_fields['yoast_title'] = meta_title
                    if meta_description:
                        custom_fields['yoast_metadesc'] = meta_description
                    if focus_keyword:
                        custom_fields['yoast_focuskw'] = focus_keyword
                    
                    if custom_fields:
                        custom_response = self._request('POST',
                            f"{self.api_url}/posts/{post_id}",
                            json=custom_fields,
                            timeout=10
                        )
                        if custom_response.status_code == 200:
                            result['yoast'] = True
                            result['success'] = True
                            logger.info("Yoast meta set via custom REST fields")
                except Exception as e:
                    logger.debug(f"Custom REST fields approach failed: {e}")
            
            # APPROACH 4: Try individual field updates (some hosts have size limits)
            if not result['success']:
                logger.info("Trying individual field updates...")
                for field_name, field_value in all_meta.items():
                    try:
                        individual_response = self._request('POST',
                            f"{self.api_url}/posts/{post_id}",
                            json={'meta': {field_name: field_value}},
                            timeout=10
                        )
                        if individual_response.status_code == 200:
                            logger.info(f"Set {field_name} individually")
                            result['success'] = True
                            if 'yoast' in field_name:
                                result['yoast'] = True
                            if 'rank_math' in field_name:
                                result['rankmath'] = True
                    except Exception as e:
                        logger.warning(f"Failed to set {field_name}: {e}")
            
            # Log final result
            if result['success']:
                logger.info(f"SEO meta setting completed. Yoast: {result['yoast']}, RankMath: {result['rankmath']}")
            else:
                logger.warning("All SEO meta approaches failed. You may need to:")
                logger.warning("1. Install 'Yoast SEO REST API' addon, OR")
                logger.warning("2. Add code to register meta fields with show_in_rest=true, OR")
                logger.warning("3. Manually set meta in WordPress admin")
            
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
            
            response = self._request('POST',
                f"{self.api_url}/posts/{post_id}",
                
                json={'meta': meta_fields},
                timeout=15
            )
            
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
            response = self._request('GET',
                f"{self.api_url}/categories",
                
                params={'per_page': 100},
                timeout=10
            )
            if response.status_code == 200:
                return [{'id': c['id'], 'name': c['name'], 'slug': c['slug']} 
                        for c in response.json()]
            return []
        except Exception as e:
            return []
    
    def get_posts(self, status: str = 'publish', per_page: int = 10) -> list:
        """Get recent posts"""
        try:
            response = self._request('GET',
                f"{self.api_url}/posts",
                
                params={'status': status, 'per_page': per_page},
                timeout=10
            )
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
        
        # Build proper tags - service type + location
        tags = []
        if content.primary_keyword:
            # Extract service type from keyword (e.g., "AC Repair" from "AC Repair Port Charlotte")
            keyword = content.primary_keyword.strip()
            
            # Common service keywords to extract
            service_keywords = [
                'AC Repair', 'AC Installation', 'AC Maintenance', 'AC Service',
                'HVAC Repair', 'HVAC Installation', 'HVAC Maintenance', 'HVAC Service',
                'Heating Repair', 'Heating Installation', 'Heating Maintenance',
                'Air Conditioning', 'Furnace Repair', 'Heat Pump',
                'Duct Cleaning', 'Thermostat', 'Indoor Air Quality'
            ]
            
            # Find matching service type
            keyword_lower = keyword.lower()
            for service in service_keywords:
                if service.lower() in keyword_lower:
                    tags.append(service)
                    break
            
            # Add the full keyword as a tag
            tags.append(keyword)
        
        # Add city as tag
        if client.geo:
            city = client.geo.split(',')[0].strip()
            tags.append(city)
            # Add "City + Service" combo tag if we have both
            if tags and len(tags) > 0:
                service_tag = tags[0] if tags[0] != keyword else None
                if service_tag:
                    tags.append(f"{service_tag} {city}")
        
        # Remove duplicates and limit
        seen = set()
        unique_tags = []
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in seen and len(tag) > 2:
                seen.add(tag_lower)
                unique_tags.append(tag)
        tags = unique_tags[:8]
        
        # Use body field (DBContentQueue uses 'body' not 'content')
        post_body = content.body or ''
        
        # Generate SEO-friendly slug from keyword
        slug = None
        if content.primary_keyword:
            slug = re.sub(r'[^a-z0-9]+', '-', content.primary_keyword.lower()).strip('-')[:60]
        
        # Get featured image URL if available
        featured_image = getattr(content, 'featured_image_url', None) or getattr(content, 'image_url', None)
        
        # Use content.title for WordPress post title (this is the blog title)
        # Use content.meta_title for Yoast SEO title
        post_title = content.title
        seo_title = content.meta_title if content.meta_title else content.title
        
        # Publish with full SEO data including Yoast fields
        result = wp.create_post(
            title=post_title,  # Blog post title
            content=post_body,
            status='publish',
            categories=categories if categories else None,
            tags=tags if tags else None,
            meta_description=content.meta_description,
            meta_title=seo_title,  # Yoast SEO title
            focus_keyword=content.primary_keyword,  # Set Yoast focus keyword
            featured_image_url=featured_image,
            slug=slug
        )
        
        if result.get('success'):
            # Update content queue
            content.status = 'published'
            content.published_at = datetime.utcnow()
            content.published_url = result.get('url')
            content.wordpress_post_id = result.get('post_id')
            
            # Also save as blog post (use 'body' not 'content')
            from app.routes.content import _generate_blog_tags
            wp_client = DBClient.query.get(client_id)
            wp_geo = (wp_client.geo or '') if wp_client else ''
            wp_city = wp_geo.split(',')[0].strip() if wp_geo else ''
            
            blog = DBBlogPost(
                client_id=client_id,
                title=content.title,
                primary_keyword=content.primary_keyword,
                body=post_body,
                meta_title=content.meta_title,
                meta_description=content.meta_description,
                status='published',
                word_count=content.word_count,
                seo_score=content.our_seo_score,
                target_city=wp_city,
                tags=_generate_blog_tags(content.primary_keyword, city=wp_city, industry=wp_client.industry if wp_client else '')
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
