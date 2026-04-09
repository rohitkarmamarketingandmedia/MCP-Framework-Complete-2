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
from app.models.db_models import DBBlogPost, DBSocialPost, DBClient, ContentStatus
import json

content_bp = Blueprint('content', __name__)
ai_service = AIService()
seo_service = SEOService()
data_service = DataService()


def _generate_blog_tags(keyword, city='', industry='', client_name=''):
    """
    Auto-generate 5 Title Case tags for a blog post.
    EVERY tag must include the location/city name for local SEO.
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

    def ensure_city(tag_text):
        """Ensure every tag includes the city name for local SEO"""
        if not city:
            return tag_text
        if city.lower() in tag_text.lower():
            return tag_text
        return f"{tag_text} {city}"

    tags = []
    city = (city or '').strip()
    keyword = (keyword or '').strip()
    industry = (industry or '').strip()

    # Treat generic/placeholder industry values as empty — they produce useless tags
    _generic_industries = {'other', 'general', 'n/a', 'na', 'none', 'unknown', 'misc', 'miscellaneous', ''}
    if industry.lower() in _generic_industries:
        industry = ''

    # Extract the core service from keyword (strip location parts like "in City", "near City")
    import re
    core_service = keyword
    if keyword:
        core_service = re.split(r'\s+(?:in|near|for|around)\s+', keyword, flags=re.IGNORECASE)[0].strip()
        # Also strip trailing city name if present
        if city and city.lower() in core_service.lower():
            core_service = re.sub(re.escape(city), '', core_service, flags=re.IGNORECASE).strip()
            core_service = re.sub(r'\s+', ' ', core_service).strip()
        # Strip trailing prepositions left over from stripping
        core_service = re.sub(r'\s+(in|near|for|around|at|of)$', '', core_service, flags=re.IGNORECASE).strip()

    # Use industry OR fall back to core service for category-style tags
    category = industry if industry else core_service

    # 1. Primary keyword + city (e.g. "Sarasota SEO Company")
    if keyword:
        tags.append(title_case(ensure_city(keyword)))

    # 2. City + core service reversed (e.g. "Sarasota Search Engine Optimization")
    if city and core_service:
        tag = title_case(f"{city} {core_service}")
        if tag not in tags:
            tags.append(tag)

    # 3. Best [service] in [city] (e.g. "Best SEO Company in Sarasota")
    if core_service and city:
        tag = title_case(f"Best {core_service} in {city}")
        if tag not in tags:
            tags.append(tag)

    # 4. Professional [service] [city] (e.g. "Professional SEO Services Sarasota")
    if core_service and city:
        tag = title_case(f"Professional {core_service} Services {city}")
        if tag not in tags:
            tags.append(tag)
    elif core_service:
        tag = title_case(f"Professional {core_service}")
        if tag not in tags:
            tags.append(tag)

    # 5. [Service] services near me / [city] (e.g. "SEO Services in Sarasota")
    if core_service and city:
        tag = title_case(f"{core_service} Services in {city}")
        if tag not in tags:
            tags.append(tag)

    # 6. Industry + city if we have a real industry (e.g. "Digital Marketing Sarasota")
    if industry and city:
        tag = title_case(f"{industry} in {city}")
        if tag not in tags:
            tags.append(tag)

    # Additional fillers using keyword variations to guarantee 5+
    fillers = []
    if city and core_service:
        fillers += [
            title_case(f"Top {core_service} {city}"),
            title_case(f"{city} {core_service} Experts"),
            title_case(f"Affordable {core_service} in {city}"),
            title_case(f"{core_service} Company {city}"),
            title_case(f"Local {core_service} in {city}"),
            title_case(f"Expert {core_service} {city}"),
        ]
    elif core_service:
        fillers += [
            title_case(f"Top {core_service}"),
            title_case(f"Expert {core_service}"),
            title_case(f"Professional {core_service}"),
        ]
    if client_name and core_service:
        fillers.append(title_case(f"{client_name} {core_service}"))

    for filler in fillers:
        if filler and filler not in tags and len(tags) < 5:
            tags.append(filler)

    # Deduplicate while preserving order, ensure at least 5
    seen = set()
    unique = []
    for t in tags:
        t_clean = t.strip()
        if t_clean and t_clean not in seen:
            seen.add(t_clean)
            unique.append(t_clean)
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
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')

    return jsonify({
        'claude_configured': bool(anthropic_key),
        'claude_key_prefix': anthropic_key[:10] + '...' if anthropic_key else 'NOT SET',
        'can_generate': current_user.can_generate_content,
        'user_role': str(current_user.role)
    })


@content_bp.route('/test-ai', methods=['POST'])
@token_required
def test_ai_generation(current_user):
    """Quick test to verify Claude AI is working"""
    import os
    import time

    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not anthropic_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 500

    start_time = time.time()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key, max_retries=0)
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=20,
            messages=[{'role': 'user', 'content': 'Say "AI is working" in exactly 3 words'}]
        )

        elapsed = time.time() - start_time
        return jsonify({
            'success': True,
            'response': response.content[0].text,
            'elapsed_seconds': round(elapsed, 2),
            'model': 'claude-haiku-4-5-20251001'
        })

    except anthropic.AuthenticationError:
        return jsonify({'error': 'ANTHROPIC_API_KEY is invalid or expired'}), 500
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
            state = geo_parts[1].strip() if len(geo_parts) > 1 else ''
            
            # Build internal links list
            internal_links = []
            for page in service_pages[:6]:
                if isinstance(page, dict) and page.get('url') and page.get('title'):
                    url = page['url']
                    if not url.startswith('http'):
                        url = f"https://{client.website_url.rstrip('/')}/{url.lstrip('/')}" if client.website_url else url
                    internal_links.append({'url': url, 'title': page['title']})
            
            # Parse client service cities and areas for city detection
            client_service_cities = []
            client_service_areas = []
            if hasattr(client, 'service_cities') and client.service_cities:
                client_service_cities = [c.strip() for c in client.service_cities.split(',') if c.strip()]
            if hasattr(client, 'service_areas') and client.service_areas:
                client_service_areas = [c.strip() for c in client.service_areas.split(',') if c.strip()]

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
                target_words=max(word_count, 1800),  # Minimum 1800 for quality, same as sync endpoint
                faq_count=faq_count if include_faq else 0,
                internal_links=internal_links,
                service_cities=client_service_cities,
                service_areas=client_service_areas
            )

            result = blog_gen.generate(blog_request)
            
            logger.info(f"[TASK {task_id}] BlogAISingle returned. Word count: {result.get('word_count', 0)}")
            
            if result.get('error'):
                error_code = result.get('error_code', '')
                logger.error(f"[TASK {task_id}] AI error ({error_code}): {result['error']}")
                _set_task(task_id, {'status': 'error', 'error': result['error'], 'error_code': error_code})
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
            
            # Store fact-check report if available
            fact_check = result.get('fact_check')
            if fact_check and isinstance(fact_check, dict):
                blog_post.fact_check_report = json.dumps(fact_check)
                blog_post.fact_check_score = fact_check.get('accuracy_score')
            
            data_service.save_blog_post(blog_post)
            
            _set_task(task_id, {
                'status': 'complete',
                'blog_id': blog_post.id,
                'title': blog_post.title,
                'word_count': blog_post.word_count,
                'links_added': links_added,
                'seo_score': seo_score,
                'seo_recommendations': seo_score_result.get('recommendations', []),
                'fact_check_score': fact_check.get('accuracy_score') if fact_check else None,
                'fact_check_flagged': fact_check.get('total_flagged', 0) if fact_check else 0
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
        skip_fact_check = data.get('skip_fact_check', False)  # Skip fact-check for bulk generation

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
        state = geo_parts[1].strip() if len(geo_parts) > 1 else ''
        
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
        
        # Parse client service cities and areas for city detection
        _svc_cities = [c.strip() for c in (getattr(client, 'service_cities', '') or '').split(',') if c.strip()]
        _svc_areas = [c.strip() for c in (getattr(client, 'service_areas', '') or '').split(',') if c.strip()]

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
            custom_faqs=custom_faqs,
            service_cities=_svc_cities,
            service_areas=_svc_areas,
            verify_content=not skip_fact_check  # Skip fact-check in bulk to speed up
        )
        
        result = blog_gen.generate(blog_request)
        
        logger.info(f"[SYNC] BlogAISingle returned: {result.get('word_count', 0)} words")
        
        if result.get('error'):
            error_msg = result['error']
            error_code = result.get('error_code', '')
            logger.error(f"[SYNC] AI error ({error_code}): {error_msg}")

            # Return specific HTTP status for credit/auth errors
            if error_code == 'ANTHROPIC_CREDITS_EXHAUSTED':
                return jsonify({'error': error_msg, 'error_code': 'credits_exhausted'}), 402
            elif error_code == 'ANTHROPIC_AUTH_ERROR':
                return jsonify({'error': error_msg, 'error_code': 'auth_error'}), 503
            elif error_code == 'ANTHROPIC_RATE_LIMIT':
                return jsonify({'error': error_msg, 'error_code': 'rate_limit'}), 429
            elif error_code == 'ANTHROPIC_API_ERROR':
                return jsonify({'error': error_msg, 'error_code': 'api_error'}), 503
            return jsonify({'error': error_msg}), 500

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
        
        # Store fact-check report if available
        fact_check = result.get('fact_check')
        if fact_check and isinstance(fact_check, dict):
            blog_post.fact_check_report = json.dumps(fact_check)
            blog_post.fact_check_score = fact_check.get('accuracy_score')
        
        data_service.save_blog_post(blog_post)
        
        logger.info(f"[SYNC] Blog generation complete: {blog_post.id}, {blog_post.word_count} words")
        
        return jsonify({
            'success': True,
            'blog_id': blog_post.id,
            'title': blog_post.title,
            'word_count': blog_post.word_count,
            'seo_score': seo_score,
            'fact_check_score': fact_check.get('accuracy_score') if fact_check else None,
            'fact_check_flagged': fact_check.get('total_flagged', 0) if fact_check else 0
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"[SYNC] Unexpected error: {e}\n{error_trace}")
        print(f"[BLOG-ERROR] {e}\n{error_trace}", flush=True)
        return jsonify({'error': f'Server error: {str(e)}', 'trace': error_trace[:1000]}), 500


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
            max(data.get('word_count', 1500), 1500),  # Minimum 1500 words for quality
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
    state = geo_parts[1].strip() if len(geo_parts) > 1 else ''
    
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

    _svc_cities2 = [c.strip() for c in (getattr(client, 'service_cities', '') or '').split(',') if c.strip()]
    _svc_areas2 = [c.strip() for c in (getattr(client, 'service_areas', '') or '').split(',') if c.strip()]

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
        internal_links=blog_internal_links,
        service_cities=_svc_cities2,
        service_areas=_svc_areas2
    )
    
    result = blog_gen.generate(blog_request)
    
    if result.get('error'):
        error_code = result.get('error_code', '')
        status = 402 if error_code == 'ANTHROPIC_CREDITS_EXHAUSTED' else 429 if error_code == 'ANTHROPIC_RATE_LIMIT' else 503 if error_code == 'ANTHROPIC_API_ERROR' else 500
        return jsonify({'error': result['error'], 'error_code': error_code}), status

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
    state = geo_parts[1].strip() if len(geo_parts) > 1 else ''
    
    _bulk_svc_cities = [c.strip() for c in (getattr(client, 'service_cities', '') or '').split(',') if c.strip()]
    _bulk_svc_areas = [c.strip() for c in (getattr(client, 'service_areas', '') or '').split(',') if c.strip()]

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
                internal_links=blog_internal_links,
                service_cities=_bulk_svc_cities,
                service_areas=_bulk_svc_areas
            )
            
            logger.info(f"[BULK] BlogRequest created, calling generate...")
            result = blog_gen.generate(blog_request)
            logger.info(f"[BULK] Generate returned, checking result...")
            
            if result.get('error'):
                error_code = result.get('error_code', '')
                logger.error(f"[BULK] Generation returned error ({error_code}): {result['error']}")
                # If credits exhausted, stop entire bulk — no point continuing
                if error_code == 'ANTHROPIC_CREDITS_EXHAUSTED':
                    results.append({'keyword': keyword, 'success': False, 'error': result['error'], 'error_code': error_code})
                    break
                results.append({
                    'keyword': keyword,
                    'success': False,
                    'error': result['error'],
                    'error_code': error_code
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

            # Save fact-check data if available
            fact_check = result.get('fact_check')
            if fact_check and isinstance(fact_check, dict):
                blog_post.fact_check_report = json.dumps(fact_check)
                blog_post.fact_check_score = fact_check.get('accuracy_score')

            data_service.save_blog_post(blog_post)
            
            results.append({
                'keyword': keyword,
                'success': True,
                'content_id': blog_post.id,
                'title': blog_post.title,
                'word_count': blog_post.word_count,
                'links_added': links_added,
                'seo_score': seo_score,
                'fact_check_score': fact_check.get('accuracy_score') if fact_check else None,
                'fact_check_flagged': fact_check.get('total_flagged', 0) if fact_check else 0
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

    # Calculate SEO score if there's actual content
    if body and len(body) > 100:
        try:
            client = DBClient.query.get(client_id)
            location = client.geo if client else ''
            kw = blog_post.primary_keyword or ''
            seo_result = seo_scoring_engine.score_content(
                content={
                    'title': title or '',
                    'meta_title': blog_post.meta_title or title or '',
                    'meta_description': blog_post.meta_description or '',
                    'h1': title or '',
                    'body': body
                },
                target_keyword=kw,
                location=location
            )
            blog_post.seo_score = seo_result.get('total_score', 0)
        except Exception as e:
            logger.warning(f"SEO scoring failed for manual post: {e}")

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
    
    import json as _json_mod

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
        content.tags = _json_mod.dumps(data['tags']) if isinstance(data['tags'], list) else data['tags']
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
    
    # Handle faq_content if provided
    if 'faq_content' in data:
        val = data['faq_content']
        if isinstance(val, list):
            content.faq_content = _json_mod.dumps(val)
        elif isinstance(val, str):
            content.faq_content = val

    # Auto-extract FAQs from body if faq_content is still empty
    if 'body' in data and not content.faq_content:
        body_text = data['body'] or ''
        plain_text = re.sub(r'<[^>]+>', '\n', body_text)
        plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)
        extracted_faqs = _extract_faqs_from_text(plain_text)
        if extracted_faqs:
            content.faq_content = _json_mod.dumps(extracted_faqs)
            logger.info(f"Auto-extracted {len(extracted_faqs)} FAQs from body for content {content_id}")

    # Enhance body HTML if it's missing heading tags or links
    if content.body and len(content.body) > 200:
        body_html = content.body
        has_headings = bool(re.search(r'<h[1-6][^>]*>', body_html, re.IGNORECASE))
        has_links = bool(re.search(r'<a\s[^>]*href=', body_html, re.IGNORECASE))
        has_html = bool(re.search(r'<(?:p|div|span|strong|em)\b', body_html, re.IGNORECASE))

        if not has_headings:
            if has_html:
                # Body has HTML (from WYSIWYG editor) but no headings
                # Promote short standalone lines to headings
                body_html = _promote_headings_in_html(body_html)
            elif re.search(r'^#{1,6}\s+', body_html, re.MULTILINE):
                body_html = _markdown_to_html(body_html)
            else:
                body_html = _plaintext_to_html(body_html)
            content.body = body_html
            logger.info(f"Enhanced body with HTML headings for content {content_id}")

        if not has_links:
            # Try to inject internal links from stored metadata
            stored_links = []
            if content.internal_links:
                try:
                    stored_links = _json_mod.loads(content.internal_links) if isinstance(content.internal_links, str) else content.internal_links
                except (ValueError, TypeError):
                    pass
            if stored_links:
                content.body = _inject_internal_links(content.body, stored_links)
                logger.info(f"Injected {len(stored_links)} internal links into body for content {content_id}")

    # Recalculate SEO score if body or title changed
    if 'body' in data or 'title' in data or 'meta_title' in data or 'meta_description' in data:
        try:
            client = DBClient.query.get(content.client_id) if hasattr(content, 'client_id') else None
            location = client.geo if client else ''
            kw = content.primary_keyword or ''
            seo_result = seo_scoring_engine.score_content(
                content={
                    'title': content.title or '',
                    'meta_title': content.meta_title or '',
                    'meta_description': content.meta_description or '',
                    'h1': content.title or '',
                    'body': content.body or ''
                },
                target_keyword=kw,
                location=location
            )
            content.seo_score = seo_result.get('total_score', 0)
            # Log full breakdown for debugging
            factors = seo_result.get('factors', {})
            breakdown_log = ' | '.join([f"{k}: {v.get('score',0)}/{v.get('max',0)}" for k, v in factors.items()])
            logger.info(f"SEO score for {content_id}: {content.seo_score}/100 | {breakdown_log}")
        except Exception as e:
            logger.warning(f"SEO score recalculation failed for {content_id}: {e}")
            import traceback
            traceback.print_exc()

    # Store SEO breakdown for frontend display
    _seo_breakdown = {}
    try:
        _seo_breakdown = seo_result.get('factors', {})
    except NameError:
        pass

    data_service.save_blog_post(content)

    # Send notification if status changed to approved
    new_status = data.get('status', '')
    if new_status == 'approved' and old_status != 'approved':
        try:
            from app.services.notification_service import get_notification_service
            from app.models.db_models import DBUser

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
    
    resp = {
        'message': 'Content updated',
        'content': content.to_dict(),
        'seo_score': content.seo_score
    }
    if _seo_breakdown:
        resp['seo_breakdown'] = {k: {'score': v.get('score', 0), 'max': v.get('max', 0), 'message': v.get('message', '')} for k, v in _seo_breakdown.items()}
    return jsonify(resp)


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
        'slug', 'excerpt', 'tags', 'secondary_keywords',
        'internal_links', 'target_city'
    ]

    updated_fields = []
    for field in updatable_fields:
        if field in data:
            val = data[field]
            # JSON-encode list/dict fields
            if field in ('tags', 'secondary_keywords', 'internal_links') and isinstance(val, (list, dict)):
                val = json.dumps(val)
            setattr(blog, field, val)
            updated_fields.append(field)

    # Handle faq_content — accept direct JSON or extract from body
    if 'faq_content' in data:
        val = data['faq_content']
        if isinstance(val, list):
            blog.faq_content = json.dumps(val)
        elif isinstance(val, str):
            blog.faq_content = val
        updated_fields.append('faq_content')

    # Recalculate word count if body changed
    if 'body' in data:
        blog.word_count = len((data['body'] or '').split())

    # Auto-extract FAQs from body if faq_content is still empty
    if 'body' in data and not blog.faq_content:
        body_text = data['body'] or ''
        # Strip HTML tags to get plain text for FAQ extraction
        plain_text = re.sub(r'<[^>]+>', '\n', body_text)
        plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)
        extracted_faqs = _extract_faqs_from_text(plain_text)
        if extracted_faqs:
            blog.faq_content = json.dumps(extracted_faqs)
            if 'faq_content' not in updated_fields:
                updated_fields.append('faq_content')
            logger.info(f"Auto-extracted {len(extracted_faqs)} FAQs from body for blog {blog_id}")

    # Recalculate SEO score if content fields changed
    content_changed = any(f in updated_fields for f in ['body', 'title', 'meta_title', 'meta_description', 'primary_keyword'])
    if content_changed and blog.body and len(blog.body) > 100:
        try:
            client = DBClient.query.get(blog.client_id)
            location = client.geo if client else ''
            kw = blog.primary_keyword or ''
            seo_result = seo_scoring_engine.score_content(
                content={
                    'title': blog.title or '',
                    'meta_title': blog.meta_title or '',
                    'meta_description': blog.meta_description or '',
                    'h1': blog.title or '',
                    'body': blog.body or ''
                },
                target_keyword=kw,
                location=location
            )
            blog.seo_score = seo_result.get('total_score', 0)
            logger.info(f"Recalculated SEO score for blog {blog_id}: {blog.seo_score}")
        except Exception as e:
            logger.warning(f"SEO score recalculation failed for blog {blog_id}: {e}")

    if updated_fields:
        db.session.commit()

    return jsonify({
        'success': True,
        'id': blog.id,
        'updated_fields': updated_fields,
        'seo_score': blog.seo_score,
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


@content_bp.route('/blog/<blog_id>/seo-debug', methods=['GET'])
@token_required
def seo_debug(current_user, blog_id):
    """
    Debug SEO score — shows full breakdown and body structure analysis.
    GET /api/content/blog/{blog_id}/seo-debug
    """
    import json as _jmod
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403

    body = blog.body or ''
    client = DBClient.query.get(blog.client_id)
    location = client.geo if client else ''
    kw = blog.primary_keyword or ''

    # Body structure analysis
    h1_tags = re.findall(r'<h1[^>]*>(.*?)</h1>', body, re.IGNORECASE | re.DOTALL)
    h2_tags = re.findall(r'<h2[^>]*>(.*?)</h2>', body, re.IGNORECASE | re.DOTALL)
    h3_tags = re.findall(r'<h3[^>]*>(.*?)</h3>', body, re.IGNORECASE | re.DOTALL)
    a_tags = re.findall(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', body, re.IGNORECASE | re.DOTALL)
    has_p_tags = bool(re.search(r'<p[^>]*>', body, re.IGNORECASE))
    has_strong = bool(re.search(r'<strong[^>]*>', body, re.IGNORECASE))

    # Run scoring
    seo_result = seo_scoring_engine.score_content(
        content={
            'title': blog.title or '',
            'meta_title': blog.meta_title or '',
            'meta_description': blog.meta_description or '',
            'h1': blog.title or '',
            'body': body
        },
        target_keyword=kw,
        location=location
    )

    # Stored internal links
    stored_links = []
    if blog.internal_links:
        try:
            stored_links = _jmod.loads(blog.internal_links) if isinstance(blog.internal_links, str) else blog.internal_links
        except (ValueError, TypeError):
            pass

    return jsonify({
        'blog_id': blog_id,
        'keyword': kw,
        'seo_score': seo_result.get('total_score', 0),
        'body_analysis': {
            'length': len(body),
            'word_count': len(body.split()),
            'has_p_tags': has_p_tags,
            'has_strong_tags': has_strong,
            'h1_count': len(h1_tags),
            'h1_texts': [re.sub(r'<[^>]+>', '', h).strip() for h in h1_tags],
            'h2_count': len(h2_tags),
            'h2_texts': [re.sub(r'<[^>]+>', '', h).strip() for h in h2_tags],
            'h3_count': len(h3_tags),
            'h3_texts': [re.sub(r'<[^>]+>', '', h).strip() for h in h3_tags],
            'a_tag_count': len(a_tags),
            'a_tags': [{'href': href, 'text': re.sub(r'<[^>]+>', '', txt).strip()} for href, txt in a_tags[:20]],
            'stored_links_count': len(stored_links),
            'body_first_500': body[:500]
        },
        'factors': {k: {'score': v.get('score', 0), 'max': v.get('max', 0), 'message': v.get('message', '')} for k, v in seo_result.get('factors', {}).items()},
        'recommendations': seo_result.get('recommendations', [])
    })


@content_bp.route('/blog/<blog_id>/fact-check', methods=['POST'])
@token_required
def run_fact_check(current_user, blog_id):
    """
    Run fact-check verification on an existing blog post.

    POST /api/content/blog/{blog_id}/fact-check
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403

    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404

    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403

    try:
        from app.services.blog_ai_single import get_blog_ai_single, BlogRequest
        from app.database import db

        # Get client info for the BlogRequest
        client = data_service.get_client(blog.client_id)
        if not client:
            return jsonify({'error': 'Client not found'}), 404

        # Build a minimal BlogRequest with what we know
        # DBClient has 'geo' (e.g. "Venice, Florida") — split into city/state
        geo = client.geo or ''
        geo_parts = [p.strip() for p in geo.split(',', 1)] if geo else ['', '']
        fc_city = geo_parts[0] if len(geo_parts) > 0 else ''
        fc_state = geo_parts[1] if len(geo_parts) > 1 else ''

        blog_request = BlogRequest(
            keyword=blog.primary_keyword or blog.title or '',
            city=fc_city,
            state=fc_state,
            company_name=client.business_name or '',
            industry=client.industry or '',
        )

        # Build result dict with blog content for verification
        result = {
            'body': blog.body or '',
            'faq_items': []
        }

        # Try to extract FAQ items from the stored blog data
        blog_dict = blog.to_dict()
        if blog_dict.get('faq_items'):
            result['faq_items'] = blog_dict['faq_items']

        blog_ai = get_blog_ai_single()
        fact_check = blog_ai._verify_content(result, blog_request)

        if fact_check and isinstance(fact_check, dict):
            blog.fact_check_report = json.dumps(fact_check)
            blog.fact_check_score = fact_check.get('accuracy_score')
            db.session.commit()

            return jsonify({
                'success': True,
                'fact_check_report': fact_check,
                'fact_check_score': fact_check.get('accuracy_score'),
                'fact_check_status': fact_check.get('status', 'unknown')
            })
        else:
            return jsonify({'error': 'Fact-check returned no data'}), 500

    except Exception as e:
        import traceback
        logger.error(f"Fact-check error for blog {blog_id}: {e}\n{traceback.format_exc()}")
        return jsonify({'error': f'Fact-check failed: {str(e)}'}), 500


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
        
        # Build tags — EVERY tag must include city/location name for local SEO
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

        def ensure_city_in_tag(tag_text):
            """Ensure every tag includes the city name"""
            if not city:
                return tag_text
            if city.lower() in tag_text.lower():
                return tag_text
            return f"{tag_text} {city}"

        # Extract core service from keyword
        service = ''
        if content.primary_keyword:
            service = content.primary_keyword.lower()
            for loc_word in [' in ', ' near ', ' for ', city.lower() if city else '']:
                if loc_word:
                    service = service.split(loc_word)[0].strip()

        # 1. Primary keyword + city
        if content.primary_keyword:
            tags.append(title_case(ensure_city_in_tag(content.primary_keyword)))

        # 2. City + service (reversed)
        if city and service:
            tags.append(title_case(f"{city} {service}"))

        # 3. Best [service] in [city]
        if service and city:
            tags.append(title_case(f"Best {service} in {city}"))

        # 4. Add secondary keywords — each with city
        if content.secondary_keywords:
            try:
                keywords = json.loads(content.secondary_keywords) if isinstance(content.secondary_keywords, str) else content.secondary_keywords
                if keywords:
                    for kw in keywords[:5]:
                        if kw:
                            kw_tag = title_case(ensure_city_in_tag(kw))
                            if kw_tag not in tags and len(tags) < 10:
                                tags.append(kw_tag)
            except (json.JSONDecodeError, TypeError):
                pass

        # 5. Industry-based tags — ALL include city
        industry = client.industry.lower() if client.industry else ''
        if city:
            if 'dent' in industry:
                extra_tags = [f'Dentist {city}', f'{city} Dental', f'Dental Care {city}', f'Oral Health {city}']
            elif 'hvac' in industry or 'air' in industry:
                extra_tags = [f'HVAC {city}', f'{city} AC Repair', f'Air Conditioning {city}', f'Heating {city}']
            elif 'plumb' in industry:
                extra_tags = [f'Plumber {city}', f'{city} Plumbing', f'Plumbing Services {city}']
            elif 'roof' in industry:
                extra_tags = [f'Roofer {city}', f'{city} Roofing', f'Roof Repair {city}']
            elif 'law' in industry or 'legal' in industry:
                extra_tags = [f'Lawyer {city}', f'{city} Attorney', f'Legal Services {city}']
            else:
                extra_tags = [f'{city} Services', f'Local Business {city}', f'Professional Services {city}']
        else:
            extra_tags = []

        for tag in extra_tags:
            if tag and tag not in tags and len(tags) < 10:
                tags.append(tag)

        # Ensure minimum 5 tags — all with city
        if len(tags) < 5 and city:
            filler_tags = [f'Local {city}', f'{city} Expert Services', f'Professional {industry} {city}' if industry else f'Professional Services {city}']
            for tag in filler_tags:
                tag = title_case(tag)
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

        result = ai_service.generate_raw(refine_prompt, max_tokens=8000)
        
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


