"""
MCP Framework - Content Schedule Routes
Schedule management, client review endpoint, and comments
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import json
import logging

from app.routes.auth import token_required, admin_required
from app.database import db
from app.models.db_models import DBBlogPost, DBClient, ContentStatus
from app.models.schedule_models import DBContentSchedule, DBContentComment

logger = logging.getLogger(__name__)

content_schedule_bp = Blueprint('content_schedule', __name__)


# ==========================================
# SCHEDULE CRUD (admin/manager only)
# ==========================================

@content_schedule_bp.route('/<client_id>', methods=['GET'])
@token_required
def get_schedule(current_user, client_id):
    """Get content schedule for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    schedule = DBContentSchedule.query.filter_by(client_id=client_id).first()
    
    if not schedule:
        return jsonify({'schedule': None, 'message': 'No schedule configured'})
    
    return jsonify({'schedule': schedule.to_dict()})


@content_schedule_bp.route('/<client_id>', methods=['PUT'])
@token_required
def upsert_schedule(current_user, client_id):
    """Create or update content schedule for a client"""
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Manager or admin access required'}), 403
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    
    schedule = DBContentSchedule.query.filter_by(client_id=client_id).first()
    
    if not schedule:
        schedule = DBContentSchedule(client_id=client_id)
        db.session.add(schedule)
    
    # Update fields
    updatable = [
        'is_active', 'blogs_per_week', 'preferred_hour',
        'target_word_count', 'include_faq', 'faq_count', 'verify_content',
        'send_to_client', 'client_email', 'cc_emails'
    ]
    
    for field in updatable:
        if field in data:
            setattr(schedule, field, data[field])
    
    # Handle preferred_days (array)
    if 'preferred_days' in data:
        days = data['preferred_days']
        if isinstance(days, list):
            # Validate days are 0-6
            valid_days = [d for d in days if isinstance(d, int) and 0 <= d <= 6]
            schedule.set_preferred_days(valid_days)
    
    # Handle keyword_queue (array of strings)
    if 'keyword_queue' in data:
        queue = data['keyword_queue']
        if isinstance(queue, list):
            schedule.keyword_queue = json.dumps(queue)
        elif queue is None:
            schedule.keyword_queue = None
    
    # Handle blogs_per_week -> auto-set preferred_days
    if 'blogs_per_week' in data and 'preferred_days' not in data:
        bpw = data['blogs_per_week']
        day_maps = {
            1: [1],           # Tuesday
            2: [0, 3],        # Monday, Thursday
            3: [0, 2, 4],     # Mon, Wed, Fri
            4: [0, 1, 3, 4],  # Mon, Tue, Thu, Fri
            5: [0, 1, 2, 3, 4],  # Mon-Fri
            6: [0, 1, 2, 3, 4, 5],
            7: [0, 1, 2, 3, 4, 5, 6],
        }
        schedule.set_preferred_days(day_maps.get(bpw, [0, 3]))
    
    # Recalculate next run
    if schedule.is_active:
        schedule.next_generation_at = schedule._calculate_next_run()
    else:
        schedule.next_generation_at = None
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'schedule': schedule.to_dict()
    })


@content_schedule_bp.route('/<client_id>', methods=['DELETE'])
@token_required
def delete_schedule(current_user, client_id):
    """Delete content schedule"""
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Manager or admin access required'}), 403
    
    schedule = DBContentSchedule.query.filter_by(client_id=client_id).first()
    if schedule:
        db.session.delete(schedule)
        db.session.commit()
    
    return jsonify({'success': True})


@content_schedule_bp.route('/<client_id>/generate-now', methods=['POST'])
@token_required
def generate_now(current_user, client_id):
    """Manually trigger a scheduled blog generation (for testing)"""
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Manager or admin access required'}), 403
    
    schedule = DBContentSchedule.query.filter_by(client_id=client_id).first()
    if not schedule:
        return jsonify({'error': 'No schedule configured for this client'}), 404
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    try:
        from app.services.content_scheduler_service import _generate_scheduled_blog
        _generate_scheduled_blog(current_app._get_current_object(), schedule, client)
        
        return jsonify({
            'success': True,
            'message': f'Blog generated for {client.business_name}',
            'last_keyword': schedule.last_keyword_used,
            'total_generated': schedule.total_generated
        })
    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)[:200]}'}), 500


