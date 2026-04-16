# app/services/gsc_service.py
"""
Google Search Console service.

Wraps:
- URL Inspection API  (https://searchconsole.googleapis.com/v1/urlInspection/index:inspect)
- Sitemaps API        (https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/sitemaps)
- Indexing API        (https://indexing.googleapis.com/v3/urlNotifications:publish)

Tokens are stored per-client on DBClient (gsc_access_token / gsc_refresh_token)
and refreshed on demand.

NOTE on the Indexing API:
  Google documents it as "Job Postings and Livestream" only. In practice it
  accepts any URL and is widely used for general indexing, but it is a gray
  area. We always pair it with sitemap pings and (where configured) IndexNow.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

import requests

logger = logging.getLogger(__name__)


GSC_SCOPES = [
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/webmasters',
    'https://www.googleapis.com/auth/indexing',
]
GSC_SCOPE_STRING = ' '.join(GSC_SCOPES)

GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
URL_INSPECTION_URL = 'https://searchconsole.googleapis.com/v1/urlInspection/index:inspect'
SITES_LIST_URL = 'https://www.googleapis.com/webmasters/v3/sites'
SEARCH_ANALYTICS_URL = 'https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query'
SITEMAPS_BASE = 'https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps'
INDEXING_PUBLISH_URL = 'https://indexing.googleapis.com/v3/urlNotifications:publish'
INDEXING_METADATA_URL = 'https://indexing.googleapis.com/v3/urlNotifications/metadata'


class GSCError(Exception):
    """Raised when a GSC API call fails in a way callers should handle."""
    pass


class GSCService:
    """Per-client Google Search Console client.

    Construct with a DBClient instance; call methods as needed. Access tokens
    are refreshed automatically when expired.
    """

    def __init__(self, client):
        self.client = client
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _google_credentials(self) -> Tuple[str, str]:
        """Read Google OAuth credentials from environment."""
        cid = os.getenv('GOOGLE_CLIENT_ID') or os.getenv('GBP_CLIENT_ID', '')
        sec = os.getenv('GOOGLE_CLIENT_SECRET') or os.getenv('GBP_CLIENT_SECRET', '')
        if not cid or not sec:
            raise GSCError('GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (or GBP_CLIENT_ID / GBP_CLIENT_SECRET) not configured')
        return cid, sec

    def _refresh_access_token(self) -> str:
        """Refresh the stored access token using the refresh token."""
        if not self.client.gsc_refresh_token:
            raise GSCError('Client has no GSC refresh token; reconnect required')

        cid, sec = self._google_credentials()

        resp = requests.post(GOOGLE_TOKEN_URL, data={
            'client_id': cid,
            'client_secret': sec,
            'refresh_token': self.client.gsc_refresh_token,
            'grant_type': 'refresh_token',
        }, timeout=15)

        if resp.status_code != 200:
            raise GSCError(f'Token refresh failed: {resp.status_code} {resp.text[:200]}')

        data = resp.json()
        access_token = data['access_token']
        expires_in = int(data.get('expires_in', 3600))

        # Persist
        from app.database import db
        self.client.gsc_access_token = access_token
        self.client.gsc_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
        db.session.commit()
        return access_token

    def _access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        expires = self.client.gsc_token_expires_at
        if (not self.client.gsc_access_token
                or not expires
                or expires <= datetime.utcnow()):
            return self._refresh_access_token()
        return self.client.gsc_access_token

    def _authed_headers(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        headers = {
            'Authorization': f'Bearer {self._access_token()}',
            'Content-Type': 'application/json',
        }
        if extra:
            headers.update(extra)
        return headers

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------

    def list_sites(self) -> List[Dict]:
        """Return all GSC properties this client's Google account can access."""
        resp = self._session.get(SITES_LIST_URL, headers=self._authed_headers(), timeout=15)
        if resp.status_code != 200:
            raise GSCError(f'list_sites failed: {resp.status_code} {resp.text[:200]}')
        return resp.json().get('siteEntry', [])

    # ------------------------------------------------------------------
    # Search Analytics — discover URLs Google knows about
    # ------------------------------------------------------------------

    def query_search_analytics(self, days: int = 90, row_limit: int = 500) -> List[str]:
        """
        Query GSC Search Analytics for all pages Google has data on.
        Returns a list of page URLs (deduplicated).
        This goes through googleapis.com so it works even when the site itself
        is unreachable from the server.
        """
        site = self.client.gsc_site_url
        if not site:
            raise GSCError('No gsc_site_url configured')

        from datetime import date, timedelta as td
        end = date.today() - td(days=3)  # GSC data has ~3 day lag
        start = end - td(days=days)

        url = SEARCH_ANALYTICS_URL.format(site=requests.utils.quote(site, safe=''))
        body = {
            'startDate': start.isoformat(),
            'endDate': end.isoformat(),
            'dimensions': ['page'],
            'rowLimit': row_limit,
            'dataState': 'all',
        }

        resp = self._session.post(url, headers=self._authed_headers(), json=body, timeout=30)
        if resp.status_code != 200:
            raise GSCError(f'search_analytics query failed: {resp.status_code} {resp.text[:300]}')

        rows = resp.json().get('rows', [])
        pages = []
        for row in rows:
            keys = row.get('keys', [])
            if keys:
                pages.append(keys[0])

        logger.info(f'[gsc] Search Analytics returned {len(pages)} pages for {site}')
        return pages

    # ------------------------------------------------------------------
    # URL inspection — this is how we confirm "Crawled - currently not indexed"
    # ------------------------------------------------------------------

    def inspect_url(self, inspection_url: str, site_url: Optional[str] = None) -> Dict:
        """
        Inspect a single URL's coverage / indexing state.
        Returns the raw GSC inspectionResult dict.

        Reference: https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect
        """
        site = site_url or self.client.gsc_site_url
        if not site:
            raise GSCError('No gsc_site_url configured for client')

        body = {
            'inspectionUrl': inspection_url,
            'siteUrl': site,
        }
        resp = self._session.post(
            URL_INSPECTION_URL,
            headers=self._authed_headers(),
            json=body,
            timeout=30,
        )
        if resp.status_code != 200:
            raise GSCError(f'inspect_url failed: {resp.status_code} {resp.text[:500]}')
        return resp.json().get('inspectionResult', {})

    @staticmethod
    def parse_coverage_state(inspection_result: Dict) -> Dict:
        """Flatten the nested inspectionResult into the fields we store."""
        index_status = inspection_result.get('indexStatusResult', {}) or {}
        return {
            'coverage_state': index_status.get('coverageState', 'Unknown'),
            'verdict': index_status.get('verdict'),
            'robots_txt_state': index_status.get('robotsTxtState'),
            'indexing_state': index_status.get('indexingState'),
            'last_crawl_time': index_status.get('lastCrawlTime'),
            'crawled_as': index_status.get('crawledAs'),
            'page_fetch_state': index_status.get('pageFetchState'),
            'google_canonical': index_status.get('googleCanonical'),
            'user_canonical': index_status.get('userCanonical'),
            'referring_urls': index_status.get('referringUrls', []),
        }

    # ------------------------------------------------------------------
    # Sitemaps — list + (re-)submit
    # ------------------------------------------------------------------

    def list_sitemaps(self) -> List[Dict]:
        site = self.client.gsc_site_url
        if not site:
            raise GSCError('No gsc_site_url configured')
        url = SITEMAPS_BASE.format(site=requests.utils.quote(site, safe=''))
        resp = self._session.get(url, headers=self._authed_headers(), timeout=15)
        if resp.status_code != 200:
            raise GSCError(f'list_sitemaps failed: {resp.status_code} {resp.text[:200]}')
        return resp.json().get('sitemap', [])

    def submit_sitemap(self, sitemap_url: str) -> bool:
        """(Re-)submit a sitemap. Google treats this as a crawl hint."""
        site = self.client.gsc_site_url
        if not site:
            raise GSCError('No gsc_site_url configured')
        url = SITEMAPS_BASE.format(site=requests.utils.quote(site, safe=''))
        url = f'{url}/{requests.utils.quote(sitemap_url, safe="")}'
        resp = self._session.put(url, headers=self._authed_headers(), timeout=15)
        if resp.status_code not in (200, 204):
            logger.warning(f'submit_sitemap failed: {resp.status_code} {resp.text[:200]}')
            return False
        return True

    @staticmethod
    def ping_sitemap_public(sitemap_url: str) -> bool:
        """Unauthenticated sitemap ping — Google's legacy open endpoint."""
        try:
            r = requests.get(
                'https://www.google.com/ping',
                params={'sitemap': sitemap_url},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as e:
            logger.warning(f'ping_sitemap_public failed: {e}')
            return False

    # ------------------------------------------------------------------
    # Indexing API — notify Google of URL updates
    # ------------------------------------------------------------------

    def notify_url_updated(self, url: str) -> Dict:
        """
        Notify Google's Indexing API that a URL has been updated.
        Returns the parsed response; raises GSCError on HTTP failure.
        """
        body = {'url': url, 'type': 'URL_UPDATED'}
        resp = self._session.post(
            INDEXING_PUBLISH_URL,
            headers=self._authed_headers(),
            json=body,
            timeout=15,
        )
        if resp.status_code != 200:
            raise GSCError(f'notify_url_updated failed: {resp.status_code} {resp.text[:300]}')
        return resp.json()

    def notify_url_deleted(self, url: str) -> Dict:
        body = {'url': url, 'type': 'URL_DELETED'}
        resp = self._session.post(
            INDEXING_PUBLISH_URL,
            headers=self._authed_headers(),
            json=body,
            timeout=15,
        )
        if resp.status_code != 200:
            raise GSCError(f'notify_url_deleted failed: {resp.status_code} {resp.text[:300]}')
        return resp.json()

    def get_indexing_metadata(self, url: str) -> Dict:
        """Most-recent Indexing API notification for a URL (debugging aid)."""
        resp = self._session.get(
            INDEXING_METADATA_URL,
            headers=self._authed_headers(),
            params={'url': url},
            timeout=15,
        )
        if resp.status_code != 200:
            raise GSCError(f'get_indexing_metadata failed: {resp.status_code} {resp.text[:200]}')
        return resp.json()


def for_client(client) -> GSCService:
    """Convenience factory: build a GSCService for a given DBClient."""
    return GSCService(client)
