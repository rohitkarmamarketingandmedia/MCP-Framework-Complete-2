"""
MCP Framework - Publishing Routes
WordPress and CMS content publishing
"""
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import token_required
from app.services.cms_service import CMSService
from app.services.social_service import SocialService
from app.services.db_service import DataService
from app.services.wordpress_service import WordPressService
from app.models.db_models import ContentStatus
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

publish_bp = Blueprint('publish', __name__)
cms_service = CMSService()
social_service = SocialService()
data_service = DataService()


@publish_bp.route('/wordpress/test', methods=['POST'])
@token_required
def test_wordpress_connection(current_user):
    """
    Test WordPress connection with provided credentials
    
    POST /api/publish/wordpress/test
    {
        "wordpress_url": "https://example.com",
        "wordpress_user": "admin",
        "wordpress_app_password": "xxxx xxxx xxxx xxxx"
    }
    
    OR
    
    {
        "client_id": "client_xxx"  // Use stored client credentials
    }
    """
    data = request.get_json(silent=True) or {}
    
    # Get credentials either from request or from stored client config
    if data.get('client_id'):
        client = data_service.get_client(data['client_id'])
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        if not current_user.has_access_to_client(data['client_id']):
            return jsonify({'error': 'Access denied'}), 403
        
        integrations = client.get_integrations()
        
        # Get WordPress credentials - check integrations first, then direct fields
        wp_url = integrations.get('wordpress_url') or client.wordpress_url
        wp_user = integrations.get('wordpress_user') or client.wordpress_user
        wp_password = integrations.get('wordpress_app_password') or client.wordpress_app_password
        
        if not wp_url:
            return jsonify({
                'success': False,
                'error': 'WordPress URL not configured',
                'message': 'Please configure WordPress URL in client settings first.'
            }), 400
        
        if not wp_user or not wp_password:
            return jsonify({
                'success': False,
                'error': 'WordPress credentials incomplete',
                'message': 'Please configure WordPress username and application password in client settings.',
                'has_url': bool(wp_url),
                'has_user': bool(wp_user),
                'has_password': bool(wp_password)
            }), 400
    else:
        # Use provided credentials
        wp_url = data.get('wordpress_url')
        wp_user = data.get('wordpress_user')
        wp_password = data.get('wordpress_app_password')
        
        if not all([wp_url, wp_user, wp_password]):
            return jsonify({
                'success': False,
                'error': 'Missing credentials',
                'message': 'Please provide wordpress_url, wordpress_user, and wordpress_app_password'
            }), 400
    
    # Test connection
    try:
        wp_service = WordPressService(
            site_url=wp_url,
            username=wp_user,
            app_password=wp_password
        )
        result = wp_service.test_connection()
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.',
            'message': 'Failed to test WordPress connection'
        }), 500


@publish_bp.route('/wordpress', methods=['POST'])
@token_required
def publish_to_wordpress(current_user):
    """
    Publish content to WordPress
    
    POST /api/publish/wordpress
    {
        "content_id": "content_abc123",
        "status": "publish",
        "categories": ["Roofing", "Tips"],
        "tags": ["roof repair", "maintenance"],
        "featured_image_url": "https://...",
        "custom_wp_url": null
    }
    """
    data = request.get_json(silent=True) or {}
    
    if not data.get('content_id'):
        return jsonify({'error': 'content_id required'}), 400
    
    content = data_service.get_blog_post(data['content_id'])
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get client for WP credentials
    client = data_service.get_client(content.client_id)
    integrations = client.get_integrations() if client else {}
    
    # Use client's WP credentials (support both new and legacy field names)
    wp_url = data.get('custom_wp_url') or integrations.get('wordpress_url') or client.wordpress_url or current_app.config.get('WP_BASE_URL')
    wp_user = integrations.get('wordpress_user') or client.wordpress_user or current_app.config.get('WP_USERNAME')
    wp_password = integrations.get('wordpress_app_password') or integrations.get('wordpress_api_key') or client.wordpress_app_password or current_app.config.get('WP_APP_PASSWORD')
    
    if not wp_url:
        return jsonify({'error': 'WordPress URL not configured for this client'}), 400
    
    if not wp_user or not wp_password:
        return jsonify({'error': 'WordPress credentials not configured for this client'}), 400
    
    # Publish
    result = cms_service.publish_to_wordpress(
        wp_url=wp_url,
        wp_username=wp_user,
        wp_password=wp_password,
        title=content.title,
        body=content.body,
        meta_title=content.meta_title,
        meta_description=content.meta_description,
        status=data.get('status', 'draft'),
        categories=data.get('categories', []),
        tags=data.get('tags', []),
        featured_image_url=data.get('featured_image_url')
    )
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    # Update content with published URL
    content.status = ContentStatus.PUBLISHED
    content.published_at = datetime.utcnow()
    content.published_url = result.get('url', '')
    data_service.save_blog_post(content)
    
    # Send notification to admins
    try:
        from app.services.notification_service import get_notification_service
        notification_service = get_notification_service()
        from app.models.db_models import DBUser
        
        admins = DBUser.query.filter_by(role='admin', is_active=True).all()
        logger.info(f"Sending WordPress publish notifications to {len(admins)} admins")
        
        for admin in admins:
            notification_service.notify_content_published(
                user_id=admin.id,
                client_name=client.business_name if client else 'Unknown',
                content_title=content.title,
                content_url=result.get('url', ''),
                platform='WordPress',
                content_id=content.id,
                client_id=content.client_id
            )
    except Exception as e:
        logger.error(f"Failed to send publish notification: {e}")
        import traceback
        traceback.print_exc()
    
    return jsonify({
        'success': True,
        'post_id': result.get('post_id'),
        'url': result.get('url'),
        'status': data.get('status', 'draft')
    })


