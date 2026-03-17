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


@semrush_bp.route('/test-mobile-db', methods=['GET'])
def test_mobile_db():
    """
    Diagnostic: test which mobile database format SEMrush accepts.
    Tests google.com (always has data) with multiple DB formats.

    GET /api/semrush/test-mobile-db
    """
    api_key = os.environ.get('SEMRUSH_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'No API key'}), 400

    domain = request.args.get('domain', 'google.com')
    formats = ['us_mobile', 'mobile_us', 'us.mobile', 'us-mobile']
    results = {}

    for fmt in formats:
        try:
            resp = requests.get('https://api.semrush.com/', params={
                'type': 'domain_organic',
                'key': api_key,
                'domain': domain,
                'database': fmt,
                'export_columns': 'Ph,Po,Nq',
                'display_limit': 2
            }, timeout=15)
            text = resp.text.strip()
            is_error = text.startswith('ERROR')
            lines = text.split('\n')
            results[fmt] = {
                'status': 'ERROR' if is_error else 'OK',
                'lines': len(lines),
                'preview': text[:300],
            }
        except Exception as e:
            results[fmt] = {'status': 'EXCEPTION', 'error': str(e)}

    return jsonify({'domain': domain, 'results': results})


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
    Keyword Gap Analysis — matches SEMrush Keyword Gap methodology.

    Approach (union-based, per-domain pulls):
      1. Pull domain_organic for EACH domain (client + competitors) with
         IDENTICAL params: database=us, device=desktop, rank ≤ 100.
      2. Build ONE unified keyword set: union(all domain keywords).
      3. For each keyword, map rankings per domain.
      4. Use ONE source for volume / KD / CPC / competition / results
         (first non-zero value across the pulls — they share the same
         database so metrics are consistent).
      5. Classify: missing, weak, strong, shared, untapped, unique.
      6. Filter out any keyword where ALL domains rank > 100 (shouldn't
         exist after the ≤ 100 filter, but safety net).
      7. All domains use the same snapshot timestamp.

    GET /api/semrush/keyword-gap/{client_id}?device=desktop|mobile
    """
    from app.models.db_models import DBClient, DBCompetitor
    from datetime import datetime, timezone
    import logging
    _log = logging.getLogger(__name__)

    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403

    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    # Get active competitors — SEMrush Keyword Gap supports max 4 competitors
    # (total 5 domains: 1 target + up to 4 competitors).
    # Default to top 2 to match the typical SEMrush comparison view.
    max_comps = request.args.get('max_competitors', 4, type=int)
    max_comps = min(max_comps, 4)  # hard cap at 4

    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).limit(max_comps).all()

    competitor_domains = [semrush_service._clean_domain(c.domain)
                          for c in competitors if c.domain]

    client_domain = ''
    if client.website_url:
        client_domain = semrush_service._clean_domain(client.website_url)

    if not client_domain:
        return jsonify({'error': 'Client domain not configured', 'gaps': []}), 400

    if not semrush_service.is_configured():
        return jsonify({
            'error': 'SEMrush API key not configured. Add your API key in Settings to enable live keyword gap analysis.',
            'gaps': [],
            'competitors': competitor_domains,
            'source': 'not_configured'
        }), 503

    # ─── Consistent params for every pull ───
    DATABASE   = 'us'
    DEVICE     = request.args.get('device', 'desktop').lower()
    if DEVICE not in ('desktop', 'mobile'):
        DEVICE = 'desktop'
    PULL_LIMIT = 500        # per domain
    snapshot_ts = datetime.now(timezone.utc).isoformat()

    all_domains = [client_domain] + competitor_domains
    _log.info(f"[KEYWORD-GAP] Union-based pull for {all_domains}, db={DATABASE}")

    try:
        # ============================================
        # STEP 1 — Pull domain_organic per domain
        # ============================================
        domain_results = {}   # domain -> {keyword_lower: {position, metrics…}}
        api_errors = []

        for dom in all_domains:
            result = semrush_service.get_domain_organic_for_gap(
                dom, limit=PULL_LIMIT, database=DATABASE, device=DEVICE
            )
            if result.get('error'):
                api_errors.append(f"{dom}: {result['error']}")
                _log.warning(f"[KEYWORD-GAP] Error pulling {dom}: {result['error']}")
                domain_results[dom] = {}
                continue

            kw_map = {}
            for kw in result.get('keywords', []):
                key = kw['keyword']  # already lowercased
                kw_map[key] = kw
            domain_results[dom] = kw_map
            _log.info(f"[KEYWORD-GAP]   {dom}: {len(kw_map)} keywords")

        # If ALL pulls failed, return a helpful error
        if len(api_errors) == len(all_domains):
            # Check if this is a "NOTHING FOUND" issue (common for mobile)
            all_nothing_found = all('NOTHING FOUND' in e for e in api_errors)
            if all_nothing_found and DEVICE == 'mobile':
                return jsonify({
                    'error': f'No mobile ranking data available in SEMrush for these domains. '
                             f'These sites may not have enough mobile search presence. '
                             f'Try switching to Desktop.',
                    'gaps': [],
                    'competitors': competitor_domains,
                    'source': 'semrush',
                    'device': DEVICE,
                    'total_keywords': 0,
                    'stats': {'missing': 0, 'weak': 0, 'strong': 0,
                              'shared': 0, 'unique': 0, 'untapped': 0},
                }), 200  # 200 so frontend treats it as "no data" not crash
            return jsonify({
                'error': f"All SEMrush API calls failed: {'; '.join(api_errors)}",
                'gaps': []
            }), 502

        # ============================================
        # STEP 2 — Build unified keyword set
        # ============================================
        all_keywords = set()
        for kw_map in domain_results.values():
            all_keywords.update(kw_map.keys())

        _log.info(f"[KEYWORD-GAP] Unified keyword set: {len(all_keywords)} keywords")

        # ============================================
        # STEP 3+4 — Map rankings & pick ONE source for metrics
        # ============================================
        transformed_gaps = []

        for kw_lower in all_keywords:
            # Gather positions for each domain
            your_data = domain_results.get(client_domain, {}).get(kw_lower)
            your_pos = your_data['position'] if your_data else None

            comp_positions_ordered = []
            for comp_dom in competitor_domains:
                comp_data = domain_results.get(comp_dom, {}).get(kw_lower)
                comp_positions_ordered.append(
                    comp_data['position'] if comp_data else None
                )

            # ── Filter: skip if ALL domains rank > 100 or have no rank ──
            has_any_rank = (your_pos is not None) or any(
                p is not None for p in comp_positions_ordered
            )
            if not has_any_rank:
                continue

            # ── ONE source for metrics ──
            # Pick from the first domain that has this keyword
            # (all use same DB so volume/KD/CPC are identical)
            metrics = None
            for dom in all_domains:
                d = domain_results.get(dom, {}).get(kw_lower)
                if d:
                    metrics = d
                    break

            volume = metrics['volume'] if metrics else 0
            kd     = metrics['difficulty'] if metrics else 0
            cpc    = metrics['cpc'] if metrics else 0.0
            com    = metrics['competition'] if metrics else 0.0
            results_count = metrics['results'] if metrics else 0
            display_kw = metrics['keyword_display'] if metrics else kw_lower

            # ── Competitor helpers ──
            comp1 = comp_positions_ordered[0] if len(comp_positions_ordered) > 0 else None
            comp2 = comp_positions_ordered[1] if len(comp_positions_ordered) > 1 else None

            comp_valid = [p for p in comp_positions_ordered if p is not None]
            best_comp  = min(comp_valid) if comp_valid else None
            worst_comp = max(comp_valid) if comp_valid else None
            any_comp   = len(comp_valid) > 0
            all_comp   = (len(competitor_domains) > 0 and
                          all(p is not None for p in comp_positions_ordered))

            # ============================================
            # STEP 5 — Classify (SEMrush definitions)
            # ============================================
            if your_pos and all_comp:
                if your_pos > worst_comp:
                    gap_type = 'weak'
                elif your_pos < best_comp:
                    gap_type = 'strong'
                else:
                    gap_type = 'shared'
            elif your_pos and any_comp:
                gap_type = 'shared'
            elif your_pos and not any_comp:
                gap_type = 'unique'
            elif not your_pos and all_comp:
                gap_type = 'missing'
            elif not your_pos and any_comp:
                gap_type = 'untapped'
            else:
                gap_type = 'untapped'

            # Priority scoring
            vol = volume or 0
            if gap_type == 'missing' and best_comp and best_comp <= 20 and vol >= 30:
                priority = 'HIGH'
            elif gap_type == 'missing' and vol >= 50:
                priority = 'HIGH'
            elif gap_type == 'missing':
                priority = 'HIGH' if vol >= 20 else 'MEDIUM'
            elif gap_type == 'weak' and your_pos and your_pos > 20 and best_comp and best_comp <= 10:
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
                'keyword': display_kw,
                'you': your_pos,
                'comp1': comp1,
                'comp2': comp2,
                'volume': volume,
                'kd': kd,
                'cpc': cpc,
                'com': com,
                'results': results_count,
                'priority': priority,
                'gap_type': gap_type,
            })

        # ============================================
        # Sort: missing first, then by priority + volume
        # ============================================
        type_order = {'missing': 0, 'weak': 1, 'shared': 2, 'strong': 3,
                      'unique': 4, 'untapped': 5}
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}

        transformed_gaps.sort(key=lambda x: (
            type_order.get(x.get('gap_type', 'untapped'), 5),
            priority_order.get(x.get('priority', 'LOW'), 2),
            -(x.get('volume', 0) or 0)
        ))

        # Stats (Shared tab in SEMrush includes weak + strong)
        stats = {
            'missing':  sum(1 for g in transformed_gaps if g['gap_type'] == 'missing'),
            'weak':     sum(1 for g in transformed_gaps if g['gap_type'] == 'weak'),
            'strong':   sum(1 for g in transformed_gaps if g['gap_type'] == 'strong'),
            'shared':   sum(1 for g in transformed_gaps if g['gap_type'] in ('shared', 'weak', 'strong')),
            'unique':   sum(1 for g in transformed_gaps if g['gap_type'] == 'unique'),
            'untapped': sum(1 for g in transformed_gaps if g['gap_type'] == 'untapped'),
        }

        _log.info(
            f"[KEYWORD-GAP] Result: {len(transformed_gaps)} total — "
            f"shared={stats['shared']} (weak={stats['weak']}, strong={stats['strong']}), "
            f"missing={stats['missing']}, untapped={stats['untapped']}, unique={stats['unique']}"
        )

        return jsonify({
            'client_id': client_id,
            'gaps': transformed_gaps[:500],
            'competitors': competitor_domains,
            'source': 'semrush',
            'database': DATABASE,
            'device': DEVICE,
            'snapshot': snapshot_ts,
            'total_keywords': len(transformed_gaps),
            'your_keywords': sum(1 for g in transformed_gaps if g.get('you') is not None),
            'stats': stats,
            'pull_errors': api_errors if api_errors else None,
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
