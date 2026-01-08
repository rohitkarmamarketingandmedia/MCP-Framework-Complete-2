"""
MCP Framework - Social Service
Google Business Profile, Facebook, Instagram, LinkedIn publishing
"""
import os
import requests
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SocialService:
    """Social media publishing service"""
    
    def __init__(self):
        pass  # API keys read at runtime via properties
    
    @property
    def gbp_api_key(self):
        return os.environ.get('GBP_API_KEY', '')
    
    @property
    def facebook_token(self):
        return os.environ.get('FACEBOOK_ACCESS_TOKEN', '')
    
    @property
    def facebook_page_id(self):
        return os.environ.get('FACEBOOK_PAGE_ID', '')
    
    @property
    def instagram_token(self):
        return os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')
    
    @property
    def linkedin_token(self):
        return os.environ.get('LINKEDIN_ACCESS_TOKEN', '')
    
    def publish_to_gbp(
        self,
        location_id: str,
        text: str,
        image_url: str = None,
        cta_type: str = None,
        cta_url: str = None,
        access_token: str = None,
        account_id: str = None
    ) -> Dict[str, Any]:
        """
        Publish post to Google Business Profile
        
        Args:
            location_id: GBP location ID
            text: Post content
            image_url: Optional image URL
            cta_type: LEARN_MORE, BOOK, ORDER, SHOP, SIGN_UP, CALL
            cta_url: URL for CTA button
            access_token: OAuth access token for GBP
            account_id: GBP account ID
        """
        token = access_token or self.gbp_api_key
        if not token:
            return {'success': False, 'error': 'GBP access token not configured'}
        
        try:
            # Build post data
            post_data = {
                'languageCode': 'en-US',
                'summary': text[:1500],  # GBP limit
                'topicType': 'STANDARD'
            }
            
            # Add CTA if provided
            if cta_type and cta_url:
                post_data['callToAction'] = {
                    'actionType': cta_type,
                    'url': cta_url
                }
            
            # Add media if provided
            if image_url:
                post_data['media'] = {
                    'mediaFormat': 'PHOTO',
                    'sourceUrl': image_url
                }
            
            # Build GBP API URL
            # Google Business Profile has multiple API endpoints:
            # - Old: mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/localPosts
            # - New: mybusinessbusinessinformation.googleapis.com for info
            # - Posting: Use accounts/-/locations/{locationId} with wildcard
            
            # Try with wildcard account first (most compatible)
            if 'accounts/' in str(location_id) and 'locations/' in str(location_id):
                # Already has full path format
                base_path = location_id
            else:
                # Use wildcard account - GBP API supports this for authenticated users
                base_path = f'accounts/-/locations/{location_id}'
            
            url = f'https://mybusiness.googleapis.com/v4/{base_path}/localPosts'
            
            logger.info(f"Publishing to GBP: {url}")
            
            response = requests.post(
                url,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                json=post_data,
                timeout=30
            )
            
            if response.status_code == 401:
                return {'success': False, 'error': 'GBP token expired - please reconnect Google Business'}
            
            if response.status_code == 404:
                return {'success': False, 'error': 'GBP location not found - please reconnect Google Business'}
            
            if not response.ok:
                error_text = response.text[:200]
                logger.error(f"GBP API error {response.status_code}: {error_text}")
                return {'success': False, 'error': f'GBP error: {error_text}'}
            
            result = response.json()
            
            return {
                'success': True,
                'post_id': result.get('name', '').split('/')[-1],
                'state': result.get('state', 'LIVE')
            }
            
        except requests.RequestException as e:
            logger.error(f"GBP publish error: {e}")
            return {'success': False, 'error': f'GBP API error: {str(e)}'}
    
    def publish_to_facebook(
        self,
        page_id: str = None,
        access_token: str = None,
        message: str = '',
        link: str = None,
        image_url: str = None
    ) -> Dict[str, Any]:
        """
        Publish post to Facebook Page
        
        Args:
            page_id: Facebook Page ID
            access_token: Page access token
            message: Post message
            link: URL to share
            image_url: Image URL for photo post
        """
        page_id = page_id or self.facebook_page_id
        access_token = access_token or self.facebook_token
        
        if not page_id or not access_token:
            return {'success': False, 'error': 'Facebook not connected - please reconnect in Settings'}
        
        try:
            if image_url:
                # Photo post
                endpoint = f'https://graph.facebook.com/v18.0/{page_id}/photos'
                data = {
                    'url': image_url,
                    'caption': message,
                    'access_token': access_token
                }
            else:
                # Link or text post
                endpoint = f'https://graph.facebook.com/v18.0/{page_id}/feed'
                data = {
                    'message': message,
                    'access_token': access_token
                }
                if link:
                    data['link'] = link
            
            logger.info(f"Publishing to Facebook page {page_id}")
            response = requests.post(endpoint, data=data, timeout=30)
            
            if response.status_code == 401 or response.status_code == 190:
                return {'success': False, 'error': 'Facebook token expired - please reconnect'}
            
            result = response.json()
            
            if 'error' in result:
                error_msg = result['error'].get('message', 'Unknown error')
                logger.error(f"Facebook API error: {error_msg}")
                return {'success': False, 'error': f'Facebook: {error_msg}'}
            
            response.raise_for_status()
            
            return {
                'success': True,
                'post_id': result.get('id', result.get('post_id', ''))
            }
            
        except requests.RequestException as e:
            logger.error(f"Facebook publish error: {e}")
            return {'success': False, 'error': f'Facebook API error: {str(e)}'}
    
    def publish_to_instagram(
        self,
        account_id: str = None,
        access_token: str = None,
        image_url: str = None,
        caption: str = ''
    ) -> Dict[str, Any]:
        """
        Publish post to Instagram Business Account
        
        Note: Instagram API requires image posts - no text-only posts
        """
        access_token = access_token or self.instagram_token
        
        if not account_id or not access_token:
            return {'error': 'Instagram credentials not configured', 'mock': True, 'post_id': 'mock_ig_123'}
        
        if not image_url:
            return {'error': 'Instagram requires an image URL'}
        
        try:
            # Step 1: Create media container
            container_response = requests.post(
                f'https://graph.facebook.com/v18.0/{account_id}/media',
                data={
                    'image_url': image_url,
                    'caption': caption[:2200],  # IG limit
                    'access_token': access_token
                },
                timeout=30
            )
            
            container_response.raise_for_status()
            container_id = container_response.json().get('id')
            
            # Step 2: Publish container
            publish_response = requests.post(
                f'https://graph.facebook.com/v18.0/{account_id}/media_publish',
                data={
                    'creation_id': container_id,
                    'access_token': access_token
                },
                timeout=30
            )
            
            publish_response.raise_for_status()
            
            return {
                'success': True,
                'post_id': publish_response.json().get('id', '')
            }
            
        except requests.RequestException as e:
            return {'error': f'Instagram API error: {str(e)}'}
    
    def publish_to_linkedin(
        self,
        organization_id: str = None,
        access_token: str = None,
        text: str = '',
        link: str = None,
        link_title: str = None,
        link_description: str = None
    ) -> Dict[str, Any]:
        """Publish post to LinkedIn Company Page"""
        access_token = access_token or self.linkedin_token
        
        if not organization_id or not access_token:
            return {'success': False, 'error': 'LinkedIn not connected - please reconnect in Settings'}
        
        try:
            post_data = {
                'author': f'urn:li:organization:{organization_id}',
                'lifecycleState': 'PUBLISHED',
                'specificContent': {
                    'com.linkedin.ugc.ShareContent': {
                        'shareCommentary': {
                            'text': text[:3000]  # LinkedIn limit
                        },
                        'shareMediaCategory': 'NONE'
                    }
                },
                'visibility': {
                    'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'
                }
            }
            
            # Add link if provided
            if link:
                post_data['specificContent']['com.linkedin.ugc.ShareContent']['shareMediaCategory'] = 'ARTICLE'
                post_data['specificContent']['com.linkedin.ugc.ShareContent']['media'] = [{
                    'status': 'READY',
                    'originalUrl': link,
                    'title': {'text': link_title or ''},
                    'description': {'text': link_description or ''}
                }]
            
            logger.info(f"Publishing to LinkedIn org {organization_id}")
            response = requests.post(
                'https://api.linkedin.com/v2/ugcPosts',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                    'X-Restli-Protocol-Version': '2.0.0'
                },
                json=post_data,
                timeout=30
            )
            
            if response.status_code == 401:
                return {'success': False, 'error': 'LinkedIn token expired - please reconnect'}
            
            if not response.ok:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('message', response.text[:100])
                logger.error(f"LinkedIn API error: {error_msg}")
                return {'success': False, 'error': f'LinkedIn: {error_msg}'}
            
            return {
                'success': True,
                'post_id': response.headers.get('x-restli-id', response.json().get('id', ''))
            }
            
        except requests.RequestException as e:
            logger.error(f"LinkedIn publish error: {e}")
            return {'success': False, 'error': f'LinkedIn API error: {str(e)}'}
    
    def get_gbp_insights(
        self,
        location_id: str,
        metrics: List[str] = None
    ) -> Dict[str, Any]:
        """Get GBP performance insights"""
        if not self.gbp_api_key:
            return self._mock_gbp_insights(location_id)
        
        metrics = metrics or ['QUERIES_DIRECT', 'QUERIES_INDIRECT', 'VIEWS_MAPS', 'VIEWS_SEARCH', 'ACTIONS_WEBSITE', 'ACTIONS_PHONE']
        
        try:
            response = requests.get(
                f'https://mybusiness.googleapis.com/v4/accounts/{{account_id}}/locations/{location_id}/insights',
                headers={'Authorization': f'Bearer {self.gbp_api_key}'},
                params={'metric': metrics},
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            return {'error': f'GBP API error: {str(e)}'}
    
    def _mock_gbp_insights(self, location_id: str) -> Dict:
        """Return mock GBP insights for development"""
        return {
            'location_id': location_id,
            'insights': {
                'views': {'maps': 450, 'search': 1200},
                'actions': {'website': 85, 'phone': 42, 'directions': 65},
                'queries': {'direct': 320, 'discovery': 880}
            },
            'period': 'last_30_days',
            'note': 'Mock data - configure GBP_API_KEY for real data'
        }
