"""
MCP Framework - Service Page Generator
Creates high-converting service and location landing pages
"""
import logging
import uuid
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.database import db
from app.models.db_models import DBServicePage, DBClient

logger = logging.getLogger(__name__)


class ServicePageGenerator:
    """Generates conversion-optimized service and location pages"""
    
    def __init__(self, ai_service=None):
        self.ai_service = ai_service
    
    def set_ai_service(self, ai_service):
        self.ai_service = ai_service
    
    # ==========================================
    # Page Generation
    # ==========================================
    
    def generate_service_page(
        self,
        client: DBClient,
        service: str,
        location: Optional[str] = None,
        additional_context: Dict = None
    ) -> Dict[str, Any]:
        """
        Generate a complete service landing page
        
        Args:
            client: The client
            service: Service name (e.g., "roof repair")
            location: Optional location for geo-targeting
            additional_context: Additional info for content generation
        
        Returns:
            Generated page content dict
        """
        # Determine page type and keyword
        if location:
            page_type = 'service_location'
            primary_keyword = f"{service} {location}"
            title = f"{service.title()} in {location} | {client.business_name}"
        else:
            page_type = 'service'
            primary_keyword = f"{service} {client.geo}" if client.geo else service
            location = client.geo
            title = f"{service.title()} Services | {client.business_name}"
        
        # Generate slug
        slug = self._generate_slug(primary_keyword)
        
        # Build context for AI
        context = {
            'business_name': client.business_name,
            'industry': client.industry,
            'service': service,
            'location': location or client.geo,
            'phone': client.phone,
            'primary_keyword': primary_keyword,
            'usps': client.get_unique_selling_points(),
            'service_areas': client.get_service_areas(),
            'tone': client.tone,
            **(additional_context or {})
        }
        
        # Generate content with AI
        if self.ai_service:
            content = self._generate_with_ai(context)
        else:
            content = self._generate_template(context)
        
        # Create page record
        page_id = f"svcpg_{uuid.uuid4().hex[:12]}"
        
        # Ensure required fields have defaults
        hero_headline = content.get('hero_headline') or content.get('headline') or f"{service.title()} Services in {location}"
        body_content = content.get('body_content') or content.get('content') or content.get('main_content') or f"Professional {service} services from {client.business_name}."
        
        page = DBServicePage(
            id=page_id,
            client_id=client.id,
            page_type=page_type,
            title=title,
            slug=slug,
            service=service,
            location=location,
            primary_keyword=primary_keyword,
            secondary_keywords=content.get('secondary_keywords', []),
            hero_headline=hero_headline,
            hero_subheadline=content.get('hero_subheadline') or content.get('subheadline') or f"Trusted {service} experts serving {location}",
            intro_text=content.get('intro_text') or content.get('introduction'),
            body_content=body_content,
            cta_headline=content.get('cta_headline', f"Get Your Free {service.title()} Quote"),
            cta_button_text=content.get('cta_button_text', 'Get Free Estimate'),
            form_headline=content.get('form_headline', "Request Your Free Quote"),
            trust_badges=content.get('trust_badges', ['Licensed', 'Insured', 'Free Estimates']),
            meta_title=content.get('meta_title', title)[:70],
            meta_description=content.get('meta_description', '')[:160],
            schema_markup=self._generate_schema(client, service, location),
            status='draft',
            created_at=datetime.utcnow()
        )
        
        db.session.add(page)
        db.session.commit()
        
        return {
            'success': True,
            'page': page.to_dict(),
            'full_content': {
                'hero_headline': hero_headline,
                'hero_subheadline': content.get('hero_subheadline') or content.get('subheadline'),
                'intro_text': content.get('intro_text') or content.get('introduction'),
                'body_content': body_content,
                'cta_headline': content.get('cta_headline'),
                'trust_badges': content.get('trust_badges'),
                'faq': content.get('faq', [])
            }
        }
    
    def generate_location_page(
        self,
        client: DBClient,
        location: str,
        services: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a location-specific landing page
        
        Args:
            client: The client
            location: Location name (e.g., "Bradenton, FL")
            services: Optional list of services to highlight
        """
        services = services or [client.industry]
        primary_keyword = f"{client.industry} {location}"
        
        title = f"{client.industry.title()} Services in {location} | {client.business_name}"
        slug = self._generate_slug(f"{client.industry}-{location}")
        
        context = {
            'business_name': client.business_name,
            'industry': client.industry,
            'services': services,
            'location': location,
            'phone': client.phone,
            'primary_keyword': primary_keyword,
            'usps': client.get_unique_selling_points(),
            'tone': client.tone
        }
        
        if self.ai_service:
            content = self._generate_location_with_ai(context)
        else:
            content = self._generate_location_template(context)
        
        page_id = f"locpg_{uuid.uuid4().hex[:12]}"
        
        page = DBServicePage(
            id=page_id,
            client_id=client.id,
            page_type='location',
            title=title,
            slug=slug,
            service=None,
            location=location,
            primary_keyword=primary_keyword,
            hero_headline=content['hero_headline'],
            hero_subheadline=content.get('hero_subheadline'),
            intro_text=content.get('intro_text'),
            body_content=content['body_content'],
            cta_headline=content.get('cta_headline'),
            cta_button_text=content.get('cta_button_text', 'Get Free Estimate'),
            form_headline=content.get('form_headline'),
            trust_badges=content.get('trust_badges', ['Licensed', 'Insured', 'Local']),
            meta_title=content.get('meta_title', title)[:70],
            meta_description=content.get('meta_description', '')[:160],
            schema_markup=self._generate_schema(client, client.industry, location),
            status='draft',
            created_at=datetime.utcnow()
        )
        
        db.session.add(page)
        db.session.commit()
        
        return {
            'success': True,
            'page': page.to_dict(),
            'full_content': content
        }
    
    def generate_bulk_pages(
        self,
        client: DBClient,
        services: List[str] = None,
        locations: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate multiple service and location pages
        
        Args:
            client: The client
            services: List of services (defaults to primary keywords)
            locations: List of locations (defaults to service areas)
        
        Returns:
            Summary of generated pages
        """
        services = services or client.get_primary_keywords()
        locations = locations or client.get_service_areas() or [client.geo]
        
        results = {
            'service_pages': [],
            'location_pages': [],
            'errors': []
        }
        
        # Generate service pages for primary location
        for service in services[:5]:  # Limit to 5
            try:
                result = self.generate_service_page(client, service)
                if result.get('success'):
                    results['service_pages'].append(result['page'])
                else:
                    results['errors'].append({'service': service, 'error': result.get('error')})
            except Exception as e:
                results['errors'].append({'service': service, 'error': str(e)})
        
        # Generate location pages
        for location in locations[:5]:  # Limit to 5
            if location == client.geo:
                continue  # Skip primary location, covered by service pages
            try:
                result = self.generate_location_page(client, location)
                if result.get('success'):
                    results['location_pages'].append(result['page'])
                else:
                    results['errors'].append({'location': location, 'error': result.get('error')})
            except Exception as e:
                results['errors'].append({'location': location, 'error': str(e)})
        
        return {
            'success': True,
            'total_pages': len(results['service_pages']) + len(results['location_pages']),
            'service_pages': results['service_pages'],
            'location_pages': results['location_pages'],
            'errors': results['errors']
        }
    
    # ==========================================
    # AI Content Generation
    # ==========================================
    
    def _generate_with_ai(self, context: Dict) -> Dict:
        """Generate service page content using AI agent config"""
        # Build user input with all context
        target_words = context.get('word_count', 1200)
        user_input = f"""Generate a service page for:

BUSINESS INFO:
- Company: {context['business_name']}
- Industry: {context['industry']}
- Location: {context['location']}
- Phone: {context.get('phone', 'N/A')}
- Unique Selling Points: {', '.join(context.get('usps', []))}

SERVICE: {context['service']}
PRIMARY KEYWORD: {context['primary_keyword']}
TONE: {context.get('tone', 'professional')}
TARGET WORD COUNT: {target_words} words (body_content MUST be at least {target_words} words)

Requirements:
- Start headline with the primary keyword or service name
- Include location naturally in content
- Focus on benefits and outcomes, not features
- Include specific trust signals (years in business, licenses, guarantees)
- Make the content scannable with clear paragraphs
- body_content MUST be full HTML with multiple sections totaling AT LEAST {target_words} words
- Include {context.get('include_faq', True) and 3 or 0} FAQs in the body if FAQs are requested
- Do NOT write short stubs — write a complete, thorough page
- Return ONLY valid JSON"""

        system_prompt = """You are an expert SEO copywriter specializing in local service business landing pages.
Generate detailed, conversion-focused service pages with rich HTML content.
Return ONLY valid JSON — no markdown, no extra text."""

        try:
            # Try using the agent config first
            result = self.ai_service.generate_raw_with_agent(
                agent_name='service_page_writer',
                user_input=user_input,
                variables={
                    'keyword': context['primary_keyword'],
                    'location': context['location']
                }
            )

            # Parse JSON response
            if isinstance(result, str):
                # Clean up potential markdown code blocks
                result = result.replace('```json', '').replace('```', '').strip()
                result = json.loads(result)

            return result

        except Exception as agent_err:
            logger.warning(f"Agent-based generation failed ({agent_err}), falling back to direct AI call")
            try:
                # Fallback: direct AI call with full prompt to honour the requested word count
                direct_prompt = f"""{system_prompt}

{user_input}

Return a JSON object with keys: hero_headline, hero_subheadline, intro_text, body_content (full HTML, {target_words}+ words), cta_headline, cta_button_text, form_headline, trust_badges (list), faq (list of {{question, answer}}), meta_title, meta_description, secondary_keywords (list)."""
                raw = self.ai_service.generate_raw(direct_prompt, max_tokens=16000)
                if isinstance(raw, str):
                    raw = raw.replace('```json', '').replace('```', '').strip()
                    return json.loads(raw)
            except Exception as direct_err:
                logger.error(f"Direct AI generation also failed: {direct_err}")
            return self._generate_template(context)

    def _generate_location_with_ai(self, context: Dict) -> Dict:
        """Generate location page content using AI agent config"""
        services_list = ', '.join(context.get('services', []))
        
        target_words = context.get('word_count', 1200)
        user_input = f"""Generate a location-focused landing page:

BUSINESS INFO:
- Company: {context['business_name']}
- Industry: {context['industry']}
- Services: {services_list}
- Phone: {context.get('phone', 'N/A')}
- Unique Selling Points: {', '.join(context.get('usps', []))}

TARGET LOCATION: {context['location']}
PRIMARY KEYWORD: {context['primary_keyword']}
TONE: {context.get('tone', 'professional')}
TARGET WORD COUNT: {target_words} words (body_content MUST be at least {target_words} words)

Generate location-specific content emphasizing local service and expertise.
body_content must be full HTML with multiple detailed sections totaling AT LEAST {target_words} words.
Return ONLY valid JSON."""

        system_prompt = """You are an expert SEO copywriter specializing in local service business landing pages.
Generate detailed, conversion-focused location pages with rich HTML content.
Return ONLY valid JSON — no markdown, no extra text."""

        try:
            result = self.ai_service.generate_raw_with_agent(
                agent_name='service_page_writer',
                user_input=user_input,
                variables={
                    'keyword': context['primary_keyword'],
                    'location': context['location']
                }
            )

            if isinstance(result, str):
                result = result.replace('```json', '').replace('```', '').strip()
                result = json.loads(result)

            return result

        except Exception as agent_err:
            logger.warning(f"Agent-based location generation failed ({agent_err}), falling back to direct AI call")
            try:
                direct_prompt = f"""{system_prompt}

{user_input}

Return a JSON object with keys: hero_headline, hero_subheadline, intro_text, body_content (full HTML, {target_words}+ words), cta_headline, cta_button_text, form_headline, trust_badges (list), faq (list of {{question, answer}}), meta_title, meta_description, secondary_keywords (list)."""
                raw = self.ai_service.generate_raw(direct_prompt, max_tokens=16000)
                if isinstance(raw, str):
                    raw = raw.replace('```json', '').replace('```', '').strip()
                    return json.loads(raw)
            except Exception as direct_err:
                logger.error(f"Direct AI location generation also failed: {direct_err}")
            return self._generate_location_template(context)
    
    # ==========================================
    # Template Fallbacks
    # ==========================================
    
    def _generate_template(self, context: Dict) -> Dict:
        """Generate service page content from template (expanded fallback ~600+ words)"""
        service = context['service']
        location = context['location']
        business = context['business_name']
        industry = context.get('industry', service)
        phone = context.get('phone', '')
        usps = context.get('usps', [])
        usps_html = ''.join([f'<li><strong>{u}</strong></li>' for u in usps[:5]]) if usps else ''

        body = f"""<h2>Why Choose {business} for {service.title()} in {location}?</h2>
<p>When you need reliable {service} services in {location}, choosing the right company makes all the difference.
{business} has built a strong reputation across {location} by consistently delivering high-quality results,
transparent pricing, and outstanding customer service. Whether you're a homeowner or a business, our team
brings the expertise and dedication needed to handle your {service} project from start to finish.</p>

<p>We understand that every {service} job is unique. That's why we begin every project with a thorough
assessment of your specific needs, followed by a clear, no-obligation estimate so you always know what to
expect — with no hidden fees or surprises along the way.</p>

<h2>Our {service.title()} Services in {location}</h2>
<p>At {business}, we offer a comprehensive range of {service} solutions designed to meet the needs of
{location} residents and businesses. Our services include:</p>
<ul>
<li><strong>Initial Consultation &amp; Free Estimate</strong> – We assess your project needs and provide an
honest, detailed quote at no cost.</li>
<li><strong>Professional {service.title()} Work</strong> – Our skilled technicians handle every aspect of
your {service} project with precision and care.</li>
<li><strong>Quality Materials &amp; Methods</strong> – We only use proven materials and industry-best
techniques to ensure lasting results.</li>
<li><strong>Project Management</strong> – From scheduling to completion, we coordinate every detail so
you don't have to worry.</li>
<li><strong>Clean-Up &amp; Final Walkthrough</strong> – We leave your property clean and walk you through
the completed work before we consider the job done.</li>
{usps_html}
</ul>

<h2>What Sets {business} Apart</h2>
<p>There are many {service} companies in {location}, but {business} stands out for reasons our customers
notice from the very first call:</p>
<ul>
<li><strong>Licensed &amp; Insured</strong> – You're fully protected on every job we perform.</li>
<li><strong>Experienced Team</strong> – Our technicians have the hands-on training to handle projects of
any size or complexity.</li>
<li><strong>Clear Communication</strong> – We keep you informed at every stage, so you're never left
guessing about the status of your project.</li>
<li><strong>Competitive Pricing</strong> – Fair rates with detailed, itemized estimates so you know
exactly where your money goes.</li>
<li><strong>Satisfaction Guarantee</strong> – We stand behind our work. If something isn't right,
we'll make it right.</li>
</ul>

<h2>Serving {location} and Surrounding Communities</h2>
<p>We are proud to be a locally rooted company serving homeowners and businesses throughout {location}
and nearby areas. Our familiarity with the local market means we understand the conditions, requirements,
and expectations specific to your community. When you call {business}, you're getting a neighbor who
cares about the quality of work — not a distant contractor who moves on to the next job.</p>

<p>Our {service} crews are available to handle urgent requests, scheduled maintenance, and full-scale
projects alike. No matter the scope of your {service} needs, we have the resources and experience to
deliver exceptional results on time and within budget.</p>

<h2>The {business} Process</h2>
<p>Getting started is simple. Here's what you can expect when you contact us for {service} services
in {location}:</p>
<ol>
<li><strong>Call or Submit a Request</strong> – Reach out by phone{' at ' + phone if phone else ''} or
fill out our quick online form.</li>
<li><strong>Free Consultation &amp; Estimate</strong> – We'll schedule a convenient time to assess
your {service} needs and provide a detailed, no-obligation quote.</li>
<li><strong>Project Planning</strong> – Once approved, we schedule your project at a time that works
for you and outline a clear timeline.</li>
<li><strong>Expert Execution</strong> – Our team gets to work, keeping you informed throughout the
entire process.</li>
<li><strong>Final Review &amp; Sign-Off</strong> – We walk through the completed work with you to
ensure you're 100% satisfied before we close out the job.</li>
</ol>

<h2>Frequently Asked Questions About {service.title()} in {location}</h2>
<p>We know you may have questions before getting started. Here are answers to the ones we hear most often:</p>
<p><strong>How much does {service} cost in {location}?</strong><br />
The cost varies depending on the size and complexity of your specific project. We provide free,
detailed estimates so you have a clear picture of costs before any work begins. Contact us to
schedule yours today.</p>
<p><strong>How long will my {service} project take?</strong><br />
Most projects can be completed within the timeframe we outline during your initial consultation.
We'll give you a realistic timeline upfront and keep you informed of any changes.</p>
<p><strong>Do you offer any warranties or guarantees?</strong><br />
Yes. We stand behind the quality of our work. Ask us about our specific warranty terms when you
request your free estimate.</p>"""

        return {
            'hero_headline': f"{service.title()} Services in {location}",
            'hero_subheadline': f"Professional {service} services you can trust — serving {location} with quality workmanship and free estimates.",
            'intro_text': (
                f"Looking for reliable {service} services in {location}? {business} delivers "
                f"expert {service} solutions with transparent pricing, experienced technicians, "
                f"and a satisfaction guarantee. Contact us today for your free estimate."
            ),
            'body_content': body,
            'cta_headline': f"Ready for Professional {service.title()} in {location}?",
            'cta_button_text': "Get Your Free Quote",
            'form_headline': "Request Your Free Estimate",
            'trust_badges': ['Licensed', 'Insured', 'Free Estimates', 'Satisfaction Guaranteed'],
            'faq': [
                {
                    'question': f"How much does {service} cost in {location}?",
                    'answer': f"The cost of {service} varies depending on the scope of work. Contact us for a free, no-obligation estimate tailored to your specific needs."
                },
                {
                    'question': f"How long does {service} typically take?",
                    'answer': f"Project timelines depend on the size and complexity of the job. We'll provide a clear timeline during your free consultation."
                },
                {
                    'question': f"Are you licensed and insured for {service} work?",
                    'answer': f"Yes! {business} is fully licensed and insured for your protection and peace of mind."
                },
                {
                    'question': f"Do you offer free estimates for {service} in {location}?",
                    'answer': f"Absolutely. We provide free, no-obligation estimates for all {service} projects in {location} and surrounding areas. Contact us to schedule yours."
                }
            ],
            'meta_title': f"{service.title()} in {location} | {business}",
            'meta_description': f"Professional {service} services in {location}. {business} offers quality workmanship, free estimates, and satisfaction guaranteed. Call today!",
            'secondary_keywords': [
                f"{service} {location}",
                f"{service} near me",
                f"best {service} {location}",
                f"{service} company {location}"
            ]
        }
    
    def _generate_location_template(self, context: Dict) -> Dict:
        """Generate location page content from template (expanded fallback ~600+ words)"""
        location = context['location']
        business = context['business_name']
        industry = context['industry']
        services = context.get('services', [industry])
        phone = context.get('phone', '')
        usps = context.get('usps', [])

        services_list = ', '.join(services[:4])
        services_li = ''.join([f'<li><strong>{s.title()}</strong> – Expert {s} services for {location} homes and businesses.</li>' for s in services[:5]])
        usps_li = ''.join([f'<li>{u}</li>' for u in usps[:4]]) if usps else ''

        body = f"""<h2>{location}'s Trusted {industry.title()} Professionals</h2>
<p>When {location} residents and businesses need dependable {industry} services, they turn to {business}.
We have built our reputation on quality workmanship, honest pricing, and a genuine commitment to the
communities we serve. From routine maintenance to complex projects, our experienced team is ready to
help with all of your {industry} needs in {location} and the surrounding area.</p>

<p>We know you have options when choosing a {industry} provider in {location}. What sets {business}
apart is our combination of local knowledge, skilled technicians, and an unwavering focus on customer
satisfaction. Every project we take on — large or small — receives the same level of care and attention
to detail.</p>

<h2>{industry.title()} Services We Offer in {location}</h2>
<p>Our comprehensive {industry} services in {location} include:</p>
<ul>
{services_li if services_li else f'<li><strong>{industry.title()} Services</strong> – Full-service {industry} solutions for {location} properties.</li>'}
<li><strong>Free Estimates</strong> – Transparent, no-obligation quotes for every project.</li>
<li><strong>Emergency Response</strong> – Available when you need us most.</li>
<li><strong>Routine Maintenance</strong> – Scheduled upkeep to keep your property in top condition.</li>
</ul>

<h2>Why {location} Residents Choose {business}</h2>
<p>We understand the unique needs of {location} properties and take pride in delivering results that
last. Here's why our customers continue to trust {business} with their {industry} needs:</p>
<ul>
<li><strong>Local Expertise</strong> – We know {location}'s conditions, codes, and community standards inside and out.</li>
<li><strong>Licensed &amp; Insured</strong> – Every project is fully covered for your peace of mind.</li>
<li><strong>Transparent Pricing</strong> – No hidden fees. Detailed quotes before work begins.</li>
<li><strong>Experienced Team</strong> – Skilled technicians with hands-on experience across all project types.</li>
<li><strong>Satisfaction Guaranteed</strong> – We don't consider a job done until you're happy with the results.</li>
{usps_li}
</ul>

<h2>Our Service Area in and Around {location}</h2>
<p>Based in the area, {business} proudly serves homeowners and businesses throughout {location} and
surrounding communities. Our familiarity with local regulations, weather conditions, and property types
means we can deliver the right solution efficiently and effectively — every time.</p>

<p>Whether you're located in the heart of {location} or in a neighboring community, our team can
typically schedule a consultation quickly and complete your project with minimal disruption to your
daily routine.</p>

<h2>How to Get Started</h2>
<p>Getting {industry} services from {business} in {location} is straightforward:</p>
<ol>
<li><strong>Contact Us</strong> – Call{(' us at ' + phone) if phone else ''} or submit our online request form.</li>
<li><strong>Free Estimate</strong> – We'll schedule a convenient time to assess your needs and provide a detailed quote.</li>
<li><strong>Approve &amp; Schedule</strong> – Once you're happy with the estimate, we lock in a start date that works for you.</li>
<li><strong>Expert Service</strong> – Our team completes your project on time with quality you can see.</li>
<li><strong>Final Walkthrough</strong> – We review the finished work with you to ensure your complete satisfaction.</li>
</ol>

<h2>Frequently Asked Questions — {industry.title()} in {location}</h2>
<p><strong>Do you serve all of {location}?</strong><br />
Yes! We serve {location} and the surrounding communities. Contact us to confirm coverage for your
specific address.</p>
<p><strong>How quickly can you start?</strong><br />
Scheduling depends on project type and current availability. Contact us and we'll do our best to
accommodate your timeline.</p>
<p><strong>Do you provide free estimates in {location}?</strong><br />
Absolutely. We offer free, no-obligation estimates for all {industry} projects in {location}.
There's no cost to get a quote, and no pressure to commit.</p>"""

        return {
            'hero_headline': f"{industry.title()} Services in {location}",
            'hero_subheadline': f"Your trusted local {industry} professionals — serving {location} with quality, transparency, and pride.",
            'intro_text': (
                f"{business} is proud to serve the {location} community with professional {industry} services. "
                f"Our experienced team brings quality workmanship and outstanding customer service to every project. "
                f"Contact us for a free, no-obligation estimate."
            ),
            'body_content': body,
            'cta_headline': f"Need {industry.title()} Services in {location}?",
            'cta_button_text': "Get Free Estimate",
            'form_headline': f"Request a Free Estimate in {location}",
            'trust_badges': ['Local Company', 'Licensed', 'Insured', 'Free Estimates'],
            'faq': [
                {
                    'question': f"What {industry} services do you offer in {location}?",
                    'answer': f"We offer a full range of {industry} services in {location} including {services_list}. Contact us to discuss your specific needs."
                },
                {
                    'question': f"Are you licensed and insured to work in {location}?",
                    'answer': f"Yes, {business} is fully licensed and insured. You're protected on every job we perform in {location}."
                },
                {
                    'question': f"How do I get a free estimate for {industry} work in {location}?",
                    'answer': f"Simply call us{(' at ' + phone) if phone else ''} or fill out the form on this page. We'll schedule a convenient time and provide a detailed, no-obligation quote."
                }
            ],
            'meta_title': f"{industry.title()} in {location} | {business}",
            'meta_description': f"Professional {industry} services in {location}. {business} offers quality work, free estimates, and fast service. Call today!",
            'secondary_keywords': [
                f"{industry} {location}",
                f"{industry} near me",
                f"best {industry} {location}"
            ]
        }
    
    # ==========================================
    # Utilities
    # ==========================================
    
    def _generate_slug(self, text: str) -> str:
        """Generate URL-friendly slug from text"""
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')[:60]
    
    def _generate_schema(
        self, 
        client: DBClient, 
        service: str, 
        location: str
    ) -> str:
        """Generate LocalBusiness schema markup"""
        schema = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": client.business_name,
            "description": f"Professional {service} services in {location}",
            "areaServed": location,
            "serviceType": service
        }
        
        if client.phone:
            schema["telephone"] = client.phone
        
        if client.website_url:
            schema["url"] = client.website_url
        
        if client.geo:
            schema["address"] = {
                "@type": "PostalAddress",
                "addressLocality": location.split(',')[0].strip() if ',' in location else location
            }
        
        return json.dumps(schema, indent=2)
    
    def get_client_pages(
        self, 
        client_id: str, 
        page_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """Get service pages for a client"""
        query = DBServicePage.query.filter(DBServicePage.client_id == client_id)
        
        if page_type:
            query = query.filter(DBServicePage.page_type == page_type)
        
        if status:
            query = query.filter(DBServicePage.status == status)
        
        pages = query.order_by(DBServicePage.created_at.desc()).all()
        return [p.to_dict() for p in pages]
    
    def get_full_page(self, page_id: str) -> Optional[Dict]:
        """Get full page content"""
        page = DBServicePage.query.get(page_id)
        if not page:
            return None
        
        return {
            'id': page.id,
            'client_id': page.client_id,
            'page_type': page.page_type,
            'title': page.title,
            'slug': page.slug,
            'service': page.service,
            'location': page.location,
            'primary_keyword': page.primary_keyword,
            'secondary_keywords': page.secondary_keywords,
            'hero_headline': page.hero_headline,
            'hero_subheadline': page.hero_subheadline,
            'intro_text': page.intro_text,
            'body_content': page.body_content,
            'cta_headline': page.cta_headline,
            'cta_button_text': page.cta_button_text,
            'form_headline': page.form_headline,
            'trust_badges': page.trust_badges,
            'meta_title': page.meta_title,
            'meta_description': page.meta_description,
            'schema_markup': page.schema_markup,
            'status': page.status,
            'published_url': page.published_url,
            'created_at': page.created_at.isoformat() if page.created_at else None
        }
    
    def export_page_html(self, page_id: str, client: DBClient, include_form: bool = True) -> str:
        """Export page as standalone HTML"""
        page = DBServicePage.query.get(page_id)
        if not page:
            return None
        
        # Import lead service for form if needed
        form_html = ""
        if include_form:
            from app.services.lead_service import lead_service
            form_html = lead_service.generate_form_embed(
                client.id,
                {
                    'services': [page.service] if page.service else [],
                    'button_text': page.cta_button_text or 'Get Free Quote'
                }
            )
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page.meta_title or page.title}</title>
    <meta name="description" content="{page.meta_description or ''}">
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="application/ld+json">
{page.schema_markup or '{}'}
    </script>