@publish_bp.route('/gbp', methods=['POST'])
@token_required
def publish_to_gbp(current_user):
    """
    Publish post to Google Business Profile
    
    POST /api/publish/gbp
    {
        "post_id": "social_abc123",
        "call_to_action": {
            "type": "LEARN_MORE",
            "url": "https://example.com"
        }
    }
    """
    data = request.get_json(silent=True) or {}
    
    if not data.get('post_id'):
        return jsonify({'error': 'post_id required'}), 400
    
    post = data_service.get_social_post(data['post_id'])
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if post.platform != 'gbp':
        return jsonify({'error': 'Post is not a GBP post'}), 400
    
    if not current_user.has_access_to_client(post.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(post.client_id)
    integrations = client.get_integrations() if client else {}
    location_id = integrations.get('gbp_location_id') or current_app.config['GBP_LOCATION_ID']
    
    if not location_id:
        return jsonify({'error': 'GBP Location ID not configured'}), 400
    
    result = social_service.publish_to_gbp(
        location_id=location_id,
        text=post.content,
        cta_type=data.get('call_to_action', {}).get('type'),
        cta_url=data.get('call_to_action', {}).get('url') or post.link_url
    )
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    # Update post status
    post.status = ContentStatus.PUBLISHED
    post.published_at = datetime.utcnow()
    post.published_id = result.get('post_id', '')
    data_service.save_social_post(post)
    
    return jsonify({
        'success': True,
        'gbp_post_id': result.get('post_id')
    })


@publish_bp.route('/facebook', methods=['POST'])
@token_required
def publish_to_facebook(current_user):
    """
    Publish post to Facebook
    
    POST /api/publish/facebook
    {
        "post_id": "social_abc123"
    }
    """
    data = request.get_json(silent=True) or {}
    
    if not data.get('post_id'):
        return jsonify({'error': 'post_id required'}), 400
    
    post = data_service.get_social_post(data['post_id'])
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if post.platform != 'facebook':
        return jsonify({'error': 'Post is not a Facebook post'}), 400
    
    if not current_user.has_access_to_client(post.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    result = social_service.publish_to_facebook(
        page_id=current_app.config['FACEBOOK_PAGE_ID'],
        access_token=current_app.config['FACEBOOK_ACCESS_TOKEN'],
        message=post.content,
        link=post.link_url
    )
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    post.status = ContentStatus.PUBLISHED
    post.published_at = datetime.utcnow()
    post.published_id = result.get('post_id', '')
    data_service.save_social_post(post)
    
    return jsonify({
        'success': True,
        'facebook_post_id': result.get('post_id')
    })


@publish_bp.route('/bulk', methods=['POST'])
@token_required
def bulk_publish(current_user):
    """
    Bulk publish multiple items
    
    POST /api/publish/bulk
    {
        "items": [
            {"type": "content", "id": "content_abc", "destination": "wordpress"},
            {"type": "social", "id": "social_xyz", "destination": "facebook"}
        ]
    }
    """
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    
    results = []
    for item in items:
        item_type = item.get('type')
        item_id = item.get('id')
        destination = item.get('destination')
        
        try:
            if item_type == 'content' and destination == 'wordpress':
                # Publish content to WordPress
                content = data_service.get_blog_post(item_id)
                if content and current_user.has_access_to_client(content.client_id):
                    result = cms_service.publish_to_wordpress(
                        wp_url=current_app.config['WP_BASE_URL'],
                        wp_username=current_app.config['WP_USERNAME'],
                        wp_password=current_app.config['WP_APP_PASSWORD'],
                        title=content.title,
                        body=content.body,
                        meta_title=content.meta_title,
                        meta_description=content.meta_description,
                        status='publish'
                    )
                    results.append({
                        'id': item_id,
                        'success': not result.get('error'),
                        'url': result.get('url'),
                        'error': result.get('error')
                    })
                else:
                    results.append({'id': item_id, 'success': False, 'error': 'Not found or no access'})
            
            elif item_type == 'social':
                post = data_service.get_social_post(item_id)
                if post and current_user.has_access_to_client(post.client_id):
                    # Route to appropriate platform
                    if destination == 'facebook':
                        result = social_service.publish_to_facebook(
                            page_id=current_app.config['FACEBOOK_PAGE_ID'],
                            access_token=current_app.config['FACEBOOK_ACCESS_TOKEN'],
                            message=post.content,
                            link=post.link_url
                        )
                    elif destination == 'gbp':
                        client = data_service.get_client(post.client_id)
                        integrations = client.get_integrations() if client else {}
                        result = social_service.publish_to_gbp(
                            location_id=integrations.get('gbp_location_id'),
                            text=post.content
                        )
                    else:
                        result = {'error': f'Unsupported destination: {destination}'}
                    
                    results.append({
                        'id': item_id,
                        'success': not result.get('error'),
                        'error': result.get('error')
                    })
                else:
                    results.append({'id': item_id, 'success': False, 'error': 'Not found or no access'})
            else:
                results.append({'id': item_id, 'success': False, 'error': 'Invalid type'})
        
        except Exception as e:
            results.append({'id': item_id, 'success': False, 'error': 'An error occurred. Please try again.'})
    
    return jsonify({
        'total': len(items),
        'successful': sum(1 for r in results if r.get('success')),
        'results': results
    })


@publish_bp.route('/status/<content_id>', methods=['GET'])
@token_required
def get_publish_status(current_user, content_id):
    """Get publishing status for content"""
    content = data_service.get_blog_post(content_id)
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'content_id': content_id,
        'status': content.status,
        'published_at': content.published_at.isoformat() if content.published_at else None,
        'published_url': content.published_url
    })