# ==========================================
# CONTENT CALENDAR — Cross-Client Dashboard
# ==========================================

@content_bp.route('/calendar', methods=['GET'])
@token_required
def get_content_calendar(current_user):
    """
    Get content calendar data across all clients (admin) or a single client.
    
    GET /api/content/calendar?month=2026-03&client_id=xxx
    
    Query params:
        month: YYYY-MM (default: current month)
        client_id: optional, filter to one client
        status: optional, filter by status (draft/review/approved/published)
    
    Returns calendar data with content items organized by date.
    """
    from app.models.db_models import DBClient, DBBlogPost, DBSocialPost
    from app.database import db
    from sqlalchemy import and_, or_
    
    # Parse month parameter
    month_str = request.args.get('month', '')
    show_all = month_str == 'all'
    
    if not show_all and month_str:
        try:
            year, month = int(month_str.split('-')[0]), int(month_str.split('-')[1])
        except (ValueError, IndexError):
            year, month = datetime.utcnow().year, datetime.utcnow().month
    else:
        year, month = datetime.utcnow().year, datetime.utcnow().month
    
    # Date range for the month (include a week before/after for calendar view)
    from datetime import timedelta
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    
    # Extend range for calendar padding (or show everything for 'all')
    if show_all:
        view_start = datetime(2020, 1, 1)
        view_end = datetime(2030, 1, 1)
    else:
        view_start = month_start - timedelta(days=7)
        view_end = month_end + timedelta(days=7)
    
    client_id = request.args.get('client_id')
    status_filter = request.args.get('status')
    
    # Determine which clients the user can see
    if client_id:
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
        client_ids = [client_id]
    elif current_user.role in ('admin', 'super_admin'):
        # Admin sees all clients
        clients = DBClient.query.all()
        client_ids = [c.id for c in clients]
    else:
        # Regular user sees their assigned clients
        client_ids = [c.id for c in current_user.get_accessible_clients()]
    
    # Build client name lookup
    clients_map = {}
    for c in DBClient.query.filter(DBClient.id.in_(client_ids)).all():
        clients_map[c.id] = {
            'name': c.business_name,
            'industry': c.industry
        }
    
    # Query blog posts
    blog_query = DBBlogPost.query.filter(DBBlogPost.client_id.in_(client_ids))
    
    if status_filter:
        blog_query = blog_query.filter(DBBlogPost.status == status_filter)
    
    # Get blogs that have scheduled_for, published_at, or created_at in range
    blogs = blog_query.filter(
        or_(
            and_(DBBlogPost.scheduled_for >= view_start, DBBlogPost.scheduled_for < view_end),
            and_(DBBlogPost.published_at >= view_start, DBBlogPost.published_at < view_end),
            and_(DBBlogPost.created_at >= view_start, DBBlogPost.created_at < view_end),
        )
    ).order_by(DBBlogPost.created_at.desc()).all()
    
    # Query social posts
    social_query = DBSocialPost.query.filter(DBSocialPost.client_id.in_(client_ids))
    
    if status_filter:
        social_query = social_query.filter(DBSocialPost.status == status_filter)
    
    socials = social_query.filter(
        or_(
            and_(DBSocialPost.scheduled_for >= view_start, DBSocialPost.scheduled_for < view_end),
            and_(DBSocialPost.published_at >= view_start, DBSocialPost.published_at < view_end),
            and_(DBSocialPost.created_at >= view_start, DBSocialPost.created_at < view_end),
        )
    ).order_by(DBSocialPost.created_at.desc()).all()
    
    # Build calendar items
    items = []
    
    for blog in blogs:
        # Determine the display date (priority: scheduled > published > created)
        display_date = (
            blog.scheduled_for or blog.published_at or blog.created_at
        )
        
        items.append({
            'id': blog.id,
            'type': 'blog',
            'title': blog.title,
            'status': blog.status,
            'client_id': blog.client_id,
            'client_name': clients_map.get(blog.client_id, {}).get('name', 'Unknown'),
            'date': display_date.strftime('%Y-%m-%d') if display_date else None,
            'datetime': display_date.isoformat() if display_date else None,
            'scheduled_for': blog.scheduled_for.isoformat() if blog.scheduled_for else None,
            'published_at': blog.published_at.isoformat() if blog.published_at else None,
            'created_at': blog.created_at.isoformat() if blog.created_at else None,
            'primary_keyword': blog.primary_keyword,
            'seo_score': blog.seo_score,
            'word_count': blog.word_count,
            'published_url': blog.published_url,
        })
    
    for social in socials:
        display_date = (
            social.scheduled_for or social.published_at or social.created_at
        )
        
        items.append({
            'id': social.id,
            'type': 'social',
            'platform': social.platform,
            'title': (social.content or '')[:80],
            'status': social.status,
            'client_id': social.client_id,
            'client_name': clients_map.get(social.client_id, {}).get('name', 'Unknown'),
            'date': display_date.strftime('%Y-%m-%d') if display_date else None,
            'datetime': display_date.isoformat() if display_date else None,
            'scheduled_for': social.scheduled_for.isoformat() if social.scheduled_for else None,
            'published_at': social.published_at.isoformat() if social.published_at else None,
            'created_at': social.created_at.isoformat() if social.created_at else None,
        })
    
    # Summary stats
    status_counts = {
        'draft': sum(1 for i in items if i['status'] == 'draft'),
        'review': sum(1 for i in items if i['status'] == 'review'),
        'approved': sum(1 for i in items if i['status'] == 'approved'),
        'published': sum(1 for i in items if i['status'] == 'published'),
        'scheduled': sum(1 for i in items if i.get('scheduled_for')),
    }
    
    # Group by date for calendar view
    by_date = {}
    for item in items:
        d = item.get('date')
        if d:
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(item)
    
    return jsonify({
        'month': f'{year}-{month:02d}',
        'total_items': len(items),
        'status_counts': status_counts,
        'clients_count': len(set(i['client_id'] for i in items)),
        'items': items,
        'by_date': by_date
    })


