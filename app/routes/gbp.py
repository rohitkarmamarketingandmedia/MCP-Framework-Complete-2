"""
MCP Framework - Google Business Profile API Routes
"""
from flask import Blueprint, request, jsonify, redirect
from datetime import datetime

from app.routes.auth import token_required
from app.services.gbp_service import gbp_service
from app.models.db_models import DBClient
from app.database import db

gbp_bp = Blueprint('gbp', __name__)


# ==========================================
# OAuth Flow
# ==========================================

@gbp_bp.route('/auth/url', methods=['GET'])
@token_required
def get_auth_url(current_user):
    """
    Get OAuth authorization URL for GBP
    
    GET /api/gbp/auth/url?client_id=xxx&redirect_uri=https://...
    """
    if not gbp_service.is_configured():
        return jsonify({'error': 'GBP not configured. Set GBP_CLIENT_ID and GBP_CLIENT_SECRET.'}), 400
    
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    
    if not client_id or not redirect_uri:
        return jsonify({'error': 'client_id and redirect_uri are required'}), 400
    
    auth_url = gbp_service.get_auth_url(redirect_uri, state=client_id)
    
    return jsonify({'auth_url': auth_url})


@gbp_bp.route('/auth/callback', methods=['GET'])
def oauth_callback():
    """
    OAuth callback handler
    
    GET /api/gbp/auth/callback?code=xxx&state=client_id
    """
    code = request.args.get('code')
    client_id = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        return jsonify({'error': error}), 400
    
    if not code or not client_id:
        return jsonify({'error': 'Missing code or state'}), 400
    
    # Get the redirect URI that was used
    redirect_uri = request.url.split('?')[0]
    
    # Exchange code for tokens
    tokens = gbp_service.exchange_code(code, redirect_uri)
    
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    # Store refresh token in client record
    client = DBClient.query.get(client_id)
    if client:
        client.gbp_access_token = tokens.get('refresh_token')
        db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'GBP connected successfully',
        'client_id': client_id
    })


# ==========================================
# Accounts & Locations
# ==========================================

