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
    
    data = request.get_json(silent=True) or {}
    
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
        
        # Check if any providers are configured
        available_providers = ImageConfig.get_available_providers()
        logger.info(f"Image generation request - Available providers: {available_providers}")
        
        if not available_providers:
            return jsonify({
                'success': False,
                'error': 'No image providers configured. Add OPENAI_API_KEY for DALL-E or UNSPLASH_ACCESS_KEY for stock photos.'
            }), 400
        
        result = image_service.generate_image(
            prompt=prompt,
            style=data.get('style', 'photorealistic'),
            size=data.get('size', '1024x1024'),
            provider=data.get('provider', 'auto'),
            negative_prompt=data.get('negative_prompt'),
            quality=data.get('quality', 'standard'),
            client_id=client_id
        )
        
        if not result.get('success'):
            logger.error(f"Image generation failed: {result.get('error')}")
        else:
            logger.info(f"Image generated successfully: {result.get('url')}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Image generation failed: {str(e)}'
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
    
    data = request.get_json(silent=True) or {}
    
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
    data = request.get_json(silent=True) or {}
    
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


# ==========================================
# CLIENT IMAGE LIBRARY
# ==========================================

from werkzeug.utils import secure_filename
import uuid

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@images_bp.route('/library/<client_id>', methods=['GET'])
@token_required
def get_client_image_library(current_user, client_id):
    """
    Get all images in a client's library
    
    GET /api/images/library/{client_id}
    Query params:
        category - Filter by category (hero, work, team, logo, etc.)
        limit - Max results (default 50)
    """
    from app.models.db_models import DBClientImage
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    category = request.args.get('category')
    limit = safe_int(request.args.get('limit'), 50)
    
    query = DBClientImage.query.filter_by(client_id=client_id, is_active=True)
    
    if category:
        query = query.filter_by(category=category)
    
    images = query.order_by(DBClientImage.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'images': [img.to_dict() for img in images],
        'count': len(images)
    })


