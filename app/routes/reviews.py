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
        days=safe_int(request.args.get('days'), 90, max_val=3650),
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
    Auto-generates a response suggestion for new reviews.
    
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
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    result = review_service.add_review(client_id, data)
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Auto-generate response suggestion for the new review
    review_id = result.get('review', {}).get('id')
    if review_id:
        try:
            response_result = review_service.generate_response(review_id)
            if response_result.get('suggested_response'):
                result['suggested_response'] = response_result['suggested_response']
                result['auto_response_generated'] = True
        except Exception as e:
            logger.warning(f"Auto-response generation failed for review {review_id}: {e}")
            result['auto_response_generated'] = False
    
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
    
    data = request.get_json(silent=True) or {}
    
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


@reviews_bp.route('/<review_id>/reply', methods=['POST'])
@token_required
def post_review_reply(current_user, review_id):
    """
    Save a reply to a review (moves suggested_response to response_text)
    
    POST /api/reviews/<review_id>/reply
    {"response_text": "Thank you for your review..."}
    """
    review = DBReview.query.get(review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    if not current_user.has_access_to_client(review.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json(silent=True) or {}
    response_text = data.get('response_text', '').strip()
    
    if not response_text:
        return jsonify({'error': 'response_text is required'}), 400
    
    review.response_text = response_text
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'review_id': review_id,
        'response_text': response_text
    })


@reviews_bp.route('/generate-all-responses', methods=['POST'])
@token_required
def generate_all_responses(current_user):
    """
    Generate AI responses for all pending reviews
    
    POST /api/reviews/generate-all-responses?client_id=xxx
    or POST body: {"client_id": "xxx"}
    """
    data = request.get_json(silent=True) or {}
    client_id = request.args.get('client_id') or data.get('client_id')
    
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
    data = request.get_json(silent=True) or {}
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
        'results': results,
        'diagnostics': {
            'sendgrid_configured': bool(review_service.sendgrid_key),
            'from_email': review_service.from_email,
            'to_email': data.get('customer_email'),
            'method': method
        }
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
    
    data = request.get_json(silent=True) or {}
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
    data = request.get_json(silent=True) or {}
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