@gbp_bp.route('/accounts', methods=['GET'])
@token_required
def get_accounts(current_user):
    """Get all GBP accounts for a client"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected for this client'}), 400
    
    # Get fresh access token
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    access_token = tokens.get('access_token')
    
    # Get accounts
    result = gbp_service.get_accounts(access_token)
    
    return jsonify(result)


@gbp_bp.route('/locations', methods=['GET'])
@token_required
def get_locations(current_user):
    """Get all locations for a GBP account"""
    client_id = request.args.get('client_id')
    account_id = request.args.get('account_id')
    
    if not client_id or not account_id:
        return jsonify({'error': 'client_id and account_id are required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    result = gbp_service.get_locations(tokens['access_token'], account_id)
    
    return jsonify(result)


@gbp_bp.route('/location/set', methods=['POST'])
@token_required
def set_location(current_user):
    """
    Set the GBP location for a client
    
    POST /api/gbp/location/set
    {
        "client_id": "xxx",
        "account_id": "xxx",
        "location_id": "xxx"
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    client.gbp_account_id = data.get('account_id')
    client.gbp_location_id = data.get('location_id')
    db.session.commit()
    
    return jsonify({
        'success': True,
        'gbp_account_id': client.gbp_account_id,
        'gbp_location_id': client.gbp_location_id
    })


# ==========================================
# Posts
# ==========================================

@gbp_bp.route('/posts', methods=['GET'])
@token_required
def get_posts(current_user):
    """Get all posts for a location"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    if not client.gbp_account_id or not client.gbp_location_id:
        return jsonify({'error': 'GBP location not set'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    location_name = f"accounts/{client.gbp_account_id}/locations/{client.gbp_location_id}"
    result = gbp_service.get_posts(tokens['access_token'], location_name)
    
    return jsonify(result)


@gbp_bp.route('/posts', methods=['POST'])
@token_required
def create_post(current_user):
    """
    Create a GBP post
    
    POST /api/gbp/posts
    {
        "client_id": "xxx",
        "post_type": "STANDARD",
        "summary": "Post content...",
        "call_to_action": {"actionType": "LEARN_MORE", "url": "https://..."},
        "media": [{"mediaFormat": "PHOTO", "sourceUrl": "https://..."}]
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    if not client.gbp_account_id or not client.gbp_location_id:
        return jsonify({'error': 'GBP location not set'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    location_name = f"accounts/{client.gbp_account_id}/locations/{client.gbp_location_id}"
    
    result = gbp_service.create_post(
        access_token=tokens['access_token'],
        location_name=location_name,
        post_type=data.get('post_type', 'STANDARD'),
        summary=data.get('summary'),
        call_to_action=data.get('call_to_action'),
        media=data.get('media'),
        event=data.get('event'),
        offer=data.get('offer')
    )
    
    return jsonify(result)


@gbp_bp.route('/posts/from-social', methods=['POST'])
@token_required
def post_from_social(current_user):
    """
    Publish an existing social post to GBP
    
    POST /api/gbp/posts/from-social
    {
        "client_id": "xxx",
        "social_post": {
            "text": "...",
            "image_url": "...",
            "link_url": "..."
        }
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    client_id = data.get('client_id')
    social_post = data.get('social_post')
    
    if not client_id or not social_post:
        return jsonify({'error': 'client_id and social_post are required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    if not client.gbp_account_id or not client.gbp_location_id:
        return jsonify({'error': 'GBP location not set'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    location_name = f"accounts/{client.gbp_account_id}/locations/{client.gbp_location_id}"
    
    result = gbp_service.publish_social_post_to_gbp(
        access_token=tokens['access_token'],
        location_name=location_name,
        social_post=social_post
    )
    
    return jsonify(result)


# ==========================================
# Reviews (via GBP API)
# ==========================================

@gbp_bp.route('/reviews', methods=['GET'])
@token_required
def get_gbp_reviews(current_user):
    """Get reviews from GBP"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    if not client.gbp_account_id or not client.gbp_location_id:
        return jsonify({'error': 'GBP location not set'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    location_name = f"accounts/{client.gbp_account_id}/locations/{client.gbp_location_id}"
    result = gbp_service.get_reviews(tokens['access_token'], location_name)
    
    return jsonify(result)


@gbp_bp.route('/reviews/<review_name>/reply', methods=['POST'])
@token_required
def reply_to_gbp_review(current_user, review_name):
    """
    Reply to a GBP review
    
    POST /api/gbp/reviews/{review_name}/reply
    {
        "client_id": "xxx",
        "comment": "Thank you for..."
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    comment = data.get('comment')
    
    if not client_id or not comment:
        return jsonify({'error': 'client_id and comment are required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    result = gbp_service.reply_to_review(
        access_token=tokens['access_token'],
        review_name=review_name,
        comment=comment
    )
    
    return jsonify(result)


# ==========================================
# Q&A
# ==========================================

@gbp_bp.route('/questions', methods=['GET'])
@token_required
def get_questions(current_user):
    """Get Q&A for a location"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    if not client.gbp_account_id or not client.gbp_location_id:
        return jsonify({'error': 'GBP location not set'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    location_name = f"accounts/{client.gbp_account_id}/locations/{client.gbp_location_id}"
    result = gbp_service.get_questions(tokens['access_token'], location_name)
    
    return jsonify(result)


@gbp_bp.route('/questions/<question_name>/answer', methods=['POST'])
@token_required
def answer_question(current_user, question_name):
    """Answer a GBP question"""
    data = request.get_json() or {}
    client_id = data.get('client_id')
    answer = data.get('answer')
    
    if not client_id or not answer:
        return jsonify({'error': 'client_id and answer are required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    result = gbp_service.answer_question(
        access_token=tokens['access_token'],
        question_name=question_name,
        answer_text=answer
    )
    
    return jsonify(result)


# ==========================================
# Insights
# ==========================================

@gbp_bp.route('/insights', methods=['GET'])
@token_required
def get_insights(current_user):
    """Get GBP performance insights"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client or not client.gbp_access_token:
        return jsonify({'error': 'GBP not connected'}), 400
    
    if not client.gbp_account_id or not client.gbp_location_id:
        return jsonify({'error': 'GBP location not set'}), 400
    
    tokens = gbp_service.refresh_access_token(client.gbp_access_token)
    if 'error' in tokens:
        return jsonify(tokens), 400
    
    location_name = f"accounts/{client.gbp_account_id}/locations/{client.gbp_location_id}"
    result = gbp_service.get_insights(tokens['access_token'], location_name)
    
    return jsonify(result)


# ==========================================
# Status Check
# ==========================================

@gbp_bp.route('/status', methods=['GET'])
@token_required
def get_gbp_status(current_user):
    """Check GBP connection status for a client"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    return jsonify({
        'configured': gbp_service.is_configured(),
        'connected': bool(client.gbp_access_token),
        'location_set': bool(client.gbp_account_id and client.gbp_location_id),
        'account_id': client.gbp_account_id,
        'location_id': client.gbp_location_id
    })
