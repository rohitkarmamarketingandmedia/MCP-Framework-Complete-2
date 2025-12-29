"""
MCP Framework - Approval Workflow Routes
Handles content approval, feedback, and revision requests
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.routes.auth import token_required
from app.database import db
from app.models.db_models import DBBlogPost, DBSocialPost, DBClient, DBUser

logger = logging.getLogger(__name__)
approval_bp = Blueprint('approval', __name__)


# ==========================================
# CONTENT APPROVAL
# ==========================================

@approval_bp.route('/pending', methods=['GET'])
@token_required
def get_pending_approvals(current_user):
    """
    Get all content pending approval for a client
    
    GET /api/approval/pending?client_id=xxx
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get pending blogs
    pending_blogs = DBBlogPost.query.filter(
        DBBlogPost.client_id == client_id,
        DBBlogPost.status.in_(['draft', 'pending_approval', 'revision_requested'])
    ).order_by(DBBlogPost.created_at.desc()).all()
    
    # Get pending social posts
    pending_social = DBSocialPost.query.filter(
        DBSocialPost.client_id == client_id,
        DBSocialPost.status.in_(['draft', 'pending_approval', 'revision_requested'])
    ).order_by(DBSocialPost.created_at.desc()).all()
    
    items = []
    
    for blog in pending_blogs:
        items.append({
            'id': blog.id,
            'type': 'blog',
            'title': blog.title,
            'status': blog.status,
            'meta_description': blog.meta_description,
            'body': blog.body,
            'word_count': blog.word_count,
            'primary_keyword': blog.primary_keyword,
            'created_at': blog.created_at.isoformat() if blog.created_at else None,
            'scheduled_for': blog.scheduled_for.isoformat() if blog.scheduled_for else None,
            'feedback': get_content_feedback(blog.id, 'blog'),
            'revision_notes': blog.revision_notes if hasattr(blog, 'revision_notes') else None
        })
    
    for post in pending_social:
        items.append({
            'id': post.id,
            'type': 'social',
            'title': f"{post.platform.title()} Post" if post.platform else "Social Post",
            'platform': post.platform,
            'status': post.status,
            'content': post.content,
            'hashtags': post.hashtags,
            'created_at': post.created_at.isoformat() if post.created_at else None,
            'scheduled_for': post.scheduled_for.isoformat() if post.scheduled_for else None,
            'feedback': get_content_feedback(post.id, 'social'),
            'revision_notes': post.revision_notes if hasattr(post, 'revision_notes') else None
        })
    
    # Sort by status priority (revision_requested first, then pending, then draft)
    status_priority = {'revision_requested': 0, 'pending_approval': 1, 'draft': 2}
    items.sort(key=lambda x: status_priority.get(x['status'], 3))
    
    return jsonify({
        'items': items,
        'total': len(items),
        'by_status': {
            'draft': len([i for i in items if i['status'] == 'draft']),
            'pending_approval': len([i for i in items if i['status'] == 'pending_approval']),
            'revision_requested': len([i for i in items if i['status'] == 'revision_requested'])
        }
    })


@approval_bp.route('/approve/<content_type>/<content_id>', methods=['POST'])
@token_required
def approve_content(current_user, content_type, content_id):
    """
    Approve content for publishing
    
    POST /api/approval/approve/{content_type}/{content_id}
    {
        "notes": "Optional approval notes",
        "schedule_for": "2024-12-20T10:00:00Z"  // Optional, auto-schedule after approval
    }
    """
    data = request.get_json(silent=True) or {}
    
    if content_type == 'blog':
        content = DBBlogPost.query.get(content_id)
    elif content_type == 'social':
        content = DBSocialPost.query.get(content_id)
    else:
        return jsonify({'error': f'Invalid content type: {content_type}'}), 400
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Update status
    content.status = 'approved'
    
    # Optionally schedule
    schedule_for = data.get('schedule_for')
    if schedule_for:
        try:
            content.scheduled_for = datetime.fromisoformat(schedule_for.replace('Z', '+00:00'))
            content.status = 'scheduled'
        except Exception as e:
            pass
    
    # Store approval info
    if hasattr(content, 'approved_at'):
        content.approved_at = datetime.utcnow()
    if hasattr(content, 'approved_by'):
        content.approved_by = current_user.id
    
    db.session.commit()
    
    # Send notification to agency
    try:
        from app.services.notification_service import get_notification_service
        notification_service = get_notification_service()
        
        # Notify all admins about approval
        admins = DBUser.query.filter_by(role='admin', is_active=True).all()
        client = DBClient.query.get(content.client_id)
        
        for admin in admins:
            notification_service.notify_content_approved(
                user_id=admin.id,
                client_name=client.business_name if client else 'Unknown',
                content_title=content.title if hasattr(content, 'title') else 'Social Post',
                approved_by=current_user.email,
                content_id=content_id,
                client_id=content.client_id
            )
    except Exception as e:
        logger.warning(f"Failed to send approval notification: {e}")
        import traceback
        traceback.print_exc()
    
    # Fire webhook for external systems
    try:
        from app.services.webhook_events_service import get_webhook_events_service
        webhook_service = get_webhook_events_service()
        
        client = DBClient.query.get(content.client_id)
        
        webhook_service.content_approved(
            content_id=content_id,
            content_type=content_type,
            client_id=content.client_id,
            data={
                'title': content.title if hasattr(content, 'title') else 'Social Post',
                'client_name': client.business_name if client else None,
                'status': content.status,
                'scheduled_for': content.scheduled_for.isoformat() if content.scheduled_for else None,
                'approved_by': current_user.email,
                'body': content.body if hasattr(content, 'body') else content.content,
                'meta_description': content.meta_description if hasattr(content, 'meta_description') else None,
                'platform': content.platform if hasattr(content, 'platform') else None
            }
        )
        logger.info(f"Webhook fired: content.approved for {content_type}/{content_id}")
    except Exception as e:
        logger.warning(f"Failed to fire approval webhook: {e}")
    
    logger.info(f"Content approved: {content_type}/{content_id} by user {current_user.id}")
    
    return jsonify({
        'success': True,
        'status': content.status,
        'message': 'Content approved successfully'
    })


