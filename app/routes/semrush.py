"""
MCP Framework - SEMRush Routes
Competitor research, keyword data, and domain analytics API
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.semrush_service import SEMRushService
from app.database import db
import os
import requests

semrush_bp = Blueprint('semrush', __name__)
semrush_service = SEMRushService()


@semrush_bp.route('/check-units', methods=['GET'])
def check_units():
    """Check SEMrush API units balance directly - no auth needed for diagnostics"""
    api_key = os.environ.get('SEMRUSH_API_KEY', '')
    
    if not api_key:
        return jsonify({'error': 'SEMRUSH_API_KEY not set'})
    
    results = {
        'key_prefix': api_key[:8] + '...',
        'key_length': len(api_key),
    }
    
    # Try the direct API units check
    try:
        resp = requests.get(
            'https://www.semrush.com/users/countapiunits.html',
            params={'key': api_key},
            timeout=10
        )
        results['units_check'] = {
            'status_code': resp.status_code,
            'response': resp.text.strip()[:200]
        }
    except Exception as e:
        results['units_check'] = {'error': str(e)}
    
    # Try a minimal API call to test
    try:
        resp = requests.get(
            'https://api.semrush.com/',
            params={
                'type': 'domain_rank',
                'key': api_key,
                'domain': 'google.com',
                'database': 'us',
                'export_columns': 'Dn,Rk'
            },
            timeout=10
        )
        results['test_call'] = {
            'status_code': resp.status_code,
            'response': resp.text.strip()[:300]
        }
    except Exception as e:
        results['test_call'] = {'error': str(e)}
    
    return jsonify(results)


@semrush_bp.route('/status', methods=['GET'])
@token_required
def get_status(current_user):
    """Check if SEMRush API is configured"""
    
    # Read env var directly
    api_key_direct = os.environ.get('SEMRUSH_API_KEY', '')
    
    # Read via service property
    api_key_service = semrush_service.api_key
    
    # List all env vars with SEMRUSH in name (for debugging)
    semrush_vars = {k: len(v) for k, v in os.environ.items() if 'SEMRUSH' in k.upper()}
    
    configured = semrush_service.is_configured()
    
    return jsonify({
        'configured': configured,
        'message': 'SEMRush API ready' if configured else 'SEMRUSH_API_KEY not set in environment',
        'debug': {
            'direct_env_length': len(api_key_direct),
            'service_key_length': len(api_key_service),
            'semrush_env_vars': semrush_vars,
            'all_env_var_count': len(os.environ)
        }
    })


@semrush_bp.route('/test', methods=['GET'])
@token_required
def test_api(current_user):
    """
    Test SEMRush API with a real call
    
    GET /api/semrush/test?domain=example.com
    """
    api_key = os.environ.get('SEMRUSH_API_KEY', '')
    domain = request.args.get('domain', 'cliffsac.com')
    
    if not api_key:
        return jsonify({
            'success': False,
            'error': 'SEMRUSH_API_KEY not configured',
            'configured': False
        })
    
    try:
        # Make a simple API call to get domain overview
        params = {
            'type': 'domain_rank',
            'key': api_key,
            'domain': domain,
            'database': 'us',
            'export_columns': 'Dn,Rk,Or,Ot,Oc,Ad,At,Ac'
        }
        
        response = requests.get('https://api.semrush.com/', params=params, timeout=30)
        
        result = {
            'success': response.status_code == 200,
            'configured': True,
            'api_key_length': len(api_key),
            'status_code': response.status_code,
            'domain': domain,
            'response_length': len(response.text),
            'response_preview': response.text[:500] if response.text else 'Empty response'
        }
        
        # Check for API errors
        if response.text.startswith('ERROR'):
            result['success'] = False
            result['error'] = response.text[:200]
            result['error_type'] = 'api_error'
            
            # Common error translations
            if 'ERROR 132' in response.text:
                result['error_message'] = 'API units balance is zero. Add more API units to your SEMrush account.'
            elif 'ERROR 120' in response.text:
                result['error_message'] = 'Invalid API key'
            elif 'ERROR 134' in response.text:
                result['error_message'] = 'API access denied'
        else:
            # Parse successful response
            lines = response.text.strip().split('\n')
            if len(lines) > 1:
                headers = lines[0].split(';')
                values = lines[1].split(';') if len(lines) > 1 else []
                result['data'] = dict(zip(headers, values)) if len(headers) == len(values) else None
                result['raw_headers'] = headers
                result['raw_values'] = values
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'configured': True,
            'error': str(e),
            'error_type': 'exception'
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
    data = request.get_json(silent=True) or {}
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
    data = request.get_json(silent=True) or {}
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
    
    data = request.get_json(silent=True) or {}
    research_type = data.get('research_type', 'full')
    update_client = data.get('update_client', True)
    
    results = {}
    
    # Research based on client's website
    if client.website_url:
        if research_type in ['full', 'competitors']:
            results['competitor_research'] = semrush_service.full_competitor_research(client.website_url)
    
    # Research based on primary keywords
    primary_kws = client.get_primary_keywords()
    if primary_kws and research_type in ['full', 'keywords']:
        keyword_results = []
        for kw in primary_kws[:5]:  # Limit to 5 to save API units
            kw_research = semrush_service.keyword_research_package(kw, client.geo)
            keyword_results.append(kw_research)
        results['keyword_research'] = keyword_results
    
    # Update client with discovered data if requested
    if update_client and results:
        # Add discovered competitors
        if results.get('competitor_research', {}).get('competitors'):
            existing_comps = set(client.get_competitors())
            new_comps = [c['domain'] for c in results['competitor_research']['competitors'][:5]]
            client.set_competitors(list(existing_comps | set(new_comps)))
        
        # Add discovered keywords
        if results.get('keyword_research'):
            existing_secondary = set(client.get_secondary_keywords())
            for kr in results['keyword_research']:
                for opp in kr.get('opportunities', [])[:3]:
                    existing_secondary.add(opp['keyword'])
            client.set_secondary_keywords(list(existing_secondary)[:20])
        
        data_service.save_client(client)
        results['client_updated'] = True
        results['client'] = client.to_dict()
    
    return jsonify(results)


@semrush_bp.route('/keyword-gap/<client_id>', methods=['GET'])
@token_required
def client_keyword_gap(current_user, client_id):
    """
    Keyword Gap Analysis — replicates SEMrush Keyword Gap logic.
    
    1. Pulls domain_organic for client + each competitor individually
    2. Merges into unified keyword map
    3. Classifies: missing, weak, strong, shared
    4. Returns sorted by priority
    
    GET /api/semrush/keyword-gap/{client_id}
    """
    from app.models.db_models import DBClient, DBCompetitor
    import logging
    _log = logging.getLogger(__name__)
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get ALL active competitors (not limited to 2)
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).limit(5).all()
    
    competitor_domains = [semrush_service._clean_domain(c.domain) for c in competitors if c.domain]
    
    client_domain = ''
    if client.website_url:
        client_domain = semrush_service._clean_domain(client.website_url)
    
    if not client_domain:
        return jsonify({'error': 'Client domain not configured', 'gaps': []}), 400
    
    # If no SEMRush API, return error — no demo/simulated data
    if not semrush_service.is_configured():
        return jsonify({
            'error': 'SEMrush API key not configured. Add your API key in Settings to enable live keyword gap analysis.',
            'gaps': [],
            'competitors': competitor_domains,
            'source': 'not_configured'
        }), 503
    
    # ============================================
    # STEP 1: Use SEMrush native domain_domains API
    # This matches SEMrush's Keyword Gap tool exactly
    # ============================================
    database = 'us'
    pull_limit = 500

    try:
        _log.info(f"[KEYWORD-GAP] Using domain_domains API for {client_domain} vs {competitor_domains}")
        comparison = semrush_service.get_keyword_comparison(
            client_domain, competitor_domains, limit=pull_limit, database=database
        )

        if comparison.get('error'):
            _log.warning(f"[KEYWORD-GAP] domain_domains error: {comparison.get('error')}")
            return jsonify({
                'error': f"SEMrush API error: {comparison.get('error')}",
                'gaps': []
            }), 502

        raw_keywords = comparison.get('keywords', [])
        _log.info(f"[KEYWORD-GAP] domain_domains returned {len(raw_keywords)} keywords")

        # ============================================
        # STEP 2: Transform and classify each keyword
        # ============================================
        transformed_gaps = []

        for kw_data in raw_keywords:
            keyword = kw_data.get('keyword', '').strip()
            if not keyword:
                continue

            your_pos = kw_data.get('your_position')
            volume = kw_data.get('volume', 0)

            # Get competitor positions in order
            comp_positions = kw_data.get('competitor_positions', {})
            comp_positions_ordered = []
            for comp_domain in competitor_domains:
                pos = comp_positions.get(comp_domain)
                comp_positions_ordered.append(pos)

            comp1 = comp_positions_ordered[0] if len(comp_positions_ordered) > 0 else None
            comp2 = comp_positions_ordered[1] if len(comp_positions_ordered) > 1 else None

            # Best/worst competitor positions
            comp_positions_valid = [p for p in comp_positions_ordered if p is not None]
            best_comp_pos = min(comp_positions_valid) if comp_positions_valid else None
            worst_comp_pos = max(comp_positions_valid) if comp_positions_valid else None
            any_comp_ranks = len(comp_positions_valid) > 0
            all_comp_rank = (len(comp_positions_ordered) > 0 and
                            all(p is not None for p in comp_positions_ordered))

            # ============================================
            # Classify (SEMrush Keyword Gap logic)
            # ============================================
            # Shared  = ALL domains rank (you + every competitor)
            #   Weak   = subset: you rank worse than ALL competitors
            #   Strong = subset: you rank better than ALL competitors
            # Missing = you don't rank, ALL competitors rank
            # Untapped = you don't rank, only SOME competitors rank
            # Unique  = only you rank, no competitors rank
            if your_pos and all_comp_rank:
                if your_pos > worst_comp_pos:
                    gap_type = 'weak'
                elif your_pos < best_comp_pos:
                    gap_type = 'strong'
                else:
                    gap_type = 'shared'
            elif your_pos and any_comp_ranks:
                gap_type = 'shared'
            elif your_pos and not any_comp_ranks:
                gap_type = 'unique'
            elif not your_pos and all_comp_rank:
                gap_type = 'missing'
            elif not your_pos and any_comp_ranks:
                gap_type = 'untapped'
            else:
                gap_type = 'untapped'

            # Priority based on gap type, position, and volume
            vol = volume or 0

            if gap_type == 'missing' and best_comp_pos and best_comp_pos <= 20 and vol >= 30:
                priority = 'HIGH'
            elif gap_type == 'missing' and vol >= 50:
                priority = 'HIGH'
            elif gap_type == 'missing':
                priority = 'HIGH' if vol >= 20 else 'MEDIUM'
            elif gap_type == 'weak' and your_pos and your_pos > 20 and best_comp_pos and best_comp_pos <= 10:
                priority = 'HIGH'
            elif gap_type == 'strong' and your_pos and your_pos <= 3 and vol >= 50:
                priority = 'HIGH'
            elif gap_type == 'strong' and your_pos and your_pos <= 10 and vol >= 100:
                priority = 'HIGH'
            elif your_pos and your_pos <= 10 and vol >= 30:
                priority = 'MEDIUM'
            elif your_pos and your_pos <= 20 and vol >= 50:
                priority = 'MEDIUM'
            elif your_pos and your_pos <= 50:
                priority = 'MEDIUM'
            elif vol < 20:
                priority = 'LOW'
            else:
                priority = 'MEDIUM'

            transformed_gaps.append({
                'keyword': keyword,
                'you': your_pos,
                'comp1': comp1,
                'comp2': comp2,
                'volume': volume,
                'kd': kw_data.get('difficulty', 0),
                'cpc': kw_data.get('cpc', 0),
                'com': kw_data.get('competition', 0),
                'results': kw_data.get('results', 0),
                'priority': priority,
                'gap_type': gap_type
            })
        
        # ============================================
        # STEP 5: Sort — missing first, then by priority and volume
        # ============================================
        type_order = {'missing': 0, 'weak': 1, 'shared': 2, 'strong': 3, 'unique': 4, 'untapped': 5}
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        
        transformed_gaps.sort(key=lambda x: (
            type_order.get(x.get('gap_type', 'untapped'), 5),
            priority_order.get(x.get('priority', 'LOW'), 2),
            -(x.get('volume', 0) or 0)
        ))
        
        # Stats — note: Shared tab in SEMrush includes weak+strong as subsets
        stats = {
            'missing': sum(1 for g in transformed_gaps if g['gap_type'] == 'missing'),
            'weak': sum(1 for g in transformed_gaps if g['gap_type'] == 'weak'),
            'strong': sum(1 for g in transformed_gaps if g['gap_type'] == 'strong'),
            'shared': sum(1 for g in transformed_gaps if g['gap_type'] in ('shared', 'weak', 'strong')),
            'unique': sum(1 for g in transformed_gaps if g['gap_type'] == 'unique'),
            'untapped': sum(1 for g in transformed_gaps if g['gap_type'] == 'untapped'),
        }

        _log.info(f"[KEYWORD-GAP] Result: {len(transformed_gaps)} total — shared={stats['shared']} (weak={stats['weak']}, strong={stats['strong']}), missing={stats['missing']}, untapped={stats['untapped']}, unique={stats['unique']}")
        
        return jsonify({
            'client_id': client_id,
            'gaps': transformed_gaps[:500],  # Return up to 500
            'competitors': competitor_domains,
            'source': 'semrush',
            'database': database,
            'total_keywords': len(transformed_gaps),
            'your_keywords': sum(1 for g in transformed_gaps if g.get('you') is not None),
            'stats': stats,
            'filtered_by_industry': False
        })
        
    except Exception as e:
        import traceback
        _log.error(f"[KEYWORD-GAP] Exception: {e}\n{traceback.format_exc()}")
        return jsonify({
            'client_id': client_id,
            'gaps': [],
            'competitors': competitor_domains,
            'source': 'error',
            'error': str(e)
        }), 500


def _generate_simulated_gaps(client, competitors):
    """Generate simulated gap data when SEMrush is not configured"""
    gaps = []
    keywords = client.get_primary_keywords() + client.get_secondary_keywords()
    geo = client.geo or ''
    geo_lower = geo.lower().strip()
    city_name = geo_lower.split(',')[0].strip() if ',' in geo_lower else geo_lower.split()[0] if geo_lower else ''
    
    for kw in keywords[:15]:
        kw_lower = kw.lower()
        already_has_geo = city_name and city_name in kw_lower
        full_kw = kw.strip() if already_has_geo else f"{kw} {geo}".strip() if geo else kw.strip()
        
        gaps.append({
            'keyword': full_kw,
            'you': None if len(gaps) % 3 == 0 else (len(gaps) % 20 + 5),
            'comp1': (len(gaps) % 15 + 1) if competitors else None,
            'comp2': (len(gaps) % 18 + 3) if len(competitors) > 1 else None,
            'volume': (len(gaps) + 1) * 200,
            'priority': 'HIGH' if len(gaps) % 3 == 0 else ('MEDIUM' if len(gaps) % 2 == 0 else 'LOW'),
            'gap_type': 'missing' if len(gaps) % 3 == 0 else 'weak'
        })
    
    return gaps


@semrush_bp.route('/sync-keywords/<client_id>', methods=['POST'])
@token_required
def sync_keywords_from_semrush(current_user, client_id):
    """
    Pull ALL organic keywords from SEMrush and update client's keyword list
    
    POST /api/semrush/sync-keywords/{client_id}
    """
    from app.models.db_models import DBClient
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not semrush_service.is_configured():
        return jsonify({'error': 'SEMrush API not configured'}), 400
    
    client_domain = client.website_url.replace('https://', '').replace('http://', '').split('/')[0] if client.website_url else ''
    if not client_domain:
        return jsonify({'error': 'Client domain not configured'}), 400
    
    # Pull up to 200 organic keywords sorted by volume
    result = semrush_service.get_domain_organic_keywords(client_domain, limit=200)
    
    if result.get('error'):
        return jsonify(result), 500
    
    semrush_keywords = [kw['keyword'] for kw in result.get('keywords', []) if kw.get('position', 999) <= 100]
    
    if not semrush_keywords:
        return jsonify({'error': 'No keywords found for this domain', 'synced': 0}), 200
    
    # Merge with existing keywords (don't remove manually added ones)
    existing_primary = set(client.get_primary_keywords())
    existing_secondary = set(client.get_secondary_keywords())
    all_existing = existing_primary | existing_secondary
    
    # New keywords from SEMrush that aren't already tracked
    new_keywords = [kw for kw in semrush_keywords if kw not in all_existing]
    
    # Top 20 by volume go to primary, rest to secondary
    top_semrush = semrush_keywords[:20]
    rest_semrush = semrush_keywords[20:]
    
    # Merge: keep existing primary + add top SEMrush keywords not already there
    updated_primary = list(existing_primary)
    for kw in top_semrush:
        if kw not in existing_primary and kw not in existing_secondary:
            updated_primary.append(kw)
    
    updated_secondary = list(existing_secondary)
    for kw in rest_semrush:
        if kw not in existing_primary and kw not in existing_secondary:
            updated_secondary.append(kw)
    
    # Save
    client.primary_keywords = ', '.join(updated_primary[:50])  # Cap at 50 primary
    client.secondary_keywords = ', '.join(updated_secondary[:100])  # Cap at 100 secondary
    
    db.session.commit()
    
    return jsonify({
        'synced': len(new_keywords),
        'total_from_semrush': len(semrush_keywords),
        'primary_count': len(updated_primary),
        'secondary_count': len(updated_secondary),
        'new_keywords': new_keywords[:20],  # Preview of what was added
        'source': 'semrush'
    })
