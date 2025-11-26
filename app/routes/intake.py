"""
MCP Framework - Intake Routes
Client onboarding with SEMRush research integration
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.ai_service import AIService
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from app.services.semrush_service import SEMRushService
from app.models.db_models import DBClient, DBBlogPost, DBSocialPost, ContentStatus

intake_bp = Blueprint('intake', __name__)
ai_service = AIService()
seo_service = SEOService()
data_service = DataService()
semrush_service = SEMRushService()


@intake_bp.route('/analyze', methods=['POST'])
@token_required
def analyze_transcript(current_user):
    """
    Analyze client interview transcript and extract structured data
    
    POST /api/intake/analyze
    {
        "transcript": "Full transcript text from discovery call...",
        "industry_hint": "roofing"
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    if not data.get('transcript'):
        return jsonify({'error': 'transcript is required'}), 400
    
    transcript = data['transcript']
    industry_hint = data.get('industry_hint', '')
    
    # Build extraction prompt
    prompt = _build_extraction_prompt(transcript, industry_hint)
    
    # Call AI for extraction
    result = ai_service._call_openai(prompt, max_tokens=3000)
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    # Parse the response
    extracted = _parse_extraction_response(result.get('content', ''))
    
    if extracted.get('error'):
        return jsonify({'error': extracted['error']}), 500
    
    return jsonify({
        'success': True,
        'extracted': extracted
    })


@intake_bp.route('/research', methods=['POST'])
@token_required
def research_domain(current_user):
    """
    Research a domain using SEMRush before creating client
    
    POST /api/intake/research
    {
        "website": "https://example.com",
        "primary_keyword": "roof repair",
        "location": "Sarasota, FL"
    }
    
    Returns competitor data, keyword suggestions, and more
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    website = data.get('website', '')
    primary_keyword = data.get('primary_keyword', '')
    location = data.get('location', '')
    
    results = {
        'semrush_available': semrush_service.is_configured(),
        'domain_research': None,
        'keyword_research': None,
        'competitors': [],
        'keyword_suggestions': [],
        'questions': [],
        'keyword_gaps': []
    }
    
    if not semrush_service.is_configured():
        return jsonify({
            'success': True,
            'warning': 'SEMRush API not configured - skipping research',
            'results': results
        })
    
    # Research domain if provided
    if website:
        try:
            domain_research = semrush_service.full_competitor_research(website)
            if not domain_research.get('error'):
                results['domain_research'] = domain_research.get('overview')
                results['competitors'] = domain_research.get('competitors', [])[:5]
                results['keyword_gaps'] = domain_research.get('keyword_gaps', [])[:20]
        except Exception as e:
            results['domain_error'] = str(e)
    
    # Research primary keyword if provided
    if primary_keyword:
        try:
            search_term = f"{primary_keyword} {location}".strip() if location else primary_keyword
            keyword_research = semrush_service.keyword_research_package(primary_keyword, location)
            if not keyword_research.get('error'):
                results['keyword_research'] = keyword_research.get('seed_metrics')
                results['keyword_suggestions'] = keyword_research.get('variations', [])[:15]
                results['questions'] = keyword_research.get('questions', [])[:10]
                results['opportunities'] = keyword_research.get('opportunities', [])[:10]
        except Exception as e:
            results['keyword_error'] = str(e)
    
    return jsonify({
        'success': True,
        'results': results
    })


@intake_bp.route('/pipeline', methods=['POST'])
@token_required
def full_pipeline(current_user):
    """
    Complete intake-to-content pipeline with SEMRush research
    Creates client + researches + generates all content
    
    POST /api/intake/pipeline
    {
        "business_name": "ABC Roofing",
        "website": "https://abcroofing.com",
        "industry": "roofing",
        "geo": "Sarasota, FL",
        "phone": "941-555-1234",
        "email": "info@abcroofing.com",
        "service_areas": ["Sarasota", "Bradenton", "Venice"],
        "primary_keywords": ["roof repair sarasota"],
        "secondary_keywords": [],
        "competitors": [],
        "usps": ["24-hour emergency service"],
        "tone": "professional",
        "blog_count": 3,
        "social_count": 3,
        "run_semrush_research": true,
        "generate_content": true
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required = ['business_name', 'industry', 'geo']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    response = {
        'success': True,
        'steps': [],
        'research': {},
        'client': None,
        'content': {
            'blogs': [],
            'social': []
        },
        'errors': []
    }
    
    # ==========================================
    # STEP 1: SEMRush Research (if enabled)
    # ==========================================
    run_research = data.get('run_semrush_research', True)
    discovered_competitors = []
    discovered_keywords = []
    discovered_questions = []
    
    if run_research and semrush_service.is_configured():
        response['steps'].append('semrush_research')
        
        # Research domain
        if data.get('website'):
            try:
                domain_research = semrush_service.full_competitor_research(data['website'])
                if not domain_research.get('error'):
                    response['research']['domain'] = {
                        'overview': domain_research.get('overview'),
                        'top_keywords': domain_research.get('top_keywords', [])[:10],
                        'backlinks': domain_research.get('backlinks')
                    }
                    discovered_competitors = [
                        c['domain'] for c in domain_research.get('competitors', [])[:5]
                    ]
                    # Get keyword gaps as content opportunities
                    for gap in domain_research.get('keyword_gaps', [])[:10]:
                        if gap.get('keyword') and gap.get('volume', 0) > 50:
                            discovered_keywords.append({
                                'keyword': gap['keyword'],
                                'volume': gap.get('volume', 0),
                                'difficulty': gap.get('difficulty', 0),
                                'source': 'competitor_gap'
                            })
            except Exception as e:
                response['errors'].append(f'Domain research failed: {str(e)}')
        
        # Research primary keywords
        primary_keywords = data.get('primary_keywords', [])
        if primary_keywords:
            try:
                for pk in primary_keywords[:3]:  # Limit to save API units
                    kw_research = semrush_service.keyword_research_package(pk, data.get('geo', ''))
                    if not kw_research.get('error'):
                        # Store seed metrics
                        if not response['research'].get('keywords'):
                            response['research']['keywords'] = []
                        response['research']['keywords'].append({
                            'keyword': pk,
                            'metrics': kw_research.get('seed_metrics'),
                            'variations_count': kw_research.get('total_variations', 0)
                        })
                        
                        # Collect keyword opportunities
                        for opp in kw_research.get('opportunities', [])[:5]:
                            discovered_keywords.append({
                                'keyword': opp['keyword'],
                                'volume': opp.get('volume', 0),
                                'difficulty': opp.get('difficulty', 0),
                                'source': 'variation'
                            })
                        
                        # Collect questions for FAQ content
                        for q in kw_research.get('questions', [])[:5]:
                            discovered_questions.append(q['keyword'])
            except Exception as e:
                response['errors'].append(f'Keyword research failed: {str(e)}')
        
        response['research']['discovered_competitors'] = discovered_competitors
        response['research']['discovered_keywords'] = discovered_keywords[:20]
        response['research']['discovered_questions'] = discovered_questions[:15]
    elif run_research:
        response['steps'].append('semrush_skipped')
        response['research']['note'] = 'SEMRush API not configured'
    
    # ==========================================
    # STEP 2: Create Client
    # ==========================================
    response['steps'].append('create_client')
    
    # Merge discovered data with provided data
    final_competitors = list(set(
        (data.get('competitors') or []) + discovered_competitors
    ))[:10]
    
    final_secondary_keywords = list(set(
        (data.get('secondary_keywords') or []) + 
        [k['keyword'] for k in discovered_keywords]
    ))[:20]
    
    client = DBClient(
        business_name=data['business_name'],
        industry=data['industry'],
        geo=data['geo'],
        website_url=data.get('website'),
        phone=data.get('phone'),
        email=data.get('email'),
        service_areas=data.get('service_areas', []),
        primary_keywords=data.get('primary_keywords', []),
        secondary_keywords=final_secondary_keywords,
        competitors=final_competitors,
        tone=data.get('tone', 'professional'),
        unique_selling_points=data.get('usps', []),
        service_pages=data.get('service_pages', [])  # For internal linking
    )
    
    data_service.save_client(client)
    response['client'] = client.to_dict()
    
    # ==========================================
    # STEP 3: Generate Content (if enabled)
    # ==========================================
    if data.get('generate_content', False):
        response['steps'].append('generate_content')
        
        blog_count = min(data.get('blog_count', 3), 5)  # Max 5 to avoid timeout
        social_count = min(data.get('social_count', 3), 5)
        
        # Build blog topics from keywords
        blog_topics = []
        
        # Use provided primary keywords first
        for pk in data.get('primary_keywords', [])[:blog_count]:
            blog_topics.append({
                'keyword': pk,
                'word_count': 1200,
                'include_faq': True
            })
        
        # Fill remaining with discovered keywords (sorted by volume)
        if len(blog_topics) < blog_count and discovered_keywords:
            sorted_keywords = sorted(
                discovered_keywords, 
                key=lambda x: x.get('volume', 0), 
                reverse=True
            )
            for kw in sorted_keywords:
                if len(blog_topics) >= blog_count:
                    break
                if kw['keyword'] not in [t['keyword'] for t in blog_topics]:
                    blog_topics.append({
                        'keyword': kw['keyword'],
                        'word_count': 1200,
                        'include_faq': True
                    })
        
        # Get internal linking service
        from app.services.internal_linking_service import internal_linking_service
        service_pages = client.get_service_pages()
        
        # Generate blogs
        for topic in blog_topics:
            try:
                result = ai_service.generate_blog_post(
                    keyword=topic['keyword'],
                    geo=client.geo,
                    industry=client.industry,
                    word_count=topic.get('word_count', 1200),
                    tone=client.tone,
                    business_name=client.business_name,
                    include_faq=topic.get('include_faq', True),
                    faq_count=5,
                    internal_links=service_pages,
                    usps=client.get_unique_selling_points()
                )
                
                if not result.get('error'):
                    # Process with internal linking
                    body_content = result.get('body', '')
                    links_added = 0
                    
                    if service_pages and body_content:
                        link_result = internal_linking_service.process_blog_content(
                            content=body_content,
                            service_pages=service_pages,
                            primary_keyword=topic['keyword'],
                            location=client.geo,
                            business_name=client.business_name,
                            fix_headings=True,
                            add_cta=True
                        )
                        body_content = link_result['content']
                        links_added = link_result['links_added']
                    
                    blog_post = DBBlogPost(
                        client_id=client.id,
                        title=result.get('title', topic['keyword']),
                        body=body_content,
                        meta_title=result.get('meta_title', ''),
                        meta_description=result.get('meta_description', ''),
                        primary_keyword=topic['keyword'],
                        secondary_keywords=result.get('secondary_keywords', []),
                        internal_links=service_pages,
                        faq_content=result.get('faq_items', []),
                        word_count=len(body_content.split()),
                        status=ContentStatus.DRAFT
                    )
                    data_service.save_blog_post(blog_post)
                    response['content']['blogs'].append({
                        'id': blog_post.id,
                        'title': blog_post.title,
                        'keyword': topic['keyword'],
                        'word_count': blog_post.word_count,
                        'links_added': links_added,
                        'status': 'generated'
                    })
                else:
                    response['content']['blogs'].append({
                        'keyword': topic['keyword'],
                        'status': 'failed',
                        'error': result.get('error')
                    })
            except Exception as e:
                response['content']['blogs'].append({
                    'keyword': topic['keyword'],
                    'status': 'failed',
                    'error': str(e)
                })
                response['errors'].append(f"Blog generation failed for '{topic['keyword']}': {str(e)}")
        
        # Build social topics
        social_topics = []
        
        # Use primary keywords as topics
        for pk in data.get('primary_keywords', [])[:social_count]:
            social_topics.append(f"Tips about {pk}")
        
        # Add discovered questions as topics
        for q in discovered_questions[:social_count - len(social_topics)]:
            social_topics.append(q)
        
        # Fill with generic industry topics
        generic_topics = [
            f"Why choose a professional {client.industry} service",
            f"Common {client.industry} mistakes to avoid",
            f"Seasonal {client.industry} tips for {client.geo}"
        ]
        for gt in generic_topics:
            if len(social_topics) >= social_count:
                break
            social_topics.append(gt)
        
        # Generate social posts
        platforms = ['gbp', 'facebook', 'instagram']
        for topic in social_topics[:social_count]:
            for platform in platforms:
                try:
                    result = ai_service.generate_social_post(
                        topic=topic,
                        platform=platform,
                        business_name=client.business_name,
                        industry=client.industry,
                        geo=client.geo,
                        tone=client.tone
                    )
                    
                    if not result.get('error'):
                        post = DBSocialPost(
                            client_id=client.id,
                            platform=platform,
                            content=result.get('text', ''),
                            hashtags=result.get('hashtags', []),
                            cta_type=result.get('cta', ''),
                            status=ContentStatus.DRAFT
                        )
                        data_service.save_social_post(post)
                        response['content']['social'].append({
                            'id': post.id,
                            'platform': platform,
                            'topic': topic,
                            'status': 'generated'
                        })
                except Exception as e:
                    response['content']['social'].append({
                        'platform': platform,
                        'topic': topic,
                        'status': 'failed',
                        'error': str(e)
                    })
    
    # ==========================================
    # SUMMARY
    # ==========================================
    response['summary'] = {
        'client_created': True,
        'client_id': client.id,
        'competitors_found': len(final_competitors),
        'keywords_discovered': len(discovered_keywords),
        'blogs_generated': len([b for b in response['content']['blogs'] if b.get('status') == 'generated']),
        'blogs_failed': len([b for b in response['content']['blogs'] if b.get('status') == 'failed']),
        'social_generated': len([s for s in response['content']['social'] if s.get('status') == 'generated']),
        'social_failed': len([s for s in response['content']['social'] if s.get('status') == 'failed']),
        'errors_count': len(response['errors'])
    }
    
    return jsonify(response)


@intake_bp.route('/quick', methods=['POST'])
@token_required
def quick_intake(current_user):
    """
    Quick intake - just website URL, we figure out the rest
    
    POST /api/intake/quick
    {
        "website": "https://example.com",
        "generate_content": true
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    website = data.get('website', '').strip()
    
    if not website:
        return jsonify({'error': 'website is required'}), 400
    
    # Clean domain
    domain = website.lower().replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
    
    response = {
        'success': True,
        'website': website,
        'domain': domain,
        'research': {},
        'suggested_profile': {},
        'errors': []
    }
    
    # Step 1: SEMRush research
    if semrush_service.is_configured():
        try:
            # Get domain overview
            overview = semrush_service.get_domain_overview(domain)
            if not overview.get('error'):
                response['research']['overview'] = overview
            
            # Get top organic keywords
            keywords = semrush_service.get_domain_organic_keywords(domain, limit=20)
            if not keywords.get('error'):
                response['research']['top_keywords'] = keywords.get('keywords', [])
            
            # Get competitors
            competitors = semrush_service.get_competitors(domain, limit=5)
            if not competitors.get('error'):
                response['research']['competitors'] = competitors.get('competitors', [])
            
            # Build suggested profile from research
            top_kws = keywords.get('keywords', []) if not keywords.get('error') else []
            
            # Try to infer industry from keywords
            industry = _infer_industry(top_kws)
            
            # Try to infer location from keywords
            location = _infer_location(top_kws)
            
            response['suggested_profile'] = {
                'business_name': domain.split('.')[0].title(),
                'website': website,
                'industry': industry,
                'geo': location,
                'primary_keywords': [k['keyword'] for k in top_kws[:5]],
                'secondary_keywords': [k['keyword'] for k in top_kws[5:15]],
                'competitors': [c['domain'] for c in (competitors.get('competitors', []) if not competitors.get('error') else [])[:5]],
                'organic_traffic': overview.get('organic_traffic', 0) if not overview.get('error') else 0,
                'organic_keywords': overview.get('organic_keywords', 0) if not overview.get('error') else 0
            }
            
        except Exception as e:
            response['errors'].append(f'Research failed: {str(e)}')
    else:
        response['errors'].append('SEMRush not configured - cannot auto-research')
    
    return jsonify(response)


@intake_bp.route('/create-client', methods=['POST'])
@token_required
def create_from_extraction(current_user):
    """
    Create client profile from extracted transcript data
    
    POST /api/intake/create-client
    {
        "extracted": { ... the full extracted object ... }
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    extracted = data.get('extracted', {})
    
    if not extracted:
        return jsonify({'error': 'extracted data is required'}), 400
    
    business = extracted.get('business', {})
    seo = extracted.get('seo', {})
    content = extracted.get('content', {})
    
    # Create client object
    client = DBClient(
        business_name=business.get('name', ''),
        industry=business.get('industry', ''),
        geo=business.get('location', ''),
        website_url=business.get('website'),
        phone=business.get('phone'),
        email=business.get('email'),
        service_areas=business.get('service_areas', []),
        primary_keywords=seo.get('primary_keywords', []),
        secondary_keywords=seo.get('secondary_keywords', []),
        competitors=seo.get('competitors', []),
        tone=content.get('tone', 'professional'),
        unique_selling_points=content.get('usps', [])
    )
    
    # Save client
    data_service.save_client(client)
    
    return jsonify({
        'success': True,
        'client': client.to_dict(),
        'topics': extracted.get('topics', {})
    })


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _build_extraction_prompt(transcript: str, industry_hint: str = '') -> str:
    """Build the AI prompt for transcript extraction"""
    
    industry_context = f"The business is likely in the {industry_hint} industry." if industry_hint else ""
    
    return f"""Analyze this client discovery call transcript and extract structured business intelligence.

TRANSCRIPT:
---
{transcript}
---

{industry_context}

Extract the following information. If something isn't mentioned, make reasonable inferences or leave blank.

Return as JSON:
{{
    "business": {{
        "name": "Business name",
        "industry": "Industry type",
        "location": "City, State",
        "phone": "Phone if mentioned",
        "website": "Website if mentioned",
        "email": "Email if mentioned",
        "service_areas": ["List of cities/areas they serve"],
        "years_in_business": "How long they've been operating"
    }},
    "seo": {{
        "primary_keywords": ["Main keywords they want to rank for - include location"],
        "secondary_keywords": ["Supporting keywords"],
        "competitors": ["Competitor business names mentioned"]
    }},
    "content": {{
        "usps": ["Unique selling points - what makes them different"],
        "tone": "How they communicate (professional, friendly, technical, etc.)",
        "pain_points": ["Customer problems they solve"],
        "faqs": ["Common questions their customers ask"],
        "testimonial_themes": ["What customers praise them for"]
    }},
    "topics": {{
        "blog_posts": [
            {{"title": "Suggested blog title with location", "keyword": "target keyword", "angle": "unique angle from their USPs"}}
        ],
        "social_posts": [
            {{"topic": "Social post topic", "platforms": ["gbp", "facebook", "instagram"]}}
        ]
    }}
}}

Be specific to their location and industry. Generate at least 5 blog topics and 5 social topics based on what was discussed.
"""


def _parse_extraction_response(content: str) -> dict:
    """Parse AI extraction response"""
    import json
    
    try:
        # Clean markdown if present
        if '```' in content:
            parts = content.split('```')
            for part in parts:
                if part.strip().startswith('json') or part.strip().startswith('{'):
                    content = part.replace('json', '', 1).strip()
                    break
        
        return json.loads(content)
    except json.JSONDecodeError as e:
        return {'error': f'Failed to parse AI response: {str(e)}', 'raw': content}


def _infer_industry(keywords: list) -> str:
    """Try to infer industry from keyword patterns"""
    if not keywords:
        return 'general'
    
    # Combine all keywords into one string for pattern matching
    all_text = ' '.join([k.get('keyword', '') for k in keywords]).lower()
    
    industry_patterns = {
        'roofing': ['roof', 'roofing', 'shingle', 'gutter'],
        'hvac': ['hvac', 'air conditioning', 'heating', 'furnace', 'ac repair'],
        'plumbing': ['plumber', 'plumbing', 'drain', 'pipe', 'water heater'],
        'electrical': ['electrician', 'electrical', 'wiring', 'outlet'],
        'dental': ['dentist', 'dental', 'teeth', 'orthodont'],
        'legal': ['lawyer', 'attorney', 'legal', 'law firm'],
        'real estate': ['realtor', 'real estate', 'homes for sale', 'property'],
        'landscaping': ['landscap', 'lawn', 'garden', 'tree service'],
        'windows': ['window', 'door', 'glass', 'replacement window']
    }
    
    for industry, patterns in industry_patterns.items():
        for pattern in patterns:
            if pattern in all_text:
                return industry
    
    return 'general'


def _infer_location(keywords: list) -> str:
    """Try to infer location from keywords"""
    if not keywords:
        return ''
    
    # Common US states and their abbreviations
    states = {
        'florida': 'FL', 'fl': 'FL',
        'california': 'CA', 'ca': 'CA',
        'texas': 'TX', 'tx': 'TX',
        'new york': 'NY', 'ny': 'NY',
        'arizona': 'AZ', 'az': 'AZ',
        # Add more as needed
    }
    
    for kw in keywords:
        keyword = kw.get('keyword', '').lower()
        words = keyword.split()
        
        # Look for city + state patterns
        for i, word in enumerate(words):
            for state_name, abbrev in states.items():
                if word == state_name or word == abbrev.lower():
                    # Return previous word as city + state
                    if i > 0:
                        city = words[i-1].title()
                        return f"{city}, {abbrev}"
    
    return ''

