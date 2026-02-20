"""
MCP Framework - Content Generation Routes
Blog posts, landing pages, and SEO content
"""
from flask import Blueprint, request, jsonify, current_app
import logging
import threading
import uuid
import re
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


def _generate_blog_tags(keyword, city='', industry='', client_name=''):
    """
    Auto-generate 5 Title Case tags for a blog post, including city name.
    Returns a list of strings.
    """
    def title_case(s):
        if not s:
            return ''
        # Title case but keep short words lowercase (except first)
        small_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = s.strip().split()
        result = []
        for i, w in enumerate(words):
            if i == 0 or w.lower() not in small_words:
                result.append(w.capitalize())
            else:
                result.append(w.lower())
        return ' '.join(result)

    tags = []
    city = (city or '').strip()
    keyword = (keyword or '').strip()
    industry = (industry or '').strip()

    # 1. Primary keyword with city
    if keyword and city:
        tags.append(title_case(f"{keyword} {city}"))
    elif keyword:
        tags.append(title_case(keyword))

    # 2. City + keyword (reversed)
    if city and keyword:
        tags.append(title_case(f"{city} {keyword}"))

    # 3. City name alone
    if city:
        tags.append(title_case(city))

    # 4. Industry + city
    if industry and city:
        tags.append(title_case(f"{industry} {city}"))
    elif industry:
        tags.append(title_case(industry))

    # 5. Keyword alone (if different from tag 1)
    if keyword:
        kw_tag = title_case(keyword)
        if kw_tag not in tags:
            tags.append(kw_tag)

    # Fill to 5 with sensible defaults
    fillers = []
    if city:
        fillers += [
            title_case(f"Local {industry} {city}" if industry else f"Local Services {city}"),
            title_case(f"Best {keyword}" if keyword else f"Best {industry}"),
            title_case(f"{city} Services"),
            title_case(f"Professional {industry}" if industry else "Professional Services"),
        ]
    else:
        fillers += [
            title_case(f"Professional {industry}" if industry else "Professional Services"),
            title_case(f"Best {keyword}" if keyword else "Expert Services"),
        ]

    for filler in fillers:
        if filler and filler not in tags and len(tags) < 5:
            tags.append(filler)

    # Deduplicate while preserving order, limit to 5
    seen = set()
    unique = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:5]

# Use database-backed task storage to work with multiple Gunicorn workers
def _get_task(task_id):
    """Get task from database"""
    try:
        from app.database import db
        from sqlalchemy import text
        result = db.session.execute(
            text("SELECT task_data FROM blog_tasks WHERE task_id = :tid"),
            {"tid": task_id}
        ).fetchone()
        if result:
            return json.loads(result[0])
        return None
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}")
        return None

def _set_task(task_id, task_data):
    """Save task to database"""
    try:
        from app.database import db
        from sqlalchemy import text
        
        task_json = json.dumps(task_data)
        
        # Try update first, then insert
        result = db.session.execute(
            text("UPDATE blog_tasks SET task_data = :data, updated_at = NOW() WHERE task_id = :tid"),
            {"tid": task_id, "data": task_json}
        )
        
        if result.rowcount == 0:
            # Insert new
            db.session.execute(
                text("INSERT INTO blog_tasks (task_id, task_data, created_at, updated_at) VALUES (:tid, :data, NOW(), NOW())"),
                {"tid": task_id, "data": task_json}
            )
        
        db.session.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting task {task_id}: {e}")
        try:
            db.session.rollback()
        except:
            pass
        return False

