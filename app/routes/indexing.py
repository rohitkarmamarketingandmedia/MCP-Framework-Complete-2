# app/routes/indexing.py
"""
Indexing automation API.

Per-client workflow:
    1. POST /api/indexing/connect/<client_id>         -> returns Google auth URL
    2. GET  /api/oauth/callback/gsc                   -> (handled here) stores tokens
    3. GET  /api/indexing/properties/<client_id>      -> list GSC sites for this account
    4. POST /api/indexing/site/<client_id>            -> set gsc_site_url
    5. POST /api/indexing/scan/<client_id>            -> scan now
    6. GET  /api/indexing/issues/<client_id>          -> list issues
    7. POST /api/indexing/issues/<id>/diagnose        -> run Claude diagnosis
    8. POST /api/indexing/issues/<id>/submit          -> resubmit
    9. POST /api/indexing/issues/<id>/recheck         -> re-inspect now
    10. GET  /api/indexing/indexnow/<client_id>       -> get/create IndexNow key
    11. POST /api/indexing/indexnow/<client_id>/verify -> verify key is hosted
"""
import os
import json
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, request, jsonify, redirect

from app.database import db
from app.models.db_models import (
    DBClient, DBIndexingIssue, DBIndexNowKey, IndexingStatus
)
from app.routes.auth import token_required
from app.services.gsc_service import (
    GSCService, GSCError, GSC_SCOPE_STRING, GOOGLE_TOKEN_URL, for_client as gsc_for_client
)
from app.services import indexing_service, indexnow_service

logger = logging.getLogger(__name__)

indexing_bp = Blueprint('indexing', __name__)


# ---------------------------------------------------------------------------
# Database-backed OAuth state store (works across Gunicorn workers)
# ---------------------------------------------------------------------------

class DBOAuthState(db.Model):
    """Temporary OAuth state tokens — survives multi-worker deployments."""
    __tablename__ = 'gsc_oauth_states'
    state = db.Column(db.String(64), primary_key=True)
    client_id = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


def _put_state(client_id: str) -> str:
    state = secrets.token_urlsafe(32)
    # Clean up any expired states while we're here
    db.session.query(DBOAuthState).filter(
        DBOAuthState.expires_at < datetime.utcnow()
    ).delete()
    row = DBOAuthState(
        state=state,
        client_id=str(client_id),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.add(row)
    db.session.commit()
    return state


def _take_state(state: str):
    row = DBOAuthState.query.get(state)
    if not row:
        return None
    data = {'client_id': row.client_id}
    db.session.delete(row)
    db.session.commit()
    if datetime.utcnow() > row.expires_at:
        return None
    return data


def _gsc_callback_url() -> str:
    app_url = os.getenv('APP_URL', 'https://mcp.karmamarketingandmedia.com')
    return f'{app_url}/api/indexing/oauth/callback'


# ---------------------------------------------------------------------------
# OAuth connect / callback
# ---------------------------------------------------------------------------

@indexing_bp.route('/connect/<client_id>', methods=['POST'])
@token_required
def connect(current_user, client_id):
    """Start the Google Search Console OAuth flow."""
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    google_client_id = os.getenv('GOOGLE_CLIENT_ID') or os.getenv('GBP_CLIENT_ID', '')
    if not google_client_id:
        return jsonify({'error': 'GOOGLE_CLIENT_ID or GBP_CLIENT_ID not configured'}), 500

    state = _put_state(client_id)
    params = {
        'client_id': google_client_id,
        'redirect_uri': _gsc_callback_url(),
        'scope': GSC_SCOPE_STRING,
        'state': state,
        'response_type': 'code',
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
    }
    auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}'
    return jsonify({'auth_url': auth_url, 'state': state})


@indexing_bp.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    """Google redirects here after the user grants access."""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')

    base_url = os.getenv(
        'APP_URL', 'https://mcp.karmamarketingandmedia.com'
    ) + '/client-dashboard'

    def _redirect_with(params_str):
        """Build redirect: query params BEFORE the hash so JS can read them."""
        return redirect(f'{base_url}?{params_str}#indexing')

    if error:
        return _redirect_with(f'gsc_error={error}')
    if not code or not state:
        return _redirect_with('gsc_error=missing_code_or_state')

    state_data = _take_state(state)
    if not state_data:
        return _redirect_with('gsc_error=invalid_state')

    client = DBClient.query.get(state_data['client_id'])
    if not client:
        return _redirect_with('gsc_error=client_not_found')

    # Exchange code for tokens
    try:
        resp = requests.post(GOOGLE_TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': _gsc_callback_url(),
            'client_id': os.getenv('GOOGLE_CLIENT_ID') or os.getenv('GBP_CLIENT_ID', ''),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET') or os.getenv('GBP_CLIENT_SECRET', ''),
        }, timeout=15)
        data = resp.json()
    except Exception as e:
        logger.exception(f'GSC token exchange failed: {e}')
        return _redirect_with('gsc_error=token_exchange_failed')

    if 'error' in data:
        return _redirect_with(f'gsc_error={data.get("error")}')

    access_token = data.get('access_token')
    refresh_token = data.get('refresh_token')
    expires_in = int(data.get('expires_in', 3600))

    if not refresh_token:
        # Google sometimes omits refresh_token on re-consent. Warn so we can reconnect.
        logger.warning(f'GSC connect for {client.id} returned no refresh_token')

    client.gsc_access_token = access_token
    if refresh_token:
        client.gsc_refresh_token = refresh_token
    client.gsc_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
    client.gsc_connected_at = datetime.utcnow()
    client.gsc_indexing_enabled = True
    db.session.commit()

    return _redirect_with(f'gsc_connected=1&client_id={client.id}')


