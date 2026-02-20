"""
MCP Framework - Google Business Profile Integration
Post updates, manage Q&A, and handle reviews via GBP API
"""
import logging
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class GBPService:
    """
    Google Business Profile API Integration
    
    Requires:
    - GBP_CLIENT_ID
    - GBP_CLIENT_SECRET
    - GBP_REFRESH_TOKEN (per client, stored in client record)
    
    API Documentation: https://developers.google.com/my-business/reference/rest
    """
    
    def __init__(self):
        self.client_id = os.getenv('GBP_CLIENT_ID')
        self.client_secret = os.getenv('GBP_CLIENT_SECRET')
        # New v1 APIs (v4 mybusiness.googleapis.com is deprecated/removed)
        self.account_api = 'https://mybusinessaccountmanagement.googleapis.com/v1'
        self.business_info_api = 'https://mybusinessbusinessinformation.googleapis.com/v1'
        self.reviews_api = 'https://mybusiness.googleapis.com/v4'  # Reviews still on v4 for reply
        # Keep for backwards compat in code that references api_base
        self.api_base = self.reviews_api
        self.api_base_v1 = self.business_info_api
    
    def is_configured(self) -> bool:
        """Check if GBP API is configured"""
        return bool(self.client_id and self.client_secret)
    
    # ==========================================
    # Authentication
    # ==========================================
    
    def get_auth_url(self, redirect_uri: str, state: str = '') -> str:
        """
        Get OAuth authorization URL for user to grant access
        """
        if not self.is_configured():
            return None
        
        scopes = [
            'https://www.googleapis.com/auth/business.manage'
        ]
        
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state
        }
        
        query = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    
    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens
        """
        import requests
        
        try:
            response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': redirect_uri
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Token exchange failed: {response.text}")
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return {'error': str(e)}
    
    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token
        """
        import requests
        
        try:
            response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': refresh_token,
                    'grant_type': 'refresh_token'
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Token refresh failed: {response.text}")
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return {'error': str(e)}
    
    def _get_headers(self, access_token: str) -> Dict[str, str]:
        """Get API request headers"""
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    
    # ==========================================
    # Account & Location Management
    # ==========================================
    
    def get_accounts(self, access_token: str) -> Dict[str, Any]:
        """
        Get all GBP accounts the user has access to
        Uses: mybusinessaccountmanagement.googleapis.com/v1/accounts
        """
        import requests
        
        try:
            response = requests.get(
                f'{self.account_api}/accounts',
                headers=self._get_headers(access_token)
            )
            
            logger.info(f"GBP get_accounts: status={response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GBP get_accounts error: {response.status_code} - {response.text[:300]}")
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get accounts error: {e}")
            return {'error': str(e)}
    
    def get_locations(self, access_token: str, account_id: str) -> Dict[str, Any]:
        """
        Get all locations for an account
        Uses: mybusinessbusinessinformation.googleapis.com/v1/accounts/{id}/locations
        account_id: just the account name like 'accounts/123456'
        """
        import requests
        
        try:
            # The account_id may or may not include 'accounts/' prefix
            account_path = account_id if account_id.startswith('accounts/') else f'accounts/{account_id}'
            
            response = requests.get(
                f'{self.business_info_api}/{account_path}/locations',
                headers=self._get_headers(access_token),
                params={'readMask': 'name,title,storefrontAddress'}
            )
            
            logger.info(f"GBP get_locations: status={response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GBP get_locations error: {response.status_code} - {response.text[:300]}")
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get locations error: {e}")
            return {'error': str(e)}
    
    def get_location(self, access_token: str, location_name: str) -> Dict[str, Any]:
        """
        Get details for a specific location
        location_name format: locations/{location_id}
        """
        import requests
        
        try:
            response = requests.get(
                f'{self.business_info_api}/{location_name}',
                headers=self._get_headers(access_token),
                params={'readMask': 'name,title,storefrontAddress,websiteUri'}
            )
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get location error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # Posts (Local Posts / Updates)
    # ==========================================
    
    def create_post(
        self,
        access_token: str,
        location_name: str,
        post_type: str,
        summary: str,
        call_to_action: Optional[Dict] = None,
        media: Optional[List[Dict]] = None,
        event: Optional[Dict] = None,
        offer: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a local post on GBP
        
        Args:
            access_token: OAuth access token
            location_name: Full location name (accounts/xxx/locations/xxx)
            post_type: STANDARD, EVENT, OFFER, PRODUCT
            summary: Post text (max 1500 chars for STANDARD)
            call_to_action: {actionType: "LEARN_MORE", url: "https://..."}
            media: [{mediaFormat: "PHOTO", sourceUrl: "https://..."}]
            event: {title, schedule: {startDate, endDate}}
            offer: {couponCode, redeemOnlineUrl, termsConditions}
        """
        import requests
        
        try:
            post_data = {
                'languageCode': 'en-US',
                'summary': summary[:1500],
                'topicType': post_type
            }
            
            if call_to_action:
                post_data['callToAction'] = call_to_action
            
            if media:
                post_data['media'] = media
            
            if event and post_type == 'EVENT':
                post_data['event'] = event
            
            if offer and post_type == 'OFFER':
                post_data['offer'] = offer
            
            response = requests.post(
                f'{self.api_base}/{location_name}/localPosts',
                headers=self._get_headers(access_token),
                json=post_data
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"GBP post created for {location_name}")
                return {'success': True, 'post': response.json()}
            else:
                logger.error(f"GBP post failed: {response.text}")
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Create post error: {e}")
            return {'error': str(e)}
    
    def get_posts(self, access_token: str, location_name: str) -> Dict[str, Any]:
        """
        Get all posts for a location
        """
        import requests
        
        try:
            response = requests.get(
                f'{self.api_base}/{location_name}/localPosts',
                headers=self._get_headers(access_token)
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get posts error: {e}")
            return {'error': str(e)}
    
    def delete_post(self, access_token: str, post_name: str) -> Dict[str, Any]:
        """
        Delete a local post
        """
        import requests
        
        try:
            response = requests.delete(
                f'{self.api_base}/{post_name}',
                headers=self._get_headers(access_token)
            )
            
            if response.status_code in [200, 204]:
                return {'success': True}
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Delete post error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # Reviews
    # ==========================================
    
    def get_reviews(
        self, 
        access_token: str, 
        location_name: str,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Get reviews for a location
        Tries Account Management API pattern first
        location_name: e.g. 'accounts/123/locations/456' or 'locations/456'
        """
        import requests
        
        try:
            # Try the v4 endpoint (still works for reviews for some accounts)
            response = requests.get(
                f'{self.reviews_api}/{location_name}/reviews',
                headers=self._get_headers(access_token),
                params={'pageSize': page_size}
            )
            
            logger.info(f"GBP get_reviews: status={response.status_code} for {location_name}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"GBP get_reviews v4 failed: {response.status_code} - {response.text[:200]}")
                return {'error': response.text, 'reviews': []}
                
        except Exception as e:
            logger.error(f"Get reviews error: {e}")
            return {'error': str(e), 'reviews': []}
    
    def reply_to_review(
        self, 
        access_token: str, 
        review_name: str,
        comment: str
    ) -> Dict[str, Any]:
        """
        Reply to a review
        review_name: full path like 'accounts/123/locations/456/reviews/789'
        """
        import requests
        
        try:
            url = f'{self.reviews_api}/{review_name}/reply'
            logger.info(f"GBP reply_to_review: PUT {url}")
            
            response = requests.put(
                url,
                headers=self._get_headers(access_token),
                json={'comment': comment}
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully replied to review {review_name}")
                return {'success': True, 'reply': response.json()}
            else:
                logger.error(f"GBP reply error: {response.status_code} - {response.text[:300]}")
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Reply to review error: {e}")
            return {'error': str(e)}
    
    def delete_review_reply(self, access_token: str, review_name: str) -> Dict[str, Any]:
        """
        Delete a review reply
        """
        import requests
        
        try:
            response = requests.delete(
                f'{self.api_base}/{review_name}/reply',
                headers=self._get_headers(access_token)
            )
            
            if response.status_code in [200, 204]:
                return {'success': True}
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Delete reply error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # Q&A
    # ==========================================
    
    def get_questions(self, access_token: str, location_name: str) -> Dict[str, Any]:
        """
        Get questions for a location
        """
        import requests
        
        try:
            response = requests.get(
                f'{self.api_base}/{location_name}/questions',
                headers=self._get_headers(access_token)
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get questions error: {e}")
            return {'error': str(e)}
    
    def answer_question(
        self, 
        access_token: str, 
        question_name: str,
        answer_text: str
    ) -> Dict[str, Any]:
        """
        Answer a question
        """
        import requests
        
        try:
            response = requests.post(
                f'{self.api_base}/{question_name}/answers',
                headers=self._get_headers(access_token),
                json={'text': answer_text}
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Answered question {question_name}")
                return {'success': True, 'answer': response.json()}
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Answer question error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # Media (Photos)
    # ==========================================
    
    def upload_photo(
        self,
        access_token: str,
        location_name: str,
        photo_url: str,
        category: str = 'ADDITIONAL'
    ) -> Dict[str, Any]:
        """
        Upload a photo to GBP
        
        Categories: COVER, PROFILE, LOGO, EXTERIOR, INTERIOR, PRODUCT, 
                   AT_WORK, FOOD_AND_DRINK, MENU, COMMON_AREA, ROOMS, TEAMS, ADDITIONAL
        """
        import requests
        
        try:
            response = requests.post(
                f'{self.api_base}/{location_name}/media',
                headers=self._get_headers(access_token),
                json={
                    'mediaFormat': 'PHOTO',
                    'sourceUrl': photo_url,
                    'locationAssociation': {
                        'category': category
                    }
                }
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Photo uploaded to {location_name}")
                return {'success': True, 'media': response.json()}
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Upload photo error: {e}")
            return {'error': str(e)}
    
    def get_media(self, access_token: str, location_name: str) -> Dict[str, Any]:
        """
        Get all media for a location
        """
        import requests
        
        try:
            response = requests.get(
                f'{self.api_base}/{location_name}/media',
                headers=self._get_headers(access_token)
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get media error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # Insights / Performance
    # ==========================================
    
    def get_insights(
        self,
        access_token: str,
        location_name: str,
        metrics: List[str] = None,
        start_time: str = None,
        end_time: str = None
    ) -> Dict[str, Any]:
        """
        Get performance insights for a location
        
        Metrics: QUERIES_DIRECT, QUERIES_INDIRECT, QUERIES_CHAIN,
                VIEWS_MAPS, VIEWS_SEARCH, ACTIONS_WEBSITE, ACTIONS_PHONE,
                ACTIONS_DRIVING_DIRECTIONS, PHOTOS_VIEWS_MERCHANT,
                PHOTOS_VIEWS_CUSTOMERS, PHOTOS_COUNT_MERCHANT, PHOTOS_COUNT_CUSTOMERS
        """
        import requests
        
        metrics = metrics or [
            'QUERIES_DIRECT', 'QUERIES_INDIRECT',
            'VIEWS_MAPS', 'VIEWS_SEARCH',
            'ACTIONS_WEBSITE', 'ACTIONS_PHONE', 'ACTIONS_DRIVING_DIRECTIONS'
        ]
        
        try:
            params = {
                'basicRequest.metricRequests': json.dumps([{'metric': m} for m in metrics])
            }
            
            if start_time:
                params['basicRequest.timeRange.startTime'] = start_time
            if end_time:
                params['basicRequest.timeRange.endTime'] = end_time
            
            response = requests.get(
                f'{self.api_base}/{location_name}/reportInsights',
                headers=self._get_headers(access_token),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            logger.error(f"Get insights error: {e}")
            return {'error': str(e)}
    
    # ==========================================
    # Helper Methods
    # ==========================================
    
    def publish_social_post_to_gbp(
        self,
        access_token: str,
        location_name: str,
        social_post: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert a social post to GBP format and publish
        
        Args:
            social_post: From our social service {text, hashtags, cta, image_url}
        """
        # Remove hashtags (not supported on GBP)
        text = social_post.get('text', '')
        
        # Add CTA if present
        cta = social_post.get('cta')
        if cta and cta not in text:
            text = f"{text}\n\n{cta}"
        
        # Prepare media if image provided
        media = None
        if social_post.get('image_url'):
            media = [{
                'mediaFormat': 'PHOTO',
                'sourceUrl': social_post['image_url']
            }]
        
        # Prepare CTA button if URL provided
        call_to_action = None
        if social_post.get('link_url'):
            call_to_action = {
                'actionType': 'LEARN_MORE',
                'url': social_post['link_url']
            }
        
        return self.create_post(
            access_token=access_token,
            location_name=location_name,
            post_type='STANDARD',
            summary=text,
            call_to_action=call_to_action,
            media=media
        )
    
    def generate_review_response(
        self,
        review: Dict[str, Any],
        business_name: str,
        ai_service=None
    ) -> str:
        """
        Generate AI response to a review
        """
        rating = review.get('starRating', 'FIVE')
        comment = review.get('comment', '')
        reviewer = review.get('reviewer', {}).get('displayName', 'Customer')
        
        # Map star rating
        rating_map = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}
        stars = rating_map.get(rating, 5)
        
        if ai_service:
            prompt = f"""Generate a professional response to this Google review:

Business: {business_name}
Rating: {stars} stars
Reviewer: {reviewer}
Review: {comment or 'No comment provided'}

Guidelines:
- Thank the reviewer by name
- If positive (4-5 stars): Express gratitude, highlight something specific if they mentioned it
- If negative (1-2 stars): Apologize, offer to make it right, provide contact info
- If neutral (3 stars): Thank them, address concerns, invite them back
- Keep it under 500 characters
- Be genuine, not corporate
- Don't be defensive

Response:"""
            
            try:
                response = ai_service.generate_raw(prompt, max_tokens=200)
                return response.strip()
            except Exception as e:
                pass
        
        # Fallback templates
        if stars >= 4:
            return f"Thank you so much for the wonderful review, {reviewer}! We're thrilled to hear about your positive experience with {business_name}. Your support means the world to us, and we look forward to serving you again soon!"
        elif stars == 3:
            return f"Thank you for your feedback, {reviewer}. We appreciate you taking the time to share your experience. We're always working to improve, and we'd love the opportunity to exceed your expectations next time. Please don't hesitate to reach out if there's anything we can do better."
        else:
            return f"Thank you for bringing this to our attention, {reviewer}. We're sorry to hear your experience didn't meet expectations. We take all feedback seriously and would love the opportunity to make this right. Please contact us directly so we can address your concerns."


# Global instance
gbp_service = GBPService()
