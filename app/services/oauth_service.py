"""
MCP Framework - OAuth Service
Handles OAuth2 flows for Facebook, Instagram, LinkedIn, and Google Business Profile
"""
import os
import json
import hashlib
import secrets
import logging
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class OAuthConfig:
    """OAuth configuration for all platforms"""
    
    # Facebook/Instagram (Meta)
    FACEBOOK_APP_ID = os.getenv('FACEBOOK_APP_ID', '')
    FACEBOOK_APP_SECRET = os.getenv('FACEBOOK_APP_SECRET', '')
    FACEBOOK_SCOPES = 'pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,business_management'
    
    # LinkedIn
    LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID', '')
    LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET', '')
    LINKEDIN_SCOPES = 'r_liteprofile r_emailaddress w_member_social r_organization_social w_organization_social'
    
    # Google Business Profile
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
    GOOGLE_SCOPES = 'https://www.googleapis.com/auth/business.manage'
    
    # App URL for callbacks
    APP_URL = os.getenv('APP_URL', 'https://mcp-framework.onrender.com')
    
    @classmethod
    def get_callback_url(cls, platform: str) -> str:
        """Get OAuth callback URL for a platform"""
        return f"{cls.APP_URL}/api/oauth/callback/{platform}"
    
    @classmethod
    def is_configured(cls, platform: str) -> bool:
        """Check if OAuth is configured for a platform"""
        if platform in ['facebook', 'instagram']:
            return bool(cls.FACEBOOK_APP_ID and cls.FACEBOOK_APP_SECRET)
        elif platform == 'linkedin':
            return bool(cls.LINKEDIN_CLIENT_ID and cls.LINKEDIN_CLIENT_SECRET)
        elif platform in ['gbp', 'google']:
            return bool(cls.GOOGLE_CLIENT_ID and cls.GOOGLE_CLIENT_SECRET)
        return False


class OAuthState:
    """Manages OAuth state parameters for CSRF protection"""
    
    # In-memory state store (use Redis in production for multi-instance)
    _states: Dict[str, Dict] = {}
    
    @classmethod
    def generate(cls, client_id: str, user_id: str, platform: str) -> str:
        """Generate a secure state parameter"""
        state = secrets.token_urlsafe(32)
        cls._states[state] = {
            'client_id': client_id,
            'user_id': user_id,
            'platform': platform,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(minutes=10)
        }
        return state
    
    @classmethod
    def validate(cls, state: str) -> Optional[Dict]:
        """Validate and consume a state parameter"""
        if state not in cls._states:
            return None
        
        data = cls._states.pop(state)
        
        if datetime.utcnow() > data['expires_at']:
            return None
        
        return data
    
    @classmethod
    def cleanup_expired(cls):
        """Remove expired states"""
        now = datetime.utcnow()
        expired = [s for s, d in cls._states.items() if now > d['expires_at']]
        for s in expired:
            cls._states.pop(s, None)


