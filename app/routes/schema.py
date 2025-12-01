"""
MCP Framework - Schema Markup Routes
JSON-LD schema generation for SEO
"""
from flask import Blueprint, request, jsonify
from app.routes.auth import token_required
from app.services.ai_service import AIService
from app.services.db_service import DataService
from app.models.db_models import DBSchemaMarkup
import json

schema_bp = Blueprint('schema', __name__)
ai_service = AIService()
data_service = DataService()


@schema_bp.route('/generate', methods=['POST'])
@token_required
def generate_schema(current_user):
    """
    Generate JSON-LD schema markup
    
    POST /api/schema/generate
    {
        "client_id": "client_abc123",
        "schema_type": "LocalBusiness",
        "data": {
            "business_name": "ABC Roofing",
            "description": "Professional roofing services",
            "address": "123 Main St, Sarasota, FL",
            "phone": "(941) 555-1234",
            "geo": {"lat": 27.3364, "lng": -82.5306},
            "services": ["Roof Repair", "Roof Replacement"],
            "opening_hours": ["Mo-Fr 08:00-17:00", "Sa 09:00-14:00"]
        }
    }
    """
    if not current_user.can_generate_content:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    
    if not data.get('client_id') or not data.get('schema_type'):
        return jsonify({'error': 'client_id and schema_type required'}), 400
    
    client = data_service.get_client(data['client_id'])
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    if not current_user.has_access_to_client(data['client_id']):
        return jsonify({'error': 'Access denied'}), 403
    
    schema_type = data['schema_type']
    schema_data = data.get('data', {})
    
    # Generate based on type
    if schema_type == 'LocalBusiness':
        json_ld = create_local_business_schema(client, schema_data)
    elif schema_type == 'FAQ':
        faqs = schema_data.get('faqs', [])
        if not faqs:
            return jsonify({'error': 'FAQs required for FAQ schema'}), 400
        json_ld = create_faq_schema(faqs)
    elif schema_type == 'Article':
        json_ld = create_article_schema(schema_data)
    elif schema_type == 'Service':
        json_ld = create_service_schema(schema_data)
    elif schema_type == 'Product':
        json_ld = create_product_schema(schema_data)
    else:
        return jsonify({'error': f'Unsupported schema type: {schema_type}'}), 400
    
    # Save schema
    schema = DBSchemaMarkup(
        client_id=data['client_id'],
        schema_type=schema_type,
        json_ld=json_ld,
        name=schema_data.get('name', schema_type)
    )
    data_service.save_schema(schema)
    
    return jsonify({
        'success': True,
        'schema_id': schema.id,
        'schema_type': schema.schema_type,
        'json_ld': schema.get_json_ld(),
        'html_script': f'<script type="application/ld+json">\n{json.dumps(json_ld, indent=2)}\n</script>'
    })


@schema_bp.route('/validate', methods=['POST'])
@token_required
def validate_schema(current_user):
    """
    Validate JSON-LD schema
    
    POST /api/schema/validate
    {
        "schema": { ... JSON-LD object ... }
    }
    """
    data = request.get_json() or {}
    schema = data.get('schema', {})
    
    errors = []
    warnings = []
    
    # Basic validation
    if '@context' not in schema:
        errors.append('Missing @context (should be "https://schema.org")')
    elif schema['@context'] != 'https://schema.org':
        warnings.append('@context should be "https://schema.org"')
    
    if '@type' not in schema:
        errors.append('Missing @type')
    
    # Type-specific validation
    schema_type = schema.get('@type', '')
    
    if schema_type == 'LocalBusiness':
        required_fields = ['name', 'address', 'telephone']
        for field in required_fields:
            if field not in schema:
                errors.append(f'LocalBusiness: Missing required field "{field}"')
    
    elif schema_type == 'Article':
        required_fields = ['headline', 'author', 'datePublished']
        for field in required_fields:
            if field not in schema:
                errors.append(f'Article: Missing required field "{field}"')
    
    elif schema_type == 'FAQPage':
        if 'mainEntity' not in schema:
            errors.append('FAQPage: Missing mainEntity array')
        elif not isinstance(schema['mainEntity'], list):
            errors.append('FAQPage: mainEntity should be an array')
    
    return jsonify({
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    })


