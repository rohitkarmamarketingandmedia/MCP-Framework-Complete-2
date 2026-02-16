"""
MCP Framework - Accessibility Routes
API endpoints for accessibility widget config, scanning, and reports
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import json
import logging
import requests

from app.database import db
from app.models.db_models import DBClient
from app.routes.auth import token_required, optional_token
from app.services.accessibility_scanner import get_accessibility_scanner

logger = logging.getLogger(__name__)

accessibility_bp = Blueprint('accessibility', __name__, url_prefix='/api/accessibility')


# ==========================================
# Widget Configuration
# ==========================================

@accessibility_bp.route('/widget-config/<client_id>', methods=['GET'])
@token_required
def get_widget_config(current_user, client_id):
    """Get accessibility widget configuration for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Widget config stored as JSON in client metadata or a dedicated field
    config = _get_client_a11y_config(client)
    
    return jsonify(config)


@accessibility_bp.route('/widget-config/<client_id>', methods=['PUT'])
@token_required
def update_widget_config(current_user, client_id):
    """Update accessibility widget configuration"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    
    # Store config
    allowed_fields = ['enabled', 'position', 'color', 'statement_text']
    config = _get_client_a11y_config(client)
    
    for field in allowed_fields:
        if field in data:
            config[field] = data[field]
    
    _save_client_a11y_config(client, config)
    
    return jsonify({
        'message': 'Widget configuration updated',
        'config': config
    })


@accessibility_bp.route('/embed-code/<client_id>', methods=['GET'])
@token_required
def get_embed_code(current_user, client_id):
    """Get the embed code for the accessibility widget"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    config = _get_client_a11y_config(client)
    base_url = request.host_url.rstrip('/')
    
    embed_code = f"""<script>
(function() {{
    var s = document.createElement('script');
    s.src = '{base_url}/static/accessibility-widget.js';
    s.async = true;
    s.onload = function() {{
        MCPAccessibility.init({{
            clientId: '{client_id}',
            apiUrl: '{base_url}',
            position: '{config.get("position", "left")}',
            color: '{config.get("color", "#0064fe")}'
        }});
    }};
    document.head.appendChild(s);
}})();
</script>"""
    
    return jsonify({
        'embed_code': embed_code,
        'client_id': client_id
    })


# ==========================================
# Accessibility Scanner
# ==========================================

@accessibility_bp.route('/scan/<client_id>', methods=['POST'])
@token_required
def scan_website(current_user, client_id):
    """Scan a client's website for accessibility issues"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json(silent=True) or {}
    url = data.get('url', '') or client.website_url
    
    if not url:
        return jsonify({'error': 'No URL provided and no website URL configured for this client'}), 400
    
    # Ensure URL has protocol
    if not url.startswith('http'):
        url = 'https://' + url
    
    try:
        logger.info(f"Scanning accessibility for {url} (client: {client_id})")
        
        # Fetch the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; MCPAccessibilityScanner/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        html = response.text
        
        # Run the scanner
        scanner = get_accessibility_scanner()
        results = scanner.scan_html(html, url)
        
        # Save results
        config = _get_client_a11y_config(client)
        config['last_scan'] = results
        config['last_scan_date'] = datetime.utcnow().isoformat()
        _save_client_a11y_config(client, config)
        
        logger.info(f"Scan complete for {url}: score={results['summary']['score']}")
        
        return jsonify({
            'message': 'Scan complete',
            'results': results
        })
    
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return jsonify({'error': f'Could not fetch website: {str(e)}'}), 400
    except Exception as e:
        logger.error(f"Scan failed for {url}: {e}")
        return jsonify({'error': f'Scan failed: {str(e)}'}), 500


@accessibility_bp.route('/report/<client_id>', methods=['GET'])
@token_required
def get_report(current_user, client_id):
    """Get the latest accessibility scan report"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    config = _get_client_a11y_config(client)
    last_scan = config.get('last_scan')
    
    if not last_scan:
        return jsonify({
            'has_report': False,
            'message': 'No scan has been performed yet. Run a scan first.'
        })
    
    return jsonify({
        'has_report': True,
        'scan_date': config.get('last_scan_date'),
        'results': last_scan
    })


# ==========================================
# Helpers
# ==========================================

def _get_client_a11y_config(client) -> dict:
    """Get accessibility config from client integrations"""
    try:
        integrations = {}
        if hasattr(client, 'integrations') and client.integrations:
            integrations = json.loads(client.integrations) if isinstance(client.integrations, str) else client.integrations
        return integrations.get('accessibility', {
            'enabled': False,
            'position': 'left',
            'color': '#0064fe',
            'statement_text': ''
        })
    except Exception:
        return {
            'enabled': False,
            'position': 'left',
            'color': '#0064fe',
            'statement_text': ''
        }


def _save_client_a11y_config(client, config: dict):
    """Save accessibility config to client integrations"""
    try:
        integrations = {}
        if hasattr(client, 'integrations') and client.integrations:
            integrations = json.loads(client.integrations) if isinstance(client.integrations, str) else client.integrations
        integrations['accessibility'] = config
        client.integrations = json.dumps(integrations)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to save a11y config: {e}")
        db.session.rollback()