class OAuthService:
    """
    OAuth2 service for social media platforms
    
    Supported platforms:
    - facebook: Facebook Pages
    - instagram: Instagram Business (via Facebook)
    - linkedin: LinkedIn Company Pages
    - gbp/google: Google Business Profile
    """
    
    def __init__(self):
        self.config = OAuthConfig()
    
    # ==========================================
    # AUTHORIZATION URL GENERATION
    # ==========================================
    
    def get_auth_url(self, platform: str, client_id: str, user_id: str) -> Tuple[str, str]:
        """
        Generate OAuth authorization URL
        
        Args:
            platform: 'facebook', 'instagram', 'linkedin', 'gbp'
            client_id: Client ID to connect
            user_id: User initiating the connection
        
        Returns:
            Tuple of (auth_url, state)
        """
        state = OAuthState.generate(client_id, user_id, platform)
        
        if platform in ['facebook', 'instagram']:
            return self._facebook_auth_url(state), state
        elif platform == 'linkedin':
            return self._linkedin_auth_url(state), state
        elif platform in ['gbp', 'google']:
            return self._google_auth_url(state), state
        else:
            raise ValueError(f"Unsupported platform: {platform}")
    
    def _facebook_auth_url(self, state: str) -> str:
        """Generate Facebook OAuth URL (also used for Instagram)"""
        params = {
            'client_id': self.config.FACEBOOK_APP_ID,
            'redirect_uri': self.config.get_callback_url('facebook'),
            'scope': self.config.FACEBOOK_SCOPES,
            'state': state,
            'response_type': 'code'
        }
        return f"https://www.facebook.com/v18.0/dialog/oauth?{urlencode(params)}"
    
    def _linkedin_auth_url(self, state: str) -> str:
        """Generate LinkedIn OAuth URL"""
        params = {
            'client_id': self.config.LINKEDIN_CLIENT_ID,
            'redirect_uri': self.config.get_callback_url('linkedin'),
            'scope': self.config.LINKEDIN_SCOPES,
            'state': state,
            'response_type': 'code'
        }
        return f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"
    
    def _google_auth_url(self, state: str) -> str:
        """Generate Google OAuth URL for Business Profile"""
        params = {
            'client_id': self.config.GOOGLE_CLIENT_ID,
            'redirect_uri': self.config.get_callback_url('google'),
            'scope': self.config.GOOGLE_SCOPES,
            'state': state,
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent'  # Force refresh token
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    # ==========================================
    # TOKEN EXCHANGE
    # ==========================================
    
    def exchange_code(self, platform: str, code: str) -> Dict:
        """
        Exchange authorization code for access token
        
        Args:
            platform: Platform identifier
            code: Authorization code from callback
        
        Returns:
            Dict with access_token, refresh_token (if available), expires_in
        """
        if platform in ['facebook', 'instagram']:
            return self._facebook_exchange(code)
        elif platform == 'linkedin':
            return self._linkedin_exchange(code)
        elif platform in ['gbp', 'google']:
            return self._google_exchange(code)
        else:
            raise ValueError(f"Unsupported platform: {platform}")
    
    def _facebook_exchange(self, code: str) -> Dict:
        """Exchange Facebook auth code for token"""
        url = "https://graph.facebook.com/v18.0/oauth/access_token"
        params = {
            'client_id': self.config.FACEBOOK_APP_ID,
            'client_secret': self.config.FACEBOOK_APP_SECRET,
            'redirect_uri': self.config.get_callback_url('facebook'),
            'code': code
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            logger.error(f"Facebook token exchange failed: {data['error']}")
            raise OAuthError(f"Facebook error: {data['error'].get('message', 'Unknown error')}")
        
        # Get long-lived token
        access_token = data.get('access_token')
        long_lived = self._facebook_get_long_lived_token(access_token)
        
        return {
            'access_token': long_lived.get('access_token', access_token),
            'expires_in': long_lived.get('expires_in', data.get('expires_in', 3600)),
            'token_type': 'Bearer'
        }
    
    def _facebook_get_long_lived_token(self, short_token: str) -> Dict:
        """Exchange short-lived token for long-lived token (60 days)"""
        url = "https://graph.facebook.com/v18.0/oauth/access_token"
        params = {
            'grant_type': 'fb_exchange_token',
            'client_id': self.config.FACEBOOK_APP_ID,
            'client_secret': self.config.FACEBOOK_APP_SECRET,
            'fb_exchange_token': short_token
        }
        
        response = requests.get(url, params=params)
        result = response.json()
        
        if 'error' in result:
            logger.warning(f"Failed to get long-lived token: {result['error']}")
            return {'access_token': short_token}  # Fall back to short token
        
        logger.info(f"Got long-lived Facebook token, expires_in: {result.get('expires_in', 'unknown')}")
        return result
    
    def _linkedin_exchange(self, code: str) -> Dict:
        """Exchange LinkedIn auth code for token"""
        url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.config.get_callback_url('linkedin'),
            'client_id': self.config.LINKEDIN_CLIENT_ID,
            'client_secret': self.config.LINKEDIN_CLIENT_SECRET
        }
        
        response = requests.post(url, data=data)
        result = response.json()
        
        if 'error' in result:
            logger.error(f"LinkedIn token exchange failed: {result['error']}")
            raise OAuthError(f"LinkedIn error: {result.get('error_description', result['error'])}")
        
        return {
            'access_token': result.get('access_token'),
            'refresh_token': result.get('refresh_token'),
            'expires_in': result.get('expires_in', 3600),
            'token_type': 'Bearer'
        }
    
    def _google_exchange(self, code: str) -> Dict:
        """Exchange Google auth code for token"""
        url = "https://oauth2.googleapis.com/token"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.config.get_callback_url('google'),
            'client_id': self.config.GOOGLE_CLIENT_ID,
            'client_secret': self.config.GOOGLE_CLIENT_SECRET
        }
        
        response = requests.post(url, data=data)
        result = response.json()
        
        if 'error' in result:
            logger.error(f"Google token exchange failed: {result['error']}")
            raise OAuthError(f"Google error: {result.get('error_description', result['error'])}")
        
        return {
            'access_token': result.get('access_token'),
            'refresh_token': result.get('refresh_token'),
            'expires_in': result.get('expires_in', 3600),
            'token_type': 'Bearer'
        }
    
    # ==========================================
    # TOKEN REFRESH
    # ==========================================
    
    def refresh_token(self, platform: str, refresh_token: str) -> Dict:
        """
        Refresh an expired access token
        
        Note: Facebook doesn't use refresh tokens - you need to re-authenticate
        """
        if platform == 'linkedin':
            return self._linkedin_refresh(refresh_token)
        elif platform in ['gbp', 'google']:
            return self._google_refresh(refresh_token)
        else:
            raise OAuthError(f"Token refresh not supported for {platform}")
    
    def _linkedin_refresh(self, refresh_token: str) -> Dict:
        """Refresh LinkedIn token"""
        url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.LINKEDIN_CLIENT_ID,
            'client_secret': self.config.LINKEDIN_CLIENT_SECRET
        }
        
        response = requests.post(url, data=data)
        result = response.json()
        
        if 'error' in result:
            raise OAuthError(f"LinkedIn refresh failed: {result.get('error_description', result['error'])}")
        
        return {
            'access_token': result.get('access_token'),
            'refresh_token': result.get('refresh_token', refresh_token),
            'expires_in': result.get('expires_in', 3600)
        }
    
    def _google_refresh(self, refresh_token: str) -> Dict:
        """Refresh Google token"""
        url = "https://oauth2.googleapis.com/token"
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.GOOGLE_CLIENT_ID,
            'client_secret': self.config.GOOGLE_CLIENT_SECRET
        }
        
        response = requests.post(url, data=data)
        result = response.json()
        
        if 'error' in result:
            raise OAuthError(f"Google refresh failed: {result.get('error_description', result['error'])}")
        
        return {
            'access_token': result.get('access_token'),
            'refresh_token': refresh_token,  # Google doesn't return new refresh token
            'expires_in': result.get('expires_in', 3600)
        }
    
    # ==========================================
    # ACCOUNT DISCOVERY
    # ==========================================
    
    def get_facebook_pages(self, access_token: str) -> list:
        """Get list of Facebook Pages the user manages"""
        url = "https://graph.facebook.com/v18.0/me/accounts"
        params = {
            'access_token': access_token,
            'fields': 'id,name,access_token,category,picture'
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            raise OAuthError(f"Facebook error: {data['error'].get('message', 'Unknown error')}")
        
        return data.get('data', [])
    
    def get_instagram_accounts(self, access_token: str, page_id: str) -> list:
        """Get Instagram Business accounts linked to a Facebook Page"""
        url = f"https://graph.facebook.com/v18.0/{page_id}"
        params = {
            'access_token': access_token,
            'fields': 'instagram_business_account{id,username,profile_picture_url,followers_count}'
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            raise OAuthError(f"Facebook error: {data['error'].get('message', 'Unknown error')}")
        
        ig_account = data.get('instagram_business_account')
        return [ig_account] if ig_account else []
    
    def get_linkedin_organizations(self, access_token: str) -> list:
        """Get LinkedIn organizations the user can post to"""
        # First get the user's profile
        profile_url = "https://api.linkedin.com/v2/me"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        profile_response = requests.get(profile_url, headers=headers)
        profile_data = profile_response.json()
        
        if 'id' not in profile_data:
            raise OAuthError("Could not get LinkedIn profile")
        
        # Get organizations
        org_url = "https://api.linkedin.com/v2/organizationalEntityAcls"
        params = {
            'q': 'roleAssignee',
            'role': 'ADMINISTRATOR',
            'state': 'APPROVED'
        }
        
        org_response = requests.get(org_url, headers=headers, params=params)
        org_data = org_response.json()
        
        organizations = []
        for element in org_data.get('elements', []):
            org_urn = element.get('organizationalTarget', '')
            if 'urn:li:organization:' in org_urn:
                org_id = org_urn.replace('urn:li:organization:', '')
                # Get org details
                org_detail_url = f"https://api.linkedin.com/v2/organizations/{org_id}"
                org_detail = requests.get(org_detail_url, headers=headers).json()
                organizations.append({
                    'id': org_id,
                    'name': org_detail.get('localizedName', f'Organization {org_id}'),
                    'vanity_name': org_detail.get('vanityName', '')
                })
        
        return organizations
    
    def get_google_locations(self, access_token: str) -> list:
        """Get Google Business Profile locations"""
        headers = {'Authorization': f'Bearer {access_token}'}
        
        # Get accounts
        accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
        accounts_response = requests.get(accounts_url, headers=headers)
        accounts_data = accounts_response.json()
        
        if 'error' in accounts_data:
            raise OAuthError(f"Google error: {accounts_data['error'].get('message', 'Unknown error')}")
        
        locations = []
        for account in accounts_data.get('accounts', []):
            account_name = account.get('name', '')
            
            # Get locations for this account
            locations_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations"
            locations_response = requests.get(locations_url, headers=headers)
            locations_data = locations_response.json()
            
            for location in locations_data.get('locations', []):
                locations.append({
                    'id': location.get('name', '').split('/')[-1],
                    'name': location.get('title', 'Unknown Location'),
                    'address': location.get('storefrontAddress', {}).get('addressLines', [''])[0],
                    'account_id': account_name.split('/')[-1]
                })
        
        return locations
    
    # ==========================================
    # VALIDATION
    # ==========================================
    
    def validate_token(self, platform: str, access_token: str) -> Dict:
        """
        Validate an access token is still valid
        
        Returns:
            Dict with 'valid', 'expires_at', 'scopes', etc.
        """
        if platform in ['facebook', 'instagram']:
            return self._validate_facebook_token(access_token)
        elif platform == 'linkedin':
            return self._validate_linkedin_token(access_token)
        elif platform in ['gbp', 'google']:
            return self._validate_google_token(access_token)
        else:
            return {'valid': False, 'error': 'Unknown platform'}
    
    def _validate_facebook_token(self, access_token: str) -> Dict:
        """Validate Facebook token"""
        url = "https://graph.facebook.com/v18.0/debug_token"
        params = {
            'input_token': access_token,
            'access_token': f"{self.config.FACEBOOK_APP_ID}|{self.config.FACEBOOK_APP_SECRET}"
        }
        
        response = requests.get(url, params=params)
        data = response.json().get('data', {})
        
        return {
            'valid': data.get('is_valid', False),
            'expires_at': datetime.fromtimestamp(data.get('expires_at', 0)).isoformat() if data.get('expires_at') else None,
            'scopes': data.get('scopes', []),
            'app_id': data.get('app_id'),
            'user_id': data.get('user_id')
        }
    
    def _validate_linkedin_token(self, access_token: str) -> Dict:
        """Validate LinkedIn token by making a test request"""
        url = "https://api.linkedin.com/v2/me"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return {'valid': True}
        else:
            return {'valid': False, 'error': 'Token invalid or expired'}
    
    def _validate_google_token(self, access_token: str) -> Dict:
        """Validate Google token"""
        url = f"https://oauth2.googleapis.com/tokeninfo?access_token={access_token}"
        
        response = requests.get(url)
        data = response.json()
        
        if 'error' in data:
            return {'valid': False, 'error': data['error']}
        
        return {
            'valid': True,
            'expires_in': int(data.get('expires_in', 0)),
            'scope': data.get('scope', '')
        }


class OAuthError(Exception):
    """OAuth-related error"""
    pass


# Singleton instance
_oauth_service = None


def get_oauth_service() -> OAuthService:
    """Get or create OAuth service instance"""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service