@content_bp.route('/calendar/summary', methods=['GET'])
@token_required
def get_content_calendar_summary(current_user):
    """
    Quick summary of content status across all clients (for admin dashboard cards).
    
    GET /api/content/calendar/summary
    """
    from app.models.db_models import DBClient, DBBlogPost, DBSocialPost
    from app.database import db
    from sqlalchemy import func
    from datetime import timedelta
    
    # Admin/manager only
    if current_user.role not in ('admin', 'super_admin', 'manager'):
        return jsonify({'error': 'Admin access required'}), 403
    
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    
    # Blog stats by status
    blog_stats = db.session.query(
        DBBlogPost.status,
        func.count(DBBlogPost.id)
    ).group_by(DBBlogPost.status).all()
    
    blog_by_status = {s: c for s, c in blog_stats}
    
    # Blog stats by client (for the per-client breakdown)
    client_blog_stats = db.session.query(
        DBBlogPost.client_id,
        DBBlogPost.status,
        func.count(DBBlogPost.id)
    ).group_by(DBBlogPost.client_id, DBBlogPost.status).all()
    
    # Build per-client summary
    client_summaries = {}
    for client_id, status, count in client_blog_stats:
        if client_id not in client_summaries:
            client_summaries[client_id] = {'draft': 0, 'review': 0, 'approved': 0, 'published': 0, 'total': 0}
        client_summaries[client_id][status] = count
        client_summaries[client_id]['total'] += count
    
    # Add client names
    client_names = {c.id: c.business_name for c in DBClient.query.all()}
    
    per_client = []
    for cid, stats in client_summaries.items():
        per_client.append({
            'client_id': cid,
            'client_name': client_names.get(cid, 'Unknown'),
            **stats
        })
    
    # Sort by total descending
    per_client.sort(key=lambda x: x['total'], reverse=True)
    
    # Recent activity (last 30 days)
    recent_published = DBBlogPost.query.filter(
        DBBlogPost.published_at >= thirty_days_ago
    ).count()
    
    recent_created = DBBlogPost.query.filter(
        DBBlogPost.created_at >= thirty_days_ago
    ).count()
    
    # Upcoming scheduled
    upcoming = DBBlogPost.query.filter(
        DBBlogPost.scheduled_for >= now,
        DBBlogPost.status != 'published'
    ).order_by(DBBlogPost.scheduled_for.asc()).limit(10).all()
    
    # Drafts needing attention (oldest first)
    stale_drafts = DBBlogPost.query.filter(
        DBBlogPost.status == 'draft',
        DBBlogPost.created_at < thirty_days_ago
    ).order_by(DBBlogPost.created_at.asc()).limit(10).all()
    
    return jsonify({
        'total_blogs': sum(blog_by_status.values()),
        'blog_by_status': blog_by_status,
        'per_client': per_client,
        'recent_30d': {
            'published': recent_published,
            'created': recent_created,
        },
        'upcoming_scheduled': [
            {
                'id': b.id,
                'title': b.title,
                'client_id': b.client_id,
                'client_name': client_names.get(b.client_id, 'Unknown'),
                'scheduled_for': b.scheduled_for.isoformat(),
                'status': b.status
            }
            for b in upcoming
        ],
        'stale_drafts': [
            {
                'id': b.id,
                'title': b.title,
                'client_id': b.client_id,
                'client_name': client_names.get(b.client_id, 'Unknown'),
                'created_at': b.created_at.isoformat(),
                'days_old': (now - b.created_at).days
            }
            for b in stale_drafts
        ]
    })


