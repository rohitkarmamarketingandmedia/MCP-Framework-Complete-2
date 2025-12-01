"""
MCP Framework - Reviews API Routes
Review management, response generation, and review requests
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from app.routes.auth import token_required
from app.utils import safe_int
from app.services.review_service import review_service
from app.models.db_models import DBReview, DBClient
from app.database import db

reviews_bp = Blueprint('reviews', __name__)


# ==========================================
# Review Management
# ==========================================

@reviews_bp.route('/', methods=['GET'])
@token_required
def get_reviews(current_user):
    """
    Get reviews with filters
    
    GET /api/reviews?client_id=xxx&platform=google&status=pending&min_rating=1&days=90
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    reviews = review_service.get_reviews(
        client_id=client_id,
        platform=request.args.get('platform'),
        status=request.args.get('status'),
        min_rating=safe_int(request.args.get('min_rating'), None, min_val=1, max_val=5) if request.args.get('min_rating') else None,
        max_rating=safe_int(request.args.get('max_rating'), None, min_val=1, max_val=5) if request.args.get('max_rating') else None,
        days=safe_int(request.args.get('days'), 90, max_val=365),
        limit=safe_int(request.args.get('limit'), 100, max_val=500)
    )
    
    return jsonify({
        'reviews': reviews,
        'total': len(reviews)
    })