@images_bp.route('/library/<client_id>/upload', methods=['POST'])
@token_required
def upload_to_library(current_user, client_id):
    """
    Upload an image to client's library
    
    POST /api/images/library/{client_id}/upload
    Form data:
        file - The image file
        category - Category (hero, work, team, logo, general)
        title - Optional title
        alt_text - Alt text for SEO
        tags - Comma-separated tags
    """
    from app.models.db_models import DBClientImage
    from flask import current_app
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'File type not allowed. Use: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    try:
        # Read file data
        file_data = file.read()
        file.seek(0)  # Reset for potential local save
        
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower()
        
        logger.info(f"Image upload: client_id={client_id}, filename={original_filename}, size={len(file_data)} bytes")
        
        # Try FTP first if configured
        ftp_result = None
        try:
            from app.services.ftp_storage_service import get_ftp_service
            ftp = get_ftp_service()
            logger.info(f"FTP service obtained, is_configured={ftp.is_configured()}")
            if ftp.is_configured():
                category = request.form.get('category', 'general')
                logger.info(f"Attempting FTP upload: category={category}")
                ftp_result = ftp.upload_file(file_data, original_filename, client_id, category)
                if ftp_result:
                    logger.info(f"Image uploaded to FTP: {ftp_result['file_url']}")
                else:
                    logger.warning(f"FTP upload returned None - will fall back to local storage")
            else:
                logger.info("FTP not configured - using local storage")
        except Exception as e:
            logger.warning(f"FTP upload failed, falling back to local: {e}")
            import traceback
            logger.warning(f"FTP upload traceback: {traceback.format_exc()}")
        
        if ftp_result:
            # Use FTP storage
            file_url = ftp_result['file_url']
            file_path = ftp_result['file_path']
            filename = ftp_result['filename']
            storage_type = 'ftp'
        else:
            # Fall back to local storage
            upload_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'static/uploads'), 'client_images', client_id)
            os.makedirs(upload_dir, exist_ok=True)
            
            filename = f"{uuid.uuid4().hex[:12]}.{ext}"
            file_path = os.path.join(upload_dir, filename)
            
            # Save file locally
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            file_url = f"/static/uploads/client_images/{client_id}/{filename}"
            storage_type = 'local'
        
        # Get file info
        file_size = len(file_data)
        
        # Get image dimensions
        width, height = 0, 0
        try:
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(file_data)) as img:
                width, height = img.size
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Could not get image dimensions: {e}")
        
        # Parse tags
        tags_str = request.form.get('tags', '')
        tags = [t.strip() for t in tags_str.split(',') if t.strip()]
        
        # Create database record
        import json
        image = DBClientImage(
            client_id=client_id,
            filename=filename,
            file_path=file_path,
            original_filename=original_filename,
            file_url=file_url,
            file_size=file_size,
            mime_type=file.content_type or f'image/{ext}',
            width=width,
            height=height,
            title=request.form.get('title'),
            alt_text=request.form.get('alt_text'),
            category=request.form.get('category', 'general'),
            tags=tags,
            uploaded_by=current_user.id
        )
        
        db.session.add(image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Image uploaded successfully ({storage_type})',
            'storage': storage_type,
            'image': image.to_dict()
        }), 201
        
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@images_bp.route('/library/<client_id>/upload-multiple', methods=['POST'])
@token_required
def upload_multiple_to_library(current_user, client_id):
    """
    Upload multiple images to client's library
    
    POST /api/images/library/{client_id}/upload-multiple
    Form data:
        files[] - Multiple image files
        category - Category (hero, work, team, logo, general)
    """
    from app.models.db_models import DBClientImage
    from flask import current_app
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    files = request.files.getlist('files[]')
    if not files or len(files) == 0:
        # Also try 'file' for single file
        files = request.files.getlist('file')
    
    if not files or len(files) == 0:
        return jsonify({'error': 'No files provided'}), 400
    
    category = request.form.get('category', 'general')
    
    # Get FTP service
    ftp = None
    try:
        from app.services.ftp_storage_service import get_ftp_service
        ftp = get_ftp_service()
        if not ftp.is_configured():
            ftp = None
    except Exception as e:
        logger.warning(f"FTP service not available: {e}")
    
    results = []
    errors = []
    
    for file in files:
        if file.filename == '':
            continue
            
        if not allowed_file(file.filename):
            errors.append({'filename': file.filename, 'error': 'File type not allowed'})
            continue
        
        try:
            # Read file data
            file_data = file.read()
            original_filename = secure_filename(file.filename)
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
            
            # Try FTP first
            ftp_result = None
            if ftp:
                try:
                    ftp_result = ftp.upload_file(file_data, original_filename, client_id, category)
                    if ftp_result:
                        logger.info(f"Multi-upload: {original_filename} -> FTP: {ftp_result['file_url']}")
                except Exception as e:
                    logger.warning(f"FTP upload failed for {original_filename}: {e}")
            
            if ftp_result:
                file_url = ftp_result['file_url']
                file_path = ftp_result['file_path']
                filename = ftp_result['filename']
                storage_type = 'ftp'
            else:
                # Fall back to local storage
                upload_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'static/uploads'), 'client_images', client_id)
                os.makedirs(upload_dir, exist_ok=True)
                
                filename = f"{uuid.uuid4().hex[:12]}.{ext}"
                file_path = os.path.join(upload_dir, filename)
                
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                
                file_url = f"/static/uploads/client_images/{client_id}/{filename}"
                storage_type = 'local'
            
            # Get file info
            file_size = len(file_data)
            
            # Get image dimensions
            width, height = 0, 0
            try:
                from PIL import Image
                from io import BytesIO
                with Image.open(BytesIO(file_data)) as img:
                    width, height = img.size
            except:
                pass
            
            # Create database record
            image = DBClientImage(
                client_id=client_id,
                filename=filename,
                file_path=file_path,
                original_filename=original_filename,
                file_url=file_url,
                file_size=file_size,
                mime_type=file.content_type or f'image/{ext}',
                width=width,
                height=height,
                category=category,
                uploaded_by=current_user.id
            )
            
            db.session.add(image)
            db.session.commit()
            
            results.append({
                'filename': original_filename,
                'storage': storage_type,
                'url': file_url,
                'image': image.to_dict()
            })
            
        except Exception as e:
            logger.error(f"Failed to upload {file.filename}: {e}")
            errors.append({'filename': file.filename, 'error': str(e)})
    
    return jsonify({
        'success': len(results) > 0,
        'uploaded': len(results),
        'failed': len(errors),
        'results': results,
        'errors': errors
    }), 201 if results else 400


@images_bp.route('/library/<client_id>/<image_id>', methods=['PUT'])
@token_required
def update_library_image(current_user, client_id, image_id):
    """Update image metadata"""
    from app.models.db_models import DBClientImage
    import json
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    image = DBClientImage.query.filter_by(id=image_id, client_id=client_id).first()
    if not image:
        return jsonify({'error': 'Image not found'}), 404
    
    data = request.get_json(silent=True) or {}
    
    if 'title' in data:
        image.title = data['title']
    if 'alt_text' in data:
        image.alt_text = data['alt_text']
    if 'category' in data:
        image.category = data['category']
    if 'tags' in data:
        image.tags = json.dumps(data['tags'])
    
    db.session.commit()
    
    return jsonify({'success': True, 'image': image.to_dict()})


