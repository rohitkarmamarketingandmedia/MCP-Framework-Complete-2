"""
MCP Framework - Content Scheduler Service
Auto-generates blog posts on a per-client schedule, emails clients with review links
"""
import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


def run_content_schedules(app):
    """
    Main scheduler job — runs every hour.
    Checks all active content schedules and generates blogs that are due.
    """
    with app.app_context():
        try:
            from app.database import db
            from app.models.schedule_models import DBContentSchedule
            from app.models.db_models import DBClient
            
            now = datetime.utcnow()
            
            # Find schedules that are due
            due_schedules = DBContentSchedule.query.filter(
                DBContentSchedule.is_active == True,
                DBContentSchedule.next_generation_at <= now
            ).all()
            
            if not due_schedules:
                return
            
            logger.info(f"[CONTENT-SCHED] Found {len(due_schedules)} schedules due for generation")
            
            for schedule in due_schedules:
                try:
                    client = DBClient.query.get(schedule.client_id)
                    if not client or not client.is_active:
                        logger.warning(f"[CONTENT-SCHED] Client {schedule.client_id} not found or inactive, skipping")
                        schedule.last_error = "Client not found or inactive"
                        db.session.commit()
                        continue
                    
                    _generate_scheduled_blog(app, schedule, client)
                    
                except Exception as e:
                    logger.error(f"[CONTENT-SCHED] Error for client {schedule.client_id}: {e}")
                    schedule.last_error = str(e)[:500]
                    try:
                        db.session.commit()
                    except:
                        db.session.rollback()
                        
        except Exception as e:
            logger.error(f"[CONTENT-SCHED] Fatal error: {e}")


def _generate_scheduled_blog(app, schedule, client):
    """Generate a single blog post for a scheduled client"""
    from app.database import db
    from app.models.db_models import DBBlogPost, ContentStatus
    from app.services.blog_ai_single import get_blog_ai_single, BlogRequest
    from app.services.internal_linking_service import internal_linking_service
    from app.services.seo_scoring_engine import SEOScoringEngine
    
    seo_engine = SEOScoringEngine()
    
    # 1. Pick the next keyword + city
    keyword, city = _get_next_keyword_city(schedule, client)
    if not keyword:
        logger.warning(f"[CONTENT-SCHED] No keywords available for client {client.business_name}")
        schedule.last_error = "No keywords configured"
        db.session.commit()
        return
    
    logger.info(f"[CONTENT-SCHED] Generating blog for {client.business_name}: '{keyword}' in '{city}'")
    
    # 2. Parse geo
    geo = client.geo or ''
    geo_parts = geo.split(',') if geo else ['', '']
    state = geo_parts[1].strip() if len(geo_parts) > 1 else ''
    if not city:
        city = geo_parts[0].strip() if len(geo_parts) > 0 else ''
    
    # 3. Build internal links
    service_pages = client.get_service_pages() or []
    internal_links = []
    for page in service_pages[:6]:
        if isinstance(page, dict) and page.get('url') and page.get('title'):
            url = page['url']
            if not url.startswith('http') and client.website_url:
                url = f"https://{client.website_url.rstrip('/')}/{url.lstrip('/')}"
            internal_links.append({'url': url, 'title': page['title']})
    
    # 4. Generate the blog
    blog_gen = get_blog_ai_single()
    blog_request = BlogRequest(
        keyword=keyword,
        target_words=schedule.target_word_count,
        city=city,
        state=state,
        company_name=client.business_name or '',
        phone=client.phone or '',
        email=client.email or '',
        industry=client.industry or 'Local Services',
        internal_links=internal_links,
        faq_count=schedule.faq_count if schedule.include_faq else 0,
        contact_url=getattr(client, 'contact_url', '') or '',
        blog_url=getattr(client, 'blog_url', '') or '',
        verify_content=schedule.verify_content
    )
    
    result = blog_gen.generate(blog_request)
    
    if result.get('error'):
        logger.error(f"[CONTENT-SCHED] Generation failed: {result['error']}")
        schedule.last_error = result['error'][:500]
        db.session.commit()
        return
    
    body_content = result.get('body', '')
    if not body_content or len(body_content) < 100:
        schedule.last_error = "AI returned empty content"
        db.session.commit()
        return
    
    # 5. Process internal linking
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
    
    # 6. Calculate SEO score
    try:
        seo_result = seo_engine.score_content(
            content={
                'title': result.get('title', ''),
                'meta_title': result.get('meta_title', ''),
                'meta_description': result.get('meta_description', ''),
                'h1': result.get('h1', result.get('title', '')),
                'body': body_content
            },
            target_keyword=keyword,
            location=city or client.geo or ''
        )
        seo_score = seo_result.get('total_score', 0)
    except Exception:
        seo_score = 50
    
    # 7. Generate review token
    review_token = uuid.uuid4().hex + uuid.uuid4().hex[:8]  # 40-char token
    
    # 8. Generate tags (avoid duplicate city)
    from app.routes.content import _generate_blog_tags
    tags = _generate_blog_tags(keyword, city=city, industry=client.industry, client_name=client.business_name)
    
    # 9. Create blog post
    blog_post = DBBlogPost(
        client_id=client.id,
        title=result.get('title', keyword),
        body=body_content,
        meta_title=result.get('meta_title', ''),
        meta_description=result.get('meta_description', ''),
        primary_keyword=keyword,
        secondary_keywords=result.get('secondary_keywords', []),
        internal_links=service_pages,
        faq_content=result.get('faq_items', []),
        schema_markup=result.get('schema', {}),
        word_count=len(body_content.split()),
        seo_score=seo_score,
        target_city=city,
        tags=tags,
        status=ContentStatus.DRAFT
    )
    
    # Set review and schedule fields
    blog_post.review_token = review_token
    blog_post.client_status = 'pending_review'
    blog_post.auto_generated = True
    
    # Store fact-check report
    fact_check = result.get('fact_check')
    if fact_check and isinstance(fact_check, dict):
        blog_post.fact_check_report = json.dumps(fact_check)
        blog_post.fact_check_score = fact_check.get('accuracy_score')
    
    db.session.add(blog_post)
    
    # 10. Update schedule tracking
    schedule.last_keyword_used = keyword
    schedule.last_error = None
    schedule.advance_schedule()
    
    db.session.commit()
    
    logger.info(f"[CONTENT-SCHED] Created blog {blog_post.id}: '{blog_post.title}' ({blog_post.word_count} words, SEO: {seo_score})")
    
    # 11. Send email to client
    if schedule.send_to_client:
        _send_review_email(app, schedule, client, blog_post)


