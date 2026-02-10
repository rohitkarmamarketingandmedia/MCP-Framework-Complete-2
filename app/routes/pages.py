"""
MCP Framework - Service Pages API Routes
Generate and manage service/location landing pages
"""
from flask import Blueprint, request, jsonify, Response
from datetime import datetime

from app.routes.auth import token_required
from app.services.service_page_generator import service_page_generator
from app.models.db_models import DBServicePage, DBClient
from app.database import db

pages_bp = Blueprint('pages', __name__)


# ==========================================
# Page Generation
# ==========================================

@pages_bp.route('/generate', methods=['POST'])
@token_required
def generate_page(current_user):
    """
    Generate a service/landing page (unified endpoint)
    
    POST /api/pages/generate
    {
        "client_id": "client_xxx",
        "page_type": "service|location|landing|about|contact",
        "service": "roof repair",
        "location": "Sarasota, FL",
        "title": "Custom Title (optional)",
        "word_count": 1200,
        "include_faq": true,
        "include_cta": true,
        "include_schema": true
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    page_type = data.get('page_type', 'service')
    service = data.get('service')
    location = data.get('location')
    custom_title = data.get('title')
    word_count = data.get('word_count', 1200)
    include_faq = data.get('include_faq', True)
    include_cta = data.get('include_cta', True)
    include_schema = data.get('include_schema', True)
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Set up AI service
    try:
        from app.services.ai_service import ai_service
        service_page_generator.set_ai_service(ai_service)
    except Exception as e:
        pass
    
    # Use client geo if no location specified
    if not location:
        location = client.geo
    
    # Generate based on page type
    try:
        if page_type == 'location':
            result = service_page_generator.generate_location_page(
                client=client,
                location=location,
                services=client.get_services()[:5] if hasattr(client, 'get_services') else None
            )
        elif page_type in ['about', 'contact', 'landing']:
            # For now, use service page generator with modified title
            page_titles = {
                'about': f'About {client.business_name}',
                'contact': f'Contact {client.business_name}',
                'landing': custom_title or f'{client.business_name} - {location}'
            }
            result = service_page_generator.generate_service_page(
                client=client,
                service=page_titles.get(page_type, custom_title or page_type),
                location=location,
                additional_context={
                    'word_count': word_count,
                    'include_faq': include_faq,
                    'include_cta': include_cta,
                    'include_schema': include_schema,
                    'custom_title': page_titles.get(page_type, custom_title),
                    'page_type': page_type
                }
            )
        else:
            # Default: service page
            if not service:
                return jsonify({'error': 'service is required for service pages'}), 400
            
            result = service_page_generator.generate_service_page(
                client=client,
                service=service,
                location=location,
                additional_context={
                    'word_count': word_count,
                    'include_faq': include_faq,
                    'include_cta': include_cta,
                    'include_schema': include_schema,
                    'custom_title': custom_title
                }
            )
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@pages_bp.route('/generate/service', methods=['POST'])
@token_required
def generate_service_page(current_user):
    """
    Generate a service landing page
    
    POST /api/pages/generate/service
    {
        "client_id": "client_xxx",
        "service": "roof repair",
        "location": "Sarasota, FL"  // optional, defaults to client geo
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    service = data.get('service')
    
    if not client_id or not service:
        return jsonify({'error': 'client_id and service are required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Set up AI service if available
    try:
        from app.services.ai_service import ai_service
        service_page_generator.set_ai_service(ai_service)
    except Exception as e:
        pass
    
    result = service_page_generator.generate_service_page(
        client=client,
        service=service,
        location=data.get('location'),
        additional_context=data.get('context')
    )
    
    return jsonify(result)


@pages_bp.route('/generate/location', methods=['POST'])
@token_required
def generate_location_page(current_user):
    """
    Generate a location landing page
    
    POST /api/pages/generate/location
    {
        "client_id": "client_xxx",
        "location": "Bradenton, FL",
        "services": ["roof repair", "new roof"]  // optional
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    location = data.get('location')
    
    if not client_id or not location:
        return jsonify({'error': 'client_id and location are required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Set up AI service if available
    try:
        from app.services.ai_service import ai_service
        service_page_generator.set_ai_service(ai_service)
    except Exception as e:
        pass
    
    result = service_page_generator.generate_location_page(
        client=client,
        location=location,
        services=data.get('services')
    )
    
    return jsonify(result)


@pages_bp.route('/generate/bulk', methods=['POST'])
@token_required
def generate_bulk_pages(current_user):
    """
    Generate multiple service and location pages
    
    POST /api/pages/generate/bulk
    {
        "client_id": "client_xxx",
        "services": ["roof repair", "new roof", "storm damage"],
        "locations": ["Bradenton, FL", "Venice, FL"]
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Set up AI service if available
    try:
        from app.services.ai_service import ai_service
        service_page_generator.set_ai_service(ai_service)
    except Exception as e:
        pass
    
    result = service_page_generator.generate_bulk_pages(
        client=client,
        services=data.get('services'),
        locations=data.get('locations')
    )
    
    return jsonify(result)


# ==========================================
# Page Management
# ==========================================

@pages_bp.route('/', methods=['GET'])
@token_required
def get_pages(current_user):
    """
    Get service pages for a client
    
    GET /api/pages?client_id=xxx&type=service&status=draft
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    page_type = request.args.get('type')
    status = request.args.get('status')
    
    pages = service_page_generator.get_client_pages(
        client_id=client_id,
        page_type=page_type,
        status=status
    )
    
    return jsonify({
        'pages': pages,
        'total': len(pages)
    })


@pages_bp.route('/<page_id>', methods=['GET'])
@token_required
def get_page(current_user, page_id):
    """Get full page content"""
    page = service_page_generator.get_full_page(page_id)
    
    if not page:
        return jsonify({'error': 'Page not found'}), 404
    
    if not current_user.has_access_to_client(page['client_id']):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({'page': page})


@pages_bp.route('/<page_id>', methods=['PUT'])
@token_required
def update_page(current_user, page_id):
    """
    Update page content
    
    PUT /api/pages/<page_id>
    {
        "hero_headline": "New headline",
        "body_content": "Updated content...",
        "status": "published"
    }
    """
    page = DBServicePage.query.get(page_id)
    
    if not page:
        return jsonify({'error': 'Page not found'}), 404
    
    if not current_user.has_access_to_client(page.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    # Update allowed fields
    updatable = [
        'hero_headline', 'hero_subheadline', 'intro_text', 'body_content',
        'cta_headline', 'cta_button_text', 'form_headline', 'trust_badges',
        'meta_title', 'meta_description', 'status'
    ]
    
    for field in updatable:
        if field in data:
            setattr(page, field, data[field])
    
    page.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'page': service_page_generator.get_full_page(page_id)
    })


@pages_bp.route('/<page_id>', methods=['DELETE'])
@token_required
def delete_page(current_user, page_id):
    """Delete a service page"""
    page = DBServicePage.query.get(page_id)
    
    if not page:
        return jsonify({'error': 'Page not found'}), 404
    
    if not current_user.has_access_to_client(page.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    db.session.delete(page)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Page deleted'})


# ==========================================
# Export
# ==========================================

@pages_bp.route('/<page_id>/export', methods=['GET'])
@token_required
def export_page(current_user, page_id):
    """
    Export page as standalone HTML
    
    GET /api/pages/<page_id>/export?include_form=true
    """
    page = DBServicePage.query.get(page_id)
    
    if not page:
        return jsonify({'error': 'Page not found'}), 404
    
    if not current_user.has_access_to_client(page.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(page.client_id)
    include_form = request.args.get('include_form', 'true').lower() == 'true'
    
    html = service_page_generator.export_page_html(page_id, client, include_form)
    
    if request.args.get('download') == 'true':
        return Response(
            html,
            mimetype='text/html',
            headers={'Content-Disposition': f'attachment; filename={page.slug}.html'}
        )
    
    return jsonify({'html': html})


# ==========================================
# Preview
# ==========================================

@pages_bp.route('/<page_id>/preview', methods=['GET'])
@token_required
def preview_page(current_user, page_id):
    """
    Get page preview HTML (renders in iframe)
    """
    page = DBServicePage.query.get(page_id)
    
    if not page:
        return jsonify({'error': 'Page not found'}), 404
    
    if not current_user.has_access_to_client(page.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(page.client_id)
    html = service_page_generator.export_page_html(page_id, client, include_form=True)
    
    return Response(html, mimetype='text/html')


@pages_bp.route('/refine', methods=['POST'])
@token_required
def refine_page_content(current_user):
    """
    Refine page content using AI
    
    POST /api/pages/refine
    {
        "page_id": "...",
        "current_content": {...},
        "refinement_prompt": "make it more persuasive",
        "client_id": "..."
    }
    """
    data = request.get_json(silent=True) or {}
    current_content = data.get('current_content', {})
    prompt = data.get('refinement_prompt', '')
    client_id = data.get('client_id')
    
    if not prompt:
        return jsonify({'error': 'refinement_prompt is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    try:
        from app.services.ai_service import ai_service
        
        # Build the refinement prompt
        refine_prompt = f"""You are an expert copywriter refining service page content.

CURRENT CONTENT:
- Title: {current_content.get('title', '')}
- Hero Headline: {current_content.get('hero_headline', '')}
- Subheadline: {current_content.get('hero_subheadline', '')}
- Introduction: {current_content.get('intro_text', '')}
- Body Content: {current_content.get('body_content', '')}
- CTA Headline: {current_content.get('cta_headline', '')}
- Meta Title: {current_content.get('meta_title', '')}
- Meta Description: {current_content.get('meta_description', '')}

BUSINESS CONTEXT:
- Business: {client.business_name}
- Industry: {client.industry}
- Location: {client.geo}

REFINEMENT REQUEST: {prompt}

Return the refined content as JSON with these exact keys:
- title
- hero_headline
- hero_subheadline
- intro_text
- body_content
- cta_headline
- meta_title (max 70 chars)
- meta_description (max 160 chars)

Keep the same structure but apply the requested changes. Return ONLY valid JSON, no markdown."""

        result = ai_service.generate_raw(refine_prompt, max_tokens=3000)
        
        # Parse JSON response
        if isinstance(result, str):
            result = result.replace('```json', '').replace('```', '').strip()
            import json
            result = json.loads(result)
        
        return jsonify({
            'success': True,
            'refined_content': result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
