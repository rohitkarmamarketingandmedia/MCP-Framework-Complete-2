"""
MCP Framework - Content Generation Routes
Blog posts, landing pages, and SEO content
"""
from flask import Blueprint, request, jsonify, current_app
import logging
import threading
import uuid
from datetime import datetime
logger = logging.getLogger(__name__)
from app.routes.auth import token_required
from app.services.ai_service import AIService
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from app.services.seo_scoring_engine import seo_scoring_engine
from app.models.db_models import DBBlogPost, DBSocialPost, ContentStatus
import json

content_bp = Blueprint('content', __name__)
ai_service = AIService()
seo_service = SEOService()
data_service = DataService()

# In-memory task storage for background blog generation
_blog_tasks = {}
_MAX_TASKS = 100  # Prevent unbounded growth


def _cleanup_old_tasks():
    """Remove completed/errored tasks older than 10 minutes"""
    if len(_blog_tasks) < _MAX_TASKS:
        return
    
    cutoff = datetime.utcnow().timestamp() - 600  # 10 minutes
    to_delete = []
    for task_id, task in _blog_tasks.items():
        if task.get('status') in ['complete', 'error']:
            created = task.get('created_at', '')
            if created:
                try:
                    task_time = datetime.fromisoformat(created).timestamp()
                    if task_time < cutoff:
                        to_delete.append(task_id)
                except (ValueError, AttributeError, TypeError):
                    # If we can't parse the timestamp, mark for deletion
                    to_delete.append(task_id)
    
    for task_id in to_delete[:50]:  # Remove at most 50 at a time
        _blog_tasks.pop(task_id, None)


@content_bp.route('/check', methods=['GET'])
@token_required
def check_ai_config(current_user):
    """Check if AI is configured properly"""
    import os
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    
    return jsonify({
        'openai_configured': bool(openai_key),
        'openai_key_prefix': openai_key[:10] + '...' if openai_key else 'NOT SET',
        'can_generate': current_user.can_generate_content,
        'user_role': str(current_user.role)
    })


def _generate_blog_background(task_id, app, client_id, keyword, word_count, include_faq, faq_count, user_id):
    """Background thread function to generate blog"""
    with app.app_context():
        try:
            _blog_tasks[task_id]['status'] = 'generating'
            
            # Get client
            client = data_service.get_client(client_id)
            if not client:
                _blog_tasks[task_id] = {'status': 'error', 'error': 'Client not found'}
                return
            
            from app.services.internal_linking_service import internal_linking_service
            service_pages = client.get_service_pages() or []
            
            # Generate blog
            result = ai_service.generate_blog_post(
                keyword=keyword,
                geo=client.geo or '',
                industry=client.industry or '',
                word_count=word_count,
                tone=client.tone or 'professional',
                business_name=client.business_name or '',
                include_faq=include_faq,
                faq_count=faq_count,
                internal_links=service_pages,
                usps=client.get_unique_selling_points()
            )
            
            if result.get('error'):
                _blog_tasks[task_id] = {'status': 'error', 'error': result['error']}
                return
            
            # Process with internal linking
            body_content = result.get('body', '')
            links_added = 0
            
            if body_content:
                link_result = internal_linking_service.process_blog_content(
                    content=body_content,
                    service_pages=service_pages or [],
                    primary_keyword=keyword,
                    location=client.geo or '',
                    business_name=client.business_name or '',
                    fix_headings=True,
                    add_cta=True,
                    phone=client.phone,
                    website_url=client.website_url
                )
                body_content = link_result['content']
                links_added = link_result['links_added']
            
            # Generate FAQ schema if we have FAQs
            faq_items = result.get('faq_items', [])
            faq_schema = None
            if faq_items:
                faq_schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq.get('question') or faq.get('q', ''),
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": faq.get('answer') or faq.get('a', '')
                            }
                        }
                        for faq in faq_items
                        if (faq.get('question') or faq.get('q')) and (faq.get('answer') or faq.get('a'))
                    ]
                }
            
            # Calculate SEO score for the generated content
            seo_score_result = seo_scoring_engine.score_content(
                content={
                    'title': result.get('title', ''),
                    'meta_title': result.get('meta_title', ''),
                    'meta_description': result.get('meta_description', ''),
                    'h1': result.get('title', ''),
                    'body': body_content
                },
                target_keyword=keyword,
                location=client.geo or ''
            )
            seo_score = seo_score_result.get('total_score', 0)
            
            # Create blog post with SEO score
            blog_post = DBBlogPost(
                client_id=client_id,
                title=result.get('title', keyword),
                body=body_content,
                meta_title=result.get('meta_title', ''),
                meta_description=result.get('meta_description', ''),
                primary_keyword=keyword,
                secondary_keywords=result.get('secondary_keywords', []),
                internal_links=service_pages,
                faq_content=faq_items,
                schema_markup=faq_schema,
                word_count=len(body_content.split()),
                seo_score=seo_score,
                status=ContentStatus.DRAFT
            )
            
            data_service.save_blog_post(blog_post)
            
            _blog_tasks[task_id] = {
                'status': 'complete',
                'blog_id': blog_post.id,
                'title': blog_post.title,
                'word_count': blog_post.word_count,
                'links_added': links_added,
                'seo_score': seo_score,
                'seo_recommendations': seo_score_result.get('recommendations', [])
            }
            
        except Exception as e:
            logger.error(f"Background blog generation error: {e}")
            _blog_tasks[task_id] = {'status': 'error', 'error': str(e)}