def _get_next_keyword_city(schedule, client) -> tuple:
    """
    Pick the next keyword + city combination.
    Rotates through primary_keywords × service_cities matrix.
    Returns (keyword, city) tuple.
    """
    # Check custom queue first
    queue = schedule.get_keyword_queue()
    if queue:
        keyword = queue[0]
        # Remove used keyword from queue
        queue.pop(0)
        schedule.keyword_queue = json.dumps(queue)
        # Use first service city or geo
        cities = client.get_service_cities()
        city = cities[schedule.city_index % len(cities)] if cities else ''
        return keyword, city
    
    # Rotate through keywords × cities
    keywords = client.get_primary_keywords()
    cities = client.get_service_cities()
    
    if not keywords:
        # Fall back to industry-based keywords
        industry = (client.industry or '').lower()
        if industry:
            keywords = [f"{industry} services"]
        else:
            return None, ''
    
    if not cities:
        # Fall back to geo city
        geo = client.geo or ''
        geo_city = geo.split(',')[0].strip() if geo else ''
        cities = [geo_city] if geo_city else ['']
    
    # Get current position in the rotation
    ki = schedule.keyword_index % len(keywords)
    ci = schedule.city_index % len(cities)
    
    keyword = keywords[ki]
    city = cities[ci]
    
    # Advance indices for next time
    # Cycle: all cities for keyword[0], then all cities for keyword[1], etc.
    schedule.city_index = ci + 1
    if schedule.city_index >= len(cities):
        schedule.city_index = 0
        schedule.keyword_index = (ki + 1) % len(keywords)
    
    # Combine keyword + city if city not already in keyword
    if city and city.lower() not in keyword.lower():
        full_keyword = f"{keyword} {city}"
    else:
        full_keyword = keyword
    
    return full_keyword, city


