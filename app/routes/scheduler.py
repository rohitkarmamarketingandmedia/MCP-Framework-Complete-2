"""
MCP Framework - Scheduler Routes
Control and monitor background jobs
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required, admin_required
from app.services.scheduler_service import get_scheduler_status, run_job_now

scheduler_bp = Blueprint('scheduler', __name__)


@scheduler_bp.route('/status', methods=['GET'])
@token_required
def scheduler_status(current_user):
    """
    Get scheduler status and list of jobs
    
    GET /api/scheduler/status
    """
    status = get_scheduler_status()
    return jsonify(status)


@scheduler_bp.route('/jobs/<job_id>/run', methods=['POST'])
@token_required
@admin_required
def trigger_job(current_user, job_id):
    """
    Manually trigger a scheduled job to run immediately
    
    POST /api/scheduler/jobs/{job_id}/run
    """
    result = run_job_now(job_id)
    
    if result.get('error'):
        return jsonify(result), 400
    
    return jsonify(result)


@scheduler_bp.route('/test-email', methods=['POST'])
@token_required
@admin_required
def test_email(current_user):
    """
    Send a test email to verify email configuration
    
    POST /api/scheduler/test-email
    {
        "to": "test@example.com"
    }
    """
    from app.services.email_service import get_email_service
    
    data = request.get_json() or {}
    to_email = data.get('to', current_user.email)
    
    if not to_email:
        return jsonify({'error': 'No email address provided'}), 400
    
    email = get_email_service()
    success = email.send_simple(
        to=to_email,
        subject="🧪 MCP Framework - Test Email",
        body="This is a test email from your MCP Framework installation. If you received this, email notifications are working correctly!"
    )
    
    if success:
        return jsonify({'success': True, 'message': f'Test email sent to {to_email}'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send email. Check your email configuration.'}), 500


@scheduler_bp.route('/run-crawl', methods=['POST'])
@token_required
@admin_required
def manual_crawl(current_user):
    """
    Manually run competitor crawl for all clients
    
    POST /api/scheduler/run-crawl
    """
    from flask import current_app
    from app.services.scheduler_service import run_competitor_crawl
    
    try:
        run_competitor_crawl(current_app._get_current_object())
        return jsonify({'success': True, 'message': 'Competitor crawl triggered'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@scheduler_bp.route('/run-ranks', methods=['POST'])
@token_required
@admin_required
def manual_ranks(current_user):
    """
    Manually run rank check for all clients
    
    POST /api/scheduler/run-ranks
    """
    from flask import current_app
    from app.services.scheduler_service import run_rank_check
    
    try:
        run_rank_check(current_app._get_current_object())
        return jsonify({'success': True, 'message': 'Rank check triggered'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
