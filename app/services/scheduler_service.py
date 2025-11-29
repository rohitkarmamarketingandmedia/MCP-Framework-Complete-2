"""
MCP Framework - Background Scheduler
Runs automated tasks on schedule without Redis
Uses APScheduler for in-process job scheduling
"""
import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def init_scheduler(app):
    """Initialize the background scheduler with the Flask app context"""
    global scheduler
    
    if scheduler is not None:
        logger.info("Scheduler already initialized")
        return scheduler
    
    scheduler = BackgroundScheduler(
        job_defaults={
            'coalesce': True,  # Combine missed runs into one
            'max_instances': 1,  # Only one instance of each job at a time
            'misfire_grace_time': 3600  # Allow 1 hour grace for missed jobs
        }
    )
    
    # Store app reference for context
    scheduler.app = app
    
    # Add scheduled jobs
    _add_scheduled_jobs(app)
    
    # Start scheduler
    scheduler.start()
    logger.info("Background scheduler started")
    
    return scheduler


def _add_scheduled_jobs(app):
    """Add all scheduled jobs"""
    
    # Daily competitor crawl at 3 AM
    scheduler.add_job(
        func=run_competitor_crawl,
        trigger=CronTrigger(hour=3, minute=0),
        id='daily_competitor_crawl',
        name='Daily Competitor Crawl',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Daily rank check at 5 AM
    scheduler.add_job(
        func=run_rank_check,
        trigger=CronTrigger(hour=5, minute=0),
        id='daily_rank_check',
        name='Daily Rank Check',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Auto-publish scheduled content every 5 minutes
    scheduler.add_job(
        func=run_auto_publish,
        trigger=IntervalTrigger(minutes=5),
        id='auto_publish_content',
        name='Auto-Publish Scheduled Content',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Hourly alert digest (only sends if there are alerts)
    scheduler.add_job(
        func=send_alert_digest,
        trigger=CronTrigger(minute=0),  # Every hour on the hour
        id='hourly_alert_digest',
        name='Hourly Alert Digest',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Daily summary email at 8 AM
    scheduler.add_job(
        func=send_daily_summary,
        trigger=CronTrigger(hour=8, minute=0),
        id='daily_summary_email',
        name='Daily Summary Email',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    logger.info("Scheduled jobs added: competitor_crawl(3AM), rank_check(5AM), auto_publish(5min), alert_digest(hourly), daily_summary(8AM)")


def run_competitor_crawl(app):
    """Crawl all competitors for all active clients"""
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBClient, DBCompetitor
        from app.services.competitor_monitoring_service import CompetitorMonitoringService
        
        logger.info("Starting scheduled competitor crawl...")
        
        clients = DBClient.query.filter_by(is_active=True).all()
        total_new_pages = 0
        
        for client in clients:
            competitors = DBCompetitor.query.filter_by(
                client_id=client.id,
                is_active=True
            ).all()
            
            for competitor in competitors:
                try:
                    service = CompetitorMonitoringService(client.id)
                    result = service.crawl_competitor(competitor.id)
                    new_pages = result.get('new_pages', 0)
                    total_new_pages += new_pages
                    
                    if new_pages > 0:
                        logger.info(f"Found {new_pages} new pages for {competitor.name} (client: {client.business_name})")
                        
                        # Auto-generate counter content for new pages
                        _auto_generate_counter_content(client.id, competitor.id, result.get('new_page_ids', []))
                        
                except Exception as e:
                    logger.error(f"Error crawling {competitor.domain}: {e}")
        
        logger.info(f"Competitor crawl complete. Found {total_new_pages} new pages across all clients.")
        
        # Send notification if new content found
        if total_new_pages > 0:
            _notify_new_competitor_content(total_new_pages)


def _auto_generate_counter_content(client_id, competitor_id, new_page_ids):
    """Automatically generate counter-content for new competitor pages"""
    from app.models.db_models import DBCompetitorPage, DBContentQueue
    from app.services.ai_service import AIService
    from app.services.seo_scoring_engine import SEOScoringEngine
    from app.database import db
    
    for page_id in new_page_ids:
        try:
            page = DBCompetitorPage.query.get(page_id)
            if not page:
                continue
            
            # Generate counter content
            ai = AIService()
            
            # Extract keyword from competitor page title/URL
            keyword = _extract_keyword(page.title, page.url)
            
            # Generate better content
            content = ai.generate_blog_post(
                keyword=keyword,
                client_id=client_id,
                competitor_content={
                    'title': page.title,
                    'word_count': page.word_count,
                    'headings': page.headings
                }
            )
            
            if content:
                # Score both contents
                scorer = SEOScoringEngine()
                our_score = scorer.score_content(content, keyword)
                their_score = page.seo_score or 50
                
                # Add to content queue
                queue_item = DBContentQueue(
                    client_id=client_id,
                    trigger_type='competitor_post',
                    trigger_source_id=page_id,
                    title=content.get('title', f'Response to: {page.title}'),
                    primary_keyword=keyword,
                    content=content.get('content', ''),
                    word_count=content.get('word_count', 0),
                    our_seo_score=our_score.get('total_score', 0),
                    competitor_seo_score=their_score,
                    status='pending'
                )
                db.session.add(queue_item)
                
                # Mark page as countered
                page.was_countered = True
                
                db.session.commit()
                logger.info(f"Generated counter-content for: {page.title}")
                
        except Exception as e:
            logger.error(f"Error generating counter-content for page {page_id}: {e}")


def _extract_keyword(title, url):
    """Extract likely keyword from title or URL"""
    if title:
        # Remove common words, take first meaningful phrase
        title_clean = title.lower()
        for remove in ['how to', 'guide', 'tips', '2024', '2025', '|', '-', ':']:
            title_clean = title_clean.replace(remove, ' ')
        words = [w.strip() for w in title_clean.split() if len(w) > 2]
        return ' '.join(words[:4])
    return url.split('/')[-1].replace('-', ' ')


def run_rank_check(app):
    """Check rankings for all clients"""
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBClient
        from app.services.rank_tracking_service import RankTrackingService
        
        logger.info("Starting scheduled rank check...")
        
        clients = DBClient.query.filter_by(is_active=True).all()
        
        for client in clients:
            try:
                service = RankTrackingService(client.id)
                result = service.check_all_rankings()
                logger.info(f"Rank check complete for {client.business_name}: {result.get('keywords_checked', 0)} keywords")
            except Exception as e:
                logger.error(f"Error checking ranks for {client.business_name}: {e}")
        
        logger.info("Rank check complete for all clients")


def send_alert_digest(app):
    """Send digest of unread alerts if any exist"""
    with app.app_context():
        from app.models.db_models import DBAlert, DBUser
        from app.services.email_service import EmailService
        from datetime import datetime, timedelta
        
        # Get alerts from last hour that haven't been notified
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        alerts = DBAlert.query.filter(
            DBAlert.created_at >= one_hour_ago,
            DBAlert.is_read == False,
            DBAlert.notified_at == None
        ).all()
        
        if not alerts:
            return
        
        # Group by priority
        high_priority = [a for a in alerts if a.priority == 'high']
        
        if high_priority:
            # Send immediate notification for high priority
            email = EmailService()
            admins = DBUser.query.filter_by(role='admin').all()
            
            for admin in admins:
                if admin.email:
                    email.send_alert_digest(admin.email, alerts)
            
            # Mark as notified
            for alert in alerts:
                alert.notified_at = datetime.utcnow()
            
            from app.database import db
            db.session.commit()
            
            logger.info(f"Sent alert digest with {len(alerts)} alerts")


def send_daily_summary(app):
    """Send daily summary email to admins"""
    with app.app_context():
        from app.models.db_models import DBUser, DBClient, DBRankHistory, DBContentQueue, DBAlert
        from app.services.email_service import EmailService
        from datetime import datetime, timedelta
        
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Gather stats
        summary = {
            'date': datetime.utcnow().strftime('%Y-%m-%d'),
            'total_clients': DBClient.query.filter_by(is_active=True).count(),
            'content_pending': DBContentQueue.query.filter_by(status='pending').count(),
            'content_approved': DBContentQueue.query.filter(
                DBContentQueue.approved_at >= yesterday
            ).count(),
            'ranking_improvements': DBRankHistory.query.filter(
                DBRankHistory.checked_at >= yesterday,
                DBRankHistory.change > 0
            ).count(),
            'new_alerts': DBAlert.query.filter(
                DBAlert.created_at >= yesterday
            ).count()
        }
        
        # Send to admins
        email = EmailService()
        admins = DBUser.query.filter_by(role='admin').all()
        
        for admin in admins:
            if admin.email:
                email.send_daily_summary(admin.email, summary)
        
        logger.info("Daily summary email sent")


def _notify_new_competitor_content(count):
    """Send notification about new competitor content"""
    from app.services.email_service import EmailService
    from app.models.db_models import DBUser
    
    email = EmailService()
    admins = DBUser.query.filter_by(role='admin').all()
    
    for admin in admins:
        if admin.email:
            email.send_simple(
                to=admin.email,
                subject=f"🚨 {count} New Competitor Posts Detected",
                body=f"Your competitors published {count} new pieces of content. Counter-content has been auto-generated and is waiting for your approval.\n\nLogin to review: /agency"
            )


def get_scheduler_status():
    """Get current scheduler status and job list"""
    if scheduler is None:
        return {'status': 'not_initialized', 'jobs': []}
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        })
    
    return {
        'status': 'running' if scheduler.running else 'stopped',
        'jobs': jobs
    }


def run_job_now(job_id):
    """Manually trigger a job to run immediately"""
    if scheduler is None:
        return {'error': 'Scheduler not initialized'}
    
    job = scheduler.get_job(job_id)
    if job:
        job.modify(next_run_time=datetime.now())
        return {'success': True, 'message': f'Job {job_id} triggered'}
    return {'error': f'Job {job_id} not found'}


def run_auto_publish(app):
    """
    Auto-publish scheduled content that is due
    Runs every 5 minutes to check for content where:
    - status = 'scheduled'
    - scheduled_for <= now
    - client has WordPress credentials
    """
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBBlogPost, DBSocialPost, DBClient
        from app.services.wordpress_service import WordPressService
        
        now = datetime.utcnow()
        published_blogs = 0
        published_social = 0
        errors = []
        
        logger.info(f"Auto-publish check running at {now.isoformat()}")
        
        # Find scheduled blogs that are due
        due_blogs = DBBlogPost.query.filter(
            DBBlogPost.status == 'scheduled',
            DBBlogPost.scheduled_for <= now,
            DBBlogPost.scheduled_for.isnot(None)
        ).all()
        
        for blog in due_blogs:
            try:
                client = DBClient.query.get(blog.client_id)
                if not client:
                    continue
                
                # Check if WordPress is configured
                if client.wordpress_url and client.wordpress_user and client.wordpress_app_password:
                    # Publish to WordPress
                    wp = WordPressService(
                        site_url=client.wordpress_url,
                        username=client.wordpress_user,
                        app_password=client.wordpress_app_password
                    )
                    
                    # Test connection
                    test = wp.test_connection()
                    if not test.get('success'):
                        logger.warning(f"WordPress connection failed for client {client.id}: {test.get('message')}")
                        errors.append(f"Blog '{blog.title}': WP connection failed")
                        continue
                    
                    # Prepare meta for Yoast
                    meta = {
                        'meta_title': blog.meta_title,
                        'meta_description': blog.meta_description,
                        'focus_keyword': blog.primary_keyword
                    }
                    
                    # Publish
                    if blog.wordpress_post_id:
                        result = wp.update_post(
                            post_id=blog.wordpress_post_id,
                            title=blog.title,
                            content=blog.body,
                            status='publish'
                        )
                    else:
                        result = wp.create_post(
                            title=blog.title,
                            content=blog.body,
                            status='publish',
                            excerpt=blog.meta_description,
                            meta=meta
                        )
                    
                    if result.get('success'):
                        blog.wordpress_post_id = result.get('post_id')
                        blog.status = 'published'
                        blog.published_at = now
                        published_blogs += 1
                        logger.info(f"Auto-published blog '{blog.title}' to WordPress (ID: {result.get('post_id')})")
                    else:
                        errors.append(f"Blog '{blog.title}': {result.get('message')}")
                else:
                    # No WordPress - just mark as published
                    blog.status = 'published'
                    blog.published_at = now
                    published_blogs += 1
                    logger.info(f"Auto-published blog '{blog.title}' (no WordPress)")
                    
            except Exception as e:
                logger.error(f"Error auto-publishing blog {blog.id}: {e}")
                errors.append(f"Blog '{blog.title}': {str(e)}")
        
        # Find scheduled social posts that are due
        due_social = DBSocialPost.query.filter(
            DBSocialPost.status == 'scheduled',
            DBSocialPost.scheduled_for <= now,
            DBSocialPost.scheduled_for.isnot(None)
        ).all()
        
        for post in due_social:
            try:
                # For now, just mark as published
                # TODO: Add actual social media API posting (GMB, FB, etc)
                post.status = 'published'
                post.published_at = now
                published_social += 1
                logger.info(f"Auto-published social post {post.id} ({post.platform})")
                
            except Exception as e:
                logger.error(f"Error auto-publishing social {post.id}: {e}")
                errors.append(f"Social {post.id}: {str(e)}")
        
        # Commit all changes
        if published_blogs > 0 or published_social > 0:
            db.session.commit()
        
        summary = f"Auto-publish complete: {published_blogs} blogs, {published_social} social posts"
        if errors:
            summary += f", {len(errors)} errors"
            for err in errors[:5]:  # Log first 5 errors
                logger.warning(f"  - {err}")
        
        logger.info(summary)
        
        return {
            'published_blogs': published_blogs,
            'published_social': published_social,
            'errors': errors
        }