@images_bp.route('/library/<client_id>/<image_id>', methods=['DELETE'])
@token_required
def delete_library_image(current_user, client_id, image_id):
    """Delete an image from library (soft delete)"""
    from app.models.db_models import DBClientImage
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    image = DBClientImage.query.filter_by(id=image_id, client_id=client_id).first()
    if not image:
        return jsonify({'error': 'Image not found'}), 404
    
    image.is_active = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Image deleted'})


# ==========================================
# FEATURED IMAGE GENERATION
# ==========================================

@images_bp.route('/featured/<client_id>', methods=['POST'])
@token_required
def create_featured_image(current_user, client_id):
    """
    Generate a featured image with text overlay
    
    POST /api/images/featured/{client_id}
    {
        "title": "SEO Title to Overlay",
        "subtitle": "Optional subtitle", 
        "template": "gradient_bottom",
        "source_image_id": "img_xxx",   // Use specific image from library
        "source_image_url": "https://...",  // Or use external URL
        "category": "hero"  // If no source specified, pick from this category
    }
    
    Templates: gradient_bottom, gradient_full, banner_bottom, banner_branded, split_left, minimal
    """
    from app.services.featured_image_service import featured_image_service
    from app.services.data_service import data_service
    from app.models.db_models import DBClientImage
    import json
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    if not featured_image_service.is_available():
        return jsonify({
            'error': 'Featured image generation not available. Install Pillow: pip install Pillow'
        }), 500
    
    data = request.get_json(silent=True) or {}
    
    title = data.get('title')
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    template = data.get('template', 'gradient_bottom')
    subtitle = data.get('subtitle')
    
    # Get client for brand color, phone, and logo
    client = data_service.get_client(client_id)
    brand_color = None
    phone = None
    logo_url = None
    
    if client:
        try:
            integrations = json.loads(client.integrations) if client.integrations else {}
            brand_hex = integrations.get('brand_color')
            if brand_hex:
                brand_hex = brand_hex.lstrip('#')
                brand_color = tuple(int(brand_hex[i:i+2], 16) for i in (0, 2, 4))
            
            # Get phone from client
            phone = client.phone or integrations.get('phone')
            
            # Get logo URL from client
            logo_url = integrations.get('logo_url')
        except (ValueError, TypeError, KeyError):
            pass
    
    # Override with request data if provided
    phone = data.get('phone') or phone
    logo_url = data.get('logo_url') or logo_url
    cta_text = data.get('cta_text')  # Custom CTA text
    
    # Determine source image
    source_image = None
    
    if data.get('source_image_id'):
        img = DBClientImage.query.filter_by(id=data['source_image_id'], client_id=client_id).first()
        if img:
            # Prefer file_path (filesystem) over file_url
            if img.file_path and os.path.exists(img.file_path):
                source_image = img.file_path
            elif img.file_url and img.file_url.startswith('http'):
                source_image = img.file_url
            elif img.file_url and img.file_url.startswith('/static/'):
                # Convert /static/uploads/... to static/uploads/...
                source_image = img.file_url.lstrip('/')
            logger.info(f"Source image for featured: {source_image}")
    
    elif data.get('source_image_url'):
        source_image = data['source_image_url']
    
    else:
        # Pick from client library
        result = featured_image_service.create_from_client_library(
            client_id=client_id,
            title=title,
            category=data.get('category'),
            template=template,
            subtitle=subtitle,
            brand_color=brand_color
        )
        return jsonify(result), 200 if result.get('success') else 400
    
    if not source_image:
        return jsonify({'error': 'No source image provided or found'}), 400
    
    # Pass client_id to service for FTP upload
    featured_image_service._current_client_id = client_id
    
    result = featured_image_service.create_featured_image(
        source_image=source_image,
        title=title,
        template=template,
        subtitle=subtitle,
        brand_color=brand_color,
        phone=phone,
        cta_text=cta_text,
        logo_url=logo_url
    )
    
    return jsonify(result), 200 if result.get('success') else 400


@images_bp.route('/featured/templates', methods=['GET'])
@token_required
def get_featured_templates(current_user):
    """Get available featured image templates"""
    from app.services.featured_image_service import featured_image_service
    
    templates = featured_image_service.get_templates()
    
    return jsonify({
        'templates': [
            {'id': key, 'name': val['name'], 'description': val['description']}
            for key, val in templates.items()
        ]
    })


