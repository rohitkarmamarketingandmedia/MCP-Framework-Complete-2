"""
MCP Framework - OAuth Routes
Handles OAuth2 flows for Facebook, Instagram, LinkedIn, and Google Business Profile
"""
from flask import Blueprint, request, jsonify, redirect, url_for
from datetime import datetime
from urllib.parse import quote
import logging

from app.routes.auth import token_required
from app.database import db
from app.models.db_models import DBClient, DBUser
from app.services.oauth_service import (
    get_oauth_service, OAuthConfig, OAuthState, OAuthError
)

logger = logging.getLogger(__name__)
oauth_bp = Blueprint('oauth', __name__)


# ==========================================
# OAUTH CONFIGURATION CHECK
# ==========================================

@oauth_bp.route('/config', methods=['GET'])
@token_required
def get_oauth_config(current_user):
    """
    Get OAuth configuration status for all platforms
    
    GET /api/oauth/config
    """
    return jsonify({
        'platforms': {
            'facebook': {
                'configured': OAuthConfig.is_configured('facebook'),
                'name': 'Facebook / Instagram',
                'description': 'Connect Facebook Pages and Instagram Business accounts',
                'icon': 'fab fa-facebook',
                'color': '#1877F2'
            },
            'linkedin': {
                'configured': OAuthConfig.is_configured('linkedin'),
                'name': 'LinkedIn',
                'description': 'Connect LinkedIn Company Pages',
                'icon': 'fab fa-linkedin',
                'color': '#0A66C2'
            },
            'google': {
                'configured': OAuthConfig.is_configured('google'),
                'name': 'Google Business Profile',
                'description': 'Connect Google Business Profile locations',
                'icon': 'fab fa-google',
                'color': '#4285F4'
            }
        },
        'callback_base': OAuthConfig.APP_URL
    })


# ==========================================
# AUTHORIZATION INITIATION
# ==========================================