# ==========================================
# Smart Paste — parse externally-created blog content packages
# ==========================================

@content_bp.route('/smart-paste', methods=['POST'])
@token_required
def smart_paste(current_user):
    """
    Parse a pasted blog content package and create/update a blog post.
    Accepts free-form text with sections like META TITLE, SLUG, TAGS, INTERNAL LINKS, etc.
    Returns parsed fields so the frontend can review before saving.

    POST /api/content/smart-paste
    Body: { client_id, paste_text, blog_id? (optional — update existing) }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    paste_text = data.get('paste_text', '').strip()
    blog_id = data.get('blog_id')  # optional: update existing post

    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    if not paste_text:
        return jsonify({'error': 'paste_text is required'}), 400
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403

    # ---- Parse the pasted content package ----
    # If preview_only=true, just return parsed fields without creating/updating
    preview_only = data.get('preview_only', False)

    # Log the raw paste for debugging (v3 parser — subtract metadata approach)
    line_count = paste_text.count('\n')
    logger.info(f"Smart-paste v3 received: {len(paste_text)} chars, {line_count} newlines")
    logger.info(f"Smart-paste first 300 chars: {repr(paste_text[:300])}")

    parsed = _parse_content_package(paste_text)
    logger.info(f"Smart-paste parsed fields: {list(parsed.keys())} | body_len={len(parsed.get('body',''))} | links={len(parsed.get('internal_links',[]))} | paste_len={len(paste_text)}")

    if preview_only:
        # Return debug info — what was parsed and first 200 chars of body
        debug_info = {}
        for k, v in parsed.items():
            if k == 'body':
                debug_info[k] = f"({len(v)} chars) {v[:300]}..."
            elif isinstance(v, list):
                debug_info[k] = v
            else:
                debug_info[k] = v
        return jsonify({
            'parser_version': 'v3-subtract-metadata',
            'parsed_fields': list(parsed.keys()),
            'has_body': 'body' in parsed,
            'body_length': len(parsed.get('body', '')),
            'body_warning': parsed.get('body_warning'),
            'debug': debug_info,
            'paste_length': len(paste_text),
            'paste_newlines': paste_text.count('\n'),
            'paste_first_500': paste_text[:500]
        })

    if blog_id:
        # Update existing blog post with parsed fields
        blog = DBBlogPost.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog post not found'}), 404
        if blog.client_id != client_id:
            return jsonify({'error': 'Blog does not belong to this client'}), 403

        if parsed.get('meta_title'):
            blog.meta_title = parsed['meta_title'][:500]
        if parsed.get('meta_description'):
            blog.meta_description = parsed['meta_description'][:500]
        if parsed.get('slug'):
            blog.slug = parsed['slug']
        if parsed.get('primary_keyword'):
            blog.primary_keyword = parsed['primary_keyword']
        if parsed.get('secondary_keywords'):
            blog.secondary_keywords = json.dumps(parsed['secondary_keywords'])
        if parsed.get('tags'):
            blog.tags = json.dumps(parsed['tags'])
        if parsed.get('internal_links'):
            blog.internal_links = json.dumps(parsed['internal_links'])
        if parsed.get('schema_markup'):
            blog.schema_markup = json.dumps(parsed['schema_markup'])
        if parsed.get('title'):
            blog.title = parsed['title'][:500]
        if parsed.get('body'):
            blog.body = parsed['body']
            blog.word_count = len(parsed['body'].split())
        if parsed.get('excerpt'):
            blog.excerpt = parsed['excerpt']
        if parsed.get('target_city'):
            blog.target_city = parsed['target_city']
        if parsed.get('faq_items'):
            blog.faq_content = json.dumps(parsed['faq_items'])

        blog.updated_at = datetime.utcnow()
        from app.database import db as _db
        _db.session.commit()
        logger.info(f"Smart-paste updated blog {blog_id} with fields: {list(parsed.keys())}")

        return jsonify({
            'message': 'Blog post updated from pasted content',
            'parsed_fields': list(parsed.keys()),
            'blog': blog.to_dict()
        })
    else:
        # Create new blog post from parsed content
        title = parsed.get('title') or parsed.get('meta_title') or 'Untitled (from paste)'
        blog = DBBlogPost(client_id=client_id, title=title[:500])
        blog.body = parsed.get('body', '')
        blog.word_count = len(blog.body.split()) if blog.body else 0
        blog.meta_title = (parsed.get('meta_title') or title)[:500]
        blog.meta_description = (parsed.get('meta_description') or '')[:500]
        blog.slug = parsed.get('slug') or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        blog.primary_keyword = parsed.get('primary_keyword', '')
        blog.secondary_keywords = json.dumps(parsed.get('secondary_keywords', []))
        blog.tags = json.dumps(parsed.get('tags', []))
        blog.internal_links = json.dumps(parsed.get('internal_links', []))
        blog.schema_markup = json.dumps(parsed.get('schema_markup')) if parsed.get('schema_markup') else None

        # FAQ content — store as JSON array of {question, answer} objects
        faq_items = parsed.get('faq_items', [])
        if faq_items:
            blog.faq_content = json.dumps(faq_items)
            # Also auto-generate FAQPage schema if not already provided
            if not parsed.get('schema_markup'):
                faq_schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq.get('question', ''),
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": faq.get('answer', '')
                            }
                        }
                        for faq in faq_items
                        if faq.get('question') and faq.get('answer')
                    ]
                }
                blog.schema_markup = json.dumps(faq_schema)

        if parsed.get('target_city'):
            blog.target_city = parsed['target_city']
        blog.excerpt = parsed.get('excerpt', '')
        if not blog.excerpt and blog.body:
            plain = re.sub(r'<[^>]+>', '', blog.body)
            blog.excerpt = plain[:160].strip()
        blog.status = 'draft'

        # Calculate SEO score
        if blog.body and len(blog.body) > 100:
            try:
                client = DBClient.query.get(client_id)
                location = client.geo if client else ''
                seo_result = seo_scoring_engine.score_content(
                    content={
                        'title': blog.title or '',
                        'meta_title': blog.meta_title or '',
                        'meta_description': blog.meta_description or '',
                        'h1': blog.title or '',
                        'body': blog.body
                    },
                    target_keyword=blog.primary_keyword or '',
                    location=location
                )
                blog.seo_score = seo_result.get('total_score', 0)
            except Exception as e:
                logger.warning(f"SEO scoring failed for smart-paste post: {e}")

        data_service.save_blog_post(blog)
        logger.info(f"Smart-paste created blog {blog.id} for client {client_id} | body_len_on_blog={len(blog.body or '')} | word_count={blog.word_count}")

        blog_dict = blog.to_dict()
        logger.info(f"Smart-paste blog.to_dict body_len={len(blog_dict.get('body',''))} | word_count={blog_dict.get('word_count',0)}")

        return jsonify({
            'message': 'Blog post created from pasted content',
            'parsed_fields': list(parsed.keys()),
            'parsed_body_len': len(parsed.get('body', '')),
            'saved_body_len': len(blog.body or ''),
            'body_warning': parsed.get('body_warning'),
            'blog': blog_dict
        }), 201


def _parse_content_package(text: str) -> dict:
    """
    Parse a free-form content package into structured fields.

    STRATEGY: Extract labeled metadata fields first, then treat the remaining
    large block of text as the blog body. This works regardless of format.
    """
    result = {}
    text = text.strip()
    lines = text.split('\n')

    # Track which line ranges are "consumed" by metadata extraction
    consumed_lines = set()

    # ---- STEP 1: Single-line labeled fields ----
    label_patterns = {
        'meta_title': r'(?:meta\s*title|seo\s*title|page\s*title|title\s*tag)\s*[:\-–—=]\s*(.+)',
        'meta_description': r'(?:meta\s*desc(?:ription)?|seo\s*desc(?:ription)?)\s*[:\-–—=]\s*(.+)',
        'slug': r'(?:slug|url\s*slug|permalink)\s*[:\-–—=]\s*[/]?(.+)',
        'primary_keyword': r'(?:primary\s*keyword|target\s*keyword|focus\s*keyword|main\s*keyword)\s*[:\-–—=]\s*(.+)',
        'title': r'(?:blog\s*title|post\s*title|h1\b|headline|article\s*title)\s*[:\-–—=]\s*(.+)',
        'excerpt': r'(?:excerpt)\s*[:\-–—=]\s*(.+)',
    }

    for field, pattern in label_patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().strip('"\'')
            if val:
                result[field] = val
                # Mark this line as consumed
                for i, line in enumerate(lines):
                    if m.group(0).strip() in line:
                        consumed_lines.add(i)
                        break

    # ---- STEP 2: Secondary keywords ----
    sec_kw_match = re.search(
        r'(?:secondary\s*keywords?|related\s*keywords?|lsi\s*keywords?|supporting\s*keywords?|additional\s*keywords?)\s*[:\-–—=]\s*(.+)',
        text, re.IGNORECASE
    )
    if sec_kw_match:
        result['secondary_keywords'] = [k.strip().strip('"\'') for k in re.split(r'[,;|]', sec_kw_match.group(1).strip()) if k.strip()]
        for i, line in enumerate(lines):
            if sec_kw_match.group(0).strip() in line:
                consumed_lines.add(i)
                break

    # ---- STEP 3: Tags ----
    tags_match = re.search(
        r'(?:tags?|categories|wordpress\s*tags?|post\s*tags?|suggested\s*tags?)\s*[:\-–—=]\s*(.+)',
        text, re.IGNORECASE
    )
    if tags_match:
        result['tags'] = [t.strip().strip('"\'#') for t in re.split(r'[,;|]', tags_match.group(1).strip()) if t.strip()]
        for i, line in enumerate(lines):
            if tags_match.group(0).strip() in line:
                consumed_lines.add(i)
                break

    # ---- STEP 4: Internal links ----
    internal_links = []

    # Markdown links: [anchor](URL)
    for m in re.finditer(r'\[([^\]]+)\]\((https?://\S+?)\)', text):
        anchor, url = m.group(1).strip(), m.group(2).strip()
        if not any(l['url'] == url for l in internal_links):
            internal_links.append({'text': anchor, 'url': url})

    # Arrow format: anchor → URL  (with or without https://)
    for m in re.finditer(r'["\']?([^"\'→\n]{3,80}?)["\']?\s*[→⟶➜>]+\s*((?:https?://)?\S+)', text):
        anchor, url = m.group(1).strip(), m.group(2).strip().rstrip(')')
        if anchor and not re.match(r'^https?://', anchor) and not any(l['url'] == url for l in internal_links):
            # Ensure URL has protocol
            if url and not url.startswith('http'):
                url = 'https://' + url
            internal_links.append({'text': anchor, 'url': url})

    # >> format: "anchor text" >> domain.com/path  (common in content packages)
    for m in re.finditer(r'["\*]([^"\*\n]{3,80}?)["\*]\s*>>+\s*((?:https?://)?[a-zA-Z0-9][\w.-]+\.[a-z]{2,}(?:/\S*)?)', text):
        anchor, url = m.group(1).strip(), m.group(2).strip().rstrip(')')
        if anchor and not any(l['url'] == url for l in internal_links):
            if not url.startswith('http'):
                url = 'https://' + url
            internal_links.append({'text': anchor, 'url': url})

    # Bullet/asterisk link lists: * "anchor text" >> URL  or  * anchor >> URL
    for m in re.finditer(r'^\s*[•\-\*·]\s*["\']?([^"\'→>\n]{3,80}?)["\']?\s*>>+\s*((?:https?://)?[a-zA-Z0-9][\w.-]+\.[a-z]{2,}(?:/\S*)?)', text, re.MULTILINE):
        anchor, url = m.group(1).strip(), m.group(2).strip().rstrip(')')
        if anchor and not any(l['url'] == url for l in internal_links):
            if not url.startswith('http'):
                url = 'https://' + url
            internal_links.append({'text': anchor, 'url': url})

    # URL (anchor) format
    for m in re.finditer(r'(https?://\S+)\s*[\(–—\-:]\s*([^)\n]{3,80})', text):
        url, anchor = m.group(1).strip().rstrip(')'), m.group(2).strip().rstrip(')')
        if not any(l['url'] == url for l in internal_links):
            internal_links.append({'text': anchor, 'url': url})

    # Bare domain.com/path links (no anchor) — common in content packages
    # Match lines like: akelectricalfl.com/surge-protection/
    for m in re.finditer(r'^\s*[•\-\*·]\s*((?:https?://)?([a-zA-Z0-9][\w.-]+\.[a-z]{2,}/\S+))\s*$', text, re.MULTILINE):
        url = m.group(1).strip()
        domain_path = m.group(2).strip()
        if not url.startswith('http'):
            url = 'https://' + url
        if not any(l['url'] == url for l in internal_links):
            # Generate anchor from URL path
            path = url.rstrip('/').split('/')[-1]
            anchor = path.replace('-', ' ').replace('_', ' ').title()
            internal_links.append({'text': anchor, 'url': url})

    if internal_links:
        result['internal_links'] = internal_links

    # ---- STEP 5: Target city ----
    city_match = re.search(
        r'(?:target\s*city|service\s*area)\s*[:\-–—=]\s*(.+)',
        text, re.IGNORECASE
    )
    if city_match:
        result['target_city'] = city_match.group(1).strip().strip('"\'')
        for i, line in enumerate(lines):
            if city_match.group(0).strip() in line:
                consumed_lines.add(i)
                break

    # ---- STEP 6: Schema markup ----
    schema_match = re.search(r'(?:schema|json-?ld|structured\s*data)\s*[:\-–—=]?\s*\n?\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z)', text, re.IGNORECASE)
    if schema_match:
        try:
            result['schema_markup'] = json.loads(schema_match.group(1))
        except json.JSONDecodeError:
            pass

    # ---- STEP 7: BODY — the main strategy ----
    # Instead of pattern-matching the body, we SUBTRACT metadata and
    # section headers, then whatever remains is the article content.

    # Lines that are metadata labels or section headers (not body content)
    metadata_line_re = re.compile(
        r'^\s*(?:'
        r'meta\s*(?:title|desc)|seo\s*(?:title|desc|score)|'
        r'slug|permalink|url\s*slug|'
        r'(?:primary|target|focus|main|secondary|related|lsi|supporting|additional)\s*keyword|'
        r'tags?[:\-–—=]|wordpress\s*tags?|categories[:\-–—=]|'
        r'internal\s*link|linking\s*(?:strategy|instruction|note)|'
        r'schema\s*(?:markup)?|json-?ld|structured\s*data|'
        r'word\s*count|target\s*(?:city|length)|service\s*area|'
        r'deliverable\s*(?:#?\s*\d+)?[:\-–—=\s]|'
        r'seo\s*(?:score|projection|checklist)|'
        r'(?:blog|post|article)\s*title[:\-–—=]|'
        r'h1[:\-–—=]|headline[:\-–—=]|'
        r'excerpt[:\-–—=]|summary[:\-–—=]|'
        r'author[:\-–—=]|last\s*updated[:\-–—=]|publish\s*date|'
        r'cta[:\-–—=]|call\s*to\s*action|'
        r'featured\s*image|'
        # Content package section headers
        r'keyword\s*iteration|entity\s*term|full\s*article|'
        r'client\s*summary|mcp\s*copy|copy.?paste\s*ready|'
        r'publish\s*(?:date|schedule|timing)|next\s*action|refresh\s*(?:every|date)|'
        r'what\s*is\s*in\s*this\s*package|'
        r'localbusiness\s*:|howto\s*:|faqpage\s*:|'
        r'<script\s|</script>|@context|@type|'
        r'serving\s+(?:venice|sarasota|bradenton)|'
        r'[-=]{3,}|[*]{3,}'  # horizontal rules
        r')',
        re.IGNORECASE
    )

    # Also mark lines that are part of internal linking instructions
    linking_instruction_re = re.compile(
        r'^\s*[•\-\*·]\s*"[^"]+"\s*to\s*/|'  # • "keyword" to /path/
        r'^\s*[•\-\*·]\s*link\s+to\s|'         # • Link to ...
        r'^\s*anchor\s*text[:\-–—=]|'
        r'^\s*(?:link|anchor)\s*(?:#?\d+)[:\-–—=]|'
        r'^\s*[•\-\*·]\s*"[^"]+"\s*>>|'        # • "anchor" >> url
        r'^\s*[•\-\*·]\s*[^•\-\*·\n]+>>\s*\w',  # • anchor >> url (no quotes)
        re.IGNORECASE
    )

    # Schema/JSON-LD blocks — mark entire <script> blocks as metadata
    schema_line_re = re.compile(
        r'^\s*(?:<script|</script>|\{|\}|"@|"name"|"text"|"description"|"step"|"mainEntity"|"acceptedAnswer"|'
        r'"image"|"url"|"telephone"|"address"|"geo"|"openingHours"|"priceRange"|"areaServed"|'
        r'"dayOfWeek"|"opens"|"closes"|"streetAddress"|"addressLocality"|"addressRegion"|'
        r'"postalCode"|"addressCountry"|"latitude"|"longitude")',
        re.IGNORECASE
    )

    # Build body: collect ALL lines, mark each as 'meta' or 'body'
    line_classifications = []  # list of (line_text, 'meta'|'body'|'empty')

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not stripped:
            line_classifications.append((line, 'empty'))
            continue

        # Consumed by metadata extraction in steps 1-5
        if i in consumed_lines:
            line_classifications.append((line, 'meta'))
            continue

        # Metadata label lines
        if metadata_line_re.match(stripped):
            line_classifications.append((line, 'meta'))
            continue

        # Linking instruction lines
        if linking_instruction_re.match(stripped):
            line_classifications.append((line, 'meta'))
            continue

        # Schema/JSON-LD block lines
        if schema_line_re.match(stripped):
            line_classifications.append((line, 'meta'))
            continue

        # Lines that are just a URL (with or without protocol)
        if re.match(r'^(?:https?://)?\S+\.\S+/\S*\s*$', stripped) and len(stripped.split()) <= 2:
            line_classifications.append((line, 'meta'))
            continue

        # Lines that look like keyword iterations (no verb, short phrases)
        # e.g. "hurricane electrical prep Venice FL"
        # Detect: multiple similar short phrases in sequence with no punctuation
        if len(stripped.split()) <= 10 and not stripped.endswith('.') and not stripped.endswith('?') and not stripped.endswith(':'):
            # Check if this is part of a keyword list block (look at surrounding lines)
            nearby_short = 0
            for j in range(max(0, i-2), min(len(lines), i+3)):
                neighbor = lines[j].strip()
                if neighbor and len(neighbor.split()) <= 10 and not neighbor.endswith('.') and not neighbor.endswith('?'):
                    nearby_short += 1
            if nearby_short >= 4:  # 4+ short lines in a row = keyword list block
                line_classifications.append((line, 'meta'))
                continue

        # Everything else is potential body content
        line_classifications.append((line, 'body'))

    # Now find the longest contiguous run of body+empty lines
    # This is the article content
    best_start = -1
    best_end = -1
    best_len = 0
    cur_start = -1
    cur_body_chars = 0

    for i, (line, cls) in enumerate(line_classifications):
        if cls in ('body', 'empty'):
            if cur_start == -1:
                cur_start = i
                cur_body_chars = 0
            if cls == 'body':
                cur_body_chars += len(line.strip())
        else:
            # Meta line breaks the run
            if cur_start != -1 and cur_body_chars > best_len:
                best_start = cur_start
                best_end = i
                best_len = cur_body_chars
            cur_start = -1
            cur_body_chars = 0

    # Check the last run
    if cur_start != -1 and cur_body_chars > best_len:
        best_start = cur_start
        best_end = len(line_classifications)
        best_len = cur_body_chars

    body_lines = []
    if best_start >= 0:
        for i in range(best_start, best_end):
            line_text, cls = line_classifications[i]
            if cls == 'empty':
                if body_lines and body_lines[-1] != '':
                    body_lines.append('')
            else:
                body_lines.append(line_text)

    # Clean up leading/trailing empty
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    body_text = '\n'.join(body_lines).strip()

    # Count how many lines were classified as each type
    meta_count = sum(1 for _, c in line_classifications if c == 'meta')
    body_count = sum(1 for _, c in line_classifications if c == 'body')
    logger.info(f"Smart-paste parser: {len(lines)} lines total, {meta_count} meta, {body_count} body, {len(consumed_lines)} consumed | best run: {best_start}-{best_end} ({best_len} chars)")

    # Only use as body if it's substantial
    if len(body_text) > 100:
        # Check if this looks like a keyword list rather than article prose
        body_word_count = len(body_text.split())
        avg_line_len = len(body_text) / max(1, body_text.count('\n') + 1)
        comma_density = body_text.count(',') / max(1, body_word_count)

        # Keyword lists: short lines, lots of commas, few sentences
        sentence_count = len(re.findall(r'[.!?]\s', body_text))
        is_keyword_list = (
            comma_density > 0.15 and sentence_count < 3 and body_word_count < 100
        )

        if is_keyword_list:
            logger.warning(f"Smart-paste: body looks like keyword list, not article. Words={body_word_count}, commas={body_text.count(',')}, sentences={sentence_count}")
            result['body'] = body_text
            result['body_warning'] = 'keyword_list'
        else:
            # Convert headings to HTML — markdown or plain-text style
            if re.search(r'^#{1,6}\s+', body_text, re.MULTILINE):
                body_text = _markdown_to_html(body_text)
            else:
                body_text = _plaintext_to_html(body_text)

            # Inject internal links into body as <a> tags for SEO scoring
            if result.get('internal_links') and '<a ' not in body_text:
                body_text = _inject_internal_links(body_text, result['internal_links'])

            result['body'] = body_text
    else:
        logger.warning(f"Smart-paste: body too short ({len(body_text)} chars), not using. First 200: {repr(body_text[:200])}")
        result['body_warning'] = 'no_body' if len(body_text) < 10 else 'too_short'

    # ---- STEP 8: Extract FAQs ----
    # Look for FAQ Q&A pairs in the body text (before HTML conversion) or the original text
    # Common formats:
    #   Q: What is...?  A: Answer here.
    #   What is...? Answer follows on same or next line.
    #   Question line ending with ? followed by answer paragraph
    faq_items = _extract_faqs_from_text(text)
    if faq_items:
        result['faq_items'] = faq_items
        logger.info(f"Smart-paste: extracted {len(faq_items)} FAQ items")

    # ---- STEP 9: Fallback title ----
    if not result.get('title') and not result.get('meta_title'):
        for line in lines:
            clean = line.strip().lstrip('#').strip()
            if clean and len(clean) < 200 and not clean.startswith('http') and not re.match(r'^[-•*·]', clean):
                result['title'] = clean
                break

    return result


def _markdown_to_html(md_text: str) -> str:
    """Convert basic markdown to HTML for blog body content."""
    html_lines = []
    in_list = False

    for line in md_text.split('\n'):
        stripped = line.strip()

        # Headings
        h_match = re.match(r'^(#{1,6})\s+(.+)', stripped)
        if h_match:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            level = len(h_match.group(1))
            html_lines.append(f'<h{level}>{h_match.group(2).strip()}</h{level}>')
            continue

        # Bold + italic
        stripped = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', stripped)
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', stripped)

        # Links [text](url)
        stripped = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', stripped)

        # Unordered list items
        li_match = re.match(r'^[-*•·]\s+(.+)', stripped)
        if li_match:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{li_match.group(1)}</li>')
            continue

        # Ordered list items
        oli_match = re.match(r'^\d+[.)]\s+(.+)', stripped)
        if oli_match:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{oli_match.group(1)}</li>')
            continue

        # Close list if we hit a non-list line
        if in_list and stripped:
            html_lines.append('</ul>')
            in_list = False

        # Empty line = paragraph break
        if not stripped:
            html_lines.append('')
            continue

        # Regular paragraph
        html_lines.append(f'<p>{stripped}</p>')

    if in_list:
        html_lines.append('</ul>')

    return '\n'.join(html_lines)


def _plaintext_to_html(text: str) -> str:
    """
    Convert plain-text blog content to HTML with proper heading detection.
    Detects common heading patterns like:
    - "Step 1: Title Here"
    - "What Is Hurricane Electrical Prep?"
    - "Frequently Asked Questions"
    - "During the Storm: What Not to Do"
    - Short standalone lines followed by paragraph text
    """
    html_lines = []
    in_list = False
    lines = text.split('\n')

    # Patterns that indicate a line is a heading (not body prose)
    heading_patterns = [
        # Step N: Title
        r'^Step\s+\d+\s*[:\-–—]\s*.+',
        # Question-style headings: What Is..., How Do..., Why..., When Should...
        r'^(?:What|How|Why|When|Where|Who|Which|Do|Does|Is|Are|Can|Should|Will)\s+.{10,80}\??$',
        # Short title-case lines (3-10 words, no period at end)
        # e.g. "During the Storm: What Not to Do", "Frequently Asked Questions"
    ]
    heading_re = re.compile('|'.join(heading_patterns), re.IGNORECASE)

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Empty line
        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('')
            continue

        # Already HTML
        if stripped.startswith('<h') or stripped.startswith('<p') or stripped.startswith('<ul') or stripped.startswith('<li'):
            html_lines.append(stripped)
            continue

        # Unordered list items
        li_match = re.match(r'^[-*•·]\s+(.+)', stripped)
        if li_match:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{li_match.group(1)}</li>')
            continue

        # Ordered list items
        oli_match = re.match(r'^\d+[.)]\s+(.+)', stripped)
        if oli_match:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{oli_match.group(1)}</li>')
            continue

        # Close list if we hit a non-list line
        if in_list and stripped:
            html_lines.append('</ul>')
            in_list = False

        # Check if this is a heading
        is_heading = False
        heading_level = 2  # default to h2

        # Explicit heading pattern matches
        if heading_re.match(stripped):
            is_heading = True

        # Short title-like lines: 2-12 words, no period, not a sentence
        if not is_heading:
            word_count = len(stripped.split())
            ends_with_period = stripped.endswith('.')
            has_colon = ':' in stripped

            if word_count <= 12 and not ends_with_period:
                # Check if next non-empty line is a longer paragraph
                next_content = ''
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j].strip():
                        next_content = lines[j].strip()
                        break
                # Check if previous non-empty line was also short (avoid marking list items)
                if next_content and len(next_content.split()) > 15:
                    is_heading = True

        # Determine heading level
        if is_heading:
            # First heading in the article = h1 (title), rest are h2
            # "Step N:" or FAQ-style = h2, sub-items = h3
            if re.match(r'^Step\s+\d+', stripped, re.IGNORECASE):
                heading_level = 2
            elif re.match(r'^(?:What|How|Why|When|Where|Who|Which)\s+', stripped, re.IGNORECASE) and len(stripped.split()) <= 8:
                heading_level = 3  # FAQ sub-questions are h3
            elif any(kw in stripped.lower() for kw in ['frequently asked', 'faq', 'during the storm', 'after the storm', 'why ', 'what ak electrical']):
                heading_level = 2
            # Short sub-headings under steps
            elif len(stripped.split()) <= 6 and ':' not in stripped:
                heading_level = 3

            html_lines.append(f'<h{heading_level}>{stripped}</h{heading_level}>')
        else:
            # Regular paragraph
            html_lines.append(f'<p>{stripped}</p>')

    if in_list:
        html_lines.append('</ul>')

    return '\n'.join(html_lines)


def _promote_headings_in_html(body_html: str) -> str:
    """
    Promote short <p> or <strong> or <b> paragraphs to proper <h2>/<h3> headings.
    Handles WYSIWYG editor output where headings are just bold text in paragraphs.

    Heading detection patterns:
    - <p><strong>Step 1: ...</strong></p> → <h2>Step 1: ...</h2>
    - <p><b>What Is ...?</b></p> → <h2>What Is ...?</h2>
    - <p>Frequently Asked Questions</p> (short, no period) → <h2>...</h2>
    - Short paragraphs (≤12 words, no period) before longer paragraphs
    """
    heading_patterns = [
        # Step N: ...
        r'^Step\s+\d+\s*[:\-–—]\s*.+',
        # Question-style headings
        r'^(?:What|How|Why|When|Where|Who|Which|Do|Does|Is|Are|Can|Should|Will)\s+.{10,80}\??$',
        # Known section headers
        r'^(?:Frequently\s+Asked\s+Questions|FAQ|During\s+the\s+Storm|After\s+the\s+Storm|Why\s+.+Choose)',
    ]
    heading_re = re.compile('|'.join(heading_patterns), re.IGNORECASE)

    def is_heading_text(text):
        text = text.strip()
        if not text or len(text) > 150:
            return False
        # Explicit pattern match
        if heading_re.match(text):
            return True
        # Short text without period ending
        words = text.split()
        if 2 <= len(words) <= 12 and not text.endswith('.') and not text.endswith(','):
            return True
        return False

    def determine_level(text):
        text = text.strip()
        if re.match(r'^Step\s+\d+', text, re.IGNORECASE):
            return 2
        if re.match(r'^(?:What|How|Why|When|Where|Who)\s+', text, re.IGNORECASE) and len(text.split()) <= 10:
            return 3
        if any(kw in text.lower() for kw in ['frequently asked', 'faq', 'during the storm', 'after the storm']):
            return 2
        if len(text.split()) <= 6:
            return 3
        return 2

    # Pattern 1: <p><strong>Heading Text</strong></p> or <p><b>Heading</b></p>
    def replace_bold_headings(match):
        full = match.group(0)
        inner = match.group(1).strip()
        # Strip nested tags to get plain text
        plain = re.sub(r'<[^>]+>', '', inner).strip()
        if is_heading_text(plain):
            level = determine_level(plain)
            return f'<h{level}>{plain}</h{level}>'
        return full

    body_html = re.sub(
        r'<p[^>]*>\s*<(?:strong|b)>(.+?)</(?:strong|b)>\s*</p>',
        replace_bold_headings,
        body_html,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Pattern 2: Plain <p>short text</p> that looks like a heading
    # Only promote if no nested HTML and text matches heading patterns
    def replace_plain_headings(match):
        full = match.group(0)
        inner = match.group(1).strip()
        # Skip if it contains HTML tags (except <br>)
        if re.search(r'<(?!br)[a-z]', inner, re.IGNORECASE):
            return full
        plain = re.sub(r'<br\s*/?>', ' ', inner).strip()
        if is_heading_text(plain) and heading_re.match(plain):
            level = determine_level(plain)
            return f'<h{level}>{plain}</h{level}>'
        return full

    body_html = re.sub(
        r'<p[^>]*>(.+?)</p>',
        replace_plain_headings,
        body_html,
        flags=re.IGNORECASE | re.DOTALL
    )

    return body_html


def _inject_internal_links(body_html: str, links: list) -> str:
    """
    Inject <a> tags into the HTML body for internal links.
    Matches anchor text in the body and wraps the first occurrence with a link.
    This ensures the SEO scoring engine can count internal links.
    """
    if not links:
        return body_html

    for link in links:
        anchor = link.get('text', '')
        url = link.get('url', '')
        if not anchor or not url:
            continue

        # Escape anchor for regex
        escaped_anchor = re.escape(anchor)

        # Replace first occurrence of the anchor text (case-insensitive) that isn't already in a link
        # Only match text that's NOT inside an existing <a> tag
        pattern = rf'(?<!<a[^>]*>)(?<!["\'/])({escaped_anchor})(?!</a>)(?!["\'/])'
        replacement = f'<a href="{url}">\\1</a>'
        body_html, count = re.subn(pattern, replacement, body_html, count=1, flags=re.IGNORECASE)
        if count > 0:
            logger.debug(f"Injected internal link: '{anchor}' → {url}")

    return body_html


def _extract_faqs_from_text(text: str) -> list:
    """
    Extract FAQ question/answer pairs from pasted content.

    Detects common FAQ formats:
    1. Same-line: "Question here? Answer follows on same line."
    2. Multi-line: Question? (newline) Answer paragraph
    3. Q: Question? A: Answer
    4. FAQPage schema JSON with mainEntity array
    """
    faq_items = []

    # Strategy 1: Find a "Frequently Asked Questions" / "FAQ" section
    faq_section_match = re.search(
        r'(?:Frequently\s+Asked\s+Questions|FAQ\s*(?:Section|s)?)\s*\n([\s\S]+?)(?:\n={3,}|\n-{3,}|\nSCHEMA|\nCLIENT\s+SUMMARY|\nWhy\s+\w+\s+(?:Homeowners?|Clients?|Customers?)\s+Choose|\Z)',
        text, re.IGNORECASE
    )

    if faq_section_match:
        faq_text = faq_section_match.group(1).strip()
        lines = faq_text.split('\n')

        current_question = None
        current_answer_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Format A: Same-line Q&A — "Question here? Answer starts with capital letter."
            same_line_match = re.match(r'^(.{15,}?\?)\s+([A-Z].{20,})$', stripped)
            if same_line_match:
                # Save any previous Q&A pair first
                if current_question and current_answer_lines:
                    answer = ' '.join(current_answer_lines).strip()
                    if len(answer) > 20:
                        faq_items.append({
                            'question': current_question,
                            'answer': answer
                        })
                    current_question = None
                    current_answer_lines = []

                q = same_line_match.group(1).strip()
                a = same_line_match.group(2).strip()
                if len(q.split()) >= 4:
                    faq_items.append({'question': q, 'answer': a})
                continue

            # Format B: Question-only line (ends with ?)
            is_question = stripped.endswith('?') and len(stripped.split()) >= 4 and len(stripped) < 200

            if is_question:
                # Save previous Q&A pair
                if current_question and current_answer_lines:
                    answer = ' '.join(current_answer_lines).strip()
                    if len(answer) > 20:
                        faq_items.append({
                            'question': current_question,
                            'answer': answer
                        })
                current_question = stripped
                current_answer_lines = []
            else:
                # This is answer text (continuation)
                if current_question:
                    current_answer_lines.append(stripped)

        # Don't forget the last Q&A pair
        if current_question and current_answer_lines:
            answer = ' '.join(current_answer_lines).strip()
            if len(answer) > 20:
                faq_items.append({
                    'question': current_question,
                    'answer': answer
                })

    # Strategy 2: If no FAQ section found, try Q:/A: format
    if not faq_items:
        qa_matches = re.findall(
            r'(?:^|\n)\s*Q\s*[:.\-)]\s*(.+?\?)\s*\n\s*A\s*[:.\-)]\s*(.+?)(?=\n\s*Q\s*[:.\-)]|\n\n|\Z)',
            text, re.IGNORECASE | re.DOTALL
        )
        for q, a in qa_matches:
            q_clean = q.strip()
            a_clean = ' '.join(a.strip().split())
            if len(q_clean) > 10 and len(a_clean) > 20:
                faq_items.append({'question': q_clean, 'answer': a_clean})

    # Strategy 3: Extract from FAQPage schema JSON if present
    if not faq_items:
        schema_match = re.search(r'"@type"\s*:\s*"FAQPage"[\s\S]*?"mainEntity"\s*:\s*\[([\s\S]*?)\]', text)
        if schema_match:
            try:
                entities_text = '[' + schema_match.group(1) + ']'
                entities = json.loads(entities_text)
                for entity in entities:
                    q = entity.get('name', '')
                    accepted = entity.get('acceptedAnswer', {})
                    a = accepted.get('text', '') if isinstance(accepted, dict) else ''
                    if q and a:
                        faq_items.append({'question': q, 'answer': a})
            except (json.JSONDecodeError, KeyError):
                pass

    return faq_items


# ==========================================
# Competitor Gap Analysis
# ==========================================

@content_bp.route('/gap-analysis', methods=['POST'])
@token_required
def competitor_gap_analysis(current_user):
    """
    Run AI-powered competitor content gap analysis.
    Takes client's site and competitor URLs, returns topic suggestions.

    POST /api/content/gap-analysis
    Body: { client_id, my_site, competitor_urls: [...], num_topics: 5 }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    my_site = data.get('my_site', '').strip()
    competitor_urls = data.get('competitor_urls', [])
    num_topics = data.get('num_topics', 5)

    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403

    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    if not my_site:
        my_site = client.website_url or ''
    if not my_site:
        return jsonify({'error': 'No website URL configured for this client'}), 400

    if not competitor_urls:
        try:
            competitor_urls = json.loads(client.competitors) if client.competitors else []
        except (json.JSONDecodeError, TypeError):
            competitor_urls = []

    if not competitor_urls:
        return jsonify({'error': 'No competitor URLs provided and none configured in client settings'}), 400

    # Build the AI prompt
    competitors_list = '\n'.join(f'  - {url}' for url in competitor_urls[:5])
    industry = client.industry or 'general'
    geo = client.geo or ''

    prompt = f"""You are an expert SEO content strategist. Analyze the following websites and identify content gaps.

MY CLIENT'S WEBSITE: {my_site}
INDUSTRY: {industry}
LOCATION: {geo}

COMPETITOR WEBSITES:
{competitors_list}

TASK: Scan these competitor sites. What content are they covering that my client is NOT? Find the content gaps and suggest exactly {num_topics} blog topics my client should cover to be more helpful and rank better.

For each topic, provide:
1. **Topic Title** — a specific, SEO-optimized blog title
2. **Target Keyword** — the primary keyword to target
3. **Why It Matters** — 1-2 sentences on the gap and opportunity
4. **Estimated Search Volume** — low/medium/high
5. **Difficulty** — easy/medium/hard

Return your response as a JSON array of objects with keys: title, keyword, reason, search_volume, difficulty
Wrap the JSON in ```json ... ``` tags."""

    try:
        ai_service = AIService()
        response = ai_service.generate_raw(prompt, max_tokens=2000)

        # Parse JSON from response
        topics = []
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                topics = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        if not topics:
            # Try parsing the whole response as JSON
            try:
                topics = json.loads(response)
            except json.JSONDecodeError:
                # Return raw text as fallback
                return jsonify({
                    'message': 'Gap analysis complete (raw)',
                    'raw_response': response,
                    'topics': []
                })

        return jsonify({
            'message': f'Found {len(topics)} content gap topics',
            'my_site': my_site,
            'competitors': competitor_urls[:5],
            'topics': topics
        })

    except Exception as e:
        logger.error(f"Gap analysis failed: {e}", exc_info=True)
        return jsonify({'error': f'Gap analysis failed: {str(e)}'}), 500


