"""
MCP Framework - Social Media Routes
Social post generation for GBP, Facebook, Instagram, LinkedIn
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.ai_service import AIService
from app.services.social_service import SocialService
from app.services.db_service import DataService
from app.models.db_models import DBSocialPost, ContentStatus
from datetime import datetime
import json

social_bp = Blueprint('social', __name__)
ai_service = AIService()
social_service = SocialService()
data_service = DataService()


@social_bp.route('/generate', methods=['POST'])
@token_required
def generate_social(current_user):
    """
    Generate social media posts
    
    POST /api/social/generate
    {
        "client_id": "client_abc123",
        "topic": "Spring roof maintenance tips",
        "link_url": "https://example.com/blog/spring-roof-tips",
        "platforms": ["gbp", "facebook", "instagram"],
        "tone": "friendly",
        "include_hashtags": true,
        "hashtag_count": 5
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    required = ['client_id', 'topic']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    client = data_service.get_client(data['client_id'])
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(data['client_id']):
        return jsonify({'error': 'Access denied'}), 403
    
    platforms = data.get('platforms', ['gbp', 'facebook', 'instagram'])
    
    # Generate content for each platform
    posts = []
    for platform in platforms:
        result = ai_service.generate_social_post(
            topic=data['topic'],
            platform=platform,
            business_name=client.business_name,
            industry=client.industry,
            geo=client.geo,
            tone=data.get('tone', client.tone),
            include_hashtags=data.get('include_hashtags', True),
            hashtag_count=data.get('hashtag_count', 5),
            link_url=data.get('link_url', '')
        )
        
        post = DBSocialPost(
            client_id=data['client_id'],
            platform=platform,
            content=result.get('text', ''),
            hashtags=result.get('hashtags', []),
            link_url=data.get('link_url'),
            cta_type=result.get('cta', ''),
            status=ContentStatus.DRAFT
        )
        
        data_service.save_social_post(post)
        posts.append(post)
    
    return jsonify({
        'success': True,
        'posts': [p.to_dict() for p in posts]
    })


@social_bp.route('/kit', methods=['POST'])
@token_required
def generate_social_kit(current_user):
    """
    Generate complete social media kit (all platforms at once)
    
    POST /api/social/kit
    {
        "client_id": "client_abc123",
        "content_id": "content_xyz789",
        "custom_topic": null
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    if not data.get('client_id'):
        return jsonify({'error': 'client_id required'}), 400
    
    client = data_service.get_client(data['client_id'])
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(data['client_id']):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get topic from content or custom
    topic = data.get('custom_topic')
    link_url = ''
    
    if data.get('content_id') and not topic:
        content = data_service.get_blog_post(data['content_id'])
        if content:
            topic = content.title
            link_url = content.published_url or ''
    
    if not topic:
        return jsonify({'error': 'topic required (provide content_id or custom_topic)'}), 400
    
    # Generate for all platforms
    platforms = ['gbp', 'facebook', 'instagram', 'linkedin']
    kit = ai_service.generate_social_kit(
        topic=topic,
        business_name=client.business_name,
        industry=client.industry,
        geo=client.geo,
        tone=client.tone,
        link_url=link_url,
        platforms=platforms
    )
    
    # Save posts
    saved_posts = []
    for platform, post_data in kit.items():
        post = DBSocialPost(
            client_id=data['client_id'],
            platform=platform,
            content=post_data.get('text', ''),
            hashtags=post_data.get('hashtags', []),
            link_url=link_url if link_url else None,
            cta_type=post_data.get('cta', ''),
            status=ContentStatus.DRAFT
        )
        data_service.save_social_post(post)
        saved_posts.append(post)
    
    return jsonify({
        'success': True,
        'topic': topic,
        'kit': {
            p.platform: p.to_dict()
            for p in saved_posts
        }
    })


@social_bp.route('/<post_id>', methods=['GET'])
@token_required
def get_social_post(current_user, post_id):
    """Get social post by ID"""
    post = data_service.get_social_post(post_id)
    
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if not current_user.has_access_to_client(post.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(post.to_dict())


@social_bp.route('/<post_id>', methods=['PUT'])
@token_required
def update_social_post(current_user, post_id):
    """Update social post"""
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    post = data_service.get_social_post(post_id)
    
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if not current_user.has_access_to_client(post.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    
    if 'content' in data:
        post.content = data['content']
    if 'hashtags' in data:
        post.hashtags = json.dumps(data['hashtags'])
    if 'cta_type' in data:
        post.cta_type = data['cta_type']
    if 'status' in data:
        post.status = data['status']
    if 'scheduled_for' in data:
        post.scheduled_for = datetime.fromisoformat(data['scheduled_for'].replace('Z', '+00:00'))
    
    data_service.save_social_post(post)
    
    return jsonify({
        'message': 'Post updated',
        'post': post.to_dict()
    })


@social_bp.route('/<post_id>', methods=['DELETE'])
@token_required
def delete_social_post(current_user, post_id):
    """Delete social post"""
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    post = data_service.get_social_post(post_id)
    
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if not current_user.has_access_to_client(post.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data_service.delete_social_post(post_id)
    
    return jsonify({'message': 'Post deleted'})


@social_bp.route('/client/<client_id>', methods=['GET'])
@token_required
def list_client_posts(current_user, client_id):
    """List all social posts for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    platform_filter = request.args.get('platform')
    
    posts = data_service.get_client_social_posts(client_id, platform=platform_filter)
    
    # Optional status filter
    status_filter = request.args.get('status')
    if status_filter:
        posts = [p for p in posts if p.status == status_filter]
    
    return jsonify({
        'client_id': client_id,
        'total': len(posts),
        'posts': [p.to_dict() for p in posts]
    })


@social_bp.route('/schedule', methods=['POST'])
@token_required
def schedule_posts(current_user):
    """
    Schedule posts for publishing
    
    POST /api/social/schedule
    {
        "post_ids": ["social_abc", "social_xyz"],
        "scheduled_at": "2024-03-15T10:00:00Z"
    }
    """
    data = request.get_json()
    
    if not data.get('post_ids') or not data.get('scheduled_at'):
        return jsonify({'error': 'post_ids and scheduled_at required'}), 400
    
    scheduled_at = datetime.fromisoformat(data['scheduled_at'].replace('Z', '+00:00'))
    
    results = []
    for post_id in data['post_ids']:
        post = data_service.get_social_post(post_id)
        if post and current_user.has_access_to_client(post.client_id):
            post.scheduled_for = scheduled_at
            post.status = ContentStatus.APPROVED
            data_service.save_social_post(post)
            results.append({'id': post_id, 'scheduled': True})
        else:
            results.append({'id': post_id, 'scheduled': False, 'error': 'Not found or no access'})
    
    return jsonify({
        'scheduled_at': scheduled_at.isoformat(),
        'results': results
    })
