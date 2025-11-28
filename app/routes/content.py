"""
MCP Framework - Content Generation Routes
Blog posts, landing pages, and SEO content
"""
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import token_required
from app.services.ai_service import AIService
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from app.models.db_models import DBBlogPost, ContentStatus
import json

content_bp = Blueprint('content', __name__)
ai_service = AIService()
seo_service = SEOService()
data_service = DataService()


@content_bp.route('/generate', methods=['POST'])
@token_required
def generate_content(current_user):
    """
    Generate SEO-optimized blog content
    
    POST /api/content/generate
    {
        "client_id": "client_abc123",
        "keyword": "roof repair sarasota",
        "geo": "Sarasota, FL",
        "industry": "roofing",
        "word_count": 1200,
        "tone": "professional",
        "include_faq": true,
        "faq_count": 5,
        "internal_links": [
            {"url": "/services/roof-repair", "anchor": "roof repair services"},
            {"url": "/about", "anchor": "our roofing experts"}
        ]
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required = ['client_id', 'keyword', 'geo', 'industry']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Get client
    client = data_service.get_client(data['client_id'])
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Check access
    if not current_user.has_access_to_client(data['client_id']):
        return jsonify({'error': 'Access denied to this client'}), 403
    
    # Build generation params
    params = {
        'keyword': data['keyword'],
        'geo': data['geo'],
        'industry': data['industry'],
        'word_count': data.get('word_count', current_app.config['DEFAULT_BLOG_WORD_COUNT']),
        'tone': data.get('tone', current_app.config['DEFAULT_TONE']),
        'business_name': client.business_name,
        'include_faq': data.get('include_faq', True),
        'faq_count': data.get('faq_count', 5),
        'internal_links': data.get('internal_links', []),
        'usps': client.get_unique_selling_points()
    }
    
    # Generate content
    result = ai_service.generate_blog_post(**params)
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    # Create BlogPost object
    blog_post = DBBlogPost(
        client_id=data['client_id'],
        title=result['title'],
        body=result['body'],
        meta_title=result['meta_title'],
        meta_description=result['meta_description'],
        primary_keyword=data['keyword'],
        secondary_keywords=result.get('secondary_keywords', []),
        internal_links=data.get('internal_links', []),
        faq_content=result.get('faq_items', []),
        word_count=len(result.get('body', '').split()),
        status=ContentStatus.DRAFT
    )
    
    # Save to database
    data_service.save_blog_post(blog_post)
    
    return jsonify({
        'success': True,
        'content': blog_post.to_dict(),
        'html': result.get('html', '')
    })


@content_bp.route('/bulk-generate', methods=['POST'])
@token_required
def bulk_generate(current_user):
    """
    Generate multiple blog posts (one at a time to avoid timeouts)
    
    POST /api/content/bulk-generate
    {
        "client_id": "client_abc123",
        "topics": [
            {"keyword": "roof repair sarasota", "word_count": 1200},
            {"keyword": "roof replacement bradenton", "word_count": 1500}
        ]
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    client_id = data.get('client_id')
    topics = data.get('topics', [])
    
    if not client_id or not topics:
        return jsonify({'error': 'client_id and topics required'}), 400
    
    # Get client
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get internal linking service
    from app.services.internal_linking_service import internal_linking_service
    service_pages = client.get_service_pages()
    
    results = []
    
    for topic in topics[:5]:  # Limit to 5 to avoid timeout
        keyword = topic.get('keyword', '')
        if not keyword:
            results.append({'keyword': '', 'success': False, 'error': 'keyword required'})
            continue
        
        try:
            # Build params from client data
            params = {
                'keyword': keyword,
                'geo': client.geo,
                'industry': client.industry,
                'word_count': topic.get('word_count', current_app.config.get('DEFAULT_BLOG_WORD_COUNT', 1200)),
                'tone': client.tone or 'professional',
                'business_name': client.business_name,
                'include_faq': topic.get('include_faq', True),
                'faq_count': topic.get('faq_count', 5),
                'internal_links': service_pages,  # Pass service pages to AI
                'usps': client.get_unique_selling_points()
            }
            
            # Generate content
            result = ai_service.generate_blog_post(**params)
            
            if result.get('error'):
                results.append({
                    'keyword': keyword,
                    'success': False,
                    'error': result['error']
                })
                continue
            
            # Process content with internal linking service
            body_content = result.get('body', '')
            if service_pages and body_content:
                link_result = internal_linking_service.process_blog_content(
                    content=body_content,
                    service_pages=service_pages,
                    primary_keyword=keyword,
                    location=client.geo,
                    business_name=client.business_name,
                    fix_headings=True,
                    add_cta=True
                )
                body_content = link_result['content']
                links_added = link_result['links_added']
            else:
                links_added = 0
            
            # Create and save blog post
            blog_post = DBBlogPost(
                client_id=client_id,
                title=result.get('title', keyword),
                body=body_content,
                meta_title=result.get('meta_title', ''),
                meta_description=result.get('meta_description', ''),
                primary_keyword=keyword,
                secondary_keywords=result.get('secondary_keywords', []),
                internal_links=service_pages,
                faq_content=result.get('faq_items', []),
                word_count=len(body_content.split()),
                status=ContentStatus.DRAFT
            )
            
            data_service.save_blog_post(blog_post)
            
            results.append({
                'keyword': keyword,
                'success': True,
                'content_id': blog_post.id,
                'title': blog_post.title,
                'word_count': blog_post.word_count,
                'links_added': links_added
            })
            
        except Exception as e:
            results.append({
                'keyword': keyword,
                'success': False,
                'error': str(e)
            })
    
    return jsonify({
        'client_id': client_id,
        'total': len(topics),
        'successful': sum(1 for r in results if r.get('success')),
        'results': results
    })


@content_bp.route('/<content_id>', methods=['GET'])
@token_required
def get_content(current_user, content_id):
    """Get content by ID"""
    content = data_service.get_blog_post(content_id)
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(content.to_dict())


@content_bp.route('/<content_id>', methods=['PUT'])
@token_required
def update_content(current_user, content_id):
    """Update content"""
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    content = data_service.get_blog_post(content_id)
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    
    # Update allowed fields
    if 'title' in data:
        content.title = data['title']
    if 'body' in data:
        content.body = data['body']
        content.word_count = len(data['body'].split())
    if 'meta_title' in data:
        content.meta_title = data['meta_title']
    if 'meta_description' in data:
        content.meta_description = data['meta_description']
    if 'status' in data:
        content.status = data['status']
    
    data_service.save_blog_post(content)
    
    return jsonify({
        'message': 'Content updated',
        'content': content.to_dict()
    })


@content_bp.route('/<content_id>', methods=['DELETE'])
@token_required
def delete_content(current_user, content_id):
    """Delete content"""
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    content = data_service.get_blog_post(content_id)
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data_service.delete_blog_post(content_id)
    
    return jsonify({'message': 'Content deleted'})


@content_bp.route('/client/<client_id>', methods=['GET'])
@token_required
def list_client_content(current_user, client_id):
    """List all content for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    content_list = data_service.get_client_blog_posts(client_id)
    
    # Optional status filter
    status_filter = request.args.get('status')
    if status_filter:
        content_list = [c for c in content_list if c.status == status_filter]
    
    return jsonify({
        'client_id': client_id,
        'total': len(content_list),
        'content': [c.to_dict() for c in content_list]
    })


@content_bp.route('/seo-check', methods=['POST'])
@token_required
def seo_check(current_user):
    """
    Check SEO score of content
    
    POST /api/content/seo-check
    {
        "title": "...",
        "body": "...",
        "meta_title": "...",
        "meta_description": "...",
        "target_keyword": "..."
    }
    """
    data = request.get_json()
    
    title = data.get('title', '')
    body = data.get('body', '')
    meta_title = data.get('meta_title', '')
    meta_description = data.get('meta_description', '')
    target_keyword = data.get('target_keyword', '').lower()
    
    # Calculate checks
    checks = {
        'meta_title_present': len(meta_title) >= 30 and len(meta_title) <= 60,
        'meta_description_present': len(meta_description) >= 120 and len(meta_description) <= 160,
        'keyword_in_title': target_keyword in title.lower() if target_keyword else False,
        'keyword_in_h1': target_keyword in title.lower() if target_keyword else False,
        'word_count_sufficient': len(body.split()) >= 1200,
        'has_internal_links': body.count('href=') >= 3
    }
    
    # Calculate score
    score = sum(checks.values()) / len(checks) * 100
    
    # Recommendations
    recommendations = []
    if not checks['meta_title_present']:
        recommendations.append('Add a meta title (30-60 characters)')
    if not checks['meta_description_present']:
        recommendations.append('Add a meta description (120-160 characters)')
    if not checks['keyword_in_h1']:
        recommendations.append(f'Include target keyword "{target_keyword}" in H1/title')
    if not checks['word_count_sufficient']:
        recommendations.append('Increase content length to at least 1,200 words')
    if not checks['has_internal_links']:
        recommendations.append('Add at least 3 internal links')
    
    return jsonify({
        'score': round(score),
        'checks': checks,
        'recommendations': recommendations
    })


@content_bp.route('/blog/generate', methods=['POST'])
@token_required
def generate_blog_simple(current_user):
    """
    Simplified blog generation endpoint for client dashboard
    
    POST /api/content/blog/generate
    {
        "client_id": "uuid",
        "keyword": "ac repair sarasota",
        "word_count": 1500,
        "include_faq": true,
        "faq_count": 5,
        "generate_schema": true
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    if not data.get('client_id') or not data.get('keyword'):
        return jsonify({'error': 'client_id and keyword required'}), 400
    
    try:
        # Get client
        client = data_service.get_client(data['client_id'])
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        if not current_user.has_access_to_client(data['client_id']):
            return jsonify({'error': 'Access denied'}), 403
        
        # Get internal links from client service pages
        from app.services.internal_linking_service import internal_linking_service
        service_pages = client.get_service_pages() or []
        
        # Generate blog
        result = ai_service.generate_blog_post(
            keyword=data['keyword'],
            geo=client.geo or '',
            industry=client.industry or '',
            word_count=data.get('word_count', 1500),
            tone=client.tone or 'professional',
            business_name=client.business_name or '',
            include_faq=data.get('include_faq', True),
            faq_count=data.get('faq_count', 5),
            internal_links=service_pages,
            usps=client.get_unique_selling_points()
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 500
        
        # Process with internal linking
        body_content = result.get('body', '')
        links_added = 0
        
        if service_pages and body_content:
            link_result = internal_linking_service.process_blog_content(
                content=body_content,
                service_pages=service_pages,
                primary_keyword=data['keyword'],
                location=client.geo or '',
                business_name=client.business_name or '',
                fix_headings=True,
                add_cta=True
            )
            body_content = link_result['content']
            links_added = link_result['links_added']
        
        # Create blog post
        blog_post = DBBlogPost(
            client_id=data['client_id'],
            title=result.get('title', data['keyword']),
            body=body_content,
            meta_title=result.get('meta_title', ''),
            meta_description=result.get('meta_description', ''),
            primary_keyword=data['keyword'],
            secondary_keywords=result.get('secondary_keywords', []),
            internal_links=service_pages,
            faq_content=result.get('faq_items', []),
            word_count=len(body_content.split()),
            status=ContentStatus.DRAFT
        )
        
        data_service.save_blog_post(blog_post)
        
        # Auto-generate schema if requested
        schema_data = {}
        if data.get('generate_schema', True):
            try:
                # Generate Article schema
                article_schema = {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": result.get('meta_title', result.get('title', '')),
                    "description": result.get('meta_description', ''),
                    "author": {
                        "@type": "Organization",
                        "name": client.business_name or ''
                    },
                    "publisher": {
                        "@type": "Organization", 
                        "name": client.business_name or ''
                    },
                    "mainEntityOfPage": {
                        "@type": "WebPage"
                    }
                }
                
                # Generate FAQ schema if FAQs exist
                faq_schema = None
                if result.get('faq_items'):
                    faq_schema = {
                        "@context": "https://schema.org",
                        "@type": "FAQPage",
                        "mainEntity": [
                            {
                                "@type": "Question",
                                "name": faq.get('question', faq.get('q', '')),
                                "acceptedAnswer": {
                                    "@type": "Answer",
                                    "text": faq.get('answer', faq.get('a', ''))
                                }
                            }
                            for faq in result.get('faq_items', [])
                        ]
                    }
                
                schema_data = {
                    'article': article_schema,
                    'faq': faq_schema
                }
            except Exception as e:
                schema_data = {'error': str(e)}
        
        return jsonify({
            'success': True,
            'id': blog_post.id,
            'title': blog_post.title,
            'word_count': blog_post.word_count,
            'links_added': links_added,
            'schema': schema_data
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Blog generation error: {error_detail}")
        return jsonify({
            'error': str(e),
            'detail': 'Blog generation failed. Check server logs.'
        }), 500


@content_bp.route('/social/generate', methods=['POST'])
@token_required
def generate_social_simple(current_user):
    """
    Generate a social media post
    
    POST /api/content/social/generate
    {
        "client_id": "uuid",
        "topic": "summer AC tips",
        "platform": "gbp"  // gbp, facebook, instagram
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    if not data.get('client_id') or not data.get('topic') or not data.get('platform'):
        return jsonify({'error': 'client_id, topic, and platform required'}), 400
    
    try:
        client = data_service.get_client(data['client_id'])
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        if not current_user.has_access_to_client(data['client_id']):
            return jsonify({'error': 'Access denied'}), 403
        
        platform = data['platform'].lower()
        if platform not in ['gbp', 'facebook', 'instagram']:
            return jsonify({'error': 'Invalid platform. Use: gbp, facebook, instagram'}), 400
        
        # Generate social post
        result = ai_service.generate_social_post(
            platform=platform,
            topic=data['topic'],
            geo=client.geo or '',
            business_name=client.business_name or '',
            industry=client.industry or '',
            tone=client.tone or 'professional'
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 500
        
        # Save to database
        from app.models.db_models import DBSocialPost
        
        social_post = DBSocialPost(
            client_id=data['client_id'],
            platform=platform,
            content=result.get('content', ''),
            hashtags=result.get('hashtags', []),
            topic=data['topic'],
            status=ContentStatus.DRAFT
        )
        
        data_service.save_social_post(social_post)
        
        return jsonify({
            'success': True,
            'id': social_post.id,
            'platform': platform,
            'content': social_post.content,
            'hashtags': social_post.hashtags
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Social generation error: {error_detail}")
        return jsonify({
            'error': str(e),
            'detail': 'Social post generation failed. Check server logs.'
        }), 500
