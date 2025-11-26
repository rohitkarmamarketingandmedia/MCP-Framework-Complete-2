"""
MCP Framework - Intake Routes
Transcript analysis and client onboarding
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.ai_service import AIService
from app.services.seo_service import SEOService
from app.services.db_service import DataService
from app.models.db_models import DBClient

intake_bp = Blueprint('intake', __name__)
ai_service = AIService()
seo_service = SEOService()
data_service = DataService()


@intake_bp.route('/analyze', methods=['POST'])
@token_required
def analyze_transcript(current_user):
    """
    Analyze client interview transcript and extract structured data
    
    POST /api/intake/analyze
    {
        "transcript": "Full transcript text from discovery call...",
        "industry_hint": "roofing"  // optional
    }
    
    Returns:
        {
            "business": {
                "name": "ABC Roofing",
                "industry": "roofing",
                "location": "Sarasota, FL",
                "phone": "(941) 555-1234",
                "website": "abcroofing.com",
                "service_areas": ["Sarasota", "Bradenton", "Venice"]
            },
            "seo": {
                "primary_keywords": ["roof repair sarasota", "roofing company sarasota"],
                "secondary_keywords": ["emergency roof repair", "roof replacement"],
                "competitors": ["XYZ Roofing", "123 Roofs"]
            },
            "content": {
                "usps": ["24-hour emergency service", "family-owned since 1985"],
                "tone": "professional yet friendly",
                "pain_points": ["storm damage", "insurance claims"],
                "faqs": ["How long does a roof last?", "Do you handle insurance?"]
            },
            "topics": {
                "blog_posts": [
                    {"title": "Emergency Roof Repair in Sarasota", "keyword": "emergency roof repair sarasota", "angle": "24/7 availability"},
                    {"title": "How to Choose a Family-Owned Roofing Company", "keyword": "family roofing company", "angle": "trust and reliability"}
                ],
                "social_posts": [
                    {"topic": "Storm season preparation tips", "platforms": ["gbp", "facebook"]},
                    {"topic": "Customer testimonial highlight", "platforms": ["instagram", "facebook"]}
                ]
            }
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


@intake_bp.route('/analyze-competitors', methods=['POST'])
@token_required
def analyze_competitors(current_user):
    """
    Deep competitor analysis from extracted competitor names
    
    POST /api/intake/analyze-competitors
    {
        "competitors": ["XYZ Roofing", "123 Roofs"],
        "location": "Sarasota, FL",
        "industry": "roofing",
        "our_keywords": ["roof repair sarasota"]
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    competitors = data.get('competitors', [])
    location = data.get('location', '')
    industry = data.get('industry', '')
    our_keywords = data.get('our_keywords', [])
    
    if not competitors:
        return jsonify({'error': 'competitors list is required'}), 400
    
    # Get competitor analysis from SEO service
    analysis = []
    for comp in competitors[:5]:  # Limit to 5 competitors
        comp_data = {
            'name': comp,
            'estimated_domain': _guess_domain(comp, location),
            'rankings': {},
            'keyword_gaps': [],
            'content_opportunities': []
        }
        
        # Try to get rankings if we can guess the domain
        if comp_data['estimated_domain']:
            rankings = seo_service.get_keyword_rankings(
                domain=comp_data['estimated_domain'],
                keywords=our_keywords
            )
            comp_data['rankings'] = rankings.get('keywords', [])[:10]
        
        analysis.append(comp_data)
    
    # Generate content opportunities based on competitor gaps
    opportunities = _generate_opportunities(analysis, our_keywords, industry, location)
    
    return jsonify({
        'success': True,
        'competitors': analysis,
        'opportunities': opportunities
    })


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


@intake_bp.route('/generate-topics', methods=['POST'])
@token_required
def generate_topics(current_user):
    """
    Generate additional content topics for a client
    
    POST /api/intake/generate-topics
    {
        "client_id": "client_abc123",
        "count": 10,
        "focus": "blog"  // blog, social, or both
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    
    client_id = data.get('client_id')
    count = data.get('count', 10)
    focus = data.get('focus', 'both')
    
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    client = data_service.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Generate topics using AI
    prompt = f"""Generate {count} content topics for a {client.industry} business called "{client.business_name}" in {client.geo}.

Their unique selling points:
{chr(10).join('- ' + usp for usp in client.unique_selling_points)}

Their primary keywords:
{chr(10).join('- ' + kw for kw in client.primary_keywords)}

Their competitors: {', '.join(client.competitors)}

Focus: {focus}

Return as JSON:
{{
    "blog_posts": [
        {{"title": "SEO-optimized title", "keyword": "target keyword", "angle": "unique angle", "priority": "high/medium/low"}}
    ],
    "social_posts": [
        {{"topic": "topic description", "platforms": ["gbp", "facebook"], "content_type": "tip/testimonial/behind-scenes/promo"}}
    ]
}}

Make topics specific to {client.geo} and the {client.industry} industry. Include seasonal topics if relevant.
"""
    
    result = ai_service._call_openai(prompt, max_tokens=2000)
    
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    
    topics = _parse_json_response(result.get('content', '{}'))
    
    return jsonify({
        'success': True,
        'client_id': client_id,
        'topics': topics
    })


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


def _parse_json_response(content: str) -> dict:
    """Parse JSON from AI response"""
    import json
    
    try:
        if '```' in content:
            parts = content.split('```')
            for part in parts:
                if part.strip().startswith('json') or part.strip().startswith('{'):
                    content = part.replace('json', '', 1).strip()
                    break
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _guess_domain(business_name: str, location: str) -> str:
    """Try to guess a business domain from their name"""
    # Simple domain guessing - in production would use Google search or business API
    name_clean = business_name.lower()
    name_clean = name_clean.replace(' ', '').replace("'", '').replace('-', '')
    name_clean = ''.join(c for c in name_clean if c.isalnum())
    
    return f"https://{name_clean}.com"


def _generate_opportunities(competitor_analysis: list, keywords: list, industry: str, location: str) -> list:
    """Generate content opportunities from competitor gaps"""
    opportunities = []
    
    # Find keywords competitors rank for that we might not
    all_competitor_keywords = set()
    for comp in competitor_analysis:
        for ranking in comp.get('rankings', []):
            if isinstance(ranking, dict):
                all_competitor_keywords.add(ranking.get('keyword', ''))
    
    # Keywords they have that aren't in our list
    our_keywords_set = set(kw.lower() for kw in keywords)
    gaps = all_competitor_keywords - our_keywords_set
    
    for gap_kw in list(gaps)[:10]:
        if gap_kw:
            opportunities.append({
                'type': 'keyword_gap',
                'keyword': gap_kw,
                'action': f'Create content targeting "{gap_kw}" to compete',
                'priority': 'high'
            })
    
    # Generic opportunities based on industry
    opportunities.extend([
        {
            'type': 'local_seo',
            'keyword': f'{industry} {location}',
            'action': 'Strengthen local landing page',
            'priority': 'high'
        },
        {
            'type': 'reviews',
            'keyword': 'customer reviews',
            'action': 'Generate more Google reviews to outrank competitors',
            'priority': 'medium'
        }
    ])
    
    return opportunities