@oauth_bp.route('/authorize/<platform>', methods=['POST'])
@token_required
def initiate_oauth(current_user, platform):
    """
    Initiate OAuth flow for a platform
    
    POST /api/oauth/authorize/{platform}
    {
        "client_id": "client_abc123"
    }
    
    Returns URL to redirect user to for authorization
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    # Verify client exists and user has access
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Check if OAuth is configured
    if not OAuthConfig.is_configured(platform):
        return jsonify({
            'error': f'OAuth not configured for {platform}',
            'message': f'Please set {platform.upper()}_CLIENT_ID and {platform.upper()}_CLIENT_SECRET environment variables'
        }), 400
    
    try:
        oauth_service = get_oauth_service()
        auth_url, state = oauth_service.get_auth_url(
            platform=platform,
            client_id=client_id,
            user_id=current_user.id
        )
        
        logger.info(f"OAuth initiated for {platform}, client {client_id}, user {current_user.id}")
        
        return jsonify({
            'auth_url': auth_url,
            'state': state,
            'platform': platform,
            'client_id': client_id
        })
        
    except Exception as e:
        logger.error(f"OAuth initiation failed: {e}")
        return jsonify({'error': 'An error occurred. Please try again.'}), 500


# ==========================================
# OAUTH CALLBACKS
# ==========================================

@oauth_bp.route('/callback/<platform>', methods=['GET'])
def oauth_callback(platform):
    """
    OAuth callback handler
    
    GET /api/oauth/callback/{platform}?code=xxx&state=xxx
    
    This is called by the OAuth provider after user authorizes
    Redirects to dashboard with success/error
    """
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    error_description = request.args.get('error_description', '')
    
    # Handle OAuth errors
    if error:
        logger.warning(f"OAuth error for {platform}: {error} - {error_description}")
        return redirect(f"{OAuthConfig.APP_URL}/client-dashboard.html?oauth_error={quote(error)}&platform={platform}")
    
    # Validate state
    state_data = OAuthState.validate(state)
    if not state_data:
        logger.warning(f"Invalid OAuth state for {platform}")
        return redirect(f"{OAuthConfig.APP_URL}/client-dashboard.html?oauth_error=invalid_state&platform={platform}")
    
    client_id = state_data['client_id']
    user_id = state_data['user_id']
    
    try:
        oauth_service = get_oauth_service()
        
        # Exchange code for token
        token_data = oauth_service.exchange_code(platform, code)
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        
        # Store connection in session/temporary storage
        # We'll redirect to account selection page
        connection_data = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': expires_in,
            'client_id': client_id,
            'user_id': user_id,
            'platform': platform
        }
        
        # Store temporarily (you might want to use Redis or session)
        temp_state = OAuthState.generate(client_id, user_id, f"{platform}_connected")
        OAuthState._states[temp_state]['token_data'] = connection_data
        
        logger.info(f"OAuth successful for {platform}, client {client_id}")
        
        # Redirect to account selection - include client_id for context restoration
        return redirect(f"{OAuthConfig.APP_URL}/client-dashboard.html?oauth_success=1&platform={platform}&state={temp_state}&client_id={client_id}")
        
    except OAuthError as e:
        logger.error(f"OAuth exchange failed for {platform}: {e}")
        return redirect(f"{OAuthConfig.APP_URL}/client-dashboard.html?oauth_error={quote(str(e))}&platform={platform}")
    except Exception as e:
        logger.error(f"OAuth callback error for {platform}: {e}")
        return redirect(f"{OAuthConfig.APP_URL}/client-dashboard.html?oauth_error=server_error&platform={platform}")


# ==========================================
# ACCOUNT DISCOVERY (After OAuth)
# ==========================================

@oauth_bp.route('/accounts/<platform>', methods=['POST'])
@token_required
def get_available_accounts(current_user, platform):
    """
    Get available accounts/pages after OAuth authorization
    
    POST /api/oauth/accounts/{platform}
    {
        "state": "temp_state_from_callback"
    }
    
    Returns list of pages/accounts user can connect
    """
    data = request.get_json(silent=True) or {}
    state = data.get('state')
    
    if not state:
        return jsonify({'error': 'state is required'}), 400
    
    # Get token data from state
    state_data = OAuthState._states.get(state)
    if not state_data or 'token_data' not in state_data:
        return jsonify({'error': 'Invalid or expired state'}), 400
    
    token_data = state_data['token_data']
    access_token = token_data['access_token']
    
    try:
        oauth_service = get_oauth_service()
        
        if platform in ['facebook', 'instagram']:
            # Get Facebook Pages
            pages = oauth_service.get_facebook_pages(access_token)
            
            # For each page, check for linked Instagram
            accounts = []
            for page in pages:
                page_data = {
                    'type': 'facebook_page',
                    'id': page['id'],
                    'name': page['name'],
                    'category': page.get('category', ''),
                    'access_token': page.get('access_token'),  # Page-specific token
                    'picture': page.get('picture', {}).get('data', {}).get('url', '')
                }
                accounts.append(page_data)
                
                # Check for linked Instagram
                try:
                    ig_accounts = oauth_service.get_instagram_accounts(
                        page.get('access_token', access_token),
                        page['id']
                    )
                    for ig in ig_accounts:
                        accounts.append({
                            'type': 'instagram_business',
                            'id': ig['id'],
                            'name': ig.get('username', 'Instagram Account'),
                            'facebook_page_id': page['id'],
                            'picture': ig.get('profile_picture_url', ''),
                            'followers': ig.get('followers_count', 0)
                        })
                except Exception as ig_error:
                    logger.debug(f"No Instagram linked to page {page['id']}: {ig_error}")
            
            return jsonify({
                'platform': 'facebook',
                'accounts': accounts,
                'state': state
            })
        
        elif platform == 'linkedin':
            organizations = oauth_service.get_linkedin_organizations(access_token)
            
            # Also include personal profile
            accounts = [{
                'type': 'linkedin_personal',
                'id': 'personal',
                'name': 'Personal Profile'
            }]
            
            for org in organizations:
                accounts.append({
                    'type': 'linkedin_organization',
                    'id': org['id'],
                    'name': org['name'],
                    'vanity_name': org.get('vanity_name', '')
                })
            
            return jsonify({
                'platform': 'linkedin',
                'accounts': accounts,
                'state': state
            })
        
        elif platform in ['gbp', 'google']:
            locations = oauth_service.get_google_locations(access_token)
            
            accounts = []
            for loc in locations:
                accounts.append({
                    'type': 'google_location',
                    'id': loc['id'],
                    'name': loc['name'],
                    'address': loc.get('address', ''),
                    'account_id': loc.get('account_id', '')
                })
            
            return jsonify({
                'platform': 'google',
                'accounts': accounts,
                'state': state
            })
        
        else:
            return jsonify({'error': f'Unknown platform: {platform}'}), 400
            
    except OAuthError as e:
        return jsonify({'error': 'An error occurred. Please try again.'}), 400
    except Exception as e:
        logger.error(f"Account discovery error: {e}")
        return jsonify({'error': 'Failed to get accounts'}), 500


# ==========================================
# FINALIZE CONNECTION
# ==========================================

@oauth_bp.route('/connect', methods=['POST'])
@token_required
def finalize_connection(current_user):
    """
    Finalize OAuth connection by storing selected account
    
    POST /api/oauth/connect
    {
        "state": "temp_state",
        "account_type": "facebook_page|instagram_business|linkedin_organization|google_location",
        "account_id": "page_id or account_id",
        "account_name": "Page/Account Name"
    }
    """
    data = request.get_json(silent=True) or {}
    state = data.get('state')
    account_type = data.get('account_type')
    account_id = data.get('account_id')
    account_name = data.get('account_name', '')
    page_access_token = data.get('page_access_token')  # For Facebook Pages
    
    if not all([state, account_type, account_id]):
        return jsonify({'error': 'state, account_type, and account_id are required'}), 400
    
    # Get token data from state
    state_data = OAuthState._states.get(state)
    if not state_data or 'token_data' not in state_data:
        return jsonify({'error': 'Invalid or expired state'}), 400
    
    token_data = state_data['token_data']
    client_id = token_data['client_id']
    
    # Log what tokens we have
    user_token = token_data.get('access_token', '')
    logger.info(f"OAuth finalize: user_token_length={len(user_token)}, page_access_token_length={len(page_access_token) if page_access_token else 0}")
    
    # Prefer page token (from /me/accounts) over user token
    access_token = page_access_token or user_token
    refresh_token = token_data.get('refresh_token')
    
    # Verify client access
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Store connection based on account type
        if account_type == 'facebook_page':
            # Log existing data
            logger.info(f"BEFORE: facebook_page_id={client.facebook_page_id}, token_length={len(client.facebook_access_token) if client.facebook_access_token else 0}")
            
            client.facebook_page_id = account_id
            client.facebook_access_token = access_token
            client.facebook_connected_at = datetime.utcnow()
            platform = 'Facebook'
            logger.info(f"AFTER: Saving Facebook connection: page_id={account_id}, token_length={len(access_token) if access_token else 0}")
            
        elif account_type == 'instagram_business':
            client.instagram_account_id = account_id
            client.instagram_access_token = access_token
            client.instagram_connected_at = datetime.utcnow()
            # Also store the Facebook page ID for API calls
            facebook_page_id = data.get('facebook_page_id')
            if facebook_page_id:
                client.facebook_page_id = facebook_page_id
                client.facebook_access_token = access_token
            platform = 'Instagram'
            
        elif account_type == 'linkedin_organization':
            client.linkedin_org_id = account_id
            client.linkedin_access_token = access_token
            client.linkedin_connected_at = datetime.utcnow()
            if refresh_token:
                # Store refresh token (you might want to encrypt this)
                pass  # Could add linkedin_refresh_token field
            platform = 'LinkedIn'
            
        elif account_type == 'linkedin_personal':
            # Personal profile uses user ID
            client.linkedin_org_id = 'personal'
            client.linkedin_access_token = access_token
            client.linkedin_connected_at = datetime.utcnow()
            platform = 'LinkedIn (Personal)'
            
        elif account_type == 'google_location':
            client.gbp_location_id = account_id
            client.gbp_access_token = access_token
            # Store account_id if provided (needed for API calls)
            google_account_id = data.get('google_account_id') or data.get('account_id')
            if google_account_id:
                client.gbp_account_id = google_account_id
            if refresh_token:
                client.gbp_refresh_token = refresh_token
            client.gbp_connected_at = datetime.utcnow() if hasattr(client, 'gbp_connected_at') else None
            platform = 'Google Business Profile'
            
        else:
            return jsonify({'error': f'Unknown account type: {account_type}'}), 400
        
        db.session.commit()
        
        # Clean up state
        OAuthState._states.pop(state, None)
        
        logger.info(f"Connected {platform} for client {client_id}: {account_name} ({account_id})")
        
        return jsonify({
            'success': True,
            'platform': platform,
            'account_id': account_id,
            'account_name': account_name,
            'client_id': client_id
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Connection finalization error: {e}")
        return jsonify({'error': 'Failed to save connection'}), 500


# ==========================================
# TOKEN VALIDATION & REFRESH
# ==========================================

@oauth_bp.route('/validate/<platform>/<client_id>', methods=['GET'])
@token_required
def validate_connection(current_user, platform, client_id):
    """
    Validate that a platform connection is still valid
    
    GET /api/oauth/validate/{platform}/{client_id}
    """
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get access token based on platform
    access_token = None
    if platform == 'facebook':
        access_token = client.facebook_access_token
    elif platform == 'instagram':
        access_token = client.instagram_access_token
    elif platform == 'linkedin':
        access_token = client.linkedin_access_token
    elif platform in ['gbp', 'google']:
        access_token = client.gbp_access_token
    
    if not access_token:
        return jsonify({
            'valid': False,
            'connected': False,
            'error': 'Not connected'
        })
    
    try:
        oauth_service = get_oauth_service()
        result = oauth_service.validate_token(platform, access_token)
        result['connected'] = True
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'valid': False,
            'connected': True,
            'error': 'An error occurred. Please try again.'
        })


@oauth_bp.route('/refresh/<platform>/<client_id>', methods=['POST'])
@token_required
def refresh_connection(current_user, platform, client_id):
    """
    Refresh an expired token
    
    POST /api/oauth/refresh/{platform}/{client_id}
    """
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get refresh token
    refresh_token = None
    if platform in ['gbp', 'google']:
        refresh_token = client.gbp_refresh_token if hasattr(client, 'gbp_refresh_token') else None
    # LinkedIn refresh token would need its own field
    
    if not refresh_token:
        return jsonify({
            'error': 'No refresh token available. Please reconnect.',
            'reconnect_required': True
        }), 400
    
    try:
        oauth_service = get_oauth_service()
        new_tokens = oauth_service.refresh_token(platform, refresh_token)
        
        # Update stored token
        if platform in ['gbp', 'google']:
            client.gbp_access_token = new_tokens['access_token']
            if new_tokens.get('refresh_token'):
                client.gbp_refresh_token = new_tokens['refresh_token']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'expires_in': new_tokens.get('expires_in', 3600)
        })
        
    except OAuthError as e:
        return jsonify({
            'error': 'An error occurred. Please try again.',
            'reconnect_required': True
        }), 400


# ==========================================
# DISCONNECT
# ==========================================

@oauth_bp.route('/disconnect/<platform>/<client_id>', methods=['POST'])
@token_required
def disconnect_platform(current_user, platform, client_id):
    """
    Disconnect a platform from a client
    
    POST /api/oauth/disconnect/{platform}/{client_id}
    """
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    try:
        if platform == 'facebook':
            client.facebook_page_id = None
            client.facebook_access_token = None
            client.facebook_connected_at = None
            
        elif platform == 'instagram':
            client.instagram_account_id = None
            client.instagram_access_token = None
            client.instagram_connected_at = None
            
        elif platform == 'linkedin':
            client.linkedin_org_id = None
            client.linkedin_access_token = None
            client.linkedin_connected_at = None
            
        elif platform in ['gbp', 'google']:
            client.gbp_location_id = None
            client.gbp_access_token = None
            if hasattr(client, 'gbp_refresh_token'):
                client.gbp_refresh_token = None
            if hasattr(client, 'gbp_connected_at'):
                client.gbp_connected_at = None
        
        db.session.commit()
        
        logger.info(f"Disconnected {platform} for client {client_id}")
        
        return jsonify({
            'success': True,
            'platform': platform,
            'client_id': client_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'An error occurred. Please try again.'}), 500
