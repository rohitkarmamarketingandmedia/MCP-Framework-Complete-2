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
            hero_headline=content['hero_headline'],
            hero_subheadline=content.get('hero_subheadline'),
            intro_text=content.get('intro_text'),
            body_content=content['body_content'],
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
                'hero_headline': content['hero_headline'],
                'hero_subheadline': content.get('hero_subheadline'),
                'intro_text': content.get('intro_text'),
                'body_content': content['body_content'],
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

Requirements:
- Start headline with the primary keyword or service name
- Include location naturally in content
- Focus on benefits and outcomes, not features
- Include specific trust signals (years in business, licenses, guarantees)
- Make the content scannable with short paragraphs
- Include 3 FAQs relevant to the service
- Return ONLY valid JSON"""

        try:
            # Try using the agent config
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
            
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            return self._generate_template(context)
    
    def _generate_location_with_ai(self, context: Dict) -> Dict:
        """Generate location page content using AI agent config"""
        services_list = ', '.join(context.get('services', []))
        
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

Generate location-specific content emphasizing local service and expertise.
Return ONLY valid JSON."""

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
            
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            return self._generate_location_template(context)
    
    # ==========================================
    # Template Fallbacks
    # ==========================================
    
    def _generate_template(self, context: Dict) -> Dict:
        """Generate service page content from template"""
        service = context['service']
        location = context['location']
        business = context['business_name']
        
        return {
            'hero_headline': f"{service.title()} Services in {location}",
            'hero_subheadline': f"Professional {service} services you can trust. Call for a free estimate today.",
            'intro_text': f"""Looking for reliable {service} services in {location}? {business} has been serving 
local homeowners and businesses with professional {service} solutions. Our experienced team is committed to 
delivering quality work on every project.""",
            'body_content': f"""## Why Choose {business} for {service.title()}?

When you need {service} services in {location}, you want a contractor you can trust. {business} brings 
years of experience and a commitment to customer satisfaction to every job.

### Our {service.title()} Services Include:

- Professional assessment and free estimates
- Quality workmanship with attention to detail
- Competitive pricing with no hidden fees
- Fully licensed and insured team
- Satisfaction guaranteed on every project

### Serving {location} and Surrounding Areas

We proudly serve homeowners and businesses throughout {location} and nearby communities. Our local knowledge 
means we understand the unique needs of properties in this area.

### Get Started Today

Don't wait to address your {service} needs. Contact {business} today for a free consultation and estimate. 
Our friendly team is ready to help with your project.""",
            'cta_headline': f"Ready for Professional {service.title()}?",
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
                    'question': f"Are you licensed and insured?",
                    'answer': f"Yes! {business} is fully licensed and insured for your protection and peace of mind."
                }
            ],
            'meta_title': f"{service.title()} in {location} | {business}",
            'meta_description': f"Professional {service} services in {location}. {business} offers quality workmanship, free estimates, and satisfaction guaranteed. Call today!",
            'secondary_keywords': [
                f"{service} {location}",
                f"{service} near me",
                f"best {service} {location}"
            ]
        }
    
    def _generate_location_template(self, context: Dict) -> Dict:
        """Generate location page content from template"""
        location = context['location']
        business = context['business_name']
        industry = context['industry']
        services = context.get('services', [industry])
        
        services_list = ', '.join(services[:3])
        
        return {
            'hero_headline': f"{industry.title()} Services in {location}",
            'hero_subheadline': f"Your trusted local {industry} professionals. Serving {location} with pride.",
            'intro_text': f"""{business} is proud to serve the {location} community with professional {industry} services. 
Our experienced team brings quality workmanship and outstanding customer service to every project in your area.""",
            'body_content': f"""## {location}'s Trusted {industry.title()} Professionals

When {location} residents need {industry} services, they turn to {business}. We've built our reputation 
on quality work, fair pricing, and exceptional customer service.

### Services We Offer in {location}

Our comprehensive {industry} services include {services_list} and more. Whatever your needs, our skilled 
team has the expertise to get the job done right.

### Why {location} Chooses {business}

- **Local Knowledge**: We understand the unique needs of {location} properties
- **Fast Response**: Quick turnaround times for our neighbors
- **Quality Workmanship**: Attention to detail on every project
- **Fair Pricing**: Competitive rates with no surprises

### Ready to Get Started?

Contact us today to schedule your free consultation. We're proud to serve {location} and look forward 
to earning your business.""",
            'cta_headline': f"Need {industry.title()} Services in {location}?",
            'cta_button_text': "Get Free Estimate",
            'form_headline': f"Contact Us in {location}",
            'trust_badges': ['Local Company', 'Licensed', 'Insured', 'Free Estimates'],
            'meta_title': f"{industry.title()} in {location} | {business}",
            'meta_description': f"Professional {industry} services in {location}. {business} offers quality work, free estimates, and fast service. Call today!"
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
