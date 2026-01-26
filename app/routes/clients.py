"""
MCP Framework - Client Management Routes
CRUD operations for marketing clients
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required, admin_required
from app.services.db_service import DataService
from app.models.db_models import DBClient, UserRole
from datetime import datetime
import json

clients_bp = Blueprint('clients', __name__)
data_service = DataService()


@clients_bp.route('/', methods=['GET'])
@token_required
def list_clients(current_user):
    """List all clients (filtered by user access)"""
    if current_user.role in [UserRole.ADMIN, UserRole.MANAGER]:
        clients = data_service.get_all_clients()
    else:
        clients = [
            data_service.get_client(cid) 
            for cid in current_user.get_client_ids()
        ]
        clients = [c for c in clients if c]  # Filter None
    
    return jsonify({
        'total': len(clients),
        'clients': [c.to_dict() for c in clients]
    })


@clients_bp.route('/', methods=['POST'])
@admin_required
def create_new_client(current_user):
    """
    Create a new client
    
    POST /api/clients
    {
        "business_name": "ABC Roofing",
        "industry": "roofing",
        "geo": "Sarasota, FL",
        "website_url": "https://abcroofing.com",
        "phone": "(941) 555-1234",
        "email": "info@abcroofing.com",
        "primary_keywords": ["roof repair sarasota", "roofing company sarasota"],
        "service_areas": ["Sarasota", "Bradenton", "Venice"],
        "tone": "professional"
    }
    """
    data = request.get_json(silent=True) or {}
    
    required = ['business_name', 'industry', 'geo']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    client = DBClient(
        business_name=data['business_name'],
        industry=data['industry'],
        geo=data['geo'],
        website_url=data.get('website_url'),
        phone=data.get('phone'),
        email=data.get('email'),
        service_areas=data.get('service_areas', []),
        primary_keywords=data.get('primary_keywords', []),
        secondary_keywords=data.get('secondary_keywords', []),
        competitors=data.get('competitors', []),
        tone=data.get('tone', 'professional'),
        unique_selling_points=data.get('unique_selling_points', []),
        subscription_tier=data.get('subscription_tier', 'standard')
    )
    
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Client created successfully',
        'client': client.to_dict()
    }), 201


@clients_bp.route('/<client_id>', methods=['GET'])
@token_required
def get_client(current_user, client_id):
    """Get client by ID"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    return jsonify(client.to_dict())


@clients_bp.route('/<client_id>', methods=['PUT'])
@token_required
def update_client(current_user, client_id):
    """Update client"""
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Allow ADMIN, MANAGER, or users with access to this client
    is_admin_or_manager = current_user.role in [UserRole.ADMIN, UserRole.MANAGER]
    has_client_access = current_user.has_access_to_client(client_id)
    
    if not is_admin_or_manager and not has_client_access:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    # Update allowed fields
    if 'business_name' in data:
        client.business_name = data['business_name']
    if 'industry' in data:
        client.industry = data['industry']
    if 'geo' in data:
        client.geo = data['geo']
    if 'website_url' in data:
        client.website_url = data['website_url']
    if 'phone' in data:
        client.phone = data['phone']
    if 'email' in data:
        client.email = data['email']
    if 'service_areas' in data:
        client.service_areas = json.dumps(data['service_areas'])
    if 'primary_keywords' in data:
        client.primary_keywords = json.dumps(data['primary_keywords'])
    if 'secondary_keywords' in data:
        client.secondary_keywords = json.dumps(data['secondary_keywords'])
    if 'competitors' in data:
        client.competitors = json.dumps(data['competitors'])
    if 'tone' in data:
        client.tone = data['tone']
    if 'unique_selling_points' in data:
        client.unique_selling_points = json.dumps(data['unique_selling_points'])
    if 'service_cities' in data:
        client.service_cities = json.dumps(data['service_cities'])
    if 'subscription_tier' in data:
        client.subscription_tier = data['subscription_tier']
    if 'is_active' in data:
        client.is_active = data['is_active']
    # WordPress fields
    if 'wordpress_url' in data:
        client.wordpress_url = data['wordpress_url']
    if 'wordpress_user' in data:
        client.wordpress_user = data['wordpress_user']
    if 'wordpress_app_password' in data:
        client.wordpress_app_password = data['wordpress_app_password']
    
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Client updated',
        'client': client.to_dict()
    })