@content_bp.route('/blog/generate-async', methods=['POST'])
@token_required
def generate_blog_async(current_user):
    """
    Start async blog generation - returns immediately with task_id
    
    POST /api/content/blog/generate-async
    {
        "client_id": "uuid",
        "keyword": "ac repair sarasota",
        "word_count": 1500,
        "include_faq": true,
        "faq_count": 5
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    if not data.get('client_id') or not data.get('keyword'):
        return jsonify({'error': 'client_id and keyword required'}), 400
    
    # Verify client access
    if not current_user.has_access_to_client(data['client_id']):
        return jsonify({'error': 'Access denied'}), 403
    
    # Clean up old tasks to prevent memory leak
    _cleanup_old_tasks()
    
    # Create task
    task_id = str(uuid.uuid4())
    _blog_tasks[task_id] = {
        'status': 'pending',
        'created_at': datetime.utcnow().isoformat(),
        'keyword': data['keyword']
    }
    
    # Start background thread
    from flask import current_app
    app = current_app._get_current_object()
    
    thread = threading.Thread(
        target=_generate_blog_background,
        args=(
            task_id,
            app,
            data['client_id'],
            data['keyword'],
            data.get('word_count', 1500),
            data.get('include_faq', True),
            data.get('faq_count', 5),
            current_user.id
        )
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'task_id': task_id,
        'status': 'pending',
        'message': 'Blog generation started'
    })


@content_bp.route('/blog/task/<task_id>', methods=['GET'])
@token_required
def check_blog_task(current_user, task_id):
    """Check status of async blog generation task"""
    task = _blog_tasks.get(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify(task)


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
    
    data = request.get_json(silent=True) or {}
    
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
    # Auto-use client's service pages for internal linking if not explicitly provided
    internal_links = data.get('internal_links', [])
    if not internal_links:
        internal_links = client.get_service_pages() or []
    
    params = {
        'keyword': data['keyword'],
        'geo': data['geo'],
        'industry': data['industry'],
        'word_count': data.get('word_count', current_app.config['DEFAULT_BLOG_WORD_COUNT']),
        'tone': data.get('tone', current_app.config['DEFAULT_TONE']),
        'business_name': client.business_name or '',
        'include_faq': data.get('include_faq', True),
        'faq_count': data.get('faq_count', 5),
        'internal_links': internal_links,
        'usps': client.get_unique_selling_points() or []
    }
    
    # Generate content
    result = ai_service.generate_blog_post(**params)
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    # Post-process with internal linking service to ensure links are added
    from app.services.internal_linking_service import internal_linking_service
    body_content = result.get('body', '')
    links_added = 0
    
    if body_content:
        link_result = internal_linking_service.process_blog_content(
            content=body_content,
            service_pages=internal_links or [],
            primary_keyword=data['keyword'],
            location=data.get('geo', ''),
            business_name=client.business_name or '',
            fix_headings=True,
            add_cta=True,
            phone=client.phone,
            website_url=client.website_url
        )
        body_content = link_result['content']
        links_added = link_result.get('links_added', 0)
    
    # Generate FAQ schema if we have FAQs
    faq_items = result.get('faq_items', [])
    faq_schema = None
    if faq_items:
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq.get('question') or faq.get('q', ''),
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq.get('answer') or faq.get('a', '')
                    }
                }
                for faq in faq_items
                if (faq.get('question') or faq.get('q')) and (faq.get('answer') or faq.get('a'))
            ]
        }
    
    # Calculate SEO score
    seo_score_result = seo_scoring_engine.score_content(
        content={
            'title': result.get('title', ''),
            'meta_title': result.get('meta_title', ''),
            'meta_description': result.get('meta_description', ''),
            'h1': result.get('title', ''),
            'body': body_content
        },
        target_keyword=data['keyword'],
        location=data.get('geo', '')
    )
    seo_score = seo_score_result.get('total_score', 0)
    
    # Create BlogPost object with SEO score
    blog_post = DBBlogPost(
        client_id=data['client_id'],
        title=result['title'],
        body=body_content,  # Use processed body with links
        meta_title=result['meta_title'],
        meta_description=result['meta_description'],
        primary_keyword=data['keyword'],
        secondary_keywords=result.get('secondary_keywords', []),
        internal_links=internal_links,
        faq_content=faq_items,
        schema_markup=faq_schema,
        word_count=len(body_content.split()),
        seo_score=seo_score,
        status=ContentStatus.DRAFT
    )
    
    # Auto-generate featured image if client has images in library
    try:
        from app.services.featured_image_service import featured_image_service
        if featured_image_service.is_available():
            featured_result = featured_image_service.create_from_client_library(
                client_id=client.id,
                title=result['meta_title'] or result['title'],
                category='hero',
                template='gradient_bottom',
                subtitle=data.get('geo', client.geo)
            )
            if featured_result.get('success'):
                blog_post.featured_image_url = featured_result['file_url']
                logger.info(f"Auto-generated featured image for blog: {featured_result['file_url']}")
    except Exception as e:
        logger.warning(f"Could not auto-generate featured image: {e}")
    
    # Save to database
    data_service.save_blog_post(blog_post)
    
    return jsonify({
        'success': True,
        'content': blog_post.to_dict(),
        'html': result.get('html', ''),
        'seo_score': seo_score,
        'seo_grade': seo_score_result.get('grade', 'N/A'),
        'seo_recommendations': seo_score_result.get('recommendations', [])
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
    
    data = request.get_json(silent=True) or {}
    
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
    service_pages = client.get_service_pages() or []
    
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
                'geo': client.geo or '',
                'industry': client.industry or '',
                'word_count': topic.get('word_count', current_app.config.get('DEFAULT_BLOG_WORD_COUNT', 1200)),
                'tone': client.tone or 'professional',
                'business_name': client.business_name or '',
                'include_faq': topic.get('include_faq', True),
                'faq_count': topic.get('faq_count', 5),
                'internal_links': service_pages,  # Pass service pages to AI
                'usps': client.get_unique_selling_points() or []
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
            if body_content:
                link_result = internal_linking_service.process_blog_content(
                    content=body_content,
                    service_pages=service_pages or [],
                    primary_keyword=keyword,
                    location=client.geo or '',
                    business_name=client.business_name or '',
                    fix_headings=True,
                    add_cta=True,
                    phone=client.phone,
                    website_url=client.website_url
                )
                body_content = link_result['content']
                links_added = link_result['links_added']
            else:
                links_added = 0
            
            # Generate FAQ schema if we have FAQs
            faq_items = result.get('faq_items', [])
            faq_schema = None
            if faq_items:
                faq_schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq.get('question') or faq.get('q', ''),
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": faq.get('answer') or faq.get('a', '')
                            }
                        }
                        for faq in faq_items
                        if (faq.get('question') or faq.get('q')) and (faq.get('answer') or faq.get('a'))
                    ]
                }
            
            # Calculate SEO score
            seo_score_result = seo_scoring_engine.score_content(
                content={
                    'title': result.get('title', ''),
                    'meta_title': result.get('meta_title', ''),
                    'meta_description': result.get('meta_description', ''),
                    'h1': result.get('title', ''),
                    'body': body_content
                },
                target_keyword=keyword,
                location=client.geo or ''
            )
            seo_score = seo_score_result.get('total_score', 0)
            
            # Create and save blog post with SEO score
            blog_post = DBBlogPost(
                client_id=client_id,
                title=result.get('title', keyword),
                body=body_content,
                meta_title=result.get('meta_title', ''),
                meta_description=result.get('meta_description', ''),
                primary_keyword=keyword,
                secondary_keywords=result.get('secondary_keywords', []),
                internal_links=service_pages,
                faq_content=faq_items,
                schema_markup=faq_schema,
                word_count=len(body_content.split()),
                seo_score=seo_score,
                status=ContentStatus.DRAFT
            )
            
            data_service.save_blog_post(blog_post)
            
            results.append({
                'keyword': keyword,
                'success': True,
                'content_id': blog_post.id,
                'title': blog_post.title,
                'word_count': blog_post.word_count,
                'links_added': links_added,
                'seo_score': seo_score
            })
            
        except Exception as e:
            results.append({
                'keyword': keyword,
                'success': False,
                'error': 'An error occurred. Please try again.'
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
    
    data = request.get_json(silent=True) or {}
    old_status = content.status
    
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
    if 'scheduled_for' in data:
        from datetime import datetime
        scheduled = data['scheduled_for']
        if scheduled:
            if isinstance(scheduled, str):
                # Parse ISO format
                try:
                    scheduled = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
                except ValueError:
                    return jsonify({'error': 'Invalid scheduled_for date format'}), 400
            content.scheduled_for = scheduled
        else:
            content.scheduled_for = None
    
    data_service.save_blog_post(content)
    
    # Send notification if status changed to approved
    new_status = data.get('status', '')
    if new_status == 'approved' and old_status != 'approved':
        try:
            from app.services.notification_service import get_notification_service
            from app.models.db_models import DBUser, DBClient
            import logging
            logger = logging.getLogger(__name__)
            
            notification_service = get_notification_service()
            admins = DBUser.query.filter_by(role='admin', is_active=True).all()
            client = DBClient.query.get(content.client_id)
            
            logger.info(f"Sending approval notifications to {len(admins)} admins for content {content_id}")
            
            for admin in admins:
                notification_service.notify_content_approved(
                    user_id=admin.id,
                    client_name=client.business_name if client else 'Unknown',
                    content_title=content.title,
                    approved_by=current_user.email,
                    content_id=content_id,
                    client_id=content.client_id
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to send approval notification: {e}")
            import traceback
            traceback.print_exc()
    
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
    """List all content for a client (blogs or social posts)"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    content_type = request.args.get('type', 'blog')
    status_filter = request.args.get('status')
    
    if content_type == 'social':
        # Get social posts
        platform = request.args.get('platform')
        content_list = data_service.get_client_social_posts(client_id, platform)
        
        if status_filter:
            content_list = [c for c in content_list if c.status == status_filter]
        
        return jsonify({
            'client_id': client_id,
            'total': len(content_list),
            'content': [c.to_dict() for c in content_list],
            'posts': [c.to_dict() for c in content_list]  # Alias for compatibility
        })
    else:
        # Get blog posts (default)
        content_list = data_service.get_client_blog_posts(client_id)
        
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
    data = request.get_json(silent=True) or {}
    
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
    Redirects to async generation to avoid timeout.
    This endpoint now starts async generation and returns task_id.
    Use /blog/task/<task_id> to check status.
    """
    # Just call the async version
    return generate_blog_async(current_user)


@content_bp.route('/blog/<blog_id>', methods=['PATCH'])
@token_required
def update_blog_post(current_user, blog_id):
    """
    Update a blog post
    
    PATCH /api/content/blog/{blog_id}
    {
        "title": "optional",
        "body": "optional",
        "meta_title": "optional",
        "meta_description": "optional",
        "featured_image_url": "optional",
        "status": "optional"
    }
    """
    from app.database import db
    
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    # Update allowed fields
    updatable_fields = [
        'title', 'body', 'meta_title', 'meta_description',
        'featured_image_url', 'status', 'primary_keyword',
        'slug', 'excerpt'
    ]
    
    updated_fields = []
    for field in updatable_fields:
        if field in data:
            setattr(blog, field, data[field])
            updated_fields.append(field)
    
    if updated_fields:
        db.session.commit()
    
    return jsonify({
        'success': True,
        'id': blog.id,
        'updated_fields': updated_fields,
        'blog': blog.to_dict()
    })


@content_bp.route('/blog/<blog_id>', methods=['GET'])
@token_required
def get_blog_post(current_user, blog_id):
    """
    Get a single blog post
    
    GET /api/content/blog/{blog_id}
    """
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(blog.to_dict())


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
    
    data = request.get_json(silent=True) or {}
    
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
            content=result.get('text', result.get('content', '')),  # AI returns 'text' not 'content'
            hashtags=result.get('hashtags', []),
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
        logger.error(f"Social generation error: {error_detail}")
        return jsonify({
            'error': 'An error occurred. Please try again.',
            'detail': 'Social post generation failed. Check server logs.'
        }), 500


# ==========================================
# WORDPRESS INTEGRATION
# ==========================================

@content_bp.route('/wordpress/test', methods=['POST'])
@token_required
def test_wordpress_connection(current_user):
    """
    Test WordPress connection for a client
    
    POST /api/content/wordpress/test
    {
        "client_id": "...",
        "wordpress_url": "https://example.com",
        "wordpress_user": "admin",
        "wordpress_app_password": "xxxx xxxx xxxx xxxx"
    }
    """
    data = request.get_json(silent=True) or {}
    
    wp_url = data.get('wordpress_url', '').strip()
    wp_user = data.get('wordpress_user', '').strip()
    wp_pass = data.get('wordpress_app_password', '').strip()
    
    if not all([wp_url, wp_user, wp_pass]):
        return jsonify({
            'success': False,
            'message': 'WordPress URL, username, and app password are required'
        }), 400
    
    try:
        from app.services.wordpress_service import WordPressService
        
        wp = WordPressService(
            site_url=wp_url,
            username=wp_user,
            app_password=wp_pass
        )
        
        result = wp.test_connection()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Connection error. Please check your network.'
        }), 500


@content_bp.route('/<content_id>/publish-wordpress', methods=['POST'])
@token_required
def publish_to_wordpress(current_user, content_id):
    """
    Publish a blog post to WordPress
    
    POST /api/content/{id}/publish-wordpress
    {
        "status": "draft|publish|future"  // optional, defaults based on blog status
    }
    """
    content = data_service.get_blog_post(content_id)
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get client
    client = data_service.get_client(content.client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Check WordPress config
    missing = []
    if not client.wordpress_url:
        missing.append('WordPress URL')
    if not client.wordpress_user:
        missing.append('WordPress Username')
    if not client.wordpress_app_password:
        missing.append('WordPress App Password')
    
    if missing:
        return jsonify({
            'success': False,
            'message': f'WordPress not configured. Missing: {", ".join(missing)}. Go to Edit Client → Integrations to add credentials.'
        }), 400
    
    try:
        from app.services.wordpress_service import WordPressService
        
        wp = WordPressService(
            site_url=client.wordpress_url,
            username=client.wordpress_user,
            app_password=client.wordpress_app_password
        )
        
        # Test connection first
        test = wp.test_connection()
        if not test.get('success'):
            return jsonify(test), 400
        
        # Determine WordPress status
        data = request.get_json(silent=True) or {}
        wp_status = data.get('status')
        
        if not wp_status:
            # Auto-determine based on blog status
            if content.status == 'approved' or content.status == 'published':
                wp_status = 'publish'
            elif content.status == 'scheduled' and content.scheduled_for:
                wp_status = 'future'
            else:
                wp_status = 'draft'
        
        # Prepare meta for Yoast SEO
        meta = None
        if content.meta_title or content.meta_description or content.primary_keyword:
            meta = {
                'meta_title': content.meta_title,
                'meta_description': content.meta_description,
                'focus_keyword': content.primary_keyword
            }
        
        # Build full content including FAQs
        full_content = content.body or ''
        
        # Append FAQ section if present
        if content.faq_content:
            try:
                faqs = json.loads(content.faq_content) if isinstance(content.faq_content, str) else content.faq_content
                if faqs and len(faqs) > 0:
                    faq_html = '\n\n<div class="faq-section">\n<h2>Frequently Asked Questions</h2>\n'
                    for faq in faqs:
                        q = faq.get('question') or faq.get('q', '')
                        a = faq.get('answer') or faq.get('a', '')
                        if q and a:
                            faq_html += f'<div class="faq-item">\n<h3>{q}</h3>\n<p>{a}</p>\n</div>\n'
                    faq_html += '</div>'
                    full_content += faq_html
            except (json.JSONDecodeError, TypeError):
                pass  # Skip FAQ if parsing fails
        
        # Append Schema JSON-LD if present
        if content.schema_markup:
            try:
                schema = json.loads(content.schema_markup) if isinstance(content.schema_markup, str) else content.schema_markup
                if schema:
                    schema_html = f'\n\n<script type="application/ld+json">\n{json.dumps(schema, indent=2)}\n</script>'
                    full_content += schema_html
            except (json.JSONDecodeError, TypeError):
                pass  # Skip schema if parsing fails
        
        # Build tags from secondary keywords
        tags = []
        if content.secondary_keywords:
            try:
                keywords = json.loads(content.secondary_keywords) if isinstance(content.secondary_keywords, str) else content.secondary_keywords
                if keywords:
                    tags = keywords[:10]  # Limit to 10 tags
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Add primary keyword as first tag
        if content.primary_keyword:
            tags = [content.primary_keyword] + [t for t in tags if t.lower() != content.primary_keyword.lower()]
        
        # Check if updating existing post
        if content.wordpress_post_id:
            result = wp.update_post(
                post_id=content.wordpress_post_id,
                title=content.title,
                content=full_content,
                status=wp_status,
                excerpt=content.meta_description
            )
            # Also update Yoast SEO meta on existing post
            if result.get('success') and (content.meta_title or content.meta_description or content.primary_keyword):
                wp._set_seo_meta(
                    content.wordpress_post_id,
                    meta_title=content.meta_title,
                    meta_description=content.meta_description,
                    focus_keyword=content.primary_keyword
                )
        else:
            # Create new post
            result = wp.create_post(
                title=content.title,
                content=full_content,
                status=wp_status,
                excerpt=content.meta_description,
                meta_title=content.meta_title,  # For Yoast SEO title
                meta_description=content.meta_description,  # For Yoast meta description
                focus_keyword=content.primary_keyword,  # For Yoast focus keyword
                featured_image_url=content.featured_image_url,  # Featured image for post
                meta=meta,
                tags=tags if tags else None,
                date=content.scheduled_for if wp_status == 'future' else None
            )
        
        if result.get('success'):
            # Update blog with WordPress post ID
            content.wordpress_post_id = result.get('post_id')
            content.status = 'published' if wp_status == 'publish' else content.status
            data_service.save_blog_post(content)
            
            result['blog_status'] = content.status
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        if 'Connection refused' in error_msg or 'timeout' in error_msg.lower():
            msg = f'Cannot reach WordPress site at {client.wordpress_url}. Check if the URL is correct.'
        elif '401' in error_msg or 'Unauthorized' in error_msg:
            msg = 'WordPress authentication failed. Check your username and app password.'
        elif '403' in error_msg or 'Forbidden' in error_msg:
            msg = 'WordPress denied access. The app password may be invalid or expired.'
        elif '404' in error_msg:
            msg = f'WordPress REST API not found at {client.wordpress_url}. Ensure WordPress is installed and permalinks are enabled.'
        else:
            msg = f'Publish failed: {error_msg[:100]}' if error_msg else 'Publish failed. Check WordPress connection.'
        
        return jsonify({
            'success': False,
            'message': msg
        }), 500


@content_bp.route('/bulk-delete', methods=['POST'])
@token_required
def bulk_delete_content(current_user):
    """
    Bulk delete blog posts
    
    POST /api/content/bulk-delete
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
    errors = []
    
    for content_id in ids:
        try:
            content = data_service.get_blog_post(content_id)
            if content and current_user.has_access_to_client(content.client_id):
                data_service.delete_blog_post(content_id)
                deleted += 1
            else:
                errors.append(f"{content_id}: not found or access denied")
        except Exception as e:
            errors.append(f"{content_id}: {str(e)}")
    
    return jsonify({
        'deleted': deleted,
        'errors': errors,
        'message': f'Deleted {deleted} posts' + (f', {len(errors)} errors' if errors else '')
    })


