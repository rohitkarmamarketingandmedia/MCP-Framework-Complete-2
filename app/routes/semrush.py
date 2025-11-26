"""
MCP Framework - SEMRush Routes
Competitor research, keyword data, and domain analytics API
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.semrush_service import SEMRushService

semrush_bp = Blueprint('semrush', __name__)
semrush_service = SEMRushService()


@semrush_bp.route('/status', methods=['GET'])
@token_required
def get_status(current_user):
    """Check if SEMRush API is configured"""
    return jsonify({
        'configured': semrush_service.is_configured(),
        'message': 'SEMRush API ready' if semrush_service.is_configured() else 'SEMRUSH_API_KEY not set'
    })


# ==========================================
# KEYWORD RESEARCH
# ==========================================

@semrush_bp.route('/keyword', methods=['GET'])
@token_required
def keyword_overview(current_user):
    """
    Get keyword metrics
    
    GET /api/semrush/keyword?keyword=roof+repair+sarasota&database=us
    """
    keyword = request.args.get('keyword')
    database = request.args.get('database', 'us')
    
    if not keyword:
        return jsonify({'error': 'keyword parameter required'}), 400
    
    result = semrush_service.get_keyword_overview(keyword, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/keyword/variations', methods=['GET'])
@token_required
def keyword_variations(current_user):
    """
    Get related keyword variations
    
    GET /api/semrush/keyword/variations?keyword=roof+repair&limit=20&database=us
    """
    keyword = request.args.get('keyword')
    limit = request.args.get('limit', 20, type=int)
    database = request.args.get('database', 'us')
    
    if not keyword:
        return jsonify({'error': 'keyword parameter required'}), 400
    
    result = semrush_service.get_keyword_variations(keyword, limit, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/keyword/questions', methods=['GET'])
@token_required
def keyword_questions(current_user):
    """
    Get question-based keywords (great for FAQ content)
    
    GET /api/semrush/keyword/questions?keyword=roof+repair&limit=10
    """
    keyword = request.args.get('keyword')
    limit = request.args.get('limit', 10, type=int)
    database = request.args.get('database', 'us')
    
    if not keyword:
        return jsonify({'error': 'keyword parameter required'}), 400
    
    result = semrush_service.get_keyword_questions(keyword, limit, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/keyword/bulk', methods=['POST'])
@token_required
def bulk_keyword_overview(current_user):
    """
    Get metrics for multiple keywords
    
    POST /api/semrush/keyword/bulk
    {
        "keywords": ["roof repair sarasota", "roofing company sarasota"],
        "database": "us"
    }
    """
    data = request.get_json()
    keywords = data.get('keywords', [])
    database = data.get('database', 'us')
    
    if not keywords:
        return jsonify({'error': 'keywords array required'}), 400
    
    result = semrush_service.bulk_keyword_overview(keywords, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/keyword/research', methods=['GET'])
@token_required
def keyword_research_package(current_user):
    """
    Complete keyword research package
    
    GET /api/semrush/keyword/research?keyword=roof+repair&location=sarasota
    
    Returns seed metrics, variations, questions, and opportunities
    """
    keyword = request.args.get('keyword')
    location = request.args.get('location', '')
    database = request.args.get('database', 'us')
    
    if not keyword:
        return jsonify({'error': 'keyword parameter required'}), 400
    
    result = semrush_service.keyword_research_package(keyword, location, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


# ==========================================
# DOMAIN / COMPETITOR ANALYSIS
# ==========================================

@semrush_bp.route('/domain', methods=['GET'])
@token_required
def domain_overview(current_user):
    """
    Get domain organic traffic overview
    
    GET /api/semrush/domain?domain=example.com&database=us
    """
    domain = request.args.get('domain')
    database = request.args.get('database', 'us')
    
    if not domain:
        return jsonify({'error': 'domain parameter required'}), 400
    
    result = semrush_service.get_domain_overview(domain, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/domain/keywords', methods=['GET'])
@token_required
def domain_keywords(current_user):
    """
    Get keywords a domain ranks for
    
    GET /api/semrush/domain/keywords?domain=example.com&limit=50
    """
    domain = request.args.get('domain')
    limit = request.args.get('limit', 50, type=int)
    database = request.args.get('database', 'us')
    
    if not domain:
        return jsonify({'error': 'domain parameter required'}), 400
    
    result = semrush_service.get_domain_organic_keywords(domain, limit, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/domain/competitors', methods=['GET'])
@token_required
def domain_competitors(current_user):
    """
    Find organic competitors for a domain
    
    GET /api/semrush/domain/competitors?domain=example.com&limit=10
    """
    domain = request.args.get('domain')
    limit = request.args.get('limit', 10, type=int)
    database = request.args.get('database', 'us')
    
    if not domain:
        return jsonify({'error': 'domain parameter required'}), 400
    
    result = semrush_service.get_competitors(domain, limit, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/domain/gap', methods=['POST'])
@token_required
def keyword_gap(current_user):
    """
    Find keyword gaps vs competitors
    
    POST /api/semrush/domain/gap
    {
        "domain": "example.com",
        "competitors": ["competitor1.com", "competitor2.com"],
        "limit": 50,
        "database": "us"
    }
    """
    data = request.get_json()
    domain = data.get('domain')
    competitors = data.get('competitors', [])
    limit = data.get('limit', 50)
    database = data.get('database', 'us')
    
    if not domain:
        return jsonify({'error': 'domain required'}), 400
    
    if not competitors:
        return jsonify({'error': 'competitors array required'}), 400
    
    result = semrush_service.get_keyword_gap(domain, competitors, limit, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


@semrush_bp.route('/domain/research', methods=['GET'])
@token_required
def full_competitor_research(current_user):
    """
    Complete competitor research package
    
    GET /api/semrush/domain/research?domain=example.com
    
    Returns:
    - Domain overview
    - Top keywords
    - Competitors
    - Keyword gaps
    - Backlink overview
    """
    domain = request.args.get('domain')
    database = request.args.get('database', 'us')
    
    if not domain:
        return jsonify({'error': 'domain parameter required'}), 400
    
    result = semrush_service.full_competitor_research(domain, database)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


# ==========================================
# BACKLINKS
# ==========================================

@semrush_bp.route('/backlinks', methods=['GET'])
@token_required
def backlink_overview(current_user):
    """
    Get backlink profile overview
    
    GET /api/semrush/backlinks?domain=example.com
    """
    domain = request.args.get('domain')
    
    if not domain:
        return jsonify({'error': 'domain parameter required'}), 400
    
    result = semrush_service.get_backlink_overview(domain)
    
    if result.get('error'):
        return jsonify(result), 500
    
    return jsonify(result)


# ==========================================
# CLIENT-SPECIFIC RESEARCH
# ==========================================

@semrush_bp.route('/client/<client_id>/research', methods=['POST'])
@token_required
def client_research(current_user, client_id):
    """
    Run SEMRush research for a client and update their profile
    
    POST /api/semrush/client/{client_id}/research
    {
        "research_type": "full",  // full, keywords, competitors
        "update_client": true
    }
    """
    from app.services.db_service import DataService
    data_service = DataService()
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    research_type = data.get('research_type', 'full')
    update_client = data.get('update_client', True)
    
    results = {}
    
    # Research based on client's website
    if client.website_url:
        if research_type in ['full', 'competitors']:
            results['competitor_research'] = semrush_service.full_competitor_research(client.website_url)
    
    # Research based on primary keywords
    if client.primary_keywords and research_type in ['full', 'keywords']:
        keyword_results = []
        for kw in client.primary_keywords[:5]:  # Limit to 5 to save API units
            kw_research = semrush_service.keyword_research_package(kw, client.geo)
            keyword_results.append(kw_research)
        results['keyword_research'] = keyword_results
    
    # Update client with discovered data if requested
    if update_client and results:
        # Add discovered competitors
        if results.get('competitor_research', {}).get('competitors'):
            existing_comps = set(client.competitors or [])
            new_comps = [c['domain'] for c in results['competitor_research']['competitors'][:5]]
            client.competitors = list(existing_comps | set(new_comps))
        
        # Add discovered keywords
        if results.get('keyword_research'):
            existing_secondary = set(client.secondary_keywords or [])
            for kr in results['keyword_research']:
                for opp in kr.get('opportunities', [])[:3]:
                    existing_secondary.add(opp['keyword'])
            client.secondary_keywords = list(existing_secondary)[:20]
        
        data_service.save_client(client)
        results['client_updated'] = True
        results['client'] = client.to_dict()
    
    return jsonify(results)