@images_bp.route('/featured/from-url', methods=['POST'])
@token_required
def create_featured_from_url(current_user):
    """
    Create featured image from an external URL
    
    POST /api/images/featured/from-url
    {
        "image_url": "https://example.com/image.jpg",
        "title": "SEO Title to Overlay",
        "subtitle": "Optional subtitle",
        "template": "gradient_bottom"
    }
    
    This works with external image URLs (Unsplash, Imgur, etc.)
    """
    from app.services.featured_image_service import featured_image_service
    
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    if not featured_image_service.is_available():
        return jsonify({
            'error': 'Featured image generation not available. Install Pillow: pip install Pillow'
        }), 500
    
    data = request.get_json(silent=True) or {}
    
    image_url = data.get('image_url')
    title = data.get('title')
    
    if not image_url:
        return jsonify({'error': 'image_url is required'}), 400
    if not title:
        return jsonify({'error': 'title is required'}), 400
    
    if not image_url.startswith('http'):
        return jsonify({'error': 'image_url must be a valid HTTP/HTTPS URL'}), 400
    
    result = featured_image_service.create_featured_image(
        source_image=image_url,
        title=title,
        template=data.get('template', 'gradient_bottom'),
        subtitle=data.get('subtitle')
    )
    
    return jsonify(result), 200 if result.get('success') else 400


@images_bp.route('/categories', methods=['GET'])
def get_image_categories():
    """Get available image categories"""
    categories = [
        {'id': 'hero', 'name': 'Hero Images', 'description': 'Main banner/header images'},
        {'id': 'work', 'name': 'Work/Projects', 'description': 'Photos of completed work'},
        {'id': 'team', 'name': 'Team', 'description': 'Team member photos'},
        {'id': 'logo', 'name': 'Logos', 'description': 'Company logos and branding'},
        {'id': 'office', 'name': 'Office/Location', 'description': 'Office and location photos'},
        {'id': 'equipment', 'name': 'Equipment', 'description': 'Tools and equipment photos'},
        {'id': 'general', 'name': 'General', 'description': 'Other images'}
    ]
    return jsonify({'categories': categories})


@images_bp.route('/debug', methods=['GET'])
@token_required
def debug_image_config(current_user):
    """
    Debug endpoint to check image generation configuration
    
    GET /api/images/debug
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Admin only'}), 403
    
    import os
    
    providers = ImageConfig.get_available_providers()
    
    return jsonify({
        'available_providers': providers,
        'openai_key_set': bool(os.getenv('OPENAI_API_KEY')),
        'openai_key_length': len(os.getenv('OPENAI_API_KEY', '')),
        'stability_key_set': bool(os.getenv('STABILITY_API_KEY')),
        'replicate_token_set': bool(os.getenv('REPLICATE_API_TOKEN')),
        'unsplash_key_set': bool(os.getenv('UNSPLASH_ACCESS_KEY')),
        'upload_dir': ImageConfig.IMAGE_UPLOAD_DIR,
        'upload_dir_exists': os.path.exists(ImageConfig.IMAGE_UPLOAD_DIR),
        'pillow_available': True  # Would check PIL import
    })


@images_bp.route('/storage/status', methods=['GET'])
@token_required
def get_storage_status(current_user):
    """
    Get current storage configuration status
    
    GET /api/images/storage/status
    """
    import os
    
    # Check SFTP configuration
    sftp_configured = False
    sftp_status = None
    try:
        from app.services.sftp_storage_service import get_sftp_service
        sftp = get_sftp_service()
        sftp_configured = sftp.is_configured()
        if sftp_configured:
            sftp_status = {
                'host': os.getenv('SFTP_HOST', ''),
                'port': os.getenv('SFTP_PORT', '22'),
                'remote_path': os.getenv('SFTP_REMOTE_PATH', '/public_html/uploads'),
                'base_url': os.getenv('SFTP_BASE_URL', '')
            }
    except Exception as e:
        logger.warning(f"SFTP status check failed: {e}")
    
    return jsonify({
        'storage_type': 'sftp' if sftp_configured else 'local',
        'sftp_configured': sftp_configured,
        'sftp_status': sftp_status,
        'local_path': 'static/uploads (ephemeral on Render)',
        'warning': None if sftp_configured else 'Local storage is ephemeral - files will be lost on deploy. Configure SFTP for persistent storage.'
    })


@images_bp.route('/storage/test-sftp', methods=['POST'])
@token_required
def test_sftp_connection(current_user):
    """
    Test SFTP connection
    
    POST /api/images/storage/test-sftp
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from app.services.sftp_storage_service import get_sftp_service
        sftp = get_sftp_service()
        result = sftp.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