def _send_review_email(app, schedule, client, blog_post):
    """Send the review email to the client with the blog preview and review link"""
    try:
        from app.services.email_service import get_email_service
        email_service = get_email_service()
        
        # Determine recipient
        to_email = schedule.client_email or client.email
        if not to_email:
            logger.warning(f"[CONTENT-SCHED] No email for client {client.business_name}, skipping email")
            return
        
        # Build review URL
        base_url = app.config.get('BASE_URL', '') or _get_base_url(app)
        review_url = f"{base_url}/review/{blog_post.review_token}"
        
        # Build email
        subject = f"New Blog Post Ready for Review: {blog_post.title}"
        
        # Fact-check badge
        fc_score = blog_post.fact_check_score
        if fc_score is not None:
            if fc_score >= 80:
                fc_badge = f'<span style="background:#059669;color:white;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">✓ Accuracy: {fc_score}/100</span>'
            elif fc_score >= 60:
                fc_badge = f'<span style="background:#d97706;color:white;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">⚠ Accuracy: {fc_score}/100</span>'
            else:
                fc_badge = f'<span style="background:#dc2626;color:white;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">⚠ Accuracy: {fc_score}/100</span>'
        else:
            fc_badge = ''
        
        # Plain text excerpt
        import re
        plain_body = re.sub(r'<[^>]+>', ' ', blog_post.body or '')
        plain_body = re.sub(r'\s+', ' ', plain_body).strip()
        excerpt = plain_body[:300] + '...' if len(plain_body) > 300 else plain_body
        
        html_body = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:22px;">New Blog Post Ready</h1>
                <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">for {client.business_name}</p>
            </div>
            
            <!-- Content -->
            <div style="padding:32px;">
                <h2 style="margin:0 0 8px;font-size:20px;color:#1f2937;">{blog_post.title}</h2>
                
                <div style="margin:12px 0 20px;display:flex;gap:8px;flex-wrap:wrap;">
                    <span style="background:#ede9fe;color:#7c3aed;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">{blog_post.word_count} words</span>
                    <span style="background:#ecfdf5;color:#059669;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">SEO: {blog_post.seo_score}/100</span>
                    {fc_badge}
                </div>
                
                <div style="background:#f9fafb;border-radius:8px;padding:16px;margin:16px 0;border-left:4px solid #6366f1;">
                    <p style="margin:0;color:#4b5563;font-size:14px;line-height:1.6;">{excerpt}</p>
                </div>
                
                <p style="color:#6b7280;font-size:14px;line-height:1.5;margin:16px 0;">
                    Please review this blog post and make any edits you'd like. You can update the title, content, 
                    add a featured image, manage tags, and leave comments.
                </p>
                
                <!-- CTA Button -->
                <div style="text-align:center;margin:28px 0;">
                    <a href="{review_url}" 
                       style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;padding:14px 40px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">
                        Review &amp; Edit Blog Post
                    </a>
                </div>
                
                <p style="color:#9ca3af;font-size:12px;text-align:center;margin:20px 0 0;">
                    Or copy this link: {review_url}
                </p>
            </div>
            
            <!-- Footer -->
            <div style="background:#f9fafb;padding:20px 32px;text-align:center;border-top:1px solid #e5e7eb;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    This is an automated blog post from your content schedule. 
                    Sent by Karma Marketing + Media's Marketing Platform.
                </p>
            </div>
        </div>
        """
        
        # Send email
        cc = [e.strip() for e in (schedule.cc_emails or '').split(',') if e.strip()]
        success = email_service.send_simple(
            to=to_email,
            subject=subject,
            body=html_body,
            html=True,
            cc=cc if cc else None
        )
        
        if success:
            logger.info(f"[CONTENT-SCHED] Review email sent to {to_email} for blog {blog_post.id}")
        else:
            logger.warning(f"[CONTENT-SCHED] Failed to send review email to {to_email}")
            
    except Exception as e:
        logger.error(f"[CONTENT-SCHED] Email error: {e}")


def _get_base_url(app):
    """Get the base URL for the app"""
    import os
    # Try common env vars
    for var in ['BASE_URL', 'APP_URL', 'RENDER_EXTERNAL_URL']:
        url = os.environ.get(var, '')
        if url:
            return url.rstrip('/')
    # Fallback
    return 'https://mcp.karmamarketingandmedia.com'