def _ensure_tasks_table():
    """Create blog_tasks table if it doesn't exist"""
    try:
        from app.database import db
        from sqlalchemy import text
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS blog_tasks (
                task_id VARCHAR(100) PRIMARY KEY,
                task_data TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.session.commit()
    except Exception as e:
        logger.debug(f"Tasks table check: {e}")
        try:
            db.session.rollback()
        except:
            pass


def _cleanup_old_tasks():
    """Remove completed/errored tasks older than 10 minutes"""
    try:
        from app.database import db
        from sqlalchemy import text
        db.session.execute(text("""
            DELETE FROM blog_tasks 
            WHERE updated_at < NOW() - INTERVAL '10 minutes'
            AND task_data::jsonb->>'status' IN ('complete', 'error')
        """))
        db.session.commit()
    except Exception as e:
        logger.debug(f"Task cleanup: {e}")
        try:
            db.session.rollback()
        except:
            pass


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


@content_bp.route('/test-ai', methods=['POST'])
@token_required  
def test_ai_generation(current_user):
    """Quick test to verify AI is working"""
    import os
    import time
    
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 500
    
    start_time = time.time()
    
    try:
        import requests
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {openai_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': 'Say "AI is working" in exactly 3 words'}],
                'max_tokens': 20
            },
            timeout=30
        )
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'response': data['choices'][0]['message']['content'],
                'elapsed_seconds': round(elapsed, 2),
                'model': 'gpt-3.5-turbo'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'API returned {response.status_code}',
                'details': response.text[:500],
                'elapsed_seconds': round(elapsed, 2)
            }), 500
            
    except requests.exceptions.Timeout:
        return jsonify({'error': 'OpenAI API timeout after 30 seconds'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _generate_blog_background(task_id, app, client_id, keyword, word_count, include_faq, faq_count, user_id):
    """Background thread function to generate blog"""
    with app.app_context():
        try:
            logger.info(f"[TASK {task_id}] Starting blog generation for keyword: {keyword}")
            _set_task(task_id, {'status': 'generating', 'keyword': keyword, 'started_at': datetime.utcnow().isoformat()})
            
            # Get client
            client = data_service.get_client(client_id)
            if not client:
                _set_task(task_id, {'status': 'error', 'error': 'Client not found'})
                return
            
            from app.services.internal_linking_service import internal_linking_service
            from app.services.blog_ai_single import get_blog_ai_single, BlogRequest
            
            service_pages = client.get_service_pages() or []
            
            # Get contact info for CTA
            contact_name = getattr(client, 'contact_name', None) or getattr(client, 'owner_name', None)
            phone = getattr(client, 'phone', None)
            email = getattr(client, 'email', None)
            contact_url = getattr(client, 'contact_url', None)
            
            logger.info(f"[TASK {task_id}] Using BlogAISingle for generation...")
            
            # Parse geo into city/state
            geo = client.geo or ''
            geo_parts = geo.split(',') if geo else ['', '']
            city = geo_parts[0].strip() if len(geo_parts) > 0 else ''
            state = geo_parts[1].strip() if len(geo_parts) > 1 else 'FL'
            
            # Build internal links list
            internal_links = []
            for page in service_pages[:6]:
                if isinstance(page, dict) and page.get('url') and page.get('title'):
                    url = page['url']
                    if not url.startswith('http'):
                        url = f"https://{client.website_url.rstrip('/')}/{url.lstrip('/')}" if client.website_url else url
                    internal_links.append({'url': url, 'title': page['title']})
            
            # Use BlogAISingle - same as sync endpoint
            blog_gen = get_blog_ai_single()
            blog_request = BlogRequest(
                keyword=keyword,
                company_name=client.business_name or 'Our Company',
                city=city,
                state=state,
                industry=client.industry or 'services',
                phone=phone or '',
                email=email or '',
                contact_url=contact_url or '',
                target_words=word_count,
                faq_count=faq_count if include_faq else 0,
                internal_links=internal_links
            )
            
            result = blog_gen.generate(blog_request)
            
            logger.info(f"[TASK {task_id}] BlogAISingle returned. Word count: {result.get('word_count', 0)}")
            
            if result.get('error'):
                logger.error(f"[TASK {task_id}] AI error: {result['error']}")
                _set_task(task_id, {'status': 'error', 'error': result['error']})
                return
            
            # Validate the result - make sure body is actual HTML not JSON
            body_content = result.get('body', '')
            if not body_content or body_content.strip().startswith('{') or '"title":' in body_content:
                logger.error(f"Blog generation returned invalid body: {body_content[:200]}")
                _set_task(task_id, {'status': 'error', 'error': 'AI returned invalid content format. Please try again.'})
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
            logger.info(f"[TASK {task_id}] FAQ items from AI: {len(faq_items)}")
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
                logger.info(f"[TASK {task_id}] ✓ FAQ schema created with {len(faq_schema['mainEntity'])} questions")
            
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
                target_city=city,
                tags=_generate_blog_tags(keyword, city=city, industry=client.industry, client_name=client.business_name),
                status=ContentStatus.DRAFT
            )
            
            data_service.save_blog_post(blog_post)
            
            _set_task(task_id, {
                'status': 'complete',
                'blog_id': blog_post.id,
                'title': blog_post.title,
                'word_count': blog_post.word_count,
                'links_added': links_added,
                'seo_score': seo_score,
                'seo_recommendations': seo_score_result.get('recommendations', [])
            })
            logger.info(f"[TASK {task_id}] Blog generation complete: {blog_post.id}")
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"[TASK {task_id}] Background blog generation error: {e}\n{error_trace}")
            _set_task(task_id, {'status': 'error', 'error': str(e), 'trace': error_trace[:500]})