@content_bp.route('/bulk-approve', methods=['POST'])
@token_required
def bulk_approve_content(current_user):
    """
    Bulk approve blog posts
    
    POST /api/content/bulk-approve
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
    
    approved = 0
    
    for content_id in ids:
        try:
            content = data_service.get_blog_post(content_id)
            if content and current_user.has_access_to_client(content.client_id):
                content.status = 'approved'
                data_service.save_blog_post(content)
                approved += 1
        except Exception:
            pass
    
    return jsonify({
        'approved': approved,
        'message': f'Approved {approved} posts'
    })


@content_bp.route('/<content_id>/feedback', methods=['POST'])
@token_required
def submit_content_feedback(current_user, content_id):
    """
    Submit feedback/change request for content
    
    POST /api/content/{id}/feedback
    {
        "feedback": "Please update the introduction...",
        "type": "change_request|approval|comment"
    }
    """
    content = data_service.get_blog_post(content_id)
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    feedback_text = data.get('feedback', '')
    feedback_type = data.get('type', 'comment')
    
    if not feedback_text:
        return jsonify({'error': 'Feedback text required'}), 400
    
    try:
        from app.database import db
        from app.models.db_models import DBContentFeedback, DBClient
        from datetime import datetime
        
        # Get client for email notification
        client = DBClient.query.get(content.client_id)
        
        # Create feedback record
        feedback = DBContentFeedback(
            content_id=content_id,
            client_id=content.client_id,
            user_id=current_user.id,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            created_at=datetime.utcnow()
        )
        db.session.add(feedback)
        
        # If change request, set content back to draft
        if feedback_type == 'change_request':
            content.status = 'draft'
            # Add note to content
            notes = content.notes or ''
            content.notes = f"{notes}\n[{datetime.utcnow().strftime('%Y-%m-%d')}] Client feedback: {feedback_text}"
        
        db.session.commit()
        
        # Send email notification (async in production)
        try:
            from app.services.email_service import get_email_service
            email = get_email_service()
            
            email.send_simple(
                to=current_user.email,  # In production, send to agency admin
                subject=f"📝 Content Feedback: {content.title}",
                body=f"""
Client Feedback Received

Content: {content.title}
Client: {client.business_name if client else 'Unknown'}
Type: {feedback_type.replace('_', ' ').title()}

Feedback:
{feedback_text}

---
Please review and update the content accordingly.
                """.strip()
            )
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
        
        return jsonify({
            'success': True,
            'message': 'Feedback submitted successfully',
            'feedback_id': feedback.id
        })
        
    except Exception as e:
        # If model doesn't exist, just return success (feedback noted)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': True,
            'message': 'Feedback noted (database model pending)'
        })
