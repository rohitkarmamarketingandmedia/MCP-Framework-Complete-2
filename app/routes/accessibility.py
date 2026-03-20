"""
MCP Framework - Accessibility Routes
API endpoints for accessibility widget config, scanning, and reports
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import json
import logging
import requests as http_requests
import subprocess
import sys

from app.database import db
from app.models.db_models import DBClient
from app.routes.auth import token_required, optional_token
from app.services.accessibility_scanner import get_accessibility_scanner

logger = logging.getLogger(__name__)


def _fetch_rendered_html(url: str, timeout: int = 30) -> dict:
    """
    Fetch a URL and return fully-rendered HTML (after JavaScript execution).
    Uses Playwright (headless Chromium) if available, falls back to requests.
    Returns dict with 'html', 'method', 'final_url', 'status_code'.
    """
    # Try Playwright first — renders JavaScript like a real browser
    try:
        from playwright.sync_api import sync_playwright
        logger.info(f"Using Playwright to render {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720},
                locale='en-US',
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until='networkidle', timeout=timeout * 1000)
            except Exception:
                # networkidle can be flaky; fall back to domcontentloaded
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                    page.wait_for_timeout(3000)  # give JS 3 extra seconds
                except Exception:
                    pass
            html = page.content()
            final_url = page.url
            browser.close()
            logger.info(f"Playwright rendered {len(html)} chars for {url}")
            return {'html': html, 'method': 'playwright', 'final_url': final_url, 'status_code': 200}
    except ImportError:
        logger.info("Playwright not installed — falling back to requests")
    except Exception as e:
        logger.warning(f"Playwright failed for {url}: {e} — falling back to requests")

    # Fallback: plain HTTP fetch (won't execute JavaScript)
    # NOTE: Do NOT include 'br' (brotli) in Accept-Encoding — requests can't decode it
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    session = http_requests.Session()
    response = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    # Force proper encoding detection
    if response.encoding and response.encoding.lower() == 'iso-8859-1' and 'charset' not in response.headers.get('Content-Type', ''):
        response.encoding = response.apparent_encoding or 'utf-8'
    html = response.text
    logger.info(f"requests fetched {len(html)} chars for {url} (status={response.status_code}, encoding={response.encoding}, final_url={response.url})")
    return {'html': html, 'method': 'requests', 'final_url': str(response.url), 'status_code': response.status_code}

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

        # Fetch the fully-rendered page (Playwright if available, else requests)
        fetch_result = _fetch_rendered_html(url, timeout=30)
        html = fetch_result['html']
        fetch_method = fetch_result['method']
        final_url = fetch_result.get('final_url', url)

        logger.info(f"Fetched {len(html)} chars via {fetch_method} from {final_url}")

        # Check if we got a real page
        html_lower = html.lower()
        is_challenge = (
            ('cf-browser-verification' in html_lower or 'cf-challenge' in html_lower or 'cf_chl_opt' in html_lower) and
            len(html) < 5000
        )
        if len(html) < 100 or is_challenge:
            logger.warning(f"Received bot challenge or empty page from {url} ({len(html)} chars)")
            return jsonify({'error': 'Website returned a bot challenge page. The site may be using Cloudflare or similar protection.'}), 400

        # Log first 500 chars of HTML for debugging
        logger.info(f"HTML preview for {url}: {html[:500]}")

        # Run the scanner
        scanner = get_accessibility_scanner()
        results = scanner.scan_html(html, url)

        # Add fetch diagnostics to results
        results['fetch_info'] = {
            'method': fetch_method,
            'html_length': len(html),
            'final_url': final_url,
            'has_doctype': '<!doctype' in html_lower[:100],
            'has_html_tag': '<html' in html_lower,
            'has_head': '<head' in html_lower,
            'has_body': '<body' in html_lower,
            'has_title_tag': '<title' in html_lower,
        }

        # Save results
        config = _get_client_a11y_config(client)
        config['last_scan'] = results
        config['last_scan_date'] = datetime.utcnow().isoformat()
        _save_client_a11y_config(client, config)

        logger.info(f"Scan complete for {url}: score={results['summary']['score']}, method={fetch_method}, html_len={len(html)}")

        return jsonify({
            'message': 'Scan complete',
            'results': results
        })
    
    except http_requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return jsonify({'error': f'Could not fetch website: {str(e)}'}), 400
    except Exception as e:
        logger.error(f"Scan failed for {url}: {e}")
        return jsonify({'error': f'Scan failed: {str(e)}'}), 500


@accessibility_bp.route('/debug-fetch', methods=['POST'])
@token_required
def debug_fetch(current_user):
    """Debug endpoint: shows what HTML the server fetches for a URL"""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    if not url.startswith('http'):
        url = 'https://' + url

    try:
        fetch_result = _fetch_rendered_html(url, timeout=30)
        html = fetch_result['html']
        html_lower = html.lower()

        # Count key elements
        import re
        return jsonify({
            'url': url,
            'final_url': fetch_result.get('final_url', url),
            'method': fetch_result['method'],
            'status_code': fetch_result.get('status_code'),
            'html_length': len(html),
            'html_preview_first_1000': html[:1000],
            'html_preview_last_500': html[-500:] if len(html) > 500 else html,
            'has_doctype': '<!doctype' in html_lower[:100],
            'has_html_tag': '<html' in html_lower,
            'has_head': '<head' in html_lower,
            'has_body': '<body' in html_lower,
            'has_title': bool(re.search(r'<title[^>]*>.+?</title>', html, re.I | re.S)),
            'title_content': (re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S).group(1).strip() if re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S) else 'NOT FOUND'),
            'count_h1': len(re.findall(r'<h1\b', html, re.I)),
            'count_h2': len(re.findall(r'<h2\b', html, re.I)),
            'count_img': len(re.findall(r'<img\b', html, re.I)),
            'count_a': len(re.findall(r'<a\b', html, re.I)),
            'count_nav': len(re.findall(r'<nav\b', html, re.I)),
            'count_main': len(re.findall(r'<main\b', html, re.I)),
            'count_footer': len(re.findall(r'<footer\b', html, re.I)),
        })
    except Exception as e:
        logger.error(f"Debug fetch failed for {url}: {e}")
        return jsonify({'error': str(e)}), 500


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