@approval_bp.route('/request-changes/<content_type>/<content_id>', methods=['POST'])
@token_required
def request_changes(current_user, content_type, content_id):
    """
    Request changes/revisions to content
    
    POST /api/approval/request-changes/{content_type}/{content_id}
    {
        "feedback": "Please change the headline to be more engaging",
        "priority": "normal|high|low"
    }
    """
    data = request.get_json(silent=True) or {}
    
    feedback = data.get('feedback', '').strip()
    if not feedback:
        return jsonify({'error': 'Feedback is required'}), 400
    
    if content_type == 'blog':
        content = DBBlogPost.query.get(content_id)
    elif content_type == 'social':
        content = DBSocialPost.query.get(content_id)
    else:
        return jsonify({'error': f'Invalid content type: {content_type}'}), 400
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Update status
    content.status = 'revision_requested'
    
    # Store revision notes
    if hasattr(content, 'revision_notes'):
        content.revision_notes = feedback
    
    db.session.commit()
    
    # Store feedback in feedback table
    store_feedback(
        content_id=content_id,
        content_type=content_type,
        user_id=current_user.id,
        feedback_type='change_request',
        message=feedback,
        priority=data.get('priority', 'normal'),
        client_id=content.client_id
    )
    
    # Send notification to agency
    try:
        from app.services.notification_service import get_notification_service
        notification_service = get_notification_service()
        
        admins = DBUser.query.filter_by(role='admin', is_active=True).all()
        client = DBClient.query.get(content.client_id)
        
        for admin in admins:
            notification_service.notify_content_feedback(
                user_id=admin.id,
                client_name=client.business_name if client else 'Unknown',
                content_title=content.title if hasattr(content, 'title') else 'Social Post',
                feedback_preview=feedback[:100],
                content_type=content_type,
                content_id=content_id,
                client_id=content.client_id
            )
    except Exception as e:
        logger.warning(f"Failed to send feedback notification: {e}")
    
    logger.info(f"Changes requested for: {content_type}/{content_id} by user {current_user.id}")
    
    return jsonify({
        'success': True,
        'status': 'revision_requested',
        'message': 'Change request submitted successfully'
    })


# ==========================================
# FEEDBACK / COMMENTS
# ==========================================

@approval_bp.route('/feedback/<content_type>/<content_id>', methods=['GET'])
@token_required
def get_feedback(current_user, content_type, content_id):
    """
    Get all feedback/comments for content
    
    GET /api/approval/feedback/{content_type}/{content_id}
    """
    feedback_list = get_content_feedback(content_id, content_type)
    
    return jsonify({
        'feedback': feedback_list,
        'total': len(feedback_list)
    })