@schema_bp.route('/<schema_id>', methods=['GET'])
@token_required
def get_schema(current_user, schema_id):
    """Get schema by ID"""
    schema = data_service.get_schema(schema_id)
    
    if not schema:
        return jsonify({'error': 'Schema not found'}), 404
    
    if not current_user.has_access_to_client(schema.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    json_ld = schema.get_json_ld()
    return jsonify({
        'id': schema.id,
        'client_id': schema.client_id,
        'schema_type': schema.schema_type,
        'json_ld': json_ld,
        'html_script': f'<script type="application/ld+json">\n{json.dumps(json_ld, indent=2)}\n</script>'
    })


@schema_bp.route('/<schema_id>', methods=['DELETE'])
@token_required
def delete_schema(current_user, schema_id):
    """Delete schema"""
    schema = data_service.get_schema(schema_id)
    
    if not schema:
        return jsonify({'error': 'Schema not found'}), 404
    
    if not current_user.has_access_to_client(schema.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data_service.delete_schema(schema_id)
    
    return jsonify({'message': 'Schema deleted'})


@schema_bp.route('/client/<client_id>', methods=['GET'])
@token_required
def list_client_schemas(current_user, client_id):
    """List all schemas for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    schemas = data_service.get_client_schemas(client_id)
    
    return jsonify({
        'client_id': client_id,
        'total': len(schemas),
        'schemas': [s.to_dict() for s in schemas]
    })


# Helper functions for schema creation
def create_local_business_schema(client, data: dict) -> dict:
    """Create LocalBusiness schema"""
    return {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": data.get('business_name', client.business_name),
        "description": data.get('description', ''),
        "address": {
            "@type": "PostalAddress",
            "streetAddress": data.get('address', client.geo)
        },
        "telephone": data.get('phone', client.phone),
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": data.get('geo', {}).get('lat', 0),
            "longitude": data.get('geo', {}).get('lng', 0)
        },
        "openingHoursSpecification": data.get('opening_hours', []),
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "Services",
            "itemListElement": [
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s}}
                for s in data.get('services', [])
            ]
        }
    }


def create_faq_schema(faqs: list) -> dict:
    """Create FAQ schema"""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq.get('question', ''),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq.get('answer', '')
                }
            }
            for faq in faqs
        ]
    }


def create_article_schema(data: dict) -> dict:
    """Create Article schema"""
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": data.get('headline', ''),
        "author": {
            "@type": "Person",
            "name": data.get('author', '')
        },
        "datePublished": data.get('date_published', ''),
        "dateModified": data.get('date_modified', data.get('date_published', '')),
        "publisher": {
            "@type": "Organization",
            "name": data.get('publisher_name', ''),
            "logo": {
                "@type": "ImageObject",
                "url": data.get('publisher_logo', '')
            }
        },
        "description": data.get('description', ''),
        "image": data.get('image', '')
    }


def create_service_schema(data: dict) -> dict:
    """Create Service schema"""
    return {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": data.get('name', ''),
        "description": data.get('description', ''),
        "provider": {
            "@type": "LocalBusiness",
            "name": data.get('provider_name', ''),
            "address": data.get('address', '')
        },
        "areaServed": data.get('area_served', []),
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": data.get('name', '') + " Options",
            "itemListElement": [
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s}}
                for s in data.get('sub_services', [])
            ]
        }
    }


def create_product_schema(data: dict) -> dict:
    """Create Product schema"""
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": data.get('name', ''),
        "description": data.get('description', ''),
        "image": data.get('image', ''),
        "brand": {
            "@type": "Brand",
            "name": data.get('brand', '')
        },
        "offers": {
            "@type": "Offer",
            "price": data.get('price', ''),
            "priceCurrency": data.get('currency', 'USD'),
            "availability": data.get('availability', 'https://schema.org/InStock')
        }
    }
    
    if data.get('rating'):
        schema['aggregateRating'] = {
            "@type": "AggregateRating",
            "ratingValue": data['rating'],
            "reviewCount": data.get('review_count', 1)
        }
    
    return schema