</head>
<body class="bg-gray-50">
    <!-- Hero Section -->
    <header class="bg-gradient-to-r from-blue-600 to-blue-800 text-white py-20">
        <div class="container mx-auto px-4 max-w-6xl">
            <h1 class="text-4xl md:text-5xl font-bold mb-4">{page.hero_headline}</h1>
            <p class="text-xl text-blue-100 mb-8">{page.hero_subheadline or ''}</p>
            <a href="#contact" class="inline-block bg-white text-blue-600 px-8 py-4 rounded-lg font-bold text-lg hover:bg-blue-50 transition-colors">
                {page.cta_button_text or 'Get Free Quote'}
            </a>
            {f'<p class="mt-4 text-blue-200">Or call: <a href="tel:{client.phone}" class="underline font-semibold">{client.phone}</a></p>' if client.phone else ''}
        </div>
    </header>
    
    <!-- Trust Badges -->
    <div class="bg-gray-100 py-6 border-b">
        <div class="container mx-auto px-4 max-w-6xl">
            <div class="flex flex-wrap justify-center gap-6">
                {' '.join([f'<span class="flex items-center text-gray-700"><svg class="w-5 h-5 text-green-500 mr-2" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>{badge}</span>' for badge in (page.trust_badges or [])])}
            </div>
        </div>
    </div>
    
    <!-- Main Content -->
    <main class="py-16">
        <div class="container mx-auto px-4 max-w-6xl">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-12">
                <!-- Content -->
                <div class="lg:col-span-2">
                    {f'<p class="text-xl text-gray-600 mb-8 leading-relaxed">{page.intro_text}</p>' if page.intro_text else ''}
                    
                    <div class="prose prose-lg max-w-none">
                        {self._markdown_to_html(page.body_content)}
                    </div>
                </div>
                
                <!-- Sidebar Form -->
                <div class="lg:col-span-1">
                    <div id="contact" class="bg-white rounded-2xl shadow-xl p-8 sticky top-8">
                        <h3 class="text-2xl font-bold text-gray-800 mb-6">{page.form_headline or 'Get Your Free Quote'}</h3>
                        {form_html}
                    </div>
                </div>
            </div>
        </div>
    </main>
    
    <!-- CTA Section -->
    <section class="bg-blue-600 text-white py-16">
        <div class="container mx-auto px-4 max-w-4xl text-center">
            <h2 class="text-3xl font-bold mb-4">{page.cta_headline or 'Ready to Get Started?'}</h2>
            <p class="text-xl text-blue-100 mb-8">Contact us today for your free, no-obligation estimate.</p>
            <a href="#contact" class="inline-block bg-white text-blue-600 px-8 py-4 rounded-lg font-bold text-lg hover:bg-blue-50 transition-colors">
                {page.cta_button_text or 'Get Free Quote'}
            </a>
        </div>
    </section>
    
    <!-- Footer -->
    <footer class="bg-gray-800 text-gray-400 py-8">
        <div class="container mx-auto px-4 text-center">
            <p>&copy; {datetime.now().year} {client.business_name}. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>'''
        
        return html
    
    def _markdown_to_html(self, markdown_text: str) -> str:
        """Simple markdown to HTML conversion"""
        if not markdown_text:
            return ''
        
        html = markdown_text
        
        # Headers
        html = re.sub(r'^### (.+)$', r'<h3 class="text-xl font-semibold mt-8 mb-4">\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2 class="text-2xl font-bold mt-10 mb-4">\1</h2>', html, flags=re.MULTILINE)
        
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        
        # Lists
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.+</li>\n?)+', r'<ul class="list-disc pl-6 my-4 space-y-2">\g<0></ul>', html)
        
        # Paragraphs
        paragraphs = html.split('\n\n')
        html = '\n'.join([
            f'<p class="mb-4 text-gray-700">{p}</p>' if not p.startswith('<') else p 
            for p in paragraphs if p.strip()
        ])
        
        return html


# Global instance
service_page_generator = ServicePageGenerator()
