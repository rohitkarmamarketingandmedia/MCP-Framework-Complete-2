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
    Get keyword gap analysis for a client vs their tracked competitors
    
    GET /api/semrush/keyword-gap/{client_id}
    
    Returns keywords where competitors rank but client doesn't (or ranks worse)
    """
    from app.models.db_models import DBClient, DBCompetitor
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get competitors
    competitors = DBCompetitor.query.filter_by(
        client_id=client_id,
        is_active=True
    ).limit(2).all()
    
    # If no SEMRush API, return sample gap data based on client keywords
    if not semrush_service.is_configured():
        gaps = []
        keywords = client.get_primary_keywords() + client.get_secondary_keywords()
        geo = client.geo or ''
        geo_lower = geo.lower().strip()
        
        # Extract just the city name (before comma or state)
        city_name = geo_lower.split(',')[0].strip() if ',' in geo_lower else geo_lower.split()[0] if geo_lower else ''
        
        for kw in keywords[:15]:
            # Only append geo if keyword doesn't already contain the city name
            kw_lower = kw.lower()
            
            # Check if city is already in keyword (handles "sarasota seo" case)
            already_has_geo = city_name and city_name in kw_lower
            
            if geo and not already_has_geo:
                full_kw = f"{kw} {geo}".strip()
            else:
                full_kw = kw.strip()
            
            gaps.append({
                'keyword': full_kw,
                'you': None if len(gaps) % 3 == 0 else (len(gaps) % 20 + 5),
                'comp1': (len(gaps) % 15 + 1) if competitors else None,
                'comp2': (len(gaps) % 18 + 3) if len(competitors) > 1 else None,
                'volume': (len(gaps) + 1) * 200,
                'priority': 'HIGH' if len(gaps) % 3 == 0 else ('MEDIUM' if len(gaps) % 2 == 0 else 'LOW')
            })
        
        return jsonify({
            'client_id': client_id,
            'gaps': gaps,
            'competitors': [c.domain for c in competitors],
            'source': 'simulated'
        })
    
    # Use real SEMRush data - use domain_domains for proper comparison
    client_domain = client.website_url.replace('https://', '').replace('http://', '').split('/')[0] if client.website_url else ''
    competitor_domains = [c.domain for c in competitors]
    
    if not client_domain:
        return jsonify({
            'error': 'Client domain not configured',
            'gaps': []
        }), 400
    
    # Use domain_domains comparison for ALL shared keywords (no restrictive filter)
    try:
        result = None
        used_comparison = False
        
        if competitor_domains:
            import logging
            logging.getLogger(__name__).info(f"Trying domain_domains for {client_domain} vs {competitor_domains}")
            result = semrush_service.get_keyword_comparison(client_domain, competitor_domains, limit=500)
            
            # If domain_domains returns error or empty, fall back to individual domain_organic calls
            if result.get('error') or not result.get('keywords'):
                import logging
                logging.getLogger(__name__).info(f"domain_domains returned nothing for {client_domain}, falling back to domain_organic")
                result = None  # Will trigger fallback below
            else:
                used_comparison = True
        
        if result is None:
            # Fallback: get organic keywords for each domain individually and merge
            client_result = semrush_service.get_domain_organic_keywords(client_domain, limit=200)
            
            if client_result.get('error'):
                return jsonify({
                    'client_id': client_id,
                    'gaps': [],
                    'competitors': competitor_domains,
                    'source': 'error',
                    'error': client_result.get('error')
                })
            
            # Build keyword map for client
            client_kw_map = {}
            for kw in client_result.get('keywords', []):
                client_kw_map[kw['keyword']] = kw
            
            # Get competitor keywords
            comp_kw_maps = []
            for comp_domain in competitor_domains[:2]:
                comp_result = semrush_service.get_domain_organic_keywords(comp_domain, limit=200)
                comp_map = {}
                for kw in comp_result.get('keywords', []):
                    comp_map[kw['keyword']] = kw
                comp_kw_maps.append(comp_map)
            
            # Merge all keywords
            all_keywords = set(client_kw_map.keys())
            for comp_map in comp_kw_maps:
                all_keywords.update(comp_map.keys())
            
            # Build result in same format as comparison
            merged_keywords = []
            for kw_text in all_keywords:
                client_data = client_kw_map.get(kw_text, {})
                your_pos = client_data.get('position')
                volume = client_data.get('volume', 0)
                
                comp_positions = {}
                for i, comp_map in enumerate(comp_kw_maps):
                    comp_data = comp_map.get(kw_text, {})
                    pos = comp_data.get('position')
                    if not volume and comp_data.get('volume'):
                        volume = comp_data['volume']
                    if competitor_domains and i < len(competitor_domains):
                        comp_positions[competitor_domains[i]] = pos
                
                merged_keywords.append({
                    'keyword': kw_text,
                    'volume': volume,
                    'your_position': your_pos,
                    'competitor_positions': comp_positions
                })
            
            result = {
                'keywords': merged_keywords,
                'count': len(merged_keywords)
            }
            used_comparison = False
            
            # Debug: log sample data
            import logging
            _log = logging.getLogger(__name__)
            _log.info(f"Keyword gap fallback for {client_domain}: {len(merged_keywords)} merged keywords")
            if merged_keywords:
                sample = merged_keywords[0]
                _log.info(f"  Sample keyword: {sample}")
                _log.info(f"  Client keywords found: {len(client_kw_map)}")
                if client_kw_map:
                    first_client = list(client_kw_map.values())[0]
                    _log.info(f"  First client kw data: {first_client}")
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(f"Keyword gap exception for {client_id}: {e}\n{traceback.format_exc()}")
        return jsonify({
            'client_id': client_id,
            'gaps': [],
            'competitors': competitor_domains if competitor_domains else [],
            'source': 'error',
            'error': str(e)
        }), 500
    
    # Transform to frontend format
    transformed_gaps = []
    
    for kw in result.get('keywords', []):
        your_pos = kw.get('your_position')
        comp_positions = kw.get('competitor_positions', {})
        comp_list = list(comp_positions.values())
        comp1 = comp_list[0] if len(comp_list) > 0 else None
        comp2 = comp_list[1] if len(comp_list) > 1 else None
        volume = kw.get('volume', 0)
        
        # Calculate priority
        y = your_pos or 999
        c1 = comp1 or 999
        if not your_pos and (comp1 or comp2):
            priority = 'HIGH'  # They rank, you don't
        elif your_pos and your_pos > 20 and c1 <= 10:
            priority = 'HIGH'
        elif your_pos and your_pos > 10 and c1 <= 5:
            priority = 'HIGH'
        elif your_pos and comp1 and your_pos > comp1 + 10:
            priority = 'MEDIUM'
        else:
            priority = 'LOW'
        
        transformed_gaps.append({
            'keyword': kw.get('keyword', ''),
            'you': your_pos,
            'comp1': comp1,
            'comp2': comp2,
            'volume': volume,
            'priority': priority
        })
    
    # Sort: Keywords where you rank first (shows your positions), then high-priority gaps
    # This matches SEMrush's default view which shows all rankings
    def gap_sort_key(x):
        has_you = 1 if x.get('you') else 2  # Keywords where you rank come first
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        pri = priority_order.get(x.get('priority', 'LOW'), 2)
        vol = -(x.get('volume', 0) or 0)
        return (has_you, pri, vol)
    
    transformed_gaps.sort(key=gap_sort_key)
    
    # Debug log
    import logging
    _log = logging.getLogger(__name__)
    _log.info(f"Keyword gap result: {len(transformed_gaps)} gaps for {client_id}")
    if transformed_gaps:
        _log.info(f"  First gap: {transformed_gaps[0]}")
        with_pos = [g for g in transformed_gaps if g.get('you')]
        _log.info(f"  Gaps with 'you' position: {len(with_pos)}")
        with_vol = [g for g in transformed_gaps if g.get('volume')]
        _log.info(f"  Gaps with volume: {len(with_vol)}")
    
    return jsonify({
        'client_id': client_id,
        'gaps': transformed_gaps[:200],  # Top 200
        'competitors': competitor_domains,
        'source': 'semrush',
        'total_keywords': result.get('count', len(transformed_gaps)),
        'your_keywords': sum(1 for g in transformed_gaps if g.get('you')),
        'filtered_by_industry': False
    })


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