@content_schedule_bp.route('/all', methods=['GET'])
@token_required
def list_all_schedules(current_user):
    """List all content schedules (admin view)"""
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Manager access required'}), 403
    
    schedules = DBContentSchedule.query.all()
    
    result = []
    for s in schedules:
        client = DBClient.query.get(s.client_id)
        item = s.to_dict()
        item['client_name'] = client.business_name if client else 'Unknown'
        result.append(item)
    
    return jsonify({'schedules': result})


# ==========================================
# SEND TO CLIENT (manual - any blog post)
# ==========================================

@content_schedule_bp.route('/send-to-client/<blog_id>', methods=['POST'])
@token_required
def send_blog_to_client(current_user, blog_id):
    """
    Send any blog post to the client for review.
    Generates a review token if needed, sends email with review link.
    
    POST /api/schedule/send-to-client/{blog_id}
    {
        "email": "client@example.com",        // required
        "cc": ["manager@example.com"],         // optional
        "message": "Please review this post"   // optional custom message
    }
    """
    import uuid as _uuid
    
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog post not found'}), 404
    
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    # Get recipient email
    to_email = data.get('email', '').strip()
    if not to_email:
        # Try client email
        client = DBClient.query.get(blog.client_id)
        to_email = client.email if client else ''
    
    if not to_email:
        return jsonify({'error': 'Recipient email is required. Provide "email" in request or configure client email.'}), 400
    
    client = DBClient.query.get(blog.client_id)
    
    # Generate review token if doesn't exist
    if not blog.review_token:
        blog.review_token = _uuid.uuid4().hex + _uuid.uuid4().hex[:8]
    
    # Set client status
    blog.client_status = 'pending_review'
    
    db.session.commit()
    
    # Build review URL
    import os
    base_url = os.environ.get('BASE_URL', '') or os.environ.get('RENDER_EXTERNAL_URL', '') or os.environ.get('APP_URL', '')
    if not base_url:
        base_url = request.host_url.rstrip('/')
    review_url = f"{base_url}/review/{blog.review_token}"
    
    # Build and send email
    try:
        from app.services.email_service import email_service
        
        client_name = client.business_name if client else 'Your Business'
        custom_message = data.get('message', '').strip()
        
        # Fact-check badge
        fc_score = blog.fact_check_score
        if fc_score is not None:
            fc_color = '#059669' if fc_score >= 80 else '#d97706' if fc_score >= 60 else '#dc2626'
            fc_badge = f'<span style="background:{fc_color};color:white;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">Accuracy: {fc_score}/100</span>'
        else:
            fc_badge = ''
        
        # Plain text excerpt
        import re
        plain_body = re.sub(r'<[^>]+>', ' ', blog.body or '')
        plain_body = re.sub(r'\s+', ' ', plain_body).strip()
        excerpt = plain_body[:300] + '...' if len(plain_body) > 300 else plain_body
        
        # Custom message section
        custom_html = ''
        if custom_message:
            from markupsafe import escape
            custom_html = f'''
            <div style="background:#f0f4ff;border-left:4px solid #6366f1;border-radius:8px;padding:16px;margin:16px 0;">
                <p style="margin:0;color:#4b5563;font-size:14px;font-style:italic;">"{escape(custom_message)}"</p>
                <p style="margin:8px 0 0;color:#9ca3af;font-size:12px;">— {escape(current_user.name)}</p>
            </div>
            '''
        
        html_body = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:22px;">Blog Post Ready for Review</h1>
                <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">for {client_name}</p>
            </div>
            <div style="padding:32px;">
                {custom_html}
                <h2 style="margin:0 0 8px;font-size:20px;color:#1f2937;">{blog.title}</h2>
                <div style="margin:12px 0 20px;display:flex;gap:8px;flex-wrap:wrap;">
                    <span style="background:#ede9fe;color:#7c3aed;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">{blog.word_count} words</span>
                    <span style="background:#ecfdf5;color:#059669;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">SEO: {blog.seo_score}/100</span>
                    {fc_badge}
                </div>
                <div style="background:#f9fafb;border-radius:8px;padding:16px;margin:16px 0;border-left:4px solid #6366f1;">
                    <p style="margin:0;color:#4b5563;font-size:14px;line-height:1.6;">{excerpt}</p>
                </div>
                <p style="color:#6b7280;font-size:14px;line-height:1.5;margin:16px 0;">
                    Please review this blog post. You can edit the title, content, add images, manage tags, and leave comments.
                </p>
                <div style="text-align:center;margin:28px 0;">
                    <a href="{review_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;padding:14px 40px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">
                        Review &amp; Edit Blog Post
                    </a>
                </div>
                <p style="color:#9ca3af;font-size:12px;text-align:center;margin:20px 0 0;">
                    Or copy this link: {review_url}
                </p>
            </div>
            <div style="background:#f9fafb;padding:20px 32px;text-align:center;border-top:1px solid #e5e7eb;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    Sent by {escape(current_user.name)} from {client_name}'s Marketing Platform.
                </p>
            </div>
        </div>
        """
        
        cc = data.get('cc', [])
        if isinstance(cc, str):
            cc = [e.strip() for e in cc.split(',') if e.strip()]
        
        success = email_service.send_simple(
            to=to_email,
            subject=f"Blog Post for Review: {blog.title}",
            body=html_body,
            html=True,
            cc=cc if cc else None
        )
        
        if success:
            logger.info(f"Review email sent to {to_email} for blog {blog.id}")
        else:
            logger.warning(f"Failed to send review email to {to_email}")
            return jsonify({
                'success': True,
                'review_url': review_url,
                'email_sent': False,
                'warning': 'Blog review link created but email failed to send. Share the link manually.'
            })
        
        return jsonify({
            'success': True,
            'review_url': review_url,
            'review_token': blog.review_token,
            'email_sent': True,
            'sent_to': to_email
        })
        
    except Exception as e:
        logger.error(f"Send to client error: {e}")
        # Still return the review URL even if email fails
        return jsonify({
            'success': True,
            'review_url': review_url,
            'review_token': blog.review_token,
            'email_sent': False,
            'error': f'Review link created but email failed: {str(e)[:100]}'
        })


# ==========================================
# CLIENT REVIEW (public - no auth, token-based)
# ==========================================

@content_schedule_bp.route('/review/<review_token>', methods=['GET'])
def get_review_data(review_token):
    """
    Public endpoint - Get blog data for client review.
    No login required, secured by review token.
    """
    blog = DBBlogPost.query.filter_by(review_token=review_token).first()
    if not blog:
        return jsonify({'error': 'Review link not found or expired'}), 404
    
    client = DBClient.query.get(blog.client_id)
    
    # Get comments
    comments = DBContentComment.query.filter_by(blog_id=blog.id).order_by(
        DBContentComment.created_at.asc()
    ).all()
    
    return jsonify({
        'blog': blog.to_dict(),
        'client_name': client.business_name if client else '',
        'client_industry': client.industry if client else '',
        'comments': [c.to_dict() for c in comments]
    })


@content_schedule_bp.route('/review/<review_token>', methods=['PUT'])
def submit_client_review(review_token):
    """
    Public endpoint - Client submits edits to the blog post.
    Updates the blog and marks it as client_edited.
    """
    blog = DBBlogPost.query.filter_by(review_token=review_token).first()
    if not blog:
        return jsonify({'error': 'Review link not found or expired'}), 404
    
    data = request.get_json(silent=True) or {}
    
    # Updatable fields
    if 'title' in data and data['title']:
        blog.title = data['title'][:500]
    if 'meta_title' in data:
        blog.meta_title = (data['meta_title'] or '')[:500]
    if 'meta_description' in data:
        blog.meta_description = (data['meta_description'] or '')[:500]
    if 'body' in data and data['body']:
        blog.body = data['body']
        blog.word_count = len(data['body'].split())
    if 'tags' in data and isinstance(data['tags'], list):
        blog.tags = json.dumps(data['tags'])
    if 'featured_image_url' in data:
        blog.featured_image_url = data['featured_image_url']
    
    # Mark as edited by client
    action = data.get('action', 'save')  # 'save' or 'approve'
    
    if action == 'approve':
        blog.client_status = 'client_approved'
    else:
        blog.client_status = 'client_edited'
    
    blog.client_reviewed_at = datetime.utcnow()
    blog.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'client_status': blog.client_status,
        'message': 'Blog approved! Your team will publish it shortly.' if action == 'approve' else 'Changes saved successfully.'
    })


# ==========================================
# COMMENTS (public for clients, auth for team)
# ==========================================

@content_schedule_bp.route('/review/<review_token>/comments', methods=['POST'])
def add_client_comment(review_token):
    """Public endpoint - Client adds a comment via review link"""
    blog = DBBlogPost.query.filter_by(review_token=review_token).first()
    if not blog:
        return jsonify({'error': 'Review link not found'}), 404
    
    data = request.get_json(silent=True) or {}
    
    if not data.get('comment'):
        return jsonify({'error': 'Comment text required'}), 400
    
    comment = DBContentComment(
        blog_id=blog.id,
        comment=data['comment'],
        author_type='client',
        author_name=data.get('author_name', 'Client'),
        author_email=data.get('author_email', ''),
        parent_id=data.get('parent_id')
    )
    
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'comment': comment.to_dict()
    })


@content_schedule_bp.route('/comments/<blog_id>', methods=['GET'])
@token_required
def get_comments(current_user, blog_id):
    """Get all comments for a blog post (team view)"""
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog not found'}), 404
    
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    comments = DBContentComment.query.filter_by(blog_id=blog_id).order_by(
        DBContentComment.created_at.asc()
    ).all()
    
    return jsonify({'comments': [c.to_dict() for c in comments]})


@content_schedule_bp.route('/comments/<blog_id>', methods=['POST'])
@token_required
def add_team_comment(current_user, blog_id):
    """Team member adds a comment"""
    blog = DBBlogPost.query.get(blog_id)
    if not blog:
        return jsonify({'error': 'Blog not found'}), 404
    
    if not current_user.has_access_to_client(blog.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    if not data.get('comment'):
        return jsonify({'error': 'Comment text required'}), 400
    
    comment = DBContentComment(
        blog_id=blog_id,
        comment=data['comment'],
        author_type='team',
        author_name=current_user.name,
        author_email=current_user.email,
        user_id=current_user.id,
        parent_id=data.get('parent_id')
    )
    
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'comment': comment.to_dict()
    })


@content_schedule_bp.route('/comments/<blog_id>/<comment_id>/resolve', methods=['POST'])
@token_required
def resolve_comment(current_user, blog_id, comment_id):
    """Mark a comment as resolved"""
    comment = DBContentComment.query.get(comment_id)
    if not comment or comment.blog_id != blog_id:
        return jsonify({'error': 'Comment not found'}), 404
    
    comment.is_resolved = True
    comment.resolved_by = current_user.id
    comment.resolved_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True})


# ==========================================
# CLIENT REVIEW QUEUE (team dashboard)
# ==========================================

@content_schedule_bp.route('/client-reviews', methods=['GET'])
@token_required
def get_client_reviews(current_user):
    """
    Get all blogs that clients have edited/approved — for the agency approval queue.
    """
    if not current_user.can_manage_clients:
        return jsonify({'error': 'Manager access required'}), 403
    
    # Get blogs with client activity
    blogs = DBBlogPost.query.filter(
        DBBlogPost.client_status.in_(['client_edited', 'client_approved', 'pending_review'])
    ).order_by(DBBlogPost.updated_at.desc()).all()
    
    result = []
    for blog in blogs:
        client = DBClient.query.get(blog.client_id)
        
        # Count unresolved comments
        comment_count = DBContentComment.query.filter_by(
            blog_id=blog.id, is_resolved=False
        ).count()
        
        item = {
            'blog_id': blog.id,
            'title': blog.title,
            'client_id': blog.client_id,
            'client_name': client.business_name if client else 'Unknown',
            'client_status': blog.client_status,
            'client_reviewed_at': blog.client_reviewed_at.isoformat() if blog.client_reviewed_at else None,
            'word_count': blog.word_count,
            'seo_score': blog.seo_score,
            'fact_check_score': blog.fact_check_score,
            'unresolved_comments': comment_count,
            'status': blog.status,
            'auto_generated': blog.auto_generated,
            'created_at': blog.created_at.isoformat() if blog.created_at else None,
            'updated_at': blog.updated_at.isoformat() if blog.updated_at else None,
        }
        result.append(item)
    
    return jsonify({
        'reviews': result,
        'total': len(result),
        'pending_edit': len([r for r in result if r['client_status'] == 'client_edited']),
        'client_approved': len([r for r in result if r['client_status'] == 'client_approved']),
        'awaiting_review': len([r for r in result if r['client_status'] == 'pending_review']),
    })
