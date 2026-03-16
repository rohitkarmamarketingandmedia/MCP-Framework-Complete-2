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
    
    # If no SEMRush API, return simulated data
    if not semrush_service.is_configured():
        gaps = _generate_simulated_gaps(client, competitors)
        return jsonify({
            'client_id': client_id,
            'gaps': gaps,
            'competitors': competitor_domains,
            'source': 'simulated'
        })
    
    # ============================================
    # STEP 1: Pull domain_organic for ALL domains
    # ============================================
    database = 'us'
    pull_limit = 500  # Per domain
    
    try:
        # Pull client keywords
        _log.info(f"[KEYWORD-GAP] Pulling domain_organic for {client_domain} (limit={pull_limit})")
        client_result = semrush_service.get_domain_organic_keywords(client_domain, limit=pull_limit, database=database)
        
        client_kw_map = {}
        if not client_result.get('error'):
            for kw in client_result.get('keywords', []):
                keyword = kw.get('keyword', '').lower().strip()
                if keyword:
                    client_kw_map[keyword] = {
                        'position': kw.get('position'),
                        'volume': kw.get('volume', 0),
                        'cpc': kw.get('cpc', 0),
                        'difficulty': kw.get('difficulty', 0),
                        'url': kw.get('url', '')
                    }
        else:
            _log.warning(f"[KEYWORD-GAP] Client domain_organic error: {client_result.get('error')}")
        
        _log.info(f"[KEYWORD-GAP] Client {client_domain}: {len(client_kw_map)} keywords")
        
        # Pull each competitor's keywords
        comp_kw_maps = {}  # {domain: {keyword: {position, volume}}}
        for comp_domain in competitor_domains:
            _log.info(f"[KEYWORD-GAP] Pulling domain_organic for {comp_domain}")
            comp_result = semrush_service.get_domain_organic_keywords(comp_domain, limit=pull_limit, database=database)
            
            comp_map = {}
            if not comp_result.get('error'):
                for kw in comp_result.get('keywords', []):
                    keyword = kw.get('keyword', '').lower().strip()
                    if keyword:
                        comp_map[keyword] = {
                            'position': kw.get('position'),
                            'volume': kw.get('volume', 0)
                        }
            else:
                _log.warning(f"[KEYWORD-GAP] Competitor {comp_domain} error: {comp_result.get('error')}")
            
            comp_kw_maps[comp_domain] = comp_map
            _log.info(f"[KEYWORD-GAP] Competitor {comp_domain}: {len(comp_map)} keywords")
        
        # ============================================
        # STEP 2: Merge into unified keyword map
        # ============================================
        all_keywords = set(client_kw_map.keys())
        for comp_map in comp_kw_maps.values():
            all_keywords.update(comp_map.keys())
        
        _log.info(f"[KEYWORD-GAP] Total unique keywords across all domains: {len(all_keywords)}")
        
        # ============================================
        # STEP 3: Build gap entries with classification
        # ============================================
        transformed_gaps = []
        
        for keyword in all_keywords:
            client_data = client_kw_map.get(keyword, {})
            your_pos = client_data.get('position')
            volume = client_data.get('volume', 0)
            
            # Get competitor positions (ordered by competitor_domains list)
            comp_positions_ordered = []
            best_comp_pos = None
            
            for comp_domain in competitor_domains:
                comp_data = comp_kw_maps.get(comp_domain, {}).get(keyword, {})
                pos = comp_data.get('position')
                comp_positions_ordered.append(pos)
                
                # Get volume from competitor if client doesn't have it
                if not volume and comp_data.get('volume'):
                    volume = comp_data['volume']
                
                # Track best competitor position
                if pos and (best_comp_pos is None or pos < best_comp_pos):
                    best_comp_pos = pos
            
            comp1 = comp_positions_ordered[0] if len(comp_positions_ordered) > 0 else None
            comp2 = comp_positions_ordered[1] if len(comp_positions_ordered) > 1 else None
            
            # ============================================
            # STEP 4: Classify (missing/weak/strong/shared)
            # ============================================
            any_comp_ranks = any(p is not None for p in comp_positions_ordered)
            
            if not your_pos and any_comp_ranks:
                gap_type = 'missing'   # Competitor ranks, you don't
            elif your_pos and best_comp_pos and your_pos > best_comp_pos:
                gap_type = 'weak'      # You rank worse than best competitor
            elif your_pos and best_comp_pos and your_pos < best_comp_pos:
                gap_type = 'strong'    # You rank better
            elif your_pos and any_comp_ranks:
                gap_type = 'shared'    # Both rank, same or close
            elif your_pos and not any_comp_ranks:
                gap_type = 'unique'    # Only you rank
            else:
                gap_type = 'untapped'  # Neither ranks (shouldn't happen in merged set)
            
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
        
        # Stats
        stats = {
            'missing': sum(1 for g in transformed_gaps if g['gap_type'] == 'missing'),
            'weak': sum(1 for g in transformed_gaps if g['gap_type'] == 'weak'),
            'strong': sum(1 for g in transformed_gaps if g['gap_type'] == 'strong'),
            'shared': sum(1 for g in transformed_gaps if g['gap_type'] == 'shared'),
            'unique': sum(1 for g in transformed_gaps if g['gap_type'] == 'unique'),
        }
        
        _log.info(f"[KEYWORD-GAP] Result: {len(transformed_gaps)} total — missing={stats['missing']}, weak={stats['weak']}, strong={stats['strong']}, shared={stats['shared']}, unique={stats['unique']}")
        
        return jsonify({
            'client_id': client_id,
            'gaps': transformed_gaps[:500],  # Return up to 500
            'competitors': competitor_domains,
            'source': 'semrush',
            'database': database,
            'total_keywords': len(transformed_gaps),
            'your_keywords': len(client_kw_map),
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
