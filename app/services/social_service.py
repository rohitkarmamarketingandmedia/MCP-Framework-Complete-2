"""
MCP Framework - Social Service
Google Business Profile, Facebook, Instagram, LinkedIn publishing
"""
import os
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime


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
        cta_url: str = None
    ) -> Dict[str, Any]:
        """
        Publish post to Google Business Profile
        
        Args:
            location_id: GBP location ID
            text: Post content
            image_url: Optional image URL
            cta_type: LEARN_MORE, BOOK, ORDER, SHOP, SIGN_UP, CALL
            cta_url: URL for CTA button
        """
        if not self.gbp_api_key:
            return {'error': 'GBP API key not configured', 'mock': True, 'post_id': 'mock_gbp_123'}
        
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
            
            # GBP API endpoint
            url = f'https://mybusiness.googleapis.com/v4/accounts/{{account_id}}/locations/{location_id}/localPosts'
            
            response = requests.post(
                url,
                headers={
                    'Authorization': f'Bearer {self.gbp_api_key}',
                    'Content-Type': 'application/json'
                },
                json=post_data,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            return {
                'success': True,
                'post_id': result.get('name', '').split('/')[-1],
                'state': result.get('state', 'LIVE')
            }
            
        except requests.RequestException as e:
            return {'error': f'GBP API error: {str(e)}'}
    
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
            return {'error': 'Facebook credentials not configured', 'mock': True, 'post_id': 'mock_fb_123'}
        
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
            
            response = requests.post(endpoint, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            return {
                'success': True,
                'post_id': result.get('id', result.get('post_id', ''))
            }
            
        except requests.RequestException as e:
            return {'error': f'Facebook API error: {str(e)}'}
    
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
            return {'error': 'LinkedIn credentials not configured', 'mock': True, 'post_id': 'mock_li_123'}
        
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
            
            response.raise_for_status()
            
            return {
                'success': True,
                'post_id': response.headers.get('x-restli-id', response.json().get('id', ''))
            }
            
        except requests.RequestException as e:
            return {'error': f'LinkedIn API error: {str(e)}'}
    
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