@reviews_bp.route('/<review_id>', methods=['GET'])
@token_required
def get_review(current_user, review_id):
    """Get a single review"""
    review = review_service.get_review(review_id)
    
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    if not current_user.has_access_to_client(review.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({'review': review.to_dict()})


@reviews_bp.route('/', methods=['POST'])
@token_required
def add_review(current_user):
    """
    Manually add a review (for importing from other platforms)
    
    POST /api/reviews
    {
        "client_id": "xxx",
        "platform": "google",
        "reviewer_name": "John Smith",
        "rating": 5,
        "review_text": "Great service!",
        "review_date": "2024-01-15T10:30:00Z"
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    result = review_service.add_review(client_id, data)
    
    if result.get('error'):
        return jsonify(result), 400
    
    return jsonify(result)


@reviews_bp.route('/<review_id>/response', methods=['PUT'])
@token_required
def update_response(current_user, review_id):
    """
    Update review response
    
    PUT /api/reviews/<review_id>/response
    {
        "response_text": "Thank you for...",
        "mark_responded": true
    }
    """
    review = review_service.get_review(review_id)
    
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    if not current_user.has_access_to_client(review.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    
    result = review_service.update_review_response(
        review_id=review_id,
        response_text=data.get('response_text'),
        mark_responded=data.get('mark_responded', True)
    )
    
    return jsonify(result)


@reviews_bp.route('/<review_id>', methods=['DELETE'])
@token_required
def delete_review(current_user, review_id):
    """Delete a review from the database"""
    review = review_service.get_review(review_id)
    
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    if not current_user.has_access_to_client(review.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    db.session.delete(review)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Review deleted'})


# ==========================================
# Statistics
# ==========================================

@reviews_bp.route('/stats', methods=['GET'])
@token_required
def get_stats(current_user):
    """
    Get review statistics
    
    GET /api/reviews/stats?client_id=xxx&days=90
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    days = safe_int(request.args.get('days'), 90, max_val=365)
    stats = review_service.get_review_stats(client_id, days)
    
    return jsonify(stats)


# ==========================================
# AI Response Generation
# ==========================================

@reviews_bp.route('/<review_id>/generate-response', methods=['POST'])
@token_required
def generate_response(current_user, review_id):
    """
    Generate AI response for a review
    
    POST /api/reviews/<review_id>/generate-response
    """
    review = review_service.get_review(review_id)
    
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    if not current_user.has_access_to_client(review.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(review.client_id)
    
    # Try to get AI service
    ai_service = None
    try:
        from app.services.ai_service import ai_service as ai_svc
        ai_service = ai_svc
    except Exception as e:
        pass
    
    response = review_service.generate_response(review, client, ai_service)
    
    # Save as suggested response
    review_service.set_suggested_response(review_id, response)
    
    return jsonify({
        'success': True,
        'suggested_response': response
    })


@reviews_bp.route('/generate-all-responses', methods=['POST'])
@token_required
def generate_all_responses(current_user):
    """
    Generate AI responses for all pending reviews
    
    POST /api/reviews/generate-all-responses
    {
        "client_id": "xxx"
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Try to get AI service
    ai_service = None
    try:
        from app.services.ai_service import ai_service as ai_svc
        ai_service = ai_svc
    except Exception as e:
        pass
    
    result = review_service.generate_responses_for_pending(client_id, ai_service)
    
    return jsonify(result)


# ==========================================
# Review Requests
# ==========================================

@reviews_bp.route('/request/send', methods=['POST'])
@token_required
def send_review_request(current_user):
    """
    Send review request to a customer
    
    POST /api/reviews/request/send
    {
        "client_id": "xxx",
        "customer_name": "John Smith",
        "customer_email": "john@example.com",
        "customer_phone": "+19415551234",
        "review_url": "https://g.page/r/xxx/review",
        "service_provided": "Roof Repair",
        "method": "both"  // email, sms, both
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    review_url = data.get('review_url')
    if not review_url:
        return jsonify({'error': 'review_url is required'}), 400
    
    method = data.get('method', 'email')
    results = {'email': False, 'sms': False}
    
    if method in ['email', 'both'] and data.get('customer_email'):
        results['email'] = review_service.send_review_request_email(
            client=client,
            customer_email=data['customer_email'],
            customer_name=data.get('customer_name', ''),
            review_url=review_url,
            service_provided=data.get('service_provided')
        )
    
    if method in ['sms', 'both'] and data.get('customer_phone'):
        results['sms'] = review_service.send_review_request_sms(
            client=client,
            customer_phone=data['customer_phone'],
            customer_name=data.get('customer_name', ''),
            review_url=review_url
        )
    
    return jsonify({
        'success': results['email'] or results['sms'],
        'results': results
    })


@reviews_bp.route('/request/lead/<lead_id>', methods=['POST'])
@token_required
def send_review_request_to_lead(current_user, lead_id):
    """
    Send review request to a converted lead
    
    POST /api/reviews/request/lead/<lead_id>
    {
        "review_url": "https://g.page/r/xxx/review",
        "method": "both"
    }
    """
    from app.models.db_models import DBLead
    
    lead = DBLead.query.get(lead_id)
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    
    if not current_user.has_access_to_client(lead.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    review_url = data.get('review_url')
    
    if not review_url:
        return jsonify({'error': 'review_url is required'}), 400
    
    result = review_service.send_review_request_to_lead(
        lead_id=lead_id,
        review_url=review_url,
        method=data.get('method', 'both')
    )
    
    return jsonify(result)


@reviews_bp.route('/request/bulk', methods=['POST'])
@token_required
def send_bulk_review_requests(current_user):
    """
    Send review requests to recently converted leads
    
    POST /api/reviews/request/bulk
    {
        "client_id": "xxx",
        "review_url": "https://g.page/r/xxx/review",
        "days_since_conversion": 7,
        "method": "email"
    }
    """
    data = request.get_json() or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    review_url = data.get('review_url')
    if not review_url:
        return jsonify({'error': 'review_url is required'}), 400
    
    result = review_service.bulk_send_review_requests(
        client_id=client_id,
        review_url=review_url,
        days_since_conversion=data.get('days_since_conversion', 7),
        method=data.get('method', 'email')
    )
    
    return jsonify(result)


# ==========================================
# Widget
# ==========================================

@reviews_bp.route('/widget', methods=['GET'])
def get_review_widget():
    """
    Get embeddable review widget HTML
    
    GET /api/reviews/widget?client_id=xxx&max_reviews=5
    """
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    config = {
        'max_reviews': safe_int(request.args.get('max_reviews'), 5, max_val=20)
    }
    
    html = review_service.generate_review_widget(client_id, config)
    
    if request.args.get('format') == 'html':
        return html, 200, {'Content-Type': 'text/html'}
    
    return jsonify({'html': html})


# ==========================================
# Review URL Helper
# ==========================================

@reviews_bp.route('/url', methods=['GET'])
@token_required
def get_review_url(current_user):
    """
    Get review URL for a platform
    
    GET /api/reviews/url?client_id=xxx&platform=google
    """
    client_id = request.args.get('client_id')
    platform = request.args.get('platform', 'google')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    url = review_service.get_review_url(client, platform)
    
    return jsonify({
        'platform': platform,
        'url': url
    })