@indexing_bp.route('/disconnect/<client_id>', methods=['POST'])
@token_required
def disconnect(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    client.gsc_access_token = None
    client.gsc_refresh_token = None
    client.gsc_token_expires_at = None
    client.gsc_indexing_enabled = False
    db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Properties / site selection
# ---------------------------------------------------------------------------

@indexing_bp.route('/properties/<client_id>', methods=['GET'])
@token_required
def list_properties(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    if not client.gsc_refresh_token:
        return jsonify({'error': 'GSC not connected'}), 400

    try:
        gsc = gsc_for_client(client)
        sites = gsc.list_sites()
    except GSCError as e:
        return jsonify({'error': str(e)}), 502

    return jsonify({
        'properties': [
            {
                'site_url': s.get('siteUrl'),
                'permission_level': s.get('permissionLevel'),
            } for s in sites
        ],
        'selected': client.gsc_site_url,
    })


@indexing_bp.route('/site/<client_id>', methods=['POST'])
@token_required
def set_site(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    body = request.get_json(silent=True) or {}
    site_url = (body.get('site_url') or '').strip()
    if not site_url:
        return jsonify({'error': 'site_url required'}), 400
    client.gsc_site_url = site_url
    db.session.commit()
    return jsonify({'success': True, 'site_url': site_url})


# ---------------------------------------------------------------------------
# Scan / issues
# ---------------------------------------------------------------------------

@indexing_bp.route('/test-inspect/<client_id>', methods=['POST'])
@token_required
def test_inspect(current_user, client_id):
    """Debug: inspect a single URL and return the raw GSC response."""
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    body = request.get_json(silent=True) or {}
    test_url = (body.get('url') or '').strip()
    if not test_url:
        return jsonify({'error': 'Provide a "url" to inspect'}), 400
    try:
        gsc = gsc_for_client(client)
        raw = gsc.inspect_url(test_url)
        parsed = gsc.parse_coverage_state(raw)
        return jsonify({
            'url': test_url,
            'raw_result': raw,
            'parsed': parsed,
            'is_actionable': parsed.get('coverage_state') in indexing_service.ACTIONABLE_COVERAGE_STATES,
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@indexing_bp.route('/scan/<client_id>', methods=['POST'])
@token_required
def scan(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    body = request.get_json(silent=True) or {}
    max_urls = min(int(body.get('max_urls', 100)), 500)
    # Accept optional URLs from client (browser-side sitemap fetch)
    provided_urls = body.get('urls', [])
    if provided_urls and isinstance(provided_urls, list):
        provided_urls = [u.strip() for u in provided_urls if isinstance(u, str) and u.strip()]
    result = indexing_service.scan_client(client, max_urls=max_urls, provided_urls=provided_urls)
    return jsonify(result)


@indexing_bp.route('/import-urls/<client_id>', methods=['POST'])
@token_required
def import_urls(current_user, client_id):
    """Import a list of URLs to inspect (from browser-side sitemap parse or manual paste)."""
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    body = request.get_json(silent=True) or {}
    urls = body.get('urls', [])
    if not urls or not isinstance(urls, list):
        return jsonify({'error': 'Provide a "urls" array'}), 400
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()][:500]
    result = indexing_service.scan_client(client, max_urls=len(urls), provided_urls=urls)
    return jsonify(result)


@indexing_bp.route('/issues/<client_id>', methods=['GET'])
@token_required
def list_issues(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    status_filter = request.args.get('status')
    limit = min(int(request.args.get('limit', 100)), 500)

    q = DBIndexingIssue.query.filter_by(client_id=client_id)
    if status_filter:
        q = q.filter(DBIndexingIssue.status == status_filter)
    issues = q.order_by(DBIndexingIssue.updated_at.desc()).limit(limit).all()

    # Summary counts
    counts_rows = db.session.query(
        DBIndexingIssue.status, db.func.count(DBIndexingIssue.id)
    ).filter_by(client_id=client_id).group_by(DBIndexingIssue.status).all()
    counts = {row[0]: row[1] for row in counts_rows}

    return jsonify({
        'issues': [i.to_dict() for i in issues],
        'counts': counts,
        'last_scan_at': client.gsc_last_scan_at.isoformat() if client.gsc_last_scan_at else None,
    })


@indexing_bp.route('/issues/<int:issue_id>/diagnose', methods=['POST'])
@token_required
def diagnose(current_user, issue_id):
    issue = DBIndexingIssue.query.get(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    result = indexing_service.diagnose_issue(issue)
    return jsonify(result)


@indexing_bp.route('/issues/<int:issue_id>/submit', methods=['POST'])
@token_required
def submit(current_user, issue_id):
    issue = DBIndexingIssue.query.get(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    result = indexing_service.submit_issue(issue)
    return jsonify(result)


@indexing_bp.route('/issues/<int:issue_id>/recheck', methods=['POST'])
@token_required
def recheck(current_user, issue_id):
    issue = DBIndexingIssue.query.get(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    result = indexing_service.recheck_issue(issue)
    return jsonify(result)


@indexing_bp.route('/issues/<int:issue_id>/ignore', methods=['POST'])
@token_required
def ignore(current_user, issue_id):
    issue = DBIndexingIssue.query.get(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    issue.status = IndexingStatus.IGNORED
    db.session.commit()
    return jsonify({'success': True})


@indexing_bp.route('/issues/<int:issue_id>', methods=['GET'])
@token_required
def get_issue(current_user, issue_id):
    issue = DBIndexingIssue.query.get(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    return jsonify(issue.to_dict())


# ---------------------------------------------------------------------------
# Bulk submit (handy dashboard button)
# ---------------------------------------------------------------------------

@indexing_bp.route('/submit-all/<client_id>', methods=['POST'])
@token_required
def submit_all_pending(current_user, client_id):
    """Resubmit every issue currently in DIAGNOSED or DISCOVERED state."""
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    pending = DBIndexingIssue.query.filter(
        DBIndexingIssue.client_id == client_id,
        DBIndexingIssue.status.in_([IndexingStatus.DISCOVERED, IndexingStatus.DIAGNOSED, IndexingStatus.REMEDIATED]),
    ).limit(50).all()

    results = []
    for issue in pending:
        r = indexing_service.submit_issue(issue, client)
        results.append({'issue_id': issue.id, 'url': issue.url, 'result': r})

    return jsonify({'submitted': len(results), 'results': results})


# ---------------------------------------------------------------------------
# IndexNow helpers
# ---------------------------------------------------------------------------

@indexing_bp.route('/indexnow/<client_id>', methods=['GET'])
@token_required
def get_indexnow_key(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    record = indexnow_service.get_or_create_key(client)
    return jsonify(record.to_dict())


@indexing_bp.route('/indexnow/<client_id>/verify', methods=['POST'])
@token_required
def verify_indexnow_key(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    record = indexnow_service.get_or_create_key(client)
    ok = indexnow_service.verify_key_hosted(record)
    return jsonify({'verified': ok, 'key_location_url': record.key_location_url})


@indexing_bp.route('/indexnow/<client_id>/regenerate', methods=['POST'])
@token_required
def regenerate_indexnow_key(current_user, client_id):
    from urllib.parse import urlparse
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    record = DBIndexNowKey.query.filter_by(client_id=client_id).first()
    if not record:
        record = indexnow_service.get_or_create_key(client)
    else:
        record.key = indexnow_service.generate_key()
        host = urlparse(client.website_url or '').hostname or ''
        if host:
            record.key_location_url = indexnow_service.expected_key_location(host, record.key)
        record.verified = False
        record.verified_at = None
        db.session.commit()
    return jsonify(record.to_dict())


# ---------------------------------------------------------------------------
# Status / health
# ---------------------------------------------------------------------------

@indexing_bp.route('/status/<client_id>', methods=['GET'])
@token_required
def status(current_user, client_id):
    client = DBClient.query.get(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    counts_rows = db.session.query(
        DBIndexingIssue.status, db.func.count(DBIndexingIssue.id)
    ).filter_by(client_id=client_id).group_by(DBIndexingIssue.status).all()
    counts = {row[0]: row[1] for row in counts_rows}

    return jsonify({
        'connected': bool(client.gsc_refresh_token),
        'site_url': client.gsc_site_url,
        'indexing_enabled': client.gsc_indexing_enabled,
        'connected_at': client.gsc_connected_at.isoformat() if client.gsc_connected_at else None,
        'last_scan_at': client.gsc_last_scan_at.isoformat() if client.gsc_last_scan_at else None,
        'issue_counts': counts,
    })
