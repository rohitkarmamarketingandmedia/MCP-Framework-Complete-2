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
import logging

logger = logging.getLogger(__name__)

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
    
    data = request.get_json(silent=True) or {}
    
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
    errors = []
    
    for platform in platforms:
        result = ai_service.generate_social_post(
            topic=data['topic'],
            platform=platform,
            business_name=client.business_name or '',
            industry=client.industry or '',
            geo=client.geo or '',
            tone=data.get('tone', client.tone) or 'friendly',
            include_hashtags=data.get('include_hashtags', True),
            hashtag_count=data.get('hashtag_count', 5),
            link_url=data.get('link_url', '')
        )
        
        # Check for AI errors
        if result.get('error'):
            errors.append(f"{platform}: {result['error']}")
            continue
        
        # Check for empty content
        if not result.get('text'):
            errors.append(f"{platform}: No content generated")
            continue
        
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
    
    # Return results with any errors
    response = {
        'success': len(posts) > 0,
        'posts': [p.to_dict() for p in posts],
        'generated': len(posts),
        'requested': len(platforms)
    }
    
    if errors:
        response['errors'] = errors
        response['warning'] = f'{len(errors)} platform(s) failed to generate'
    
    return jsonify(response)


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
    
    data = request.get_json(silent=True) or {}
    
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
        business_name=client.business_name or '',
        industry=client.industry or '',
        geo=client.geo or '',
        tone=client.tone or 'friendly',
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
    
    data = request.get_json(silent=True) or {}
    
    if 'content' in data:
        post.content = data['content']
    if 'hashtags' in data:
        post.hashtags = json.dumps(data['hashtags'])
    if 'cta_type' in data:
        post.cta_type = data['cta_type']
    if 'status' in data:
        post.status = data['status']
    if 'scheduled_for' in data:
        try:
            post.scheduled_for = datetime.fromisoformat(data['scheduled_for'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid scheduled_for date format'}), 400
    
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
    data = request.get_json(silent=True) or {}
    
    if not data.get('post_ids') or not data.get('scheduled_at'):
        return jsonify({'error': 'post_ids and scheduled_at required'}), 400
    
    try:
        scheduled_at = datetime.fromisoformat(data['scheduled_at'].replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use ISO format.'}), 400
    
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


@social_bp.route('/bulk-delete', methods=['POST'])
@token_required
def bulk_delete_social(current_user):
    """
    Bulk delete social posts
    
    POST /api/social/bulk-delete
    {
        "ids": ["id1", "id2", "id3"]
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    
    deleted = 0
    
    for post_id in ids:
        try:
            post = data_service.get_social_post(post_id)
            if post and current_user.has_access_to_client(post.client_id):
                data_service.delete_social_post(post_id)
                deleted += 1
        except Exception:
            pass
    
    return jsonify({
        'deleted': deleted,
        'message': f'Deleted {deleted} posts'
    })


# ============================================
# Social Connection Management
# ============================================

@social_bp.route('/connections/<client_id>', methods=['GET'])
@token_required
def get_social_connections(current_user, client_id):
    """
    Get social media connection status for a client
    
    GET /api/social/connections/{client_id}
    """
    from app.models.db_models import DBClient
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    connections = {
        'gbp': {
            'platform': 'Google Business Profile',
            'connected': bool(client.gbp_location_id and client.gbp_access_token),
            'location_id': client.gbp_location_id,
            'icon': 'fab fa-google',
            'color': '#4285F4'
        },
        'facebook': {
            'platform': 'Facebook',
            'connected': bool(client.facebook_page_id and client.facebook_access_token),
            'page_id': client.facebook_page_id,
            'connected_at': client.facebook_connected_at.isoformat() if client.facebook_connected_at else None,
            'icon': 'fab fa-facebook',
            'color': '#1877F2'
        },
        'instagram': {
            'platform': 'Instagram',
            'connected': bool(client.instagram_account_id and client.instagram_access_token),
            'account_id': client.instagram_account_id,
            'connected_at': client.instagram_connected_at.isoformat() if client.instagram_connected_at else None,
            'icon': 'fab fa-instagram',
            'color': '#E4405F'
        },
        'linkedin': {
            'platform': 'LinkedIn',
            'connected': bool(client.linkedin_org_id and client.linkedin_access_token),
            'org_id': client.linkedin_org_id,
            'connected_at': client.linkedin_connected_at.isoformat() if client.linkedin_connected_at else None,
            'icon': 'fab fa-linkedin',
            'color': '#0A66C2'
        }
    }
    
    connected_count = sum(1 for c in connections.values() if c['connected'])
    
    return jsonify({
        'client_id': client_id,
        'connections': connections,
        'connected_count': connected_count,
        'total_platforms': 4
    })


@social_bp.route('/connect/<client_id>/<platform>', methods=['POST'])
@token_required
def connect_platform(current_user, client_id, platform):
    """
    Connect a social platform for a client
    
    POST /api/social/connect/{client_id}/{platform}
    {
        "access_token": "...",
        "page_id": "..." (for Facebook),
        "account_id": "..." (for Instagram),
        "org_id": "..." (for LinkedIn),
        "location_id": "..." (for GBP)
    }
    """
    from app.database import db
    from app.models.db_models import DBClient
    
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    access_token = data.get('access_token')
    
    if not access_token:
        return jsonify({'error': 'Access token required'}), 400
    
    platform = platform.lower()
    
    try:
        if platform == 'facebook':
            page_id = data.get('page_id')
            if not page_id:
                return jsonify({'error': 'Facebook Page ID required'}), 400
            
            client.facebook_page_id = page_id
            client.facebook_access_token = access_token
            client.facebook_connected_at = datetime.utcnow()
            
        elif platform == 'instagram':
            account_id = data.get('account_id')
            if not account_id:
                return jsonify({'error': 'Instagram Account ID required'}), 400
            
            client.instagram_account_id = account_id
            client.instagram_access_token = access_token
            client.instagram_connected_at = datetime.utcnow()
            
        elif platform == 'linkedin':
            org_id = data.get('org_id')
            if not org_id:
                return jsonify({'error': 'LinkedIn Organization ID required'}), 400
            
            client.linkedin_org_id = org_id
            client.linkedin_access_token = access_token
            client.linkedin_connected_at = datetime.utcnow()
            
        elif platform in ['gbp', 'google']:
            location_id = data.get('location_id')
            account_id = data.get('account_id')
            
            if not location_id:
                return jsonify({'error': 'GBP Location ID required'}), 400
            
            client.gbp_location_id = location_id
            client.gbp_account_id = account_id
            client.gbp_access_token = access_token
            
        else:
            return jsonify({'error': f'Unknown platform: {platform}'}), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{platform.title()} connected successfully',
            'platform': platform,
            'connected_at': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Connection failed. Please check your settings and try again.'}), 500


@social_bp.route('/disconnect/<client_id>/<platform>', methods=['POST'])
@token_required
def disconnect_platform(current_user, client_id, platform):
    """
    Disconnect a social platform from a client
    
    POST /api/social/disconnect/{client_id}/{platform}
    """
    from app.database import db
    from app.models.db_models import DBClient
    
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    platform = platform.lower()
    
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
            client.gbp_account_id = None
            client.gbp_access_token = None
            
        else:
            return jsonify({'error': f'Unknown platform: {platform}'}), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{platform.title()} disconnected',
            'platform': platform
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Disconnect failed. Please try again.'}), 500


@social_bp.route('/test/<client_id>/<platform>', methods=['POST'])
@token_required
def test_platform_connection(current_user, client_id, platform):
    """
    Test a social platform connection
    
    POST /api/social/test/{client_id}/{platform}
    """
    from app.models.db_models import DBClient
    import requests as http_requests
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    platform = platform.lower()
    
    try:
        if platform == 'facebook':
            if not client.facebook_page_id or not client.facebook_access_token:
                return jsonify({'connected': False, 'error': 'Not connected'}), 200
            
            response = http_requests.get(
                f'https://graph.facebook.com/v18.0/{client.facebook_page_id}',
                params={'access_token': client.facebook_access_token, 'fields': 'name,id'},
                timeout=10
            )
            
            if response.ok:
                data = response.json()
                return jsonify({
                    'connected': True,
                    'platform': 'Facebook',
                    'page_name': data.get('name'),
                    'page_id': data.get('id')
                })
            else:
                return jsonify({'connected': False, 'error': 'Token expired or invalid'})
                
        elif platform == 'instagram':
            if not client.instagram_account_id or not client.instagram_access_token:
                return jsonify({'connected': False, 'error': 'Not connected'}), 200
            
            response = http_requests.get(
                f'https://graph.facebook.com/v18.0/{client.instagram_account_id}',
                params={'access_token': client.instagram_access_token, 'fields': 'username,id'},
                timeout=10
            )
            
            if response.ok:
                data = response.json()
                return jsonify({
                    'connected': True,
                    'platform': 'Instagram',
                    'username': data.get('username'),
                    'account_id': data.get('id')
                })
            else:
                return jsonify({'connected': False, 'error': 'Token expired or invalid'})
                
        elif platform == 'linkedin':
            if not client.linkedin_org_id or not client.linkedin_access_token:
                return jsonify({'connected': False, 'error': 'Not connected'}), 200
            
            response = http_requests.get(
                f'https://api.linkedin.com/v2/organizations/{client.linkedin_org_id}',
                headers={
                    'Authorization': f'Bearer {client.linkedin_access_token}',
                    'X-Restli-Protocol-Version': '2.0.0'
                },
                timeout=10
            )
            
            if response.ok:
                data = response.json()
                return jsonify({
                    'connected': True,
                    'platform': 'LinkedIn',
                    'org_name': data.get('localizedName'),
                    'org_id': client.linkedin_org_id
                })
            else:
                return jsonify({'connected': False, 'error': 'Token expired or invalid'})
                
        elif platform in ['gbp', 'google']:
            if not client.gbp_location_id or not client.gbp_access_token:
                return jsonify({'connected': False, 'error': 'Not connected'}), 200
            
            return jsonify({
                'connected': True,
                'platform': 'Google Business Profile',
                'location_id': client.gbp_location_id,
                'note': 'Full verification requires OAuth flow'
            })
            
        else:
            return jsonify({'error': f'Unknown platform: {platform}'}), 400
            
    except Exception as e:
        return jsonify({'connected': False, 'error': 'An error occurred. Please try again.'})


@social_bp.route('/publish-now/<client_id>', methods=['POST'])
@token_required
def publish_now(current_user, client_id):
    """
    Publish content immediately to specified platforms
    
    POST /api/social/publish-now/{client_id}
    {
        "platforms": ["facebook", "instagram", "linkedin", "gbp"],
        "content": "Post content here",
        "image_url": "https://...",
        "link_url": "https://..."
    }
    """
    from app.models.db_models import DBClient
    
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    platforms = data.get('platforms', [])
    content = data.get('content', '')
    image_url = data.get('image_url')
    link_url = data.get('link_url')
    
    if not platforms:
        return jsonify({'error': 'No platforms specified'}), 400
    if not content:
        return jsonify({'error': 'Content required'}), 400
    
    results = {}
    
    for platform in platforms:
        platform = platform.lower()
        
        try:
            if platform == 'facebook':
                if not client.facebook_page_id or not client.facebook_access_token:
                    results['facebook'] = {'success': False, 'error': 'Not connected'}
                    continue
                    
                result = social_service.publish_to_facebook(
                    page_id=client.facebook_page_id,
                    access_token=client.facebook_access_token,
                    message=content,
                    link=link_url,
                    image_url=image_url
                )
                results['facebook'] = result
                
            elif platform == 'instagram':
                if not client.instagram_account_id or not client.instagram_access_token:
                    results['instagram'] = {'success': False, 'error': 'Not connected'}
                    continue
                if not image_url:
                    results['instagram'] = {'success': False, 'error': 'Image required for Instagram'}
                    continue
                    
                result = social_service.publish_to_instagram(
                    account_id=client.instagram_account_id,
                    access_token=client.instagram_access_token,
                    image_url=image_url,
                    caption=content
                )
                results['instagram'] = result
                
            elif platform == 'linkedin':
                if not client.linkedin_org_id or not client.linkedin_access_token:
                    results['linkedin'] = {'success': False, 'error': 'Not connected'}
                    continue
                    
                result = social_service.publish_to_linkedin(
                    organization_id=client.linkedin_org_id,
                    access_token=client.linkedin_access_token,
                    text=content,
                    link=link_url
                )
                results['linkedin'] = result
                
            elif platform in ['gbp', 'google']:
                if not client.gbp_location_id or not client.gbp_access_token:
                    results['gbp'] = {'success': False, 'error': 'Not connected'}
                    continue
                    
                result = social_service.publish_to_gbp(
                    location_id=client.gbp_location_id,
                    text=content,
                    image_url=image_url,
                    access_token=client.gbp_access_token
                )
                results['gbp'] = result
                
        except Exception as e:
            import traceback
            logger.error(f"Social publish error for {platform}: {e}")
            logger.error(traceback.format_exc())
            results[platform] = {'success': False, 'error': str(e)}
    
    successful = sum(1 for r in results.values() if r.get('success'))
    
    return jsonify({
        'success': successful > 0,
        'published_count': successful,
        'total_platforms': len(platforms),
        'results': results
    })