@reviews_bp.route('/sync', methods=['POST'])
@token_required
def sync_reviews(current_user):
    """
    Sync reviews from Google Places API
    
    POST /api/reviews/sync
    { "client_id": "xxx" }
    
    Requires GOOGLE_PLACES_API_KEY environment variable.
    Uses the client's gbp_location_id (g.page URL or Place ID) to fetch reviews.
    """
    import os
    import requests as http_requests
    import re
    import logging
    
    logger = logging.getLogger(__name__)
    
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    gbp_id = client.gbp_location_id
    if not gbp_id:
        return jsonify({'error': 'No Google Business Profile configured. Go to Settings → Integrations to add your Google review link.'}), 400
    
    api_key = os.environ.get('GOOGLE_PLACES_API_KEY')
    if not api_key:
        return jsonify({'error': 'Google Places API key not configured. Add GOOGLE_PLACES_API_KEY to your server environment variables.'}), 400
    
    try:
        # Extract Place ID from various URL formats
        place_id = None
        debug_info = {'gbp_id': gbp_id, 'steps': []}
        
        if gbp_id.startswith('ChIJ'):
            # Already a Place ID
            place_id = gbp_id
            debug_info['steps'].append('Used as direct Place ID')
        elif 'g.page' in gbp_id or 'google.com' in gbp_id or 'goo.gl' in gbp_id:
            # It's a URL — first try to resolve g.page redirect to get Place ID
            debug_info['steps'].append('Detected URL format')
            
            # Step 1: Try to follow the g.page redirect to get the actual Google Maps URL
            try:
                redirect_resp = http_requests.head(gbp_id.replace('/review', ''), allow_redirects=True, timeout=10)
                final_url = redirect_resp.url
                debug_info['resolved_url'] = final_url
                debug_info['steps'].append(f'Resolved URL: {final_url}')
                
                # Try to extract Place ID or CID from the resolved URL
                # Google Maps URLs often contain: place_id= or !1s (place ID) or data= with CID
                pid_match = re.search(r'place_id[=:]([A-Za-z0-9_-]+)', final_url)
                cid_match = re.search(r'[?&]cid=(\d+)', final_url)
                ftid_match = re.search(r'ftid=(0x[0-9a-f]+:0x[0-9a-f]+)', final_url)
                
                if pid_match:
                    place_id = pid_match.group(1)
                    debug_info['steps'].append(f'Extracted Place ID from URL: {place_id}')
                elif cid_match:
                    debug_info['cid'] = cid_match.group(1)
                    debug_info['steps'].append(f'Found CID: {cid_match.group(1)}, will search by name')
                elif ftid_match:
                    debug_info['ftid'] = ftid_match.group(1)
                    debug_info['steps'].append(f'Found FTID: {ftid_match.group(1)}, will search by name')
            except Exception as e:
                debug_info['steps'].append(f'URL redirect failed: {str(e)}')
            
            # Step 2: If no Place ID yet, search by business name
            if not place_id:
                find_url = 'https://maps.googleapis.com/maps/api/place/findplacefromtext/json'
                
                geo = client.geo or ''
                search_query = f"{client.business_name} {geo}"
                debug_info['search_query'] = search_query
                debug_info['steps'].append(f'Searching Google Places for: {search_query}')
                
                find_resp = http_requests.get(find_url, params={
                    'input': search_query,
                    'inputtype': 'textquery',
                    'fields': 'place_id,name,formatted_address',
                    'key': api_key
                }, timeout=10)
                
                find_data = find_resp.json()
                debug_info['find_response_status'] = find_data.get('status')
                debug_info['find_candidates_count'] = len(find_data.get('candidates', []))
                
                if find_data.get('candidates'):
                    place_id = find_data['candidates'][0].get('place_id')
                    found_name = find_data['candidates'][0].get('name', '')
                    debug_info['steps'].append(f'Found: {found_name} → Place ID: {place_id}')
                    logger.info(f"Resolved Place ID: {place_id} for '{search_query}'")
                else:
                    logger.warning(f"No Place ID found for '{search_query}', API status: {find_data.get('status')}")
                    debug_info['steps'].append(f'No results found. API status: {find_data.get("status")}')
                    if find_data.get('error_message'):
                        debug_info['api_error'] = find_data['error_message']
                    return jsonify({
                        'error': f'Could not find "{client.business_name}" on Google Maps. Make sure your business name and location are correct.',
                        'debug': debug_info
                    }), 404
        else:
            # Assume it's a Place ID or location ID
            place_id = gbp_id
            debug_info['steps'].append('Used as-is (assumed Place ID)')
        
        if not place_id:
            return jsonify({
                'error': 'Could not determine Place ID from your Google Business link.',
                'debug': debug_info
            }), 400
        
        debug_info['place_id'] = place_id
        debug_info['steps'].append(f'Using Place ID: {place_id}')
        
        # Fetch Place Details with reviews
        details_url = 'https://maps.googleapis.com/maps/api/place/details/json'
        details_resp = http_requests.get(details_url, params={
            'place_id': place_id,
            'fields': 'reviews,rating,user_ratings_total,name',
            'key': api_key
        }, timeout=10)
        
        details_data = details_resp.json()
        debug_info['details_status'] = details_data.get('status')
        
        if details_data.get('status') != 'OK':
            error_msg = details_data.get('error_message', details_data.get('status', 'Unknown error'))
            debug_info['steps'].append(f'Place Details API error: {error_msg}')
            return jsonify({'error': f'Google API error: {error_msg}', 'debug': debug_info}), 400
        
        result = details_data.get('result', {})
        google_reviews = result.get('reviews', [])
        
        if not google_reviews:
            return jsonify({
                'message': 'No reviews found on Google for this business.',
                'synced': 0,
                'total_rating': result.get('rating'),
                'total_reviews': result.get('user_ratings_total', 0)
            })
        
        # Import reviews into database
        import uuid
        synced_count = 0
        skipped_count = 0
        
        for gr in google_reviews:
            author = gr.get('author_name', 'Anonymous')
            rating = gr.get('rating', 5)
            text = gr.get('text', '')
            time_val = gr.get('time', 0)
            
            # Check for duplicates by reviewer name + rating + approximate date
            from sqlalchemy import and_
            existing = DBReview.query.filter(
                and_(
                    DBReview.client_id == client_id,
                    DBReview.platform == 'google',
                    DBReview.reviewer_name == author,
                    DBReview.rating == rating
                )
            ).first()
            
            if existing:
                # Update text if changed
                if text and existing.review_text != text:
                    existing.review_text = text
                    db.session.commit()
                skipped_count += 1
                continue
            
            # Create new review
            review_date = datetime.utcfromtimestamp(time_val) if time_val else datetime.utcnow()
            
            review = DBReview(
                id=str(uuid.uuid4())[:8],
                client_id=client_id,
                platform='google',
                platform_review_id=gr.get('author_url', ''),
                reviewer_name=author,
                reviewer_avatar=gr.get('profile_photo_url'),
                rating=rating,
                review_text=text,
                review_date=review_date,
                status='pending',
                sentiment='positive' if rating >= 4 else ('negative' if rating <= 2 else 'neutral')
            )
            
            db.session.add(review)
            synced_count += 1
        
        db.session.commit()
        
        # Auto-generate responses for new reviews
        auto_responded = 0
        if synced_count > 0:
            new_reviews = DBReview.query.filter(
                DBReview.client_id == client_id,
                DBReview.status == 'pending',
                DBReview.suggested_response.is_(None)
            ).limit(10).all()
            
            for rev in new_reviews:
                try:
                    review_service.generate_response(rev.id)
                    auto_responded += 1
                except Exception as e:
                    logger.warning(f"Auto-response failed for review {rev.id}: {e}")
        
        return jsonify({
            'success': True,
            'synced': synced_count,
            'skipped': skipped_count,
            'auto_responded': auto_responded,
            'total_rating': result.get('rating'),
            'total_reviews': result.get('user_ratings_total', 0),
            'message': f'Synced {synced_count} new reviews ({skipped_count} already existed)',
            'debug': debug_info
        })
        
    except http_requests.exceptions.Timeout:
        return jsonify({'error': 'Google API request timed out. Please try again.'}), 504
    except Exception as e:
        logger.error(f"Review sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500


import logging
logger = logging.getLogger(__name__)
