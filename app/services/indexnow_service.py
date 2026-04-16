# app/services/indexnow_service.py
"""
IndexNow — open protocol (Bing, Yandex, Seznam, Naver, Yep) for instantly
notifying search engines of new/updated URLs.

Flow:
    1. generate a key per host
    2. host {key}.txt at https://{host}/{key}.txt  (content = key itself)
    3. POST URLs to https://api.indexnow.org/indexnow
"""
import logging
import secrets
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

INDEXNOW_ENDPOINT = 'https://api.indexnow.org/indexnow'


class IndexNowError(Exception):
    pass


def generate_key() -> str:
    """32-128 hex chars per spec. 48 is a good balance."""
    return secrets.token_hex(24)


def expected_key_location(host: str, key: str) -> str:
    return f'https://{host}/{key}.txt'


def get_or_create_key(client) -> 'object':
    """Return the DBIndexNowKey for this client, creating one if missing."""
    from app.database import db
    from app.models.db_models import DBIndexNowKey

    existing = DBIndexNowKey.query.filter_by(client_id=client.id).first()
    if existing:
        return existing

    website = client.website_url or ''
    host = urlparse(website).hostname or ''

    record = DBIndexNowKey(
        client_id=client.id,
        key=generate_key(),
        key_location_url=expected_key_location(host, generate_key()) if host else None,
    )
    # Regenerate so location_url matches the stored key
    record.key = generate_key()
    if host:
        record.key_location_url = expected_key_location(host, record.key)
    db.session.add(record)
    db.session.commit()
    return record


def verify_key_hosted(key_record) -> bool:
    """Check that {key}.txt is publicly reachable and contains the key."""
    if not key_record.key_location_url:
        return False
    try:
        resp = requests.get(key_record.key_location_url, timeout=10)
        if resp.status_code != 200:
            return False
        if key_record.key.strip() not in resp.text.strip():
            return False

        from app.database import db
        key_record.verified = True
        key_record.verified_at = datetime.utcnow()
        db.session.commit()
        return True
    except Exception as e:
        logger.warning(f'IndexNow key verification failed: {e}')
        return False


def submit_urls(client, urls: List[str]) -> dict:
    """
    Submit one or more URLs to IndexNow. All URLs must share the same host
    as the verified key. Returns a dict with counts + raw response.
    """
    if not urls:
        return {'success': False, 'error': 'no urls'}

    key_record = get_or_create_key(client)
    if not key_record.verified:
        # Try to verify on the fly
        if not verify_key_hosted(key_record):
            return {
                'success': False,
                'error': 'indexnow_key_not_verified',
                'key_location_url': key_record.key_location_url,
                'key': key_record.key,
                'instructions': (
                    f'Host a text file at {key_record.key_location_url} whose '
                    f'contents are exactly: {key_record.key}'
                ),
            }

    host = urlparse(urls[0]).hostname
    body = {
        'host': host,
        'key': key_record.key,
        'keyLocation': key_record.key_location_url,
        'urlList': urls,
    }

    try:
        resp = requests.post(INDEXNOW_ENDPOINT, json=body, timeout=15)
        # Any 2xx is success. 202 = received but not yet processed.
        success = 200 <= resp.status_code < 300
        return {
            'success': success,
            'status_code': resp.status_code,
            'submitted_count': len(urls),
            'response_text': (resp.text or '')[:300],
        }
    except Exception as e:
        logger.error(f'IndexNow submit failed: {e}')
        return {'success': False, 'error': str(e)}
