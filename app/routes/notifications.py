"""
MCP Framework - Notification Routes
API for managing notification preferences and viewing notification history
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

from app.routes.auth import token_required, admin_required
from app.database import db
from app.models.db_models import (
    DBNotificationPreferences, DBNotificationLog, DBNotificationQueue,
    DBUser, DBClient, NotificationType
)
from app.services.notification_service import get_notification_service

notifications_bp = Blueprint('notifications', __name__)
notification_service = get_notification_service()


# ==========================================
# PREFERENCE MANAGEMENT
# ==========================================

@notifications_bp.route('/preferences', methods=['GET'])
@token_required
def get_preferences(current_user):
    """
    Get notification preferences for current user
    
    GET /api/notifications/preferences?client_id=optional
    """
    client_id = request.args.get('client_id')
    prefs = notification_service.get_user_preferences(current_user.id, client_id)
    
    return jsonify({
        'success': True,
        'preferences': prefs.to_dict()
    })


@notifications_bp.route('/preferences', methods=['PUT'])
@token_required
def update_preferences(current_user):
    """
    Update notification preferences
    
    PUT /api/notifications/preferences
    {
        "client_id": "optional - for client-specific prefs",
        "content_scheduled": true,
        "content_published": true,
        "email_enabled": true,
        "digest_frequency": "instant|daily|weekly",
        ...
    }
    """
    data = request.get_json() or {}
    client_id = data.pop('client_id', None)
    
    try:
        prefs = notification_service.update_preferences(
            user_id=current_user.id,
            updates=data,
            client_id=client_id
        )
        
        return jsonify({
            'success': True,
            'message': 'Preferences updated',
            'preferences': prefs.to_dict()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notifications_bp.route('/preferences/reset', methods=['POST'])
@token_required
def reset_preferences(current_user):
    """
    Reset preferences to defaults
    
    POST /api/notifications/preferences/reset
    {
        "client_id": "optional"
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    try:
        # Delete existing preferences
        query = DBNotificationPreferences.query.filter_by(user_id=current_user.id)
        if client_id:
            query = query.filter_by(client_id=client_id)
        else:
            query = query.filter(DBNotificationPreferences.client_id.is_(None))
        
        query.delete()
        db.session.commit()
        
        # Get fresh defaults
        prefs = notification_service.get_user_preferences(current_user.id, client_id)
        
        return jsonify({
            'success': True,
            'message': 'Preferences reset to defaults',
            'preferences': prefs.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==========================================
# NOTIFICATION HISTORY
# ==========================================

@notifications_bp.route('/history', methods=['GET'])
@token_required
def get_notification_history(current_user):
    """
    Get notification history for current user
    
    GET /api/notifications/history?limit=50&status=sent&type=content_published
    """
    limit = min(int(request.args.get('limit', 50)), 200)
    status = request.args.get('status')  # sent, failed, pending
    notification_type = request.args.get('type')
    client_id = request.args.get('client_id')
    
    query = DBNotificationLog.query.filter_by(user_id=current_user.id)
    
    if status:
        query = query.filter_by(status=status)
    if notification_type:
        query = query.filter_by(notification_type=notification_type)
    if client_id:
        query = query.filter_by(client_id=client_id)
    
    logs = query.order_by(DBNotificationLog.created_at.desc()).limit(limit).all()
    
    # Get stats
    total = DBNotificationLog.query.filter_by(user_id=current_user.id).count()
    sent = DBNotificationLog.query.filter_by(user_id=current_user.id, status='sent').count()
    failed = DBNotificationLog.query.filter_by(user_id=current_user.id, status='failed').count()
    
    return jsonify({
        'notifications': [log.to_dict() for log in logs],
        'stats': {
            'total': total,
            'sent': sent,
            'failed': failed,
            'success_rate': round((sent / total * 100), 1) if total > 0 else 100
        }
    })


@notifications_bp.route('/queue', methods=['GET'])
@token_required
def get_notification_queue(current_user):
    """
    Get pending notifications in queue
    
    GET /api/notifications/queue
    """
    queue = DBNotificationQueue.query.filter_by(
        user_id=current_user.id,
        processed=False
    ).order_by(
        DBNotificationQueue.priority.desc(),
        DBNotificationQueue.created_at.asc()
    ).all()
    
    return jsonify({
        'queue': [item.to_dict() for item in queue],
        'count': len(queue)
    })


# ==========================================
# MANUAL NOTIFICATION TRIGGERS
# ==========================================

@notifications_bp.route('/test', methods=['POST'])
@token_required
def send_test_notification(current_user):
    """
    Send a test notification to verify email is working
    
    POST /api/notifications/test
    """
    from app.services.notification_service import NotificationService
    service = NotificationService()
    
    html = service._build_email_template(
        title="🧪 Test Notification",
        message="This is a test notification to verify your email settings are working correctly.",
        details=[
            ('Sent To', current_user.email),
            ('Time', datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC'))
        ],
        cta_text="Open Dashboard",
        accent_color="#8b5cf6"
    )
    
    success = service._send_email(
        user_id=current_user.id,
        recipient_email=current_user.email,
        notification_type='test',
        subject="🧪 Test Notification from MCP Framework",
        html_body=html
    )
    
    if success:
        return jsonify({
            'success': True,
            'message': f'Test notification sent to {current_user.email}'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to send test notification. Check email configuration.'
        }), 500


@notifications_bp.route('/process-digest', methods=['POST'])
@admin_required
def process_digest(current_user):
    """
    Manually trigger digest processing for a user
    
    POST /api/notifications/process-digest
    {
        "user_id": "user_123",
        "frequency": "daily|weekly"
    }
    """
    data = request.get_json() or {}
    user_id = data.get('user_id', current_user.id)
    frequency = data.get('frequency', 'daily')
    
    if frequency not in ['daily', 'weekly']:
        return jsonify({'error': 'frequency must be daily or weekly'}), 400
    
    success = notification_service.process_digest_queue(user_id, frequency)
    
    return jsonify({
        'success': success,
        'message': f'{frequency.title()} digest processed for user {user_id}'
    })


# ==========================================
# NOTIFICATION TYPES INFO
# ==========================================

@notifications_bp.route('/types', methods=['GET'])
@token_required
def get_notification_types(current_user):
    """
    Get list of all notification types with descriptions
    
    GET /api/notifications/types
    """
    types = {
        'content': {
            'content_scheduled': {
                'name': 'Content Scheduled',
                'description': 'When content is scheduled for publishing',
                'default': True
            },
            'content_due_today': {
                'name': 'Content Due Today',
                'description': 'Morning reminder of content publishing today',
                'default': True
            },
            'content_published': {
                'name': 'Content Published',
                'description': 'When content is successfully published',
                'default': True
            },
            'content_approval_needed': {
                'name': 'Approval Needed',
                'description': 'When content needs your approval',
                'default': True
            },
            'content_approved': {
                'name': 'Content Approved',
                'description': 'When client approves content',
                'default': True
            },
            'content_feedback': {
                'name': 'Client Feedback',
                'description': 'When client leaves feedback or requests changes',
                'default': True
            }
        },
        'competitor': {
            'competitor_new_content': {
                'name': 'Competitor Content',
                'description': 'When competitor publishes new content',
                'default': True
            },
            'ranking_improved': {
                'name': 'Ranking Improved',
                'description': 'When keyword ranking improves',
                'default': True
            },
            'ranking_dropped': {
                'name': 'Ranking Dropped',
                'description': 'When keyword ranking drops',
                'default': True
            }
        },
        'publishing': {
            'wordpress_published': {
                'name': 'WordPress Published',
                'description': 'When content goes live on WordPress',
                'default': True
            },
            'wordpress_failed': {
                'name': 'WordPress Failed',
                'description': 'When WordPress publishing fails',
                'default': True
            },
            'social_published': {
                'name': 'Social Published',
                'description': 'When social posts are published',
                'default': False
            },
            'social_failed': {
                'name': 'Social Failed',
                'description': 'When social publishing fails',
                'default': True
            }
        },
        'system': {
            'weekly_digest': {
                'name': 'Weekly Digest',
                'description': 'Weekly summary of all activity',
                'default': True
            },
            'daily_summary': {
                'name': 'Daily Summary',
                'description': 'Daily activity summary',
                'default': True
            },
            'alert_digest': {
                'name': 'Alert Digest',
                'description': 'Batch of alerts when using digest mode',
                'default': True
            }
        }
    }
    
    return jsonify({
        'types': types,
        'delivery_options': {
            'instant': 'Send notifications immediately',
            'daily': 'Batch into daily digest (sent at your preferred time)',
            'weekly': 'Batch into weekly digest (sent on your preferred day)'
        }
    })


# ==========================================
# ADMIN: VIEW ALL NOTIFICATIONS
# ==========================================

@notifications_bp.route('/admin/logs', methods=['GET'])
@admin_required
def admin_get_logs(current_user):
    """
    Admin: Get all notification logs
    
    GET /api/notifications/admin/logs?limit=100&status=failed
    """
    limit = min(int(request.args.get('limit', 100)), 500)
    status = request.args.get('status')
    notification_type = request.args.get('type')
    user_id = request.args.get('user_id')
    
    query = DBNotificationLog.query
    
    if status:
        query = query.filter_by(status=status)
    if notification_type:
        query = query.filter_by(notification_type=notification_type)
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    logs = query.order_by(DBNotificationLog.created_at.desc()).limit(limit).all()
    
    # Get aggregate stats
    today = datetime.utcnow().date()
    today_start = datetime(today.year, today.month, today.day)
    
    total_today = DBNotificationLog.query.filter(
        DBNotificationLog.created_at >= today_start
    ).count()
    
    failed_today = DBNotificationLog.query.filter(
        DBNotificationLog.created_at >= today_start,
        DBNotificationLog.status == 'failed'
    ).count()
    
    return jsonify({
        'logs': [log.to_dict() for log in logs],
        'stats': {
            'total_today': total_today,
            'failed_today': failed_today,
            'total_returned': len(logs)
        }
    })


@notifications_bp.route('/admin/retry-failed', methods=['POST'])
@admin_required
def admin_retry_failed(current_user):
    """
    Admin: Retry all failed notifications
    
    POST /api/notifications/admin/retry-failed
    """
    notification_service.retry_failed_notifications()
    
    return jsonify({
        'success': True,
        'message': 'Retry process initiated for failed notifications'
    })


@notifications_bp.route('/admin/stats', methods=['GET'])
@admin_required
def admin_get_stats(current_user):
    """
    Admin: Get notification system stats
    
    GET /api/notifications/admin/stats
    """
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    week_ago = now - timedelta(days=7)
    
    # Total counts
    total_all_time = DBNotificationLog.query.count()
    total_today = DBNotificationLog.query.filter(DBNotificationLog.created_at >= today).count()
    total_week = DBNotificationLog.query.filter(DBNotificationLog.created_at >= week_ago).count()
    
    # Status breakdown
    sent = DBNotificationLog.query.filter_by(status='sent').count()
    failed = DBNotificationLog.query.filter_by(status='failed').count()
    
    # By type
    type_counts = db.session.query(
        DBNotificationLog.notification_type,
        db.func.count(DBNotificationLog.id)
    ).group_by(DBNotificationLog.notification_type).all()
    
    # Queue stats
    queue_pending = DBNotificationQueue.query.filter_by(processed=False).count()
    
    return jsonify({
        'totals': {
            'all_time': total_all_time,
            'today': total_today,
            'this_week': total_week
        },
        'status': {
            'sent': sent,
            'failed': failed,
            'success_rate': round((sent / total_all_time * 100), 1) if total_all_time > 0 else 100
        },
        'by_type': {t: c for t, c in type_counts},
        'queue': {
            'pending': queue_pending
        }
    })