@clients_bp.route('/<client_id>', methods=['DELETE'])
@admin_required
def delete_client(current_user, client_id):
    """Delete a client (hard or soft delete based on query param)"""
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Check for hard delete flag
    hard_delete = request.args.get('hard', 'false').lower() == 'true'
    
    if hard_delete:
        # Hard delete - remove client and all associated content
        from app.database import db
        from app.models.db_models import DBClient, DBBlogPost, DBSocialPost, DBChatbotConfig, DBChatConversation
        
        try:
            # Delete associated content first
            DBBlogPost.query.filter_by(client_id=client_id).delete()
            DBSocialPost.query.filter_by(client_id=client_id).delete()
            
            # Delete chatbot config and conversations
            chatbot = DBChatbotConfig.query.filter_by(client_id=client_id).first()
            if chatbot:
                DBChatConversation.query.filter_by(chatbot_id=chatbot.id).delete()
                db.session.delete(chatbot)
            
            # Delete the client
            db_client = DBClient.query.filter_by(id=client_id).first()
            if db_client:
                db.session.delete(db_client)
            
            db.session.commit()
            
            return jsonify({'message': 'Client and all content permanently deleted'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Delete failed. Please try again.'}), 500
    else:
        # Soft delete - just deactivate
        client.is_active = False
        client.updated_at = datetime.utcnow()
        data_service.save_client(client)
        
        return jsonify({'message': 'Client deactivated'})


@clients_bp.route('/<client_id>/keywords', methods=['PUT'])
@token_required
def update_keywords(current_user, client_id):
    """
    Update client keywords
    
    PUT /api/clients/<client_id>/keywords
    {
        "primary": ["keyword1", "keyword2"],
        "secondary": ["keyword3", "keyword4"]
    }
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return jsonify({'error': 'Permission denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    
    if 'primary' in data:
        client.primary_keywords = json.dumps(data['primary'])
    if 'secondary' in data:
        client.secondary_keywords = json.dumps(data['secondary'])
    
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Keywords updated',
        'primary_keywords': client.get_primary_keywords(),
        'secondary_keywords': client.get_secondary_keywords()
    })


@clients_bp.route('/<client_id>/integrations', methods=['PUT'])
@token_required
def update_integrations(current_user, client_id):
    """
    Update client API integrations
    
    PUT /api/clients/<client_id>/integrations
    {
        "wordpress_url": "https://client.com",
        "wordpress_user": "admin",
        "wordpress_app_password": "xxxx xxxx xxxx xxxx",
        "gbp_location_id": "123456",
        "ga4_property_id": "123456789"
    }
    """
    # Check access - admin/manager can manage integrations
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Permission denied'}), 403
    
    if not current_user.is_admin and not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied to this client'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    
    # Store integrations as JSON
    integrations = client.get_integrations()
    
    # WordPress settings
    if 'wordpress_url' in data:
        integrations['wordpress_url'] = data['wordpress_url']
    if 'wordpress_user' in data:
        integrations['wordpress_user'] = data['wordpress_user']
    if 'wordpress_app_password' in data:
        integrations['wordpress_app_password'] = data['wordpress_app_password']
    # Legacy field support
    if 'wordpress_api_key' in data:
        integrations['wordpress_app_password'] = data['wordpress_api_key']
    
    # Other integrations
    if 'gbp_location_id' in data:
        integrations['gbp_location_id'] = data['gbp_location_id']
    if 'ga4_property_id' in data:
        integrations['ga4_property_id'] = data['ga4_property_id']
        client.ga4_property_id = data['ga4_property_id'] or None  # Also save to direct field
    if 'callrail_company_id' in data:
        integrations['callrail_company_id'] = data['callrail_company_id']
        client.callrail_company_id = data['callrail_company_id'] or None  # Also save to direct field
    if 'callrail_account_id' in data:
        integrations['callrail_account_id'] = data['callrail_account_id']
        client.callrail_account_id = data['callrail_account_id'] or None  # Per-client account override
    if 'gsc_site_url' in data:
        integrations['gsc_site_url'] = data['gsc_site_url']
        client.gsc_site_url = data['gsc_site_url'] or None  # Also save to direct field
    
    # Direct field updates for WordPress
    if 'wordpress_url' in data:
        client.wordpress_url = data['wordpress_url'] or None
    if 'wordpress_user' in data:
        client.wordpress_user = data['wordpress_user'] or None
    if 'wordpress_app_password' in data:
        client.wordpress_app_password = data['wordpress_app_password'] or None
    
    client.integrations = json.dumps(integrations)
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Integrations updated',
        'client_id': client_id
    })


@clients_bp.route('/<client_id>/summary', methods=['GET'])
@token_required
def get_client_summary(current_user, client_id):
    """Get client summary with content counts"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    blog_posts = data_service.get_client_blog_posts(client_id)
    social_posts = data_service.get_client_social_posts(client_id)
    campaigns = data_service.get_client_campaigns(client_id)
    
    return jsonify({
        'client': client.to_dict(),
        'stats': {
            'content': {
                'total': len(blog_posts),
                'published': sum(1 for c in blog_posts if c.status == 'published'),
                'draft': sum(1 for c in blog_posts if c.status == 'draft')
            },
            'social': {
                'total': len(social_posts),
                'by_platform': {}
            },
            'campaigns': {
                'total': len(campaigns),
                'active': sum(1 for c in campaigns if c.status == 'active')
            }
        }
    })


# ==========================================
# SERVICE PAGES (Internal Linking)
# ==========================================

@clients_bp.route('/<client_id>/service-pages', methods=['GET'])
@token_required
def get_service_pages(current_user, client_id):
    """
    Get client's service pages for internal linking
    
    Returns:
    {
        "client_id": "client_abc123",
        "service_pages": [
            {"keyword": "roof repair", "url": "/roof-repair/", "title": "Roof Repair Services"}
        ]
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    return jsonify({
        'client_id': client_id,
        'service_pages': client.get_service_pages()
    })


@clients_bp.route('/<client_id>/service-pages', methods=['POST'])
@token_required
def add_service_page(current_user, client_id):
    """
    Add a service page for internal linking
    
    POST /api/clients/{id}/service-pages
    {
        "keyword": "roof repair",
        "url": "/roof-repair/",
        "title": "Roof Repair Services"
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    keyword = data.get('keyword', '').strip()
    url = data.get('url', '').strip()
    title = data.get('title', keyword).strip()
    
    if not keyword or not url:
        return jsonify({'error': 'keyword and url are required'}), 400
    
    # Get existing pages
    pages = client.get_service_pages()
    
    # Check for duplicate keyword
    for page in pages:
        if page.get('keyword', '').lower() == keyword.lower():
            return jsonify({'error': f'Service page for "{keyword}" already exists'}), 400
    
    # Add new page
    pages.append({
        'keyword': keyword,
        'url': url,
        'title': title
    })
    
    client.set_service_pages(pages)
    data_service.save_client(client)
    
    return jsonify({
        'message': 'Service page added',
        'service_pages': pages
    })


@clients_bp.route('/<client_id>/service-pages', methods=['PUT'])
@token_required
def update_service_pages(current_user, client_id):
    """
    Replace all service pages (bulk update)
    
    PUT /api/clients/{id}/service-pages
    {
        "service_pages": [
            {"keyword": "roof repair", "url": "/roof-repair/", "title": "Roof Repair"},
            {"keyword": "roof replacement", "url": "/roof-replacement/", "title": "Roof Replacement"}
        ]
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    pages = data.get('service_pages', [])
    
    # Validate structure
    validated_pages = []
    for page in pages:
        keyword = page.get('keyword', '').strip()
        url = page.get('url', '').strip()
        title = page.get('title', keyword).strip()
        
        if keyword and url:
            validated_pages.append({
                'keyword': keyword,
                'url': url,
                'title': title
            })
    
    client.set_service_pages(validated_pages)
    data_service.save_client(client)
    
    return jsonify({
        'message': f'Updated {len(validated_pages)} service pages',
        'service_pages': validated_pages
    })


@clients_bp.route('/<client_id>/service-pages/<int:index>', methods=['DELETE'])
@token_required
def delete_service_page(current_user, client_id, index):
    """
    Delete a service page by index
    
    DELETE /api/clients/{id}/service-pages/0
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    pages = client.get_service_pages()
    
    if index < 0 or index >= len(pages):
        return jsonify({'error': 'Invalid index'}), 400
    
    removed = pages.pop(index)
    client.set_service_pages(pages)
    data_service.save_client(client)
    
    return jsonify({
        'message': f'Removed service page: {removed.get("keyword")}',
        'service_pages': pages
    })


@clients_bp.route('/<client_id>/service-pages/auto-generate', methods=['POST'])
@token_required
def auto_generate_service_pages(current_user, client_id):
    """
    Auto-generate service pages from client's website
    Uses primary keywords + industry standard pages
    
    POST /api/clients/{id}/service-pages/auto-generate
    {
        "base_url": "https://example.com"  // Optional, uses client website_url if not provided
    }
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    base_url = data.get('base_url', client.website_url or '').strip().rstrip('/')
    
    if not base_url:
        return jsonify({'error': 'No base URL available'}), 400
    
    generated_pages = []
    
    # Generate from primary keywords
    for keyword in client.get_primary_keywords():
        slug = keyword.lower().replace(' ', '-').replace(',', '')
        # Remove location from slug
        for area in client.get_service_areas():
            slug = slug.replace(area.lower(), '').strip('-')
        slug = slug.strip('-')
        
        if slug:
            generated_pages.append({
                'keyword': keyword,
                'url': f'{base_url}/{slug}/',
                'title': keyword.title()
            })
    
    # Add industry-standard pages based on client industry
    industry_pages = {
        'roofing': [
            {'keyword': 'roof repair', 'slug': 'roof-repair', 'title': 'Roof Repair Services'},
            {'keyword': 'roof replacement', 'slug': 'roof-replacement', 'title': 'Roof Replacement'},
            {'keyword': 'roof inspection', 'slug': 'roof-inspection', 'title': 'Roof Inspections'},
            {'keyword': 'emergency roof repair', 'slug': 'emergency-roof-repair', 'title': 'Emergency Roof Repair'},
        ],
        'hvac': [
            {'keyword': 'ac repair', 'slug': 'ac-repair', 'title': 'AC Repair Services'},
            {'keyword': 'heating repair', 'slug': 'heating-repair', 'title': 'Heating Repair'},
            {'keyword': 'hvac installation', 'slug': 'hvac-installation', 'title': 'HVAC Installation'},
            {'keyword': 'ac maintenance', 'slug': 'ac-maintenance', 'title': 'AC Maintenance'},
        ],
        'plumbing': [
            {'keyword': 'plumbing repair', 'slug': 'plumbing-repair', 'title': 'Plumbing Repair'},
            {'keyword': 'drain cleaning', 'slug': 'drain-cleaning', 'title': 'Drain Cleaning'},
            {'keyword': 'water heater repair', 'slug': 'water-heater-repair', 'title': 'Water Heater Repair'},
            {'keyword': 'emergency plumber', 'slug': 'emergency-plumber', 'title': 'Emergency Plumber'},
        ],
        'electrical': [
            {'keyword': 'electrical repair', 'slug': 'electrical-repair', 'title': 'Electrical Repair'},
            {'keyword': 'electrical installation', 'slug': 'electrical-installation', 'title': 'Electrical Installation'},
            {'keyword': 'panel upgrade', 'slug': 'panel-upgrade', 'title': 'Panel Upgrades'},
        ],
    }
    
    industry_lower = (client.industry or '').lower()
    if industry_lower in industry_pages:
        for page in industry_pages[industry_lower]:
            # Check if keyword not already added
            existing_keywords = [p['keyword'].lower() for p in generated_pages]
            if page['keyword'].lower() not in existing_keywords:
                generated_pages.append({
                    'keyword': page['keyword'],
                    'url': f"{base_url}/{page['slug']}/",
                    'title': page['title']
                })
    
    # Merge with existing pages (don't overwrite)
    existing_pages = client.get_service_pages()
    existing_urls = [p['url'].lower() for p in existing_pages]
    
    new_pages = []
    for page in generated_pages:
        if page['url'].lower() not in existing_urls:
            new_pages.append(page)
    
    all_pages = existing_pages + new_pages
    client.set_service_pages(all_pages)
    data_service.save_client(client)
    
    return jsonify({
        'message': f'Added {len(new_pages)} new service pages',
        'new_pages': new_pages,
        'total_pages': len(all_pages),
        'service_pages': all_pages
    })


# ==========================================
# OVERVIEW DASHBOARD ENDPOINTS
# ==========================================

@clients_bp.route('/health-score/<client_id>', methods=['GET'])
@token_required
def get_health_score(current_user, client_id):
    """
    Get client marketing health score
    
    GET /api/client/health-score/<client_id>
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Calculate health score based on various factors
    score = 50  # Base score
    factors = []
    
    # Check WordPress connection (+20)
    if client.wordpress_url:
        score += 20
        factors.append({'name': 'WordPress Connected', 'points': 20})
    else:
        factors.append({'name': 'WordPress Not Connected', 'points': 0, 'max': 20})
    
    # Check keywords defined (+15)
    keywords = client.get_keywords()
    if keywords.get('primary') or keywords.get('secondary'):
        score += 15
        factors.append({'name': 'Keywords Defined', 'points': 15})
    else:
        factors.append({'name': 'No Keywords', 'points': 0, 'max': 15})
    
    # Check content created (+15)
    from app.models.db_models import DBContent
    content_count = DBContent.query.filter_by(client_id=client_id).count()
    if content_count >= 5:
        score += 15
        factors.append({'name': f'{content_count} Content Pieces', 'points': 15})
    elif content_count > 0:
        partial = min(content_count * 3, 15)
        score += partial
        factors.append({'name': f'{content_count} Content Pieces', 'points': partial, 'max': 15})
    
    # Cap at 100
    score = min(score, 100)
    
    return jsonify({
        'score': score,
        'health_score': score,
        'factors': factors,
        'grade': 'A+' if score >= 90 else 'A' if score >= 80 else 'B' if score >= 70 else 'C' if score >= 60 else 'D'
    })


@clients_bp.route('/wins/<client_id>', methods=['GET'])
@token_required
def get_wins(current_user, client_id):
    """
    Get recent wins/achievements for client
    
    GET /api/client/wins/<client_id>
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.db_models import DBContent, DBLead
    from datetime import datetime, timedelta
    
    wins = []
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    # Content created this week
    content_count = DBContent.query.filter(
        DBContent.client_id == client_id,
        DBContent.created_at >= week_ago
    ).count()
    if content_count > 0:
        wins.append({
            'type': 'content',
            'title': f'{content_count} new content pieces created',
            'icon': 'fa-file-alt',
            'color': 'purple'
        })
    
    # Leads captured this week
    lead_count = DBLead.query.filter(
        DBLead.client_id == client_id,
        DBLead.created_at >= week_ago
    ).count()
    if lead_count > 0:
        wins.append({
            'type': 'leads',
            'title': f'{lead_count} new leads captured',
            'icon': 'fa-user-plus',
            'color': 'green'
        })
    
    # Published to WordPress this week
    published = DBContent.query.filter(
        DBContent.client_id == client_id,
        DBContent.wordpress_post_id.isnot(None),
        DBContent.published_at >= week_ago
    ).count()
    if published > 0:
        wins.append({
            'type': 'published',
            'title': f'{published} posts published to WordPress',
            'icon': 'fa-globe',
            'color': 'blue'
        })
    
    return jsonify({
        'wins': wins,
        'total': len(wins)
    })


@clients_bp.route('/activity/<client_id>', methods=['GET'])
@token_required
def get_activity(current_user, client_id):
    """
    Get recent activity for client
    
    GET /api/client/activity/<client_id>?limit=10
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.db_models import DBContent, DBLead
    from datetime import datetime
    
    limit = request.args.get('limit', 10, type=int)
    activities = []
    
    # Get recent content
    contents = DBContent.query.filter_by(client_id=client_id).order_by(
        DBContent.created_at.desc()
    ).limit(limit).all()
    
    for content in contents:
        activities.append({
            'type': 'content',
            'title': f'Created: {content.title[:50]}...' if len(content.title) > 50 else f'Created: {content.title}',
            'time': content.created_at.isoformat() if content.created_at else None,
            'icon': 'fa-file-alt',
            'color': 'purple'
        })
    
    # Get recent leads
    leads = DBLead.query.filter_by(client_id=client_id).order_by(
        DBLead.created_at.desc()
    ).limit(limit).all()
    
    for lead in leads:
        activities.append({
            'type': 'lead',
            'title': f'New lead: {lead.name or lead.email or "Unknown"}',
            'time': lead.created_at.isoformat() if lead.created_at else None,
            'icon': 'fa-user-plus',
            'color': 'green'
        })
    
    # Sort by time and limit
    activities.sort(key=lambda x: x['time'] or '', reverse=True)
    activities = activities[:limit]
    
    return jsonify({
        'activities': activities,
        'total': len(activities)
    })


@clients_bp.route('/calls/<client_id>', methods=['GET'])
@token_required
def get_calls(current_user, client_id):
    """
    Get call data for client (from CallRail or mock)
    
    GET /api/client/calls/<client_id>?limit=10
    """
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    limit = request.args.get('limit', 10, type=int)
    
    # Check if CallRail is configured
    callrail_id = client.callrail_company_id
    if not callrail_id:
        return jsonify({
            'calls': [],
            'total': 0,
            'answered': 0,
            'answer_rate': 0,
            'demo_mode': True,
            'message': 'Connect CallRail in Settings to see real call data'
        })
    
    # Try to get real calls from CallRail
    try:
        from app.services.callrail_service import callrail_service
        if callrail_service.is_configured():
            calls = callrail_service.get_calls(callrail_id, limit=limit)
            answered = sum(1 for c in calls if c.get('answered'))
            return jsonify({
                'calls': calls,
                'total': len(calls),
                'answered': answered,
                'answer_rate': round(answered / len(calls) * 100) if calls else 0
            })
    except Exception as e:
        logger.warning(f"CallRail error: {e}")
    
    return jsonify({
        'calls': [],
        'total': 0,
        'answered': 0,
        'answer_rate': 0,
        'demo_mode': True,
        'message': 'CallRail not configured or error fetching calls'
    })