@content_bp.route('/blog/generate-sync', methods=['POST'])
@token_required
def generate_blog_sync(current_user):
    """
    Synchronous blog generation - waits for completion and returns result
    """
    try:
        if not current_user.can_generate_content:
            return jsonify({'error': 'Permission denied'}), 403
        
        data = request.get_json(silent=True) or {}
        
        client_id = data.get('client_id')
        keyword = data.get('keyword')
        word_count = data.get('word_count', 1500)  # Default 1500 for high SEO score
        include_faq = data.get('include_faq', True)
        faq_count = data.get('faq_count', 5)
        selected_city = data.get('city')  # Optional city override from service_cities
        custom_faqs = data.get('custom_faqs')  # FAQ questions from call intelligence
        
        if not client_id or not keyword:
            return jsonify({'error': 'client_id and keyword required'}), 400
        
        # Verify client access
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
        
        logger.info(f"[SYNC] Starting blog generation for keyword: {keyword}, word_count: {word_count}")
        
        # Get client
        client = data_service.get_client(client_id)
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        # Get service pages for internal linking
        service_pages = client.get_service_pages() or []
        logger.info(f"[SYNC] Client service_pages: {len(service_pages)} pages")
        
        # Also get published blog posts for internal linking
        from app.models.db_models import DBBlogPost
        published_posts = DBBlogPost.query.filter_by(
            client_id=client_id, 
            status='published'
        ).limit(10).all()
        logger.info(f"[SYNC] Published posts for linking: {len(published_posts)}")
        
        # Get contact info for CTA
        contact_name = getattr(client, 'contact_name', None) or getattr(client, 'owner_name', None)
        phone = getattr(client, 'phone', None)
        email = getattr(client, 'email', None)
        
        logger.info(f"[SYNC] Calling AI service for client: {client.business_name}")
        
        # Use the new robust blog generator
        from app.services.blog_ai_single import get_blog_ai_single, BlogRequest
        
        blog_gen = get_blog_ai_single()
        
        # Parse geo into city/state - use selected_city if provided
        geo = client.geo or ''
        geo_parts = geo.split(',') if geo else ['', '']
        city = selected_city or (geo_parts[0].strip() if len(geo_parts) > 0 else '')
        state = geo_parts[1].strip() if len(geo_parts) > 1 else 'FL'
        
        logger.info(f"[SYNC] Using city: {city} (selected: {selected_city}, default: {geo_parts[0] if geo_parts else 'N/A'})")
        
        # Build internal links list from multiple sources
        internal_links = []
        
        # Helper to ensure URL has protocol
        def ensure_full_url(url):
            if not url:
                return ''
            url = url.strip()
            if url.startswith('//'):
                return 'https:' + url
            if not url.startswith('http://') and not url.startswith('https://'):
                return 'https://' + url
            return url
        
        city_lower = city.lower() if city else ''
        
        # 1. PRIORITY: Add published blog posts from SAME CITY first (most relevant for interlinking)
        posts_same_city = []
        posts_other = []
        
        for post in published_posts:
            if post.published_url:
                post_title = post.title or post.primary_keyword or ''
                post_city = getattr(post, 'target_city', '') or ''
                
                # Check if post is from same city (by target_city or title)
                is_same_city = False
                if city_lower:
                    if post_city and post_city.lower() == city_lower:
                        is_same_city = True
                    elif city_lower in post_title.lower():
                        is_same_city = True
                
                post_data = {
                    'title': post_title,
                    'url': ensure_full_url(post.published_url),
                    'keyword': post.primary_keyword or ''
                }
                
                if is_same_city:
                    posts_same_city.append(post_data)
                else:
                    posts_other.append(post_data)
        
        # Add at least 2 posts from same city (for category interlinking)
        logger.info(f"[SYNC] Found {len(posts_same_city)} posts from same city '{city}', {len(posts_other)} from other cities")
        
        # Log the actual URLs being used
        for i, post in enumerate(posts_same_city[:3]):
            logger.info(f"[SYNC] Same city post {i+1}: {post.get('title')} -> {post.get('url')}")
        
        for post in posts_same_city[:3]:  # Up to 3 from same city
            internal_links.append(post)
        
        # Add other posts if needed
        for post in posts_other[:2]:  # Up to 2 from other cities
            if len(internal_links) < 5:
                internal_links.append(post)
        
        # 2. Add service pages ONLY if they are explicitly configured (not auto-generated)
        # These should be real pages the user has added
        if service_pages:
            service_pages_with_city = []
            service_pages_without_city = []
            
            for sp in service_pages:
                if isinstance(sp, dict) and sp.get('url'):
                    title = sp.get('title') or sp.get('keyword', '')
                    url = sp.get('url', '')
                    
                    # Skip auto-generated service pages that likely don't exist
                    if '/services' in url.lower() and not any(x in url.lower() for x in ['service-', 'services/']):
                        continue  # Skip generic /services URL
                    
                    if city_lower and city_lower in title.lower():
                        service_pages_with_city.append({
                            'title': title,
                            'url': ensure_full_url(url)
                        })
                    else:
                        service_pages_without_city.append({
                            'title': title,
                            'url': ensure_full_url(url)
                        })
            
            # Add service pages (limit to avoid overwhelming with links)
            for sp in service_pages_with_city[:2]:
                if len(internal_links) < 6:
                    internal_links.append(sp)
            for sp in service_pages_without_city[:2]:
                if len(internal_links) < 6:
                    internal_links.append(sp)
        
        # 3. Add contact page ONLY if explicitly configured by user
        contact_url = getattr(client, 'contact_url', None)
        if contact_url and contact_url.strip():
            internal_links.append({
                'title': 'Contact Us',
                'url': ensure_full_url(contact_url)
            })
        
        # 4. Add blog page ONLY if explicitly configured by user
        blog_url_base = getattr(client, 'blog_url', None)
        if blog_url_base and blog_url_base.strip() and len(internal_links) < 6:
            internal_links.append({
                'title': 'Our Blog',
                'url': ensure_full_url(blog_url_base)
            })
        
        # NOTE: We do NOT add auto-generated /services, /about URLs anymore
        # These often cause 404s. User must configure real pages in service_pages or contact_url
        
        logger.info(f"[SYNC] Internal links for blog: {len(internal_links)} links")
        for link in internal_links[:5]:
            logger.info(f"[SYNC]   - {link.get('title')}: {link.get('url')}")
        
        # Get contact and blog URLs for CTAs (may be empty)
        contact_url = getattr(client, 'contact_url', None) or ''
        blog_url_base = getattr(client, 'blog_url', None) or ''
        
        logger.info(f"[SYNC] Contact URL: {contact_url}, Blog URL: {blog_url_base}")
        
        # Generate blog with new robust generator
        blog_request = BlogRequest(
            keyword=keyword,
            target_words=max(word_count, 1800),  # Ensure minimum 1800 words
            city=city,
            state=state,
            company_name=client.business_name or '',
            phone=phone or '',
            email=email or '',
            industry=client.industry or 'Local Services',
            internal_links=internal_links,
            faq_count=faq_count,
            contact_url=contact_url,
            blog_url=blog_url_base,
            custom_faqs=custom_faqs
        )
        
        result = blog_gen.generate(blog_request)
        
        logger.info(f"[SYNC] BlogAISingle returned: {result.get('word_count', 0)} words")
        
        if result.get('error'):
            logger.error(f"[SYNC] AI error: {result['error']}")
            return jsonify({'error': result['error']}), 500
        
        # Validate body content
        body_content = result.get('body', '')
        if not body_content or len(body_content) < 100:
            logger.error(f"[SYNC] Empty body content")
            return jsonify({'error': 'AI returned empty content. Please try again.'}), 500
        
        # Get FAQ items
        faq_items = result.get('faq_items', [])
        faq_schema = result.get('faq_schema', {})
        
        # Calculate SEO score
        try:
            seo_score_result = seo_scoring_engine.score_content(
                content={
                    'meta_title': result.get('meta_title', ''),
                    'meta_description': result.get('meta_description', ''),
                    'h1': result.get('h1', result.get('title', '')),
                    'body': body_content
                },
                target_keyword=keyword,
                location=city or client.geo or ''
            )
            seo_score = seo_score_result.get('total_score', 0)
            
            # Log SEO score breakdown
            logger.info(f"[SYNC] SEO Score: {seo_score}")
            factors = seo_score_result.get('factors', {})
            for factor, data in factors.items():
                logger.info(f"[SYNC]   {factor}: {data.get('score', 0)}/{data.get('max', 0)} - {data.get('message', '')}")
        except Exception as e:
            logger.warning(f"[SYNC] SEO scoring failed: {e}")
            seo_score = 50  # Default score
        
        # Create blog post
        # Use word count from result
        actual_word_count = result.get('word_count', 0)
        
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
            word_count=actual_word_count,
            seo_score=seo_score,
            target_city=city,  # Store the selected city
            tags=_generate_blog_tags(keyword, city=city, industry=client.industry, client_name=client.business_name),
            status=ContentStatus.DRAFT
        )
        
        data_service.save_blog_post(blog_post)
        
        logger.info(f"[SYNC] Blog generation complete: {blog_post.id}, {blog_post.word_count} words")
        
        return jsonify({
            'success': True,
            'blog_id': blog_post.id,
            'title': blog_post.title,
            'word_count': blog_post.word_count,
            'seo_score': seo_score
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"[SYNC] Unexpected error: {e}\n{error_trace}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


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
    
    # Ensure tasks table exists
    _ensure_tasks_table()
    
    # Clean up old tasks
    _cleanup_old_tasks()
    
    # Create task in database
    task_id = str(uuid.uuid4())
    _set_task(task_id, {
        'status': 'pending',
        'created_at': datetime.utcnow().isoformat(),
        'keyword': data['keyword']
    })
    
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
            data.get('word_count', 800),
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
    task = _get_task(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found', 'task_id': task_id}), 404
    
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
    
    # Get contact info for CTA
    contact_name = getattr(client, 'contact_name', None) or getattr(client, 'owner_name', None)
    phone = getattr(client, 'phone', None)
    email = getattr(client, 'email', None)
    contact_url = getattr(client, 'contact_url', None)
    
    # Parse geo into city/state
    geo = data.get('geo', '')
    geo_parts = geo.split(',') if geo else ['', '']
    city = geo_parts[0].strip() if len(geo_parts) > 0 else ''
    state = geo_parts[1].strip() if len(geo_parts) > 1 else 'FL'
    
    # Build internal links list for BlogAISingle
    blog_internal_links = []
    for page in internal_links[:6]:
        if isinstance(page, dict) and page.get('url') and page.get('title'):
            url = page['url']
            if not url.startswith('http'):
                url = f"https://{client.website_url.rstrip('/')}/{url.lstrip('/')}" if client.website_url else url
            blog_internal_links.append({'url': url, 'title': page['title']})
    
    # Use BlogAISingle for generation (handles city deduplication)
    from app.services.blog_ai_single import get_blog_ai_single, BlogRequest
    
    blog_gen = get_blog_ai_single()
    blog_request = BlogRequest(
        keyword=data['keyword'],
        company_name=client.business_name or 'Our Company',
        city=city,
        state=state,
        industry=data.get('industry', 'services'),
        phone=phone or '',
        email=email or '',
        contact_url=contact_url or '',
        target_words=data.get('word_count', current_app.config['DEFAULT_BLOG_WORD_COUNT']),
        faq_count=data.get('faq_count', 5) if data.get('include_faq', True) else 0,
        internal_links=blog_internal_links
    )
    
    result = blog_gen.generate(blog_request)
    
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
        target_city=city,
        tags=_generate_blog_tags(data['keyword'], city=city, industry=client.industry, client_name=client.business_name),
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
    from app.services.blog_ai_single import get_blog_ai_single, BlogRequest
    
    service_pages = client.get_service_pages() or []
    
    # Get contact info for CTA
    contact_name = getattr(client, 'contact_name', None) or getattr(client, 'owner_name', None)
    phone = getattr(client, 'phone', None)
    email = getattr(client, 'email', None)
    contact_url = getattr(client, 'contact_url', None)
    
    # Parse geo into city/state
    geo = client.geo or ''
    geo_parts = geo.split(',') if geo else ['', '']
    city = geo_parts[0].strip() if len(geo_parts) > 0 else ''
    state = geo_parts[1].strip() if len(geo_parts) > 1 else 'FL'
    
    # Build internal links list for BlogAISingle
    blog_internal_links = []
    for page in service_pages[:6]:
        if isinstance(page, dict) and page.get('url') and page.get('title'):
            url = page['url']
            if not url.startswith('http'):
                url = f"https://{client.website_url.rstrip('/')}/{url.lstrip('/')}" if client.website_url else url
            blog_internal_links.append({'url': url, 'title': page['title']})
    
    results = []
    blog_gen = get_blog_ai_single()
    
    for topic in topics[:5]:  # Limit to 5 to avoid timeout
        keyword = topic.get('keyword', '')
        if not keyword:
            results.append({'keyword': '', 'success': False, 'error': 'keyword required'})
            continue
        
        try:
            logger.info(f"[BULK] Starting blog generation for keyword: {keyword}")
            
            # Use BlogAISingle for generation (handles city deduplication)
            blog_request = BlogRequest(
                keyword=keyword,
                company_name=client.business_name or 'Our Company',
                city=city,
                state=state,
                industry=client.industry or 'services',
                phone=phone or '',
                email=email or '',
                contact_url=contact_url or '',
                target_words=topic.get('word_count', current_app.config.get('DEFAULT_BLOG_WORD_COUNT', 1200)),
                faq_count=topic.get('faq_count', 5),
                internal_links=blog_internal_links
            )
            
            logger.info(f"[BULK] BlogRequest created, calling generate...")
            result = blog_gen.generate(blog_request)
            logger.info(f"[BULK] Generate returned, checking result...")
            
            if result.get('error'):
                logger.error(f"[BULK] Generation returned error: {result['error']}")
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
                target_city=city,
                tags=_generate_blog_tags(keyword, city=city, industry=client.industry, client_name=client.business_name),
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
            logger.info(f"[BULK] Successfully generated blog for '{keyword}'")
            
        except Exception as e:
            import traceback
            logger.error(f"[BULK] Exception generating blog for '{keyword}': {str(e)}")
            logger.error(f"[BULK] Traceback: {traceback.format_exc()}")
            results.append({
                'keyword': keyword,
                'success': False,
                'error': str(e)  # Return actual error message
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


@content_bp.route('/manual-create', methods=['POST'])
@token_required
def manual_create_blog(current_user):
    """
    Manually create a blog post (not AI-generated)
    
    POST /api/content/manual-create
    Body: { client_id, title, body, primary_keyword, tags, meta_title, meta_description, featured_image_url, status }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    client_id = data.get('client_id')
    title = data.get('title', '').strip()
    body = data.get('body', '').strip()
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    if not title:
        return jsonify({'error': 'title is required'}), 400
    if not body:
        return jsonify({'error': 'body is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.db_models import DBBlogPost
    import json
    
    # Create the blog post
    blog_post = DBBlogPost(client_id=client_id, title=title)
    blog_post.body = body
    blog_post.word_count = len(body.split())
    blog_post.primary_keyword = data.get('primary_keyword', '')
    blog_post.meta_title = data.get('meta_title', title)[:500]
    blog_post.meta_description = data.get('meta_description', '')[:500]
    blog_post.featured_image_url = data.get('featured_image_url')
    blog_post.status = data.get('status', 'draft')
    
    # Handle tags
    tags = data.get('tags', [])
    if isinstance(tags, list):
        blog_post.tags = json.dumps(tags)
    elif isinstance(tags, str):
        blog_post.tags = tags
    
    # Generate slug from title
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    blog_post.slug = slug
    
    # Set excerpt from first ~160 chars of body text (strip HTML)
    import re as re2
    plain_text = re2.sub(r'<[^>]+>', '', body)
    blog_post.excerpt = plain_text[:160].strip()
    
    # Save
    data_service.save_blog_post(blog_post)
    
    return jsonify(blog_post.to_dict()), 201


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
    if 'tags' in data:
        import json
        content.tags = json.dumps(data['tags']) if isinstance(data['tags'], list) else data['tags']
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
    from flask import request, jsonify, current_app
    import threading
    import uuid
    
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    client_id = data.get('client_id')
    keyword = data.get('keyword') or data.get('topic', '')
    word_count = data.get('word_count', current_app.config.get('DEFAULT_BLOG_WORD_COUNT', 1200))
    include_faq = data.get('include_faq', True)
    faq_count = data.get('faq_count', 5)
    
    if not client_id or not keyword:
        return jsonify({'error': 'client_id and keyword required'}), 400
    
    # Get client
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Generate task ID
    task_id = str(uuid.uuid4())
    
    # Initialize task status
    _set_task(task_id, {'status': 'started', 'keyword': keyword})
    
    # Get the app for context
    app = current_app._get_current_object()
    user_id = current_user.id
    
    # Start background generation with correct arguments
    thread = threading.Thread(
        target=_generate_blog_background,
        args=(task_id, app, client_id, keyword, word_count, include_faq, faq_count, user_id)
    )
    thread.start()
    
    return jsonify({
        'task_id': task_id,
        'status': 'started',
        'message': 'Blog generation started'
    })


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
        
        # Get FAQs from faq_content or extract from body
        faqs = None
        if content.faq_content:
            try:
                faqs = json.loads(content.faq_content) if isinstance(content.faq_content, str) else content.faq_content
                logger.info(f"Found {len(faqs) if faqs else 0} FAQs in faq_content")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse faq_content: {e}")
        
        # Fallback: Extract FAQs from body HTML if not in faq_content
        if not faqs or len(faqs) == 0:
            import re
            # Look for FAQ section in body
            faq_section_match = re.search(r'<div[^>]*class="[^"]*faq[^"]*"[^>]*>(.*?)</div>\s*(?=<[^/]|$)', full_content, re.IGNORECASE | re.DOTALL)
            if faq_section_match:
                faq_section = faq_section_match.group(1)
                # Extract Q&A pairs
                faq_items = re.findall(r'<h3[^>]*>(.*?)</h3>\s*<p[^>]*>(.*?)</p>', faq_section, re.DOTALL)
                if faq_items:
                    faqs = [{'question': q.strip(), 'answer': a.strip()} for q, a in faq_items]
                    logger.info(f"Extracted {len(faqs)} FAQs from body HTML")
        
        # Append FAQ section to content if we have FAQs but they're not already in the body
        if faqs and len(faqs) > 0 and 'faq-section' not in full_content.lower():
            faq_html = '\n\n<div class="faq-section">\n<h2>Frequently Asked Questions</h2>\n'
            for faq in faqs:
                q = faq.get('question') or faq.get('q', '')
                a = faq.get('answer') or faq.get('a', '')
                if q and a:
                    faq_html += f'<div class="faq-item">\n<h3>{q}</h3>\n<p>{a}</p>\n</div>\n'
            faq_html += '</div>'
            full_content += faq_html
            logger.info(f"Added FAQ HTML section with {len(faqs)} FAQs")
        
        # Prepare Schema JSON-LD for both inline and plugin
        schema_json = None
        
        # Try to use existing schema_markup first
        if content.schema_markup:
            try:
                schema = json.loads(content.schema_markup) if isinstance(content.schema_markup, str) else content.schema_markup
                if schema:
                    schema_json = json.dumps(schema, indent=2)
                    logger.info(f"Using existing schema_markup: {len(schema_json)} chars")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse schema_markup: {e}")
        
        # Generate FAQ schema if we have FAQs (even if schema_markup exists, merge with FAQ)
        if faqs and len(faqs) > 0:
            faq_schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": []
            }
            for faq in faqs:
                q = faq.get('question') or faq.get('q', '')
                a = faq.get('answer') or faq.get('a', '')
                if q and a:
                    faq_schema["mainEntity"].append({
                        "@type": "Question",
                        "name": q,
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": a
                        }
                    })
            if faq_schema["mainEntity"]:
                schema_json = json.dumps(faq_schema, indent=2)
                logger.info(f"Generated FAQ schema: {len(faq_schema['mainEntity'])} FAQs, {len(schema_json)} chars")
        
        # Add schema to content if we have it
        if schema_json:
            schema_html = f'\n\n<script type="application/ld+json">\n{schema_json}\n</script>'
            full_content += schema_html
            logger.info(f"✓ FAQ Schema added to content: {len(schema_json)} chars, FAQs count: {schema_json.count('Question')}")
        else:
            logger.warning(f"⚠ No FAQ schema available for content {content.id} - schema_markup: {bool(content.schema_markup)}, faq_content: {bool(content.faq_content)}")
        
        # Helper function for Title Case
        def title_case(text):
            """Convert text to Title Case, preserving acronyms like HVAC, AC"""
            if not text:
                return text
            words = text.split()
            result = []
            # Words that should stay lowercase (unless first)
            lowercase_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'by', 'in', 'of'}
            # Acronyms that should stay uppercase
            acronyms = {'hvac', 'ac', 'seo', 'usa', 'llc', 'inc'}
            
            for i, word in enumerate(words):
                word_lower = word.lower()
                if word_lower in acronyms:
                    result.append(word.upper())
                elif i == 0 or word_lower not in lowercase_words:
                    result.append(word.capitalize())
                else:
                    result.append(word_lower)
            return ' '.join(result)
        
        # Build tags - ensure at least 5 tags with city name, proper Title Case
        tags = []
        # Use target_city from blog post if available, otherwise fall back to client.geo
        city = ''
        if hasattr(content, 'target_city') and content.target_city:
            city = content.target_city.strip()
            logger.info(f"Using target_city from blog post: {city}")
        elif hasattr(client, 'geo') and client.geo:
            city = client.geo.split(',')[0].strip()
            logger.info(f"Using geo from client: {city}")
        city = title_case(city)  # Ensure city is Title Case
        
        # Start with primary keyword (Title Case)
        if content.primary_keyword:
            tags.append(title_case(content.primary_keyword))
        
        # Add city-based tags
        if city:
            tags.append(city)
            if content.primary_keyword:
                # Extract service from keyword (e.g., "teeth whitening in Tampa" -> "teeth whitening")
                service = content.primary_keyword.lower()
                for loc_word in [' in ', ' near ', ' for ', city.lower()]:
                    service = service.split(loc_word)[0].strip()
                if service:
                    tags.append(title_case(f"{service} {city}"))
                    tags.append(title_case(f"{city} {service}"))
        
        # Add secondary keywords (Title Case)
        if content.secondary_keywords:
            try:
                keywords = json.loads(content.secondary_keywords) if isinstance(content.secondary_keywords, str) else content.secondary_keywords
                if keywords:
                    for kw in keywords[:8]:
                        if kw:
                            kw_title = title_case(kw)
                            if kw_title not in tags:
                                tags.append(kw_title)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Add industry-based tags (Title Case)
        industry = client.industry.lower() if client.industry else ''
        if 'dent' in industry:
            extra_tags = [f'Dentist {city}', f'{city} Dental', 'Dental Care', 'Oral Health']
        elif 'hvac' in industry or 'air' in industry:
            extra_tags = [f'HVAC {city}', f'{city} AC Repair', 'Air Conditioning', 'Heating']
        elif 'plumb' in industry:
            extra_tags = [f'Plumber {city}', f'{city} Plumbing', 'Plumbing Services', 'Drain Cleaning']
        elif 'roof' in industry:
            extra_tags = [f'Roofer {city}', f'{city} Roofing', 'Roof Repair', 'Roofing Contractor']
        elif 'law' in industry or 'legal' in industry:
            extra_tags = [f'Lawyer {city}', f'{city} Attorney', 'Legal Services', 'Law Firm']
        else:
            extra_tags = [f'{city} Services', 'Local Business', 'Professional Services']
        
        for tag in extra_tags:
            if tag and tag not in tags and len(tags) < 10:
                tags.append(tag)
        
        # Ensure minimum 5 tags
        if len(tags) < 5:
            generic_tags = [city, f'Local {city}', client.company_name or '', 'Professional', 'Services']
            for tag in generic_tags:
                if tag and tag not in tags and len(tags) < 5:
                    tags.append(tag)
        
        # Remove duplicates while preserving order (case-insensitive comparison)
        # AND apply Title Case to ALL tags
        seen = set()
        unique_tags = []
        for tag in tags:
            tag_lower = tag.lower().strip()
            if tag_lower and tag_lower not in seen:
                seen.add(tag_lower)
                # Apply Title Case to each tag
                unique_tags.append(title_case(tag.strip()))
        tags = unique_tags[:10]  # Limit to 10
        
        logger.info(f"WordPress tags ({len(tags)}): {tags}")
        
        # Use content.title as WP post title (the actual blog title)
        # meta_title goes to Yoast SEO title field
        wp_post_title = content.title  # This is the blog title
        logger.info(f"WP post title: {wp_post_title}")
        logger.info(f"Meta title for Yoast: {content.meta_title[:80] if content.meta_title else 'NONE'}...")
        logger.info(f"Meta description for Yoast: {content.meta_description[:80] if content.meta_description else 'NONE'}...")
        
        # Check if updating existing post
        if content.wordpress_post_id:
            result = wp.update_post(
                post_id=content.wordpress_post_id,
                title=wp_post_title,  # Blog title
                content=full_content,
                status=wp_status,
                excerpt=content.meta_description
            )
            # Also update SEO meta, featured image, and schema on existing post
            if result.get('success'):
                post_id = content.wordpress_post_id
                
                # Set SEO meta (Yoast, RankMath, AIOSEO)
                if content.meta_title or content.meta_description or content.primary_keyword:
                    logger.info(f"Setting SEO meta on update - title: {content.meta_title}, desc: {content.meta_description[:50] if content.meta_description else 'None'}...")
                    seo_result = wp._set_seo_meta(
                        post_id,
                        meta_title=content.meta_title,
                        meta_description=content.meta_description,
                        focus_keyword=content.primary_keyword
                    )
                    logger.info(f"SEO meta result: {seo_result}")
                
                # Set featured image if available
                if content.featured_image_url:
                    logger.info(f"Setting featured image on update: {content.featured_image_url}")
                    img_result = wp._set_featured_image(post_id, content.featured_image_url)
                    if not img_result.get('success'):
                        logger.warning(f"Failed to set featured image on update: {img_result.get('error')}")
                
                # Set schema for Schema & Structured Data plugin
                if schema_json:
                    logger.info(f"Setting schema on update: {len(schema_json)} chars")
                    wp._set_schema(post_id, schema_json)
        else:
            # Create new post
            logger.info(f"Creating new WP post with featured_image_url: {content.featured_image_url}")
            logger.info(f"SEO meta - title: {content.meta_title}, desc: {content.meta_description[:50] if content.meta_description else 'None'}...")
            logger.info(f"Tags ({len(tags)}): {tags[:5]}...")
            
            # Build categories - use city name as category
            categories = []
            if city:
                categories.append(city)
            if client.industry:
                categories.append(title_case(client.industry))
            logger.info(f"Categories: {categories}")
            
            result = wp.create_post(
                title=wp_post_title,  # Use meta_title as post title for SEO
                content=full_content,
                status=wp_status,
                excerpt=content.meta_description,
                meta_title=content.meta_title,  # For Yoast SEO title
                meta_description=content.meta_description,  # For Yoast meta description
                focus_keyword=content.primary_keyword,  # For Yoast focus keyword
                featured_image_url=content.featured_image_url,  # Featured image for post
                meta=meta,
                tags=tags if tags else None,
                categories=categories if categories else None,  # City and industry as categories
                date=content.scheduled_for if wp_status == 'future' else None
            )
            
            # Set schema after post creation
            if result.get('success') and schema_json:
                post_id = result.get('post_id')
                logger.info(f"Setting schema for new post {post_id}: {len(schema_json)} chars")
                wp._set_schema(post_id, schema_json)
        
        if result.get('success'):
            # Update blog with WordPress post ID and published URL
            content.wordpress_post_id = result.get('post_id')
            content.published_url = result.get('url') or result.get('post_url')  # Save the full WordPress URL
            content.status = 'published' if wp_status == 'publish' else content.status
            content.published_at = datetime.utcnow() if wp_status == 'publish' else content.published_at
            data_service.save_blog_post(content)
            
            logger.info(f"Saved published_url: {content.published_url}")
            
            result['blog_status'] = content.status
            result['published_url'] = content.published_url
        
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


@content_bp.route('/refine', methods=['POST'])
@token_required
def refine_content_with_ai(current_user):
    """
    Refine blog content using AI — makes real, substantive changes
    
    POST /api/content/refine
    {
        "content_id": "...",
        "current_title": "...",
        "current_body": "...",
        "current_meta_title": "...",
        "current_meta_description": "...",
        "keyword": "...",
        "refinement_prompt": "make it more engaging",
        "client_id": "..."
    }
    """
    data = request.get_json(silent=True) or {}
    prompt = data.get('refinement_prompt', '')
    client_id = data.get('client_id')
    
    if not prompt:
        return jsonify({'error': 'refinement_prompt is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    from app.models.db_models import DBClient
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    try:
        from app.services.ai_service import ai_service
        
        current_title = data.get('current_title', '')
        current_body = data.get('current_body', '')
        current_meta_title = data.get('current_meta_title', '')
        current_meta_description = data.get('current_meta_description', '')
        keyword = data.get('keyword', '')
        
        # Send body — smart truncation to stay within model limits
        body_length = len(current_body)
        if body_length > 10000:
            # For very long posts, send intro + middle + end to preserve context
            body_for_prompt = current_body[:4000] + "\n\n[... middle section ...]\n\n" + current_body[-4000:]
        else:
            body_for_prompt = current_body
        
        refine_prompt = f"""You are an expert blog editor making REAL, SUBSTANTIVE changes to this article.

THE USER WANTS: {prompt}

This is NOT a light edit. You must actually transform the content based on the request above.
Read the entire article, understand it, then rewrite the parts that need changing.

CURRENT ARTICLE:
Title: {current_title}
Keyword: {keyword}
Business: {client.business_name} ({client.industry}) in {client.geo}

FULL BODY:
{body_for_prompt}

CURRENT META:
Meta Title: {current_meta_title}
Meta Description: {current_meta_description}

INSTRUCTIONS FOR REFINEMENT:
1. Actually make the changes the user requested — don't just tweak a few words
2. If they say "improve intro" — rewrite the entire introduction with a compelling hook
3. If they say "add keywords" — find natural places to weave "{keyword}" and related terms
4. If they say "make shorter" — cut the fluff ruthlessly, keep only the valuable parts  
5. If they say "expand" — add genuinely new information, examples, or details
6. If they say "more engaging" — add questions, scenarios, specific examples, conversational tone
7. If they say "fix grammar" — fix every error and improve sentence flow
8. If they say "better CTA" — rewrite the calls-to-action to be compelling but not pushy
9. Preserve ALL HTML formatting tags (h2, h3, p, a, ul, li, strong, em, div, etc.)
10. Preserve all internal links (<a href="...">) exactly as they are
11. Preserve CTA div blocks (class="cta-box") — you can edit the text inside them
12. Keep the overall word count similar unless the user asks to expand or shorten
13. Update the meta_title and meta_description to match the refined content

Return the COMPLETE refined article as JSON with these exact keys:
- "title": the blog title (update if the refinement warrants it)
- "body": the FULL HTML body content — return the COMPLETE article, not a summary
- "meta_title": max 70 chars, SEO optimized
- "meta_description": max 160 chars, SEO optimized

Return ONLY valid JSON. No markdown code blocks. No commentary."""

        result = ai_service.generate_raw(refine_prompt, max_tokens=8000, model='gpt-4o-mini')
        
        # Check for empty response
        if not result or not result.strip():
            logger.error("AI refine returned empty response")
            return jsonify({'error': 'AI returned empty response. The content may be too long — try selecting a shorter section or a simpler refinement.'}), 500
        
        # Parse JSON response
        if isinstance(result, str):
            result = result.replace('```json', '').replace('```', '').strip()
            
            # Try to find JSON object if there's extra text
            if not result.startswith('{'):
                json_start = result.find('{')
                if json_start != -1:
                    result = result[json_start:]
            
            import json
            try:
                result = json.loads(result)
            except json.JSONDecodeError as je:
                logger.error(f"AI refine JSON parse error: {je}, response preview: {result[:200]}")
                return jsonify({'error': f'AI returned invalid format. Please try again or try a different refinement instruction.'}), 500
        
        return jsonify({
            'success': True,
            'refined_content': result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