# ==========================================
# Deep Competitor Intelligence Scan
# ==========================================

@content_bp.route('/deep-gap-analysis', methods=['POST'])
@token_required
def deep_gap_analysis(current_user):
    """
    Deep competitor content gap analysis that actually crawls sites.

    1. Fetches sitemap + homepage for the client and each competitor
    2. Extracts page titles, headings, services offered
    3. Sends real crawl data to AI for comparison
    4. Returns structured report: competitor grid + gap topics + blog suggestions

    POST /api/content/deep-gap-analysis
    Body: { client_id, competitor_urls: [...], num_topics: 5 }
    """
    import requests as http_requests
    from urllib.parse import urljoin, urlparse

    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    competitor_urls = data.get('competitor_urls', [])
    num_topics = data.get('num_topics', 5)

    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403

    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    my_site = client.website_url or ''
    if not my_site:
        return jsonify({'error': 'No website URL configured for this client'}), 400

    # Get competitors from input or client settings
    if not competitor_urls:
        try:
            competitor_urls = json.loads(client.competitors) if client.competitors else []
        except (json.JSONDecodeError, TypeError):
            if isinstance(client.competitors, list):
                competitor_urls = client.competitors
            elif isinstance(client.competitors, str) and client.competitors.strip():
                competitor_urls = [u.strip() for u in client.competitors.split(',') if u.strip()]
            else:
                competitor_urls = []

    if not competitor_urls:
        return jsonify({'error': 'No competitor URLs provided and none configured in client settings'}), 400

    competitor_urls = competitor_urls[:5]  # Limit to 5

    def _clean_url(url):
        url = url.strip().rstrip('/')
        if not url.startswith('http'):
            url = 'https://' + url
        return url

    def _extract_domain(url):
        parsed = urlparse(url)
        d = parsed.netloc or parsed.path
        d = d.lower().replace('www.', '')
        return d.rstrip('/')

    def _crawl_site_intel(url, timeout=15):
        """Crawl a site and extract content intelligence: pages, titles, headings, services."""
        url = _clean_url(url)
        domain = _extract_domain(url)
        intel = {
            'url': url,
            'domain': domain,
            'page_titles': [],
            'service_pages': [],
            'blog_topics': [],
            'headings': [],
            'meta_desc': '',
            'tagline': '',
            'error': None
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        try:
            from bs4 import BeautifulSoup

            # Step 1: Homepage
            resp = http_requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
            if resp.status_code != 200:
                intel['error'] = f'HTTP {resp.status_code}'
                return intel

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Title and meta
            title_tag = soup.find('title')
            if title_tag:
                intel['tagline'] = title_tag.get_text(strip=True)[:200]

            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                intel['meta_desc'] = meta_desc.get('content', '')[:300]

            # Headings from homepage
            for h in soup.find_all(['h1', 'h2', 'h3']):
                text = h.get_text(strip=True)[:150]
                if text and len(text) > 3:
                    intel['headings'].append(text)

            # Links from homepage — categorize service vs blog
            all_links = []
            for a in soup.find_all('a', href=True):
                href = urljoin(resp.url, a.get('href', ''))
                parsed = urlparse(href)
                if domain not in parsed.netloc.lower():
                    continue
                text = a.get_text(strip=True)[:150]
                path = parsed.path.lower().rstrip('/')
                if not path or path == '/' or len(path) < 3:
                    continue
                # Skip utility pages
                if any(x in path for x in ['/wp-', '/feed', '/tag/', '/category/', '/author/', '#', '.pdf', '.jpg', '.png', '.css', '.js', '/cart', '/checkout', '/login', '/privacy', '/terms']):
                    continue
                all_links.append({'url': href, 'text': text, 'path': path})

            # Classify links
            for link in all_links:
                path = link['path']
                text = link['text'] or link['path'].split('/')[-1].replace('-', ' ').title()
                if any(x in path for x in ['/blog', '/news', '/article', '/post', '/resource']):
                    if text and len(text) > 5:
                        intel['blog_topics'].append(text)
                elif any(x in path for x in ['/service', '/about', '/contact', '/gallery', '/portfolio', '/testimonial', '/review', '/faq', '/area']):
                    intel['service_pages'].append(text)
                else:
                    intel['page_titles'].append(text)

            # Step 2: Try sitemap for comprehensive page list
            sitemap_urls = [
                f'https://{domain}/sitemap.xml',
                f'https://www.{domain}/sitemap.xml',
                f'https://{domain}/wp-sitemap.xml',
            ]
            for sm_url in sitemap_urls:
                try:
                    sm_resp = http_requests.get(sm_url, timeout=8, headers=headers)
                    if sm_resp.status_code == 200 and '<url' in sm_resp.text.lower():
                        sm_soup = BeautifulSoup(sm_resp.text, 'xml')

                        # Handle sitemap index
                        sub_sitemaps = sm_soup.find_all('sitemap')
                        if sub_sitemaps:
                            for ss in sub_sitemaps[:5]:
                                loc = ss.find('loc')
                                if loc:
                                    try:
                                        ss_resp = http_requests.get(loc.text, timeout=8, headers=headers)
                                        if ss_resp.status_code == 200:
                                            ss_soup = BeautifulSoup(ss_resp.text, 'xml')
                                            for u in ss_soup.find_all('url'):
                                                l = u.find('loc')
                                                if l and domain in l.text:
                                                    path = urlparse(l.text).path.lower()
                                                    title = path.rstrip('/').split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                                                    if '/blog' in path or '/post' in path or '/news' in path:
                                                        if title and len(title) > 3:
                                                            intel['blog_topics'].append(title)
                                                    elif title and len(title) > 3:
                                                        intel['page_titles'].append(title)
                                    except:
                                        continue
                        else:
                            for u in sm_soup.find_all('url'):
                                l = u.find('loc')
                                if l and domain in l.text:
                                    path = urlparse(l.text).path.lower()
                                    title = path.rstrip('/').split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                                    if '/blog' in path or '/post' in path or '/news' in path:
                                        if title and len(title) > 3:
                                            intel['blog_topics'].append(title)
                                    elif title and len(title) > 3:
                                        intel['page_titles'].append(title)
                        break
                except:
                    continue

            # Deduplicate
            intel['page_titles'] = list(dict.fromkeys(intel['page_titles']))[:50]
            intel['service_pages'] = list(dict.fromkeys(intel['service_pages']))[:30]
            intel['blog_topics'] = list(dict.fromkeys(intel['blog_topics']))[:50]
            intel['headings'] = list(dict.fromkeys(intel['headings']))[:30]

        except Exception as e:
            intel['error'] = str(e)
            logger.warning(f"Failed to crawl {url}: {e}")

        return intel

    try:
        logger.info(f"Starting deep gap analysis for client {client_id} vs {len(competitor_urls)} competitors")

        # Crawl all sites in parallel-ish (sequential but fast)
        my_intel = _crawl_site_intel(my_site)
        competitor_intel = []
        for comp_url in competitor_urls:
            ci = _crawl_site_intel(comp_url)
            competitor_intel.append(ci)

        # Build the AI analysis prompt with real crawl data
        industry = client.industry or 'general'
        geo = client.geo or ''
        biz_name = client.business_name or ''
        phone = client.phone or ''
        usps = ''
        try:
            usp_list = json.loads(client.unique_selling_points) if client.unique_selling_points else []
            if isinstance(usp_list, list):
                usps = '; '.join(usp_list[:5])
            elif isinstance(usp_list, str):
                usps = usp_list
        except:
            usps = client.unique_selling_points or ''

        my_pages_summary = f"""
MY CLIENT: {biz_name} ({my_intel['domain']})
Tagline: {my_intel['tagline']}
Description: {my_intel['meta_desc']}
Unique Selling Points: {usps}
Service Pages: {', '.join(my_intel['service_pages'][:20]) or 'None found'}
Blog Topics: {', '.join(my_intel['blog_topics'][:25]) or 'None found'}
Other Pages: {', '.join(my_intel['page_titles'][:20]) or 'None found'}
Homepage Headings: {', '.join(my_intel['headings'][:15]) or 'None found'}
"""

        competitors_summary = ""
        for ci in competitor_intel:
            competitors_summary += f"""
COMPETITOR: {ci['domain']}
Tagline: {ci['tagline']}
Description: {ci['meta_desc']}
Service Pages: {', '.join(ci['service_pages'][:20]) or 'None found'}
Blog Topics: {', '.join(ci['blog_topics'][:25]) or 'None found'}
Other Pages: {', '.join(ci['page_titles'][:20]) or 'None found'}
Homepage Headings: {', '.join(ci['headings'][:15]) or 'None found'}
{f"(Error crawling: {ci['error']})" if ci['error'] else ''}
"""

        prompt = f"""You are an expert SEO strategist and competitive intelligence analyst. I have crawled real data from my client's website and their competitors. Analyze this data and produce a complete competitive intelligence report.

INDUSTRY: {industry}
LOCATION: {geo}

{my_pages_summary}

{competitors_summary}

TASK: Produce a JSON response with this exact structure:

{{
  "competitor_grid": [
    {{
      "domain": "competitor.com",
      "strengths": ["strength1", "strength2"],
      "weaknesses": ["weakness1", "weakness2"],
      "services_they_cover": ["service1", "service2"],
      "content_count": 0,
      "threat_level": "high/medium/low",
      "summary": "1-2 sentence summary"
    }}
  ],
  "my_strengths": ["what my client does well based on their site content"],
  "my_weaknesses": ["content gaps or areas where client is behind"],
  "gap_topics": [
    {{
      "title": "SEO-optimized blog title targeting {geo}",
      "keyword": "primary target keyword",
      "search_volume": "low/medium/high",
      "difficulty": "easy/medium/hard",
      "reason": "2-3 sentences: what gap this fills, which competitor covers it, why it matters for revenue",
      "competitors_covering": ["competitor1.com"],
      "priority": 1,
      "estimated_traffic": "X visits/month",
      "cta_angle": "how to weave in {biz_name}'s CTA and differentiators"
    }}
  ],
  "executive_summary": "3-4 sentence overview of the competitive landscape and biggest opportunities"
}}

RULES:
- Return exactly {num_topics} gap_topics, ranked by priority (highest business impact first)
- Every blog title MUST include the city/location ({geo}) for local SEO
- gap_topics should focus on topics competitors ACTUALLY have content for (based on crawl data) that my client does NOT
- If a competitor has blog posts or service pages on a topic and my client doesn't, that's a high-priority gap
- competitor_grid should have one entry per competitor
- threat_level: "high" if they cover more topics and rank well, "medium" if comparable, "low" if thin content
- cta_angle: specific suggestions for how {biz_name} can differentiate (mention phone: {phone}, USPs: {usps})
- Be specific and actionable — no generic advice

Wrap the JSON in ```json ... ``` tags."""

        ai_svc = AIService()
        raw_response = ai_svc.generate_raw(prompt, max_tokens=4000)

        # Parse JSON
        result = {}
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_response)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        if not result:
            try:
                result = json.loads(raw_response)
            except:
                return jsonify({
                    'message': 'Analysis complete (raw)',
                    'raw_response': raw_response[:3000],
                    'crawl_data': {
                        'my_site': {
                            'domain': my_intel['domain'],
                            'pages': len(my_intel['page_titles']) + len(my_intel['blog_topics']),
                            'services': my_intel['service_pages'][:10],
                            'blogs': my_intel['blog_topics'][:10],
                        },
                        'competitors': [
                            {
                                'domain': ci['domain'],
                                'pages': len(ci['page_titles']) + len(ci['blog_topics']),
                                'services': ci['service_pages'][:10],
                                'blogs': ci['blog_topics'][:10],
                                'error': ci['error'],
                            }
                            for ci in competitor_intel
                        ]
                    }
                })

        # Attach crawl metadata
        result['crawl_data'] = {
            'my_site': {
                'domain': my_intel['domain'],
                'total_pages': len(my_intel['page_titles']) + len(my_intel['blog_topics']) + len(my_intel['service_pages']),
                'service_pages': my_intel['service_pages'][:15],
                'blog_count': len(my_intel['blog_topics']),
            },
            'competitors': [
                {
                    'domain': ci['domain'],
                    'total_pages': len(ci['page_titles']) + len(ci['blog_topics']) + len(ci['service_pages']),
                    'blog_count': len(ci['blog_topics']),
                    'error': ci['error'],
                }
                for ci in competitor_intel
            ]
        }
        result['client_id'] = client_id
        result['my_site'] = my_site
        result['competitor_urls'] = competitor_urls

        logger.info(f"Deep gap analysis complete: {len(result.get('gap_topics', []))} topics found")

        return jsonify(result)

    except Exception as e:
        logger.error(f"Deep gap analysis failed: {e}", exc_info=True)
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