@approval_bp.route('/feedback/<content_type>/<content_id>', methods=['POST'])
@token_required
def add_feedback(current_user, content_type, content_id):
    """
    Add feedback/comment to content
    
    POST /api/approval/feedback/{content_type}/{content_id}
    {
        "message": "This looks great!",
        "type": "comment|approval|change_request"
    }
    """
    data = request.get_json(silent=True) or {}
    
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    # Verify content exists and user has access
    if content_type == 'blog':
        content = DBBlogPost.query.get(content_id)
    elif content_type == 'social':
        content = DBSocialPost.query.get(content_id)
    else:
        return jsonify({'error': f'Invalid content type: {content_type}'}), 400
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    if not current_user.has_access_to_client(content.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    feedback = store_feedback(
        content_id=content_id,
        content_type=content_type,
        user_id=current_user.id,
        feedback_type=data.get('type', 'comment'),
        message=message
    )
    
    return jsonify({
        'success': True,
        'feedback': feedback
    })


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_content_feedback(content_id: str, content_type: str) -> list:
    """Get all feedback for a piece of content"""
    from app.models.db_models import DBContentFeedback
    
    try:
        feedbacks = DBContentFeedback.query.filter_by(
            content_id=content_id
        ).order_by(DBContentFeedback.created_at.desc()).all()
        
        result = []
        for fb in feedbacks:
            user = DBUser.query.get(fb.user_id)
            result.append({
                'id': fb.id,
                'user_id': fb.user_id,
                'user_name': user.name if user else 'Unknown',
                'user_role': user.role if user else None,
                'type': fb.feedback_type,
                'message': fb.feedback_text,
                'status': fb.status,
                'created_at': fb.created_at.isoformat() if fb.created_at else None,
                'addressed_at': fb.addressed_at.isoformat() if fb.addressed_at else None
            })
        return result
    except Exception as e:
        logger.warning(f"Error getting feedback: {e}")
        return []


def store_feedback(
    content_id: str,
    content_type: str,
    user_id: str,
    feedback_type: str,
    message: str,
    priority: str = 'normal',
    client_id: str = None
) -> dict:
    """Store feedback in database"""
    from app.models.db_models import DBContentFeedback
    import uuid
    
    try:
        feedback = DBContentFeedback(
            id=str(uuid.uuid4()),
            content_id=content_id,
            client_id=client_id or '',
            user_id=user_id,
            feedback_type=feedback_type,
            feedback_text=message,
            status='pending',
            created_at=datetime.utcnow()
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        user = DBUser.query.get(user_id)
        
        return {
            'id': feedback.id,
            'user_id': user_id,
            'user_name': user.name if user else 'Unknown',
            'type': feedback_type,
            'message': message,
            'status': 'pending',
            'created_at': feedback.created_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Error storing feedback: {e}")
        db.session.rollback()
        return {}


# ==========================================
# SUBMIT FOR APPROVAL (Agency side)
# ==========================================

@approval_bp.route('/submit/<content_type>/<content_id>', methods=['POST'])
@token_required
def submit_for_approval(current_user, content_type, content_id):
    """
    Submit content for client approval (agency use)
    
    POST /api/approval/submit/{content_type}/{content_id}
    {
        "notify_client": true,
        "message": "Ready for your review!"
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json(silent=True) or {}
    
    if content_type == 'blog':
        content = DBBlogPost.query.get(content_id)
    elif content_type == 'social':
        content = DBSocialPost.query.get(content_id)
    else:
        return jsonify({'error': f'Invalid content type: {content_type}'}), 400
    
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    
    # Update status
    content.status = 'pending_approval'
    db.session.commit()
    
    # Send notification to client if requested
    if data.get('notify_client', True):
        try:
            from app.services.notification_service import get_notification_service
            notification_service = get_notification_service()
            
            client = DBClient.query.get(content.client_id)
            # In a full implementation, you'd get the client's user account
            # For now, notify admins (who can forward to client)
            
            notification_service.notify_content_approval_needed(
                client_id=content.client_id,
                content_title=content.title if hasattr(content, 'title') else 'Social Post',
                content_type=content_type,
                content_id=content_id,
                message=data.get('message', '')
            )
        except Exception as e:
            logger.warning(f"Failed to send approval request notification: {e}")
    
    return jsonify({
        'success': True,
        'status': 'pending_approval',
        'message': 'Content submitted for approval'
    })


# ==========================================
# BULK OPERATIONS
# ==========================================

@approval_bp.route('/bulk-approve', methods=['POST'])
@token_required
def bulk_approve(current_user):
    """
    Approve multiple items at once
    
    POST /api/approval/bulk-approve
    {
        "items": [
            {"type": "blog", "id": "xxx"},
            {"type": "social", "id": "yyy"}
        ]
    }
    """
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    
    if not items:
        return jsonify({'error': 'No items provided'}), 400
    
    approved = 0
    errors = []
    
    for item in items:
        content_type = item.get('type')
        content_id = item.get('id')
        
        if content_type == 'blog':
            content = DBBlogPost.query.get(content_id)
        elif content_type == 'social':
            content = DBSocialPost.query.get(content_id)
        else:
            errors.append(f"Invalid type: {content_type}")
            continue
        
        if not content:
            errors.append(f"Not found: {content_id}")
            continue
        
        if not current_user.has_access_to_client(content.client_id):
            errors.append(f"Access denied: {content_id}")
            continue
        
        content.status = 'approved'
        approved += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'approved': approved,
        'errors': errors
    })
