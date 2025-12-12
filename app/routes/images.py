"""
MCP Framework - Image Generation Routes
API for AI-powered image generation
"""
from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import os
import logging

from app.routes.auth import token_required
from app.utils import safe_int
from app.database import db
from app.models.db_models import DBClient
from app.services.image_service import get_image_service, ImageConfig

logger = logging.getLogger(__name__)
images_bp = Blueprint('images', __name__)


# ==========================================
# IMAGE GENERATION
# ==========================================

@images_bp.route('/generate', methods=['POST'])
@token_required
def generate_image(current_user):
    """
    Generate an image from a text prompt
    
    POST /api/images/generate
    {
        "prompt": "A modern dental office with happy patient",
        "client_id": "optional - for organizing images",
        "style": "photorealistic|illustration|minimal|corporate|social_media|blog_header",
        "size": "1024x1024|1792x1024|1024x1792",
        "provider": "auto|dalle|stability|replicate|unsplash",
        "negative_prompt": "optional - what to avoid",
        "quality": "standard|hd"
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400
    
    client_id = data.get('client_id')
    
    # Verify client access if provided
    if client_id:
        client = DBClient.query.get(client_id)
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    try:
        image_service = get_image_service()
        
        result = image_service.generate_image(
            prompt=prompt,
            style=data.get('style', 'photorealistic'),
            size=data.get('size', '1024x1024'),
            provider=data.get('provider', 'auto'),
            negative_prompt=data.get('negative_prompt'),
            quality=data.get('quality', 'standard'),
            client_id=client_id
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }), 500


@images_bp.route('/generate-for-social', methods=['POST'])
@token_required
def generate_social_images(current_user):
    """
    Generate optimized images for multiple social platforms
    
    POST /api/images/generate-for-social
    {
        "topic": "Spring HVAC maintenance tips",
        "client_id": "client_abc123",
        "platforms": ["facebook", "instagram", "linkedin"],
        "style": "social_media"
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    
    topic = data.get('topic')
    if not topic:
        return jsonify({'error': 'topic is required'}), 400
    
    client_id = data.get('client_id')
    
    # Verify client access if provided
    if client_id:
        client = DBClient.query.get(client_id)
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    try:
        image_service = get_image_service()
        
        results = image_service.generate_social_images(
            topic=topic,
            platforms=data.get('platforms'),
            style=data.get('style', 'social_media'),
            client_id=client_id
        )
        
        # Count successes
        success_count = sum(1 for r in results.values() if r.get('success'))
        
        return jsonify({
            'success': success_count > 0,
            'generated_count': success_count,
            'total_platforms': len(results),
            'images': results
        })
        
    except Exception as e:
        logger.error(f"Social image generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }), 500


@images_bp.route('/generate-prompt', methods=['POST'])
@token_required
def generate_image_prompt(current_user):
    """
    Generate an optimized image prompt from a topic
    
    POST /api/images/generate-prompt
    {
        "topic": "Spring roof maintenance",
        "business_type": "roofing",
        "location": "Sarasota, FL",
        "style": "professional"
    }
    """
    data = request.get_json() or {}
    
    topic = data.get('topic')
    if not topic:
        return jsonify({'error': 'topic is required'}), 400
    
    try:
        image_service = get_image_service()
        
        prompt = image_service.generate_image_prompt(
            topic=topic,
            business_type=data.get('business_type'),
            location=data.get('location'),
            style=data.get('style', 'professional')
        )
        
        return jsonify({
            'success': True,
            'prompt': prompt,
            'topic': topic
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }), 500


# ==========================================
# CONFIGURATION & PROVIDERS
# ==========================================

@images_bp.route('/config', methods=['GET'])
@token_required
def get_image_config(current_user):
    """
    Get image generation configuration and available providers
    
    GET /api/images/config
    """
    providers = ImageConfig.get_available_providers()
    
    provider_info = {
        'dalle': {
            'name': 'DALL-E 3',
            'description': 'OpenAI\'s best image model - highest quality',
            'configured': 'dalle' in providers,
            'sizes': ['1024x1024', '1792x1024', '1024x1792'],
            'features': ['HD quality option', 'Prompt revision']
        },
        'stability': {
            'name': 'Stability AI',
            'description': 'Stable Diffusion XL - good quality, fast',
            'configured': 'stability' in providers,
            'sizes': ['1024x1024', '1152x896', '896x1152'],
            'features': ['Negative prompts', 'Custom seeds']
        },
        'replicate': {
            'name': 'Replicate',
            'description': 'Access to SDXL and other models',
            'configured': 'replicate' in providers,
            'sizes': ['1024x1024', '1152x896', '896x1152'],
            'features': ['Multiple models', 'Flexible sizes']
        },
        'unsplash': {
            'name': 'Unsplash',
            'description': 'High-quality stock photos (fallback)',
            'configured': 'unsplash' in providers,
            'sizes': ['Various'],
            'features': ['Free', 'Attribution required']
        }
    }
    
    styles = [
        {'id': 'photorealistic', 'name': 'Photorealistic', 'description': 'Professional photograph look'},
        {'id': 'illustration', 'name': 'Illustration', 'description': 'Digital artwork style'},
        {'id': 'minimal', 'name': 'Minimal', 'description': 'Clean, minimalist design'},
        {'id': 'corporate', 'name': 'Corporate', 'description': 'Professional business imagery'},
        {'id': 'social_media', 'name': 'Social Media', 'description': 'Eye-catching social posts'},
        {'id': 'blog_header', 'name': 'Blog Header', 'description': 'Wide format for articles'},
        {'id': 'product', 'name': 'Product', 'description': 'Product photography style'},
        {'id': 'lifestyle', 'name': 'Lifestyle', 'description': 'Authentic lifestyle shots'},
        {'id': 'abstract', 'name': 'Abstract', 'description': 'Creative abstract art'},
        {'id': 'vintage', 'name': 'Vintage', 'description': 'Retro nostalgic feel'}
    ]
    
    return jsonify({
        'providers': provider_info,
        'available_providers': providers,
        'default_provider': providers[0] if providers else None,
        'styles': styles,
        'default_size': '1024x1024'
    })


# ==========================================
# IMAGE MANAGEMENT
# ==========================================

@images_bp.route('/list', methods=['GET'])
@token_required
def list_images(current_user):
    """
    List generated images
    
    GET /api/images/list?client_id=xxx&limit=50
    """
    client_id = request.args.get('client_id')
    limit = safe_int(request.args.get('limit'), 50, max_val=200)
    
    # Verify client access if filtering by client
    if client_id:
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
    
    # List images from upload directory
    upload_dir = ImageConfig.IMAGE_UPLOAD_DIR
    base_url = ImageConfig.IMAGE_BASE_URL
    
    images = []
    
    if os.path.exists(upload_dir):
        for filename in os.listdir(upload_dir):
            if filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                # Filter by client if specified
                if client_id and not filename.startswith(client_id):
                    continue
                
                filepath = os.path.join(upload_dir, filename)
                stat = os.stat(filepath)
                
                images.append({
                    'filename': filename,
                    'url': f"{base_url}/{filename}",
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
    
    # Sort by creation time, newest first
    images.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'images': images[:limit],
        'total': len(images)
    })


@images_bp.route('/delete/<filename>', methods=['DELETE'])
@token_required
def delete_image(current_user, filename):
    """
    Delete a generated image
    
    DELETE /api/images/delete/{filename}
    """
    if not current_user.can_manage_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    # Security: prevent path traversal
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    filepath = os.path.join(ImageConfig.IMAGE_UPLOAD_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Image not found'}), 404
    
    try:
        os.remove(filepath)
        logger.info(f"Deleted image: {filename}")
        return jsonify({
            'success': True,
            'deleted': filename
        })
    except Exception as e:
        return jsonify({'error': 'An error occurred. Please try again.'}), 500


# ==========================================
# SERVE IMAGES
# ==========================================

@images_bp.route('/view/<filename>', methods=['GET'])
def view_image(filename):
    """
    Serve a generated image
    
    GET /api/images/view/{filename}
    """
    # Security: prevent path traversal
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    filepath = os.path.join(ImageConfig.IMAGE_UPLOAD_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Image not found'}), 404
    
    return send_file(filepath)