# ==========================================
# Notes System — internal / from client / for client
# ==========================================

@content_bp.route('/blog/<blog_id>/notes', methods=['GET'])
@token_required
def get_blog_notes(current_user, blog_id):
    """Get all notes for a blog post"""
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403

    try:
        notes = json.loads(blog.notes) if blog.notes else []
    except (json.JSONDecodeError, TypeError):
        notes = []

    return jsonify({'notes': notes, 'blog_id': blog_id})


@content_bp.route('/blog/<blog_id>/notes', methods=['POST'])
@token_required
def add_blog_note(current_user, blog_id):
    """
    Add a note to a blog post.
    Body: { type: 'internal'|'from_client'|'for_client', text: '...' }
    """
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    note_type = data.get('type', 'internal')
    note_text = data.get('text', '').strip()

    if note_type not in ('internal', 'from_client', 'for_client'):
        return jsonify({'error': 'Invalid note type. Must be internal, from_client, or for_client'}), 400
    if not note_text:
        return jsonify({'error': 'Note text is required'}), 400

    try:
        notes = json.loads(blog.notes) if blog.notes else []
    except (json.JSONDecodeError, TypeError):
        notes = []

    new_note = {
        'id': f"note_{uuid.uuid4().hex[:8]}",
        'type': note_type,
        'text': note_text,
        'author': current_user.name or current_user.email,
        'created_at': datetime.utcnow().isoformat()
    }
    notes.append(new_note)
    blog.notes = json.dumps(notes)
    blog.updated_at = datetime.utcnow()

    from app.database import db as _db
    _db.session.commit()

    return jsonify({'message': 'Note added', 'note': new_note, 'notes': notes}), 201


@content_bp.route('/blog/<blog_id>/notes/<note_id>', methods=['DELETE'])
@token_required
def delete_blog_note(current_user, blog_id, note_id):
    """Delete a note from a blog post"""
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403

    try:
        notes = json.loads(blog.notes) if blog.notes else []
    except (json.JSONDecodeError, TypeError):
        notes = []

    original_len = len(notes)
    notes = [n for n in notes if n.get('id') != note_id]

    if len(notes) == original_len:
        return jsonify({'error': 'Note not found'}), 404

    blog.notes = json.dumps(notes)
    blog.updated_at = datetime.utcnow()

    from app.database import db as _db
    _db.session.commit()

    return jsonify({'message': 'Note deleted', 'notes': notes})
