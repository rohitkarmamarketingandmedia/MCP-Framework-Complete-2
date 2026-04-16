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
    
    # Competitor crawl check - runs every hour to pick up competitors that are due
    scheduler.add_job(
        func=run_competitor_crawl,
        trigger=CronTrigger(minute=0),  # Every hour on the hour
        id='hourly_competitor_crawl_check',
        name='Hourly Competitor Crawl Check',
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
    
    # Content due today notification at 7 AM
    scheduler.add_job(
        func=send_content_due_notifications,
        trigger=CronTrigger(hour=7, minute=0),
        id='content_due_notifications',
        name='Content Due Today Notifications',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Process daily notification digests at 8 AM
    scheduler.add_job(
        func=process_notification_digests,
        trigger=CronTrigger(hour=8, minute=0),
        id='daily_notification_digest',
        name='Daily Notification Digest',
        replace_existing=True,
        kwargs={'app': app, 'frequency': 'daily'}
    )
    
    # Process weekly notification digests on Monday at 8 AM
    scheduler.add_job(
        func=process_notification_digests,
        trigger=CronTrigger(day_of_week='mon', hour=8, minute=0),
        id='weekly_notification_digest',
        name='Weekly Notification Digest',
        replace_existing=True,
        kwargs={'app': app, 'frequency': 'weekly'}
    )
    
    # Send 3-day client reports (Mon, Thu at 9 AM)
    scheduler.add_job(
        func=send_client_reports,
        trigger=CronTrigger(day_of_week='mon,thu', hour=9, minute=0),
        id='client_3day_reports',
        name='3-Day Client Reports',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Auto-generate review responses every 2 hours
    scheduler.add_job(
        func=auto_generate_review_responses,
        trigger=IntervalTrigger(hours=2),
        id='auto_review_responses',
        name='Auto-Generate Review Responses',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Daily intelligence ingestion at 6 AM (after rank check at 5 AM)
    scheduler.add_job(
        func=run_intelligence_pipeline,
        trigger=CronTrigger(hour=6, minute=0),
        id='daily_intelligence_pipeline',
        name='Daily Intelligence Pipeline',
        replace_existing=True,
        kwargs={'app': app}
    )
    
    # Content auto-generation - runs every hour to check for due schedules
    from app.services.content_scheduler_service import run_content_schedules
    scheduler.add_job(
        func=run_content_schedules,
        trigger=CronTrigger(minute=15),  # Every hour at :15
        id='content_auto_generation',
        name='Auto-Generate Scheduled Blog Content',
        replace_existing=True,
        kwargs={'app': app}
    )

    # Weekly Google Search Console indexing scan (Mon 3 AM, light traffic)
    scheduler.add_job(
        func=run_indexing_weekly_scan,
        trigger=CronTrigger(day_of_week='mon', hour=3, minute=0),
        id='weekly_indexing_scan',
        name='Weekly GSC Indexing Scan',
        replace_existing=True,
        kwargs={'app': app}
    )

    logger.info("Scheduled jobs added: competitor_crawl(hourly), rank_check(5AM), intelligence(6AM), auto_publish(5min), alert_digest(hourly), daily_summary(8AM), content_due(7AM), digests(8AM), 3day_reports(Mon/Thu 9AM), review_responses(2hr), indexing_scan(Mon 3AM)")


def run_indexing_weekly_scan(app):
    """Weekly GSC indexing scan across all clients with indexing enabled."""
    try:
        from app.services.indexing_service import run_weekly_scan_all_clients
        result = run_weekly_scan_all_clients(app=app)
        logger.info(f'[indexing] weekly scan result: {result}')
    except Exception as e:
        logger.exception(f'[indexing] weekly scan failed: {e}')


def run_competitor_crawl(app):
    """Crawl competitors that are due based on their schedule"""
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBClient, DBCompetitor
        from app.services.competitor_monitoring_service import CompetitorMonitoringService
        
        logger.info("Starting scheduled competitor crawl check...")
        
        now = datetime.utcnow()
        
        # Only crawl competitors that are due (next_crawl_at <= now)
        due_competitors = DBCompetitor.query.filter(
            DBCompetitor.is_active == True,
            DBCompetitor.crawl_frequency != 'manual',
            DBCompetitor.next_crawl_at != None,
            DBCompetitor.next_crawl_at <= now
        ).all()
        
        if not due_competitors:
            logger.info("No competitors due for crawl.")
            return
        
        logger.info(f"Found {len(due_competitors)} competitors due for crawl.")
        total_new_pages = 0
        
        from app.models.db_models import DBCompetitorPage
        import uuid as _uuid

        service = CompetitorMonitoringService()  # Singleton — no args needed

        for competitor in due_competitors:
            try:
                # Get known pages for this competitor from DB
                known_db_pages = DBCompetitorPage.query.filter_by(competitor_id=competitor.id).all()
                known_pages = [{'url': p.url, 'lastmod': p.last_checked_at.isoformat() if p.last_checked_at else None} for p in known_db_pages]

                # Detect new content by comparing current sitemap with known pages
                new_pages_list, updated_pages_list = service.detect_new_content(
                    competitor.domain, known_pages, competitor.last_crawl_at
                )

                new_page_count = len(new_pages_list)
                total_new_pages += new_page_count

                # Save new pages to DB
                new_page_ids = []
                for page in new_pages_list:
                    page_id = f"cpage_{_uuid.uuid4().hex[:12]}"
                    db_page = DBCompetitorPage(
                        competitor_id=competitor.id,
                        client_id=competitor.client_id,
                        url=page.get('url', ''),
                        title=page.get('title', ''),
                    )
                    db_page.id = page_id
                    db.session.add(db_page)
                    new_page_ids.append(page_id)

                # Update known pages count
                competitor.known_pages_count = len(known_db_pages) + new_page_count
                competitor.new_pages_detected = new_page_count

                if new_page_count > 0:
                    client = DBClient.query.get(competitor.client_id)
                    client_name = client.business_name if client else competitor.client_id
                    logger.info(f"Found {new_page_count} new pages for {competitor.name} (client: {client_name})")

                    # Send alert emails
                    try:
                        from app.services.email_service import email_service
                        from app.models.db_models import DBUser

                        if client:
                            recipients = set()
                            if client.email:
                                recipients.add(client.email)

                            # Notify admin/manager users with access
                            admins = DBUser.query.filter(DBUser.role.in_(['admin', 'manager']), DBUser.is_active == True).all()
                            for admin in admins:
                                if admin.email and admin.has_access_to_client(client.id):
                                    recipients.add(admin.email)

                            for recipient in recipients:
                                try:
                                    email_service.send_competitor_alert(
                                        to=recipient,
                                        client_name=client_name,
                                        competitor_name=competitor.name or competitor.domain,
                                        new_pages=new_page_count
                                    )
                                    logger.info(f"Sent crawl alert to {recipient}")
                                except Exception as email_err:
                                    logger.warning(f"Failed to send crawl alert to {recipient}: {email_err}")
                    except Exception as alert_err:
                        logger.warning(f"Could not send crawl alerts: {alert_err}")

                    # Auto-generate counter content for new pages
                    _auto_generate_counter_content(competitor.client_id, competitor.id, new_page_ids)
                
                # Update last_crawl_at and compute next_crawl_at
                competitor.last_crawl_at = now
                crawl_hour = competitor.crawl_hour if competitor.crawl_hour is not None else 3
                crawl_day = competitor.crawl_day if competitor.crawl_day is not None else 0
                
                if competitor.crawl_frequency == 'daily':
                    next_run = now.replace(hour=crawl_hour, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    competitor.next_crawl_at = next_run
                elif competitor.crawl_frequency == 'weekly':
                    days_ahead = crawl_day - now.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    next_run = now.replace(hour=crawl_hour, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
                    competitor.next_crawl_at = next_run
                    
            except Exception as e:
                logger.error(f"Error crawling {competitor.domain}: {e}")
        
        db.session.commit()
        logger.info(f"Competitor crawl complete. Found {total_new_pages} new pages across {len(due_competitors)} competitors.")
        # Per-competitor alert emails are already sent inside the loop above.
        # The global _notify_new_competitor_content call has been removed to prevent duplicate emails.


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
    """
    Daily SERP check for all clients using tracked keywords.
    Uses rank_tracking_service.run_serp_check() which:
      1. Reads tracked keywords from DB (imported from SEMrush Position Tracking)
      2. Calls SEMrush API for current positions
      3. Saves rank snapshots to rank_history table
    """
    with app.app_context():
        from app.models.db_models import DBClient
        from app.services.rank_tracking_service import rank_tracking_service

        logger.info("Starting scheduled rank check (tracked keywords)...")

        clients = DBClient.query.filter_by(is_active=True).all()
        total_checked = 0
        total_drops = 0

        for client in clients:
            try:
                domain = client.website_url or client.business_name
                if not domain:
                    logger.debug(f"No domain for {client.business_name}, skipping")
                    continue

                # Run SERP check for BOTH devices — data stays separate
                for device in ('desktop', 'mobile'):
                    result = rank_tracking_service.run_serp_check(
                        client_id=client.id,
                        domain=domain,
                        device=device,
                        force_refresh=True  # Scheduled check always hits the API
                    )

                    if result.get('error'):
                        logger.warning(f"Rank check error ({device}) for {client.business_name}: {result['error']}")
                        continue

                    kw_count = result.get('checked', 0)
                    total_checked += kw_count
                    logger.info(f"Rank check ({device}) complete for {client.business_name}: {kw_count} keywords")

                # Trigger intelligence automation rank drop detection
                try:
                    from app.services.intelligence_automation_service import intelligence_automation
                    alerts = intelligence_automation.check_rank_drops(client.id)
                    if alerts:
                        total_drops += len(alerts)
                        logger.info(f"Rank drop alerts for {client.business_name}: {len(alerts)}")
                except Exception as e:
                    logger.debug(f"Intelligence automation not available: {e}")

            except Exception as e:
                logger.error(f"Error checking ranks for {client.business_name}: {e}")

        logger.info(f"Rank check complete: {total_checked} keywords across {len(clients)} clients, {total_drops} drop alerts")


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


# Track last time a competitor content notification was sent (in-memory cooldown)
_last_competitor_notify_at: datetime = None
_COMPETITOR_NOTIFY_COOLDOWN_HOURS = 6


def _notify_new_competitor_content(count):
    """Send notification about new competitor content.
    Enforces a cooldown so the same alert cannot be sent more than once
    every _COMPETITOR_NOTIFY_COOLDOWN_HOURS hours, preventing email spam
    if the job is triggered multiple times in quick succession.
    """
    global _last_competitor_notify_at

    now = datetime.utcnow()
    if _last_competitor_notify_at is not None:
        hours_since = (now - _last_competitor_notify_at).total_seconds() / 3600
        if hours_since < _COMPETITOR_NOTIFY_COOLDOWN_HOURS:
            logger.info(
                f"Competitor notify skipped — last sent {hours_since:.1f}h ago "
                f"(cooldown: {_COMPETITOR_NOTIFY_COOLDOWN_HOURS}h)"
            )
            return

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

    _last_competitor_notify_at = now
    logger.info(f"Competitor content notification sent to admins (count={count})")


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
                        # Send failure notification
                        send_publish_notification(
                            app, 'blog', blog.id, client.id, 
                            success=False, 
                            error_message=test.get('message', 'Connection failed')
                        )
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
                        # Store the URL for notifications
                        blog.published_url = f"{client.wordpress_url}?p={result.get('post_id')}"
                        published_blogs += 1
                        logger.info(f"Auto-published blog '{blog.title}' to WordPress (ID: {result.get('post_id')})")
                        
                        # Send success notification
                        send_publish_notification(app, 'blog', blog.id, client.id, success=True)
                    else:
                        errors.append(f"Blog '{blog.title}': {result.get('message')}")
                        send_publish_notification(
                            app, 'blog', blog.id, client.id,
                            success=False,
                            error_message=result.get('message', 'Unknown error')
                        )
                else:
                    # No WordPress - just mark as published
                    blog.status = 'published'
                    blog.published_at = now
                    published_blogs += 1
                    logger.info(f"Auto-published blog '{blog.title}' (no WordPress)")
                    
                    # Send notification
                    send_publish_notification(app, 'blog', blog.id, client.id, success=True)
                    
            except Exception as e:
                logger.error(f"Error auto-publishing blog {blog.id}: {e}")
                errors.append(f"Blog '{blog.title}': {str(e)}")
        
        # Find scheduled social posts that are due
        due_social = DBSocialPost.query.filter(
            DBSocialPost.status == 'scheduled',
            DBSocialPost.scheduled_for <= now,
            DBSocialPost.scheduled_for.isnot(None)
        ).all()
        
        from app.services.social_service import SocialService
        social_service = SocialService()
        
        for post in due_social:
            try:
                client = DBClient.query.get(post.client_id)
                if not client:
                    post.status = 'published'
                    post.published_at = now
                    published_social += 1
                    continue
                
                platform = post.platform.lower() if post.platform else ''
                published_to_platform = False
                platform_post_id = None
                
                # Publish to GBP
                if platform in ['gbp', 'google', 'google_business', 'all']:
                    if client.gbp_location_id and client.gbp_access_token:
                        result = social_service.publish_to_gbp(
                            location_id=client.gbp_location_id,
                            text=post.content,
                            image_url=post.image_url,
                            cta_type=post.cta_type if hasattr(post, 'cta_type') else None,
                            cta_url=post.cta_url if hasattr(post, 'cta_url') else None
                        )
                        if result.get('success'):
                            platform_post_id = result.get('post_id')
                            published_to_platform = True
                            logger.info(f"Published to GBP: {post.id} -> {platform_post_id}")
                        elif not result.get('mock'):
                            errors.append(f"Social {post.id} GBP: {result.get('error')}")
                
                # Publish to Facebook
                if platform in ['facebook', 'fb', 'all']:
                    if client.facebook_page_id and client.facebook_access_token:
                        result = social_service.publish_to_facebook(
                            page_id=client.facebook_page_id,
                            access_token=client.facebook_access_token,
                            message=post.content,
                            link=post.link_url if hasattr(post, 'link_url') else None,
                            image_url=post.image_url
                        )
                        if result.get('success'):
                            platform_post_id = result.get('post_id')
                            published_to_platform = True
                            logger.info(f"Published to Facebook: {post.id} -> {platform_post_id}")
                        elif not result.get('mock'):
                            errors.append(f"Social {post.id} Facebook: {result.get('error')}")
                
                # Publish to Instagram
                if platform in ['instagram', 'ig', 'all']:
                    if client.instagram_account_id and client.instagram_access_token and post.image_url:
                        result = social_service.publish_to_instagram(
                            account_id=client.instagram_account_id,
                            access_token=client.instagram_access_token,
                            image_url=post.image_url,
                            caption=post.content
                        )
                        if result.get('success'):
                            platform_post_id = result.get('post_id')
                            published_to_platform = True
                            logger.info(f"Published to Instagram: {post.id} -> {platform_post_id}")
                        elif not result.get('mock'):
                            errors.append(f"Social {post.id} Instagram: {result.get('error')}")
                
                # Publish to LinkedIn
                if platform in ['linkedin', 'li', 'all']:
                    if client.linkedin_org_id and client.linkedin_access_token:
                        result = social_service.publish_to_linkedin(
                            organization_id=client.linkedin_org_id,
                            access_token=client.linkedin_access_token,
                            text=post.content,
                            link=post.link_url if hasattr(post, 'link_url') else None
                        )
                        if result.get('success'):
                            platform_post_id = result.get('post_id')
                            published_to_platform = True
                            logger.info(f"Published to LinkedIn: {post.id} -> {platform_post_id}")
                        elif not result.get('mock'):
                            errors.append(f"Social {post.id} LinkedIn: {result.get('error')}")
                
                # Mark as published
                post.status = 'published'
                post.published_at = now
                if platform_post_id:
                    post.platform_post_id = platform_post_id
                published_social += 1
                
                if published_to_platform:
                    logger.info(f"Auto-published social post {post.id} to {platform}")
                else:
                    logger.info(f"Auto-published social post {post.id} (no platform credentials)")
                
                # Send success notification
                send_publish_notification(app, 'social', post.id, client.id, success=True)
                
            except Exception as e:
                logger.error(f"Error auto-publishing social {post.id}: {e}")
                errors.append(f"Social {post.id}: {str(e)}")
                # Send failure notification
                try:
                    send_publish_notification(
                        app, 'social', post.id, post.client_id,
                        success=False,
                        error_message=str(e)
                    )
                except Exception as e:
                    pass  # Don't fail if notification fails
        
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


def send_content_due_notifications(app):
    """
    Send notifications for content scheduled to publish today
    Runs at 7 AM to give agencies time to prepare
    """
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBBlogPost, DBSocialPost, DBClient, DBUser
        from app.services.notification_service import get_notification_service
        
        notification_service = get_notification_service()
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        today_end = today_start + timedelta(days=1)
        
        logger.info(f"Checking for content due today: {today_start.date()}")
        
        # Get all due blogs
        due_blogs = DBBlogPost.query.filter(
            DBBlogPost.status == 'scheduled',
            DBBlogPost.scheduled_for >= today_start,
            DBBlogPost.scheduled_for < today_end
        ).all()
        
        # Get all due social posts
        due_social = DBSocialPost.query.filter(
            DBSocialPost.status == 'scheduled',
            DBSocialPost.scheduled_for >= today_start,
            DBSocialPost.scheduled_for < today_end
        ).all()
        
        if not due_blogs and not due_social:
            logger.info("No content due today")
            return
        
        # Group by client
        content_by_client = {}
        for blog in due_blogs:
            if blog.client_id not in content_by_client:
                content_by_client[blog.client_id] = []
            client = DBClient.query.get(blog.client_id)
            content_by_client[blog.client_id].append({
                'title': blog.title,
                'type': 'blog',
                'client_name': client.business_name if client else 'Unknown',
                'scheduled_for': blog.scheduled_for.strftime('%I:%M %p') if blog.scheduled_for else 'TBD'
            })
        
        for post in due_social:
            if post.client_id not in content_by_client:
                content_by_client[post.client_id] = []
            client = DBClient.query.get(post.client_id)
            content_by_client[post.client_id].append({
                'title': f"{post.platform.title()} post",
                'type': 'social',
                'client_name': client.business_name if client else 'Unknown',
                'scheduled_for': post.scheduled_for.strftime('%I:%M %p') if post.scheduled_for else 'TBD'
            })
        
        # Get admin users to notify
        admins = DBUser.query.filter_by(role='admin', is_active=True).all()
        
        for admin in admins:
            # Combine all content for this admin
            all_content = []
            for client_id, items in content_by_client.items():
                all_content.extend(items)
            
            if all_content:
                notification_service.notify_content_due_today(
                    user_id=admin.id,
                    content_items=all_content
                )
        
        logger.info(f"Sent content due notifications: {len(due_blogs)} blogs, {len(due_social)} social posts")


def process_notification_digests(app, frequency='daily'):
    """
    Process notification digests for users who prefer batched notifications
    
    Args:
        app: Flask application
        frequency: 'daily' or 'weekly'
    """
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBNotificationPreferences, DBUser
        from app.services.notification_service import get_notification_service
        
        notification_service = get_notification_service()
        
        # Find users who prefer this digest frequency
        prefs = DBNotificationPreferences.query.filter_by(
            email_enabled=True,
            digest_frequency=frequency
        ).all()
        
        processed = 0
        for pref in prefs:
            try:
                user = DBUser.query.get(pref.user_id)
                if user and user.is_active:
                    success = notification_service.process_digest_queue(
                        user_id=pref.user_id,
                        frequency=frequency
                    )
                    if success:
                        processed += 1
            except Exception as e:
                logger.error(f"Error processing digest for user {pref.user_id}: {e}")
        
        logger.info(f"Processed {frequency} notification digests for {processed} users")


def send_publish_notification(app, content_type, content_id, client_id, success, error_message=None):
    """
    Helper function to send publish notifications
    Called from auto-publish when content is published or fails
    
    Args:
        app: Flask application
        content_type: 'blog', 'social', 'wordpress'
        content_id: ID of the content
        client_id: Client ID
        success: Whether publishing succeeded
        error_message: Error message if failed
    """
    with app.app_context():
        from app.models.db_models import DBBlogPost, DBSocialPost, DBClient, DBUser
        from app.services.notification_service import get_notification_service
        
        notification_service = get_notification_service()
        
        client = DBClient.query.get(client_id)
        client_name = client.business_name if client else 'Unknown'
        
        # Get admin users
        admins = DBUser.query.filter_by(role='admin', is_active=True).all()
        
        for admin in admins:
            if content_type == 'blog':
                blog = DBBlogPost.query.get(content_id)
                if not blog:
                    continue
                
                if success:
                    notification_service.notify_content_published(
                        user_id=admin.id,
                        client_name=client_name,
                        content_title=blog.title,
                        content_type='blog',
                        published_url=blog.published_url,
                        content_id=content_id,
                        client_id=client_id
                    )
                    
                    # Also send WordPress-specific notification if it went to WP
                    if blog.wordpress_post_id and blog.published_url:
                        notification_service.notify_wordpress_published(
                            user_id=admin.id,
                            client_name=client_name,
                            post_title=blog.title,
                            post_url=blog.published_url,
                            content_id=content_id,
                            client_id=client_id
                        )
                else:
                    notification_service.notify_wordpress_failed(
                        user_id=admin.id,
                        client_name=client_name,
                        post_title=blog.title if blog else 'Unknown',
                        error_message=error_message or 'Publishing failed',
                        content_id=content_id,
                        client_id=client_id
                    )
            
            elif content_type == 'social':
                post = DBSocialPost.query.get(content_id)
                if not post:
                    continue
                
                if success:
                    notification_service.notify_social_published(
                        user_id=admin.id,
                        client_name=client_name,
                        platform=post.platform or 'social',
                        content_preview=post.content[:100] if post.content else '',
                        post_id=content_id,
                        client_id=client_id
                    )
                else:
                    notification_service.notify_social_failed(
                        user_id=admin.id,
                        client_name=client_name,
                        platform=post.platform or 'social',
                        error_message=error_message or 'Publishing failed',
                        post_id=content_id,
                        client_id=client_id
                    )


def send_client_reports(app):
    """
    Send 3-day snapshot reports to all active clients
    
    Runs Monday and Thursday at 9 AM
    """
    with app.app_context():
        try:
            from app.services.client_report_service import get_client_report_service
            
            report_service = get_client_report_service()
            results = report_service.send_all_3day_reports()
            
            logger.info(f"3-day client reports sent: {results['sent']} sent, {results['failed']} failed")
            
        except Exception as e:
            logger.error(f"Error sending client reports: {e}")


def auto_generate_review_responses(app):
    """
    Auto-generate AI responses for pending reviews (no response yet)
    
    Runs every 2 hours
    """
    with app.app_context():
        try:
            from app.services.review_service import get_review_service
            from app.models.db_models import DBReview
            
            review_service = get_review_service()
            
            # Find reviews without responses
            pending_reviews = DBReview.query.filter(
                DBReview.response_text.is_(None),
                DBReview.suggested_response.is_(None)
            ).limit(20).all()
            
            generated = 0
            failed = 0
            
            for review in pending_reviews:
                try:
                    result = review_service.generate_response(review.id)
                    if result.get('suggested_response'):
                        generated += 1
                        logger.debug(f"Generated response for review {review.id}")
                except Exception as e:
                    failed += 1
                    logger.warning(f"Failed to generate response for review {review.id}: {e}")
            
            if generated > 0 or failed > 0:
                logger.info(f"Auto-generated review responses: {generated} success, {failed} failed")
            
        except Exception as e:
            logger.error(f"Error in auto-generate review responses: {e}")

def run_intelligence_pipeline(app):
    """
    Daily intelligence pipeline — runs after rank check.
    For each active client:
    1. Ingest data from all 4 sources (calls, chat, reviews, forms)
    2. Update frequency windows & detect trending topics
    3. Generate content suggestions
    4. Rank drops already handled by run_rank_check
    
    Runs daily at 6 AM
    """
    with app.app_context():
        from app.database import db
        from app.models.db_models import DBClient
        
        logger.info("Starting daily intelligence pipeline...")
        
        clients = DBClient.query.filter_by(is_active=True).all()
        total_insights = 0
        total_suggestions = 0
        
        for client in clients:
            try:
                from app.services.intelligence_automation_service import intelligence_automation
                
                # 1. Ingest from chat
                try:
                    from app.models.db_models import DBChatConversation, DBChatMessage
                    from datetime import timedelta
                    
                    yesterday = datetime.utcnow() - timedelta(days=1)
                    conversations = DBChatConversation.query.filter(
                        DBChatConversation.client_id == client.id,
                        DBChatConversation.created_at >= yesterday,
                    ).all()
                    
                    if conversations:
                        conv_data = []
                        for conv in conversations:
                            messages = DBChatMessage.query.filter_by(conversation_id=conv.id).all()
                            conv_data.append({
                                'id': conv.id,
                                'messages': [{'role': m.role, 'content': m.content} for m in messages]
                            })
                        result = intelligence_automation.ingest_from_chat(client.id, conv_data)
                        total_insights += result.get('stored', 0) + result.get('updated', 0)
                except Exception as e:
                    logger.debug(f"Chat ingestion error for {client.business_name}: {e}")
                
                # 2. Ingest from reviews
                try:
                    from app.models.db_models import DBReview
                    reviews = DBReview.query.filter_by(client_id=client.id).all()
                    if reviews:
                        review_data = [{'text': r.text or getattr(r, 'comment', '') or '', 'rating': r.rating or getattr(r, 'star_rating', 0) or 0} for r in reviews]
                        result = intelligence_automation.ingest_from_reviews(client.id, review_data)
                        total_insights += result.get('stored', 0) + result.get('updated', 0)
                except Exception as e:
                    logger.debug(f"Review ingestion error for {client.business_name}: {e}")
                
                # 3. Ingest from call intelligence (if available)
                try:
                    from app.services.interaction_intelligence_service import interaction_intelligence_service
                    call_data = interaction_intelligence_service.analyze_interactions(
                        client_id=client.id, days=1, force_refresh=False
                    )
                    if call_data and not call_data.get('error'):
                        result = intelligence_automation.ingest_from_calls(client.id, call_data)
                        total_insights += result.get('stored', 0) + result.get('updated', 0)
                except Exception as e:
                    logger.debug(f"Call ingestion error for {client.business_name}: {e}")
                
                # 4. Update frequency windows & detect trending
                intelligence_automation.update_frequency_windows(client.id)
                trending = intelligence_automation.detect_trending_topics(client.id)
                
                # 5. Generate suggestions
                suggestions = intelligence_automation.generate_suggestions(client.id)
                generated = suggestions.get('total_generated', 0)
                total_suggestions += generated
                
                if generated > 0:
                    logger.info(f"Intelligence: {client.business_name} — {generated} new suggestions")
                
            except Exception as e:
                logger.error(f"Intelligence pipeline error for {client.business_name}: {e}")
        
        logger.info(f"Intelligence pipeline complete: {total_insights} insights, {total_suggestions} suggestions across {len(clients)} clients")
