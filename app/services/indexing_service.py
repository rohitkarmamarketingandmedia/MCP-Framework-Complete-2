# app/services/indexing_service.py
"""
Indexing automation orchestrator.

Pipeline:
    1. scan_client(client)       — pull candidate URLs and inspect each via GSC
    2. diagnose_issue(issue)     — Claude analyzes the page & produces a diagnosis
    3. remediate_issue(issue)    — optional auto-fix (thin content, internal links, schema)
    4. submit_issue(issue)       — re-submit to Google Indexing API + IndexNow + sitemap ping
    5. recheck_issue(issue)      — re-inspect via URL Inspection API after N days

Coverage states we care about (lowest-hanging fruit first):
    - 'Crawled - currently not indexed'
    - 'Discovered - currently not indexed'
    - 'Duplicate without user-selected canonical'
    - 'Duplicate, Google chose different canonical than user'
    - 'Alternate page with proper canonical tag'   (informational only)
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from urllib.parse import urlparse

import requests

from app.database import db
from app.models.db_models import (
    DBClient, DBIndexingIssue, DBBlogPost, IndexingStatus
)
from app.services.gsc_service import GSCService, GSCError, for_client as gsc_for_client
from app.services import indexnow_service

logger = logging.getLogger(__name__)


# States where resubmission is worth attempting (lowercase keys for matching)
_ACTIONABLE_LOWER = {
    'crawled - currently not indexed',
    'discovered - currently not indexed',
    'duplicate without user-selected canonical',
    'duplicate, google chose different canonical than user',
    'page with redirect',
}

# Keep original-case set for backward compat
ACTIONABLE_COVERAGE_STATES = {
    'Crawled - currently not indexed',
    'Discovered - currently not indexed',
    'Duplicate without user-selected canonical',
    'Duplicate, Google chose different canonical than user',
    'Page with redirect',
}


def _is_actionable(coverage_state):
    return (coverage_state or '').lower().strip() in _ACTIONABLE_LOWER


def _is_indexed(coverage_state):
    low = (coverage_state or '').lower()
    return 'submitted and indexed' in low or 'indexed, not submitted' in low


# ---------------------------------------------------------------------------
# Sitemap fetching — discover ALL site URLs
# ---------------------------------------------------------------------------

def _fetch_sitemap_urls(sitemap_url: str, max_urls: int = 500, _depth: int = 0) -> List[str]:
    """
    Fetch and parse a sitemap (or sitemap index) and return all <loc> URLs.
    Handles sitemap indexes recursively (up to 2 levels deep).
    """
    if _depth > 2:
        return []

    try:
        resp = requests.get(sitemap_url, timeout=20, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; KarmaMCPIndexer/1.0)',
        })
        if resp.status_code != 200:
            logger.warning(f'Sitemap fetch failed ({resp.status_code}): {sitemap_url}')
            return []
    except Exception as e:
        logger.warning(f'Sitemap fetch error for {sitemap_url}: {e}')
        return []

    urls = []
    content = resp.content

    # Strip XML processing instructions (<?xml-stylesheet ...?>) that can trip up parsers
    text_content = resp.text
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        # Yoast adds <?xml-stylesheet?> — try stripping it
        import re
        cleaned = re.sub(r'<\?xml-stylesheet[^?]*\?>', '', text_content)
        try:
            root = ET.fromstring(cleaned.encode('utf-8'))
        except ET.ParseError as e:
            logger.warning(f'Sitemap XML parse error for {sitemap_url}: {e}')
            return []

    # Strip namespace for easier tag matching
    ns = ''
    if root.tag.startswith('{'):
        ns = root.tag.split('}')[0] + '}'

    logger.info(f'[indexing] Parsed sitemap {sitemap_url} | root_tag={root.tag} | ns={ns}')

    # Check if this is a sitemap index (<sitemapindex> with child <sitemap><loc>)
    if 'sitemapindex' in root.tag.lower():
        child_sitemaps = root.findall(f'.//{ns}loc')
        logger.info(f'[indexing] Sitemap index has {len(child_sitemaps)} child sitemaps')
        for sitemap_el in child_sitemaps:
            child_url = (sitemap_el.text or '').strip()
            if child_url and len(urls) < max_urls:
                child_urls = _fetch_sitemap_urls(child_url, max_urls - len(urls), _depth + 1)
                urls.extend(child_urls)
                logger.info(f'[indexing] Fetched {len(child_urls)} URLs from {child_url}')
        return urls[:max_urls]

    # Regular sitemap — extract all <url><loc> entries
    for loc_el in root.findall(f'.//{ns}loc'):
        url = (loc_el.text or '').strip()
        if url:
            urls.append(url)
            if len(urls) >= max_urls:
                break

    logger.info(f'[indexing] Extracted {len(urls)} URLs from {sitemap_url}')
    return urls


def _discover_sitemaps(client: DBClient) -> List[str]:
    """
    Try to find sitemap URLs for a client. Checks:
    1. GSC sitemaps API (if connected)
    2. Common sitemap locations (sitemap.xml, sitemap_index.xml)
    Uses website_url OR gsc_site_url as the base domain.
    """
    sitemap_urls = []

    # Try GSC sitemaps API first
    try:
        gsc = gsc_for_client(client)
        sitemaps = gsc.list_sitemaps()
        for sm in sitemaps:
            path = sm.get('path', '')
            if path:
                sitemap_urls.append(path)
                logger.info(f'[indexing] Found sitemap via GSC API: {path}')
    except Exception as e:
        logger.info(f'Could not list sitemaps via GSC for {client.id}: {e}')

    # Fallback: try common sitemap URLs
    if not sitemap_urls:
        # Use website_url first, then gsc_site_url as fallback
        # gsc_site_url can be "sc-domain:example.com" (domain property) or "https://..."
        raw_base = client.website_url or client.gsc_site_url or ''
        if raw_base.startswith('sc-domain:'):
            raw_base = 'https://' + raw_base.replace('sc-domain:', '')
        base = raw_base.rstrip('/')
        if base:
            logger.info(f'[indexing] Probing sitemaps at base URL: {base}')
            # Use GET (not HEAD) — many WordPress/Yoast configs reject HEAD on sitemaps
            for path in ['/sitemap_index.xml', '/sitemap.xml', '/wp-sitemap.xml', '/post-sitemap.xml']:
                candidate = base + path
                try:
                    resp = requests.get(candidate, timeout=15, allow_redirects=True, headers={
                        'User-Agent': 'Mozilla/5.0 (compatible; KarmaMCPIndexer/1.0)',
                        'Accept': 'application/xml, text/xml, */*',
                    })
                    logger.info(f'[indexing] Sitemap probe {candidate} -> {resp.status_code} ({len(resp.content)} bytes)')
                    if resp.status_code == 200 and len(resp.content) > 50:
                        sitemap_urls.append(candidate)
                        # If we found a sitemap index, that's enough — it contains all sub-sitemaps
                        if 'sitemapindex' in resp.text[:500].lower() or 'sitemap_index' in path:
                            break
                except Exception as e:
                    logger.info(f'[indexing] Sitemap probe failed {candidate}: {e}')
        else:
            logger.warning(f'[indexing] Client {client.id} has no website_url or gsc_site_url — cannot discover sitemaps')

    logger.info(f'[indexing] Discovered {len(sitemap_urls)} sitemaps: {sitemap_urls}')
    return sitemap_urls


# ---------------------------------------------------------------------------
# Candidate URL discovery
# ---------------------------------------------------------------------------

def _candidate_urls(client: DBClient, limit: int = 100) -> List[str]:
    """
    Build the list of URLs to inspect. Sources (in priority order):
    1. URLs from the site's sitemap(s) — covers the full site
    2. GSC Search Analytics API — all URLs Google has data on (via googleapis.com)
    3. Blog posts published via our platform (as backup)
    4. URLs already tracked in DBIndexingIssue (for re-check)

    GSC URL Inspection API quota: 2,000/day/property. We cap at `limit`.
    """
    urls: List[str] = []
    seen = set()

    # 1. Sitemap URLs — try to discover ALL pages on the site
    try:
        sitemaps = _discover_sitemaps(client)
        for sm_url in sitemaps:
            if len(urls) >= limit:
                break
            sm_urls = _fetch_sitemap_urls(sm_url, max_urls=limit - len(urls))
            for u in sm_urls:
                if u not in seen:
                    urls.append(u)
                    seen.add(u)
    except Exception as e:
        logger.warning(f'Sitemap discovery failed for client {client.id}: {e}')

    # 2. GSC Search Analytics — guaranteed to work (goes through googleapis.com)
    #    Picks up pages the sitemap might miss, and works when sitemap fetch is blocked
    if len(urls) < limit:
        try:
            gsc = gsc_for_client(client)
            sa_pages = gsc.query_search_analytics(days=90, row_limit=min(limit, 500))
            logger.info(f'[indexing] Search Analytics returned {len(sa_pages)} pages')
            for u in sa_pages:
                if u not in seen and len(urls) < limit:
                    urls.append(u)
                    seen.add(u)
        except Exception as e:
            logger.warning(f'Search Analytics query failed for client {client.id}: {e}')

    # 3. Blog posts with a known published URL (catch any not in sitemap/SA)
    blog_posts = DBBlogPost.query.filter(
        DBBlogPost.client_id == client.id,
        DBBlogPost.published_url.isnot(None),
    ).order_by(DBBlogPost.created_at.desc()).limit(limit).all()
    for post in blog_posts:
        if post.published_url and post.published_url not in seen and len(urls) < limit:
            urls.append(post.published_url)
            seen.add(post.published_url)

    # 4. Include any existing issues that still need a re-check
    due_issues = DBIndexingIssue.query.filter(
        DBIndexingIssue.client_id == client.id,
        DBIndexingIssue.status.in_([
            IndexingStatus.SUBMITTED,
            IndexingStatus.STILL_UNINDEXED,
        ]),
    ).limit(limit).all()
    for issue in due_issues:
        if issue.url not in seen and len(urls) < limit:
            urls.append(issue.url)
            seen.add(issue.url)

    return urls


# ---------------------------------------------------------------------------
# Scan — pull inspection data for every candidate URL, persist issues
# ---------------------------------------------------------------------------

def scan_client(client: DBClient, max_urls: int = 100, provided_urls: List[str] = None) -> Dict:
    """
    Inspect candidate URLs, create/update DBIndexingIssue rows for any in an
    actionable coverage state.
    If provided_urls is given, those are used directly (from browser-side sitemap fetch).
    """
    if not client.gsc_refresh_token or not client.gsc_site_url:
        return {'success': False, 'error': 'GSC not connected for this client'}

    logger.info(f'[indexing] scan_client start for {client.id} | site={client.gsc_site_url} | website={client.website_url} | provided_urls={len(provided_urls or [])}')

    gsc = gsc_for_client(client)

    if provided_urls:
        urls = provided_urls[:max_urls]
        logger.info(f'[indexing] Using {len(urls)} provided URLs (browser-side fetch)')
    else:
        urls = _candidate_urls(client, limit=max_urls)

    logger.info(f'[indexing] Found {len(urls)} candidate URLs to inspect')

    if not urls:
        client.gsc_last_scan_at = datetime.utcnow()
        db.session.commit()
        return {
            'success': True, 'inspected': 0, 'new_issues': 0, 'cleared': 0,
            'debug': {
                'website_url': client.website_url,
                'gsc_site_url': client.gsc_site_url,
                'note': 'No candidate URLs found. Use "Import from Sitemap" to load URLs from your sitemap.',
            }
        }

    new_issues = 0
    cleared = 0
    inspected = 0
    errors = 0
    coverage_summary = {}  # Track how many URLs in each coverage state
    first_error = None

    for url in urls:
        try:
            result = gsc.inspect_url(url)
            parsed = GSCService.parse_coverage_state(result)
            inspected += 1

            coverage = parsed['coverage_state'] or 'Unknown'
            last_crawl = parsed.get('last_crawl_time')
            coverage_summary[coverage] = coverage_summary.get(coverage, 0) + 1

            logger.info(f'[indexing] URL: {url[:80]} | coverage: "{coverage}" | verdict: {parsed.get("verdict")}')

            existing = DBIndexingIssue.query.filter_by(
                client_id=client.id, url=url
            ).order_by(DBIndexingIssue.created_at.desc()).first()

            # If coverage is now "indexed" and we had a tracked issue -> mark resolved
            if existing and _is_indexed(coverage):
                if existing.status != IndexingStatus.INDEXED:
                    existing.status = IndexingStatus.INDEXED
                    existing.resolved_at = datetime.utcnow()
                    cleared += 1
                continue

            if not _is_actionable(coverage):
                continue

            # New or updated issue
            if existing and existing.status not in (IndexingStatus.INDEXED, IndexingStatus.IGNORED):
                existing.coverage_state = coverage
                existing.index_status = parsed.get('verdict')
                if last_crawl:
                    try:
                        existing.last_crawl_time = datetime.fromisoformat(
                            last_crawl.replace('Z', '+00:00')
                        ).replace(tzinfo=None)
                    except Exception:
                        pass
                existing.updated_at = datetime.utcnow()
            else:
                issue = DBIndexingIssue(
                    client_id=client.id,
                    url=url,
                    coverage_state=coverage,
                    index_status=parsed.get('verdict'),
                    status=IndexingStatus.DISCOVERED,
                )
                if last_crawl:
                    try:
                        issue.last_crawl_time = datetime.fromisoformat(
                            last_crawl.replace('Z', '+00:00')
                        ).replace(tzinfo=None)
                    except Exception:
                        pass
                db.session.add(issue)
                new_issues += 1

        except GSCError as e:
            errors += 1
            if not first_error:
                first_error = f'{url[:60]}: {e}'
            logger.warning(f'[indexing_scan] inspect failed for {url}: {e}')
        except Exception as e:
            errors += 1
            if not first_error:
                first_error = f'{url[:60]}: {e}'
            logger.exception(f'[indexing_scan] unexpected error for {url}: {e}')

    client.gsc_last_scan_at = datetime.utcnow()
    db.session.commit()

    logger.info(f'[indexing] scan complete: inspected={inspected} new={new_issues} cleared={cleared} errors={errors} coverage={coverage_summary}')

    return {
        'success': True,
        'inspected': inspected,
        'new_issues': new_issues,
        'cleared': cleared,
        'errors': errors,
        'coverage_breakdown': coverage_summary,
        'first_error': first_error,
    }


# ---------------------------------------------------------------------------
# Diagnose — Claude reads the page and produces structured findings
# ---------------------------------------------------------------------------

_DIAGNOSIS_SYSTEM_PROMPT = """You are an SEO technical diagnostician. You are given a single web page that Google has crawled but chosen not to index. Your job is to identify why, in structured JSON.

Output a single JSON object with exactly these keys:
- "thin_content": {"flagged": bool, "word_count": int, "notes": string}
- "weak_title_meta": {"flagged": bool, "notes": string}
- "missing_schema": {"flagged": bool, "notes": string}
- "weak_internal_links": {"flagged": bool, "notes": string}
- "likely_duplicate": {"flagged": bool, "notes": string}
- "keyword_cannibalization": {"flagged": bool, "notes": string}
- "recommendations": [list of short actionable strings, highest-impact first]
- "primary_root_cause": string   // the single most likely reason

Keep notes concise (1-2 sentences each). Output ONLY the JSON object, no prose before or after."""


def _fetch_page_html(url: str, timeout: int = 20) -> Optional[str]:
    try:
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; KarmaMCPIndexer/1.0)',
        })
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception as e:
        logger.warning(f'_fetch_page_html failed for {url}: {e}')
        return None


def _trim_html_for_prompt(html: str, max_chars: int = 18000) -> str:
    """Keep <head> + first chunk of <body>. Good-enough signal without blowing context."""
    if len(html) <= max_chars:
        return html
    head_end = html.lower().find('</head>')
    if head_end == -1:
        return html[:max_chars]
    head = html[:head_end + 7]
    body_slice = html[head_end + 7: head_end + 7 + (max_chars - len(head))]
    return head + body_slice


def diagnose_issue(issue: DBIndexingIssue) -> Dict:
    """
    Fetch the page, run Claude over it, persist a structured diagnosis.
    """
    html = _fetch_page_html(issue.url)
    if not html:
        issue.status = IndexingStatus.FAILED
        issue.last_error = 'Failed to fetch page HTML'
        db.session.commit()
        return {'success': False, 'error': 'fetch_failed'}

    trimmed = _trim_html_for_prompt(html)

    # Lazy import so this service module doesn't pull anthropic at import time
    try:
        from anthropic import Anthropic
    except ImportError:
        return {'success': False, 'error': 'anthropic_sdk_missing'}

    try:
        from app.services.token_tracker import track_usage
    except ImportError:
        track_usage = None  # tracking is optional

    import os
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'success': False, 'error': 'anthropic_api_key_missing'}

    model = 'claude-haiku-4-5-20251001'
    client_sdk = Anthropic(api_key=api_key)

    user_msg = (
        f"URL: {issue.url}\n"
        f"GSC coverage state: {issue.coverage_state}\n\n"
        f"--- Page HTML (trimmed) ---\n{trimmed}"
    )

    try:
        resp = client_sdk.messages.create(
            model=model,
            max_tokens=1200,
            system=_DIAGNOSIS_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_msg}],
        )
    except Exception as e:
        issue.status = IndexingStatus.FAILED
        issue.last_error = f'Claude call failed: {e}'
        db.session.commit()
        return {'success': False, 'error': str(e)}

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text

    # Parse JSON (allow for code-fence wrapping)
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`')
        # strip leading 'json\n' marker if present
        if cleaned.lower().startswith('json'):
            cleaned = cleaned[4:].lstrip()

    try:
        diagnosis = json.loads(cleaned)
    except Exception:
        diagnosis = {'raw_output': text, 'parse_error': True}

    issue.set_diagnosis(diagnosis)
    issue.status = IndexingStatus.DIAGNOSED
    issue.diagnosed_at = datetime.utcnow()

    # Token tracking
    if track_usage and hasattr(resp, 'usage') and resp.usage:
        try:
            track_usage(
                model=model,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                feature='indexing_diagnosis',
                client_id=issue.client_id,
                request_id=getattr(resp, 'id', None),
            )
        except Exception:
            pass

    db.session.commit()
    return {'success': True, 'diagnosis': diagnosis}


# ---------------------------------------------------------------------------
# Resubmit — ping Google (Indexing API), sitemap, and IndexNow
# ---------------------------------------------------------------------------

def submit_issue(issue: DBIndexingIssue, client: Optional[DBClient] = None) -> Dict:
    """
    Resubmit a URL through every available channel and record the result.
    """
    if client is None:
        client = DBClient.query.get(issue.client_id)
    if not client:
        return {'success': False, 'error': 'client_not_found'}

    results = {
        'google_indexing_api': None,
        'sitemap_ping': None,
        'indexnow': None,
    }

    # 1. Google Indexing API
    try:
        gsc = gsc_for_client(client)
        resp = gsc.notify_url_updated(issue.url)
        issue.submitted_to_google = True
        results['google_indexing_api'] = {'success': True, 'response': resp}
    except GSCError as e:
        results['google_indexing_api'] = {'success': False, 'error': str(e)}
    except Exception as e:
        results['google_indexing_api'] = {'success': False, 'error': str(e)}

    # 2. Sitemap ping (site-wide, not URL-specific; cheap to do)
    sitemap_url = _guess_sitemap_url(client)
    if sitemap_url:
        ok = GSCService.ping_sitemap_public(sitemap_url)
        issue.sitemap_pinged = ok
        results['sitemap_ping'] = {'success': ok, 'sitemap': sitemap_url}

    # 3. IndexNow
    try:
        indexnow_res = indexnow_service.submit_urls(client, [issue.url])
        issue.submitted_to_indexnow = bool(indexnow_res.get('success'))
        results['indexnow'] = indexnow_res
    except Exception as e:
        results['indexnow'] = {'success': False, 'error': str(e)}

    issue.submission_response = json.dumps(results)[:4000]
    issue.submitted_at = datetime.utcnow()
    issue.status = IndexingStatus.SUBMITTED
    issue.recheck_at = datetime.utcnow() + timedelta(days=7)
    db.session.commit()

    return {'success': True, 'channels': results}


def _guess_sitemap_url(client: DBClient) -> Optional[str]:
    if not client.website_url:
        return None
    base = client.website_url.rstrip('/')
    return f'{base}/sitemap.xml'


# ---------------------------------------------------------------------------
# Re-check — was it indexed?
# ---------------------------------------------------------------------------

def recheck_issue(issue: DBIndexingIssue, client: Optional[DBClient] = None) -> Dict:
    if client is None:
        client = DBClient.query.get(issue.client_id)
    if not client:
        return {'success': False, 'error': 'client_not_found'}

    try:
        gsc = gsc_for_client(client)
        result = gsc.inspect_url(issue.url)
        parsed = GSCService.parse_coverage_state(result)
    except Exception as e:
        issue.last_error = f'recheck failed: {e}'
        db.session.commit()
        return {'success': False, 'error': str(e)}

    coverage = parsed.get('coverage_state') or 'Unknown'
    issue.coverage_state = coverage
    issue.recheck_count += 1
    issue.updated_at = datetime.utcnow()

    if coverage.lower().startswith('submitted and indexed') or coverage.lower().startswith('indexed'):
        issue.status = IndexingStatus.INDEXED
        issue.resolved_at = datetime.utcnow()
        db.session.commit()
        return {'success': True, 'indexed': True}

    # Not indexed yet — schedule another re-check in 7 days, up to 4 attempts
    if issue.recheck_count < 4:
        issue.recheck_at = datetime.utcnow() + timedelta(days=7)
        issue.status = IndexingStatus.SUBMITTED
    else:
        issue.status = IndexingStatus.STILL_UNINDEXED

    db.session.commit()
    return {'success': True, 'indexed': False, 'coverage_state': coverage}


# ---------------------------------------------------------------------------
# Scheduled-job entry points
# ---------------------------------------------------------------------------

def run_weekly_scan_all_clients(app=None) -> Dict:
    """
    Scheduled job: iterate every client with indexing enabled, scan their URLs,
    and re-check any issues whose recheck_at has elapsed.
    """
    if app is not None:
        ctx = app.app_context()
        ctx.push()
    else:
        ctx = None

    summary = {'clients_processed': 0, 'issues_found': 0, 'rechecks_done': 0, 'errors': 0}

    try:
        clients = DBClient.query.filter(
            DBClient.gsc_indexing_enabled.is_(True),
            DBClient.gsc_refresh_token.isnot(None),
            DBClient.gsc_site_url.isnot(None),
        ).all()

        for client in clients:
            try:
                scan_res = scan_client(client)
                summary['clients_processed'] += 1
                summary['issues_found'] += scan_res.get('new_issues', 0)

                # Process rechecks due
                due = DBIndexingIssue.query.filter(
                    DBIndexingIssue.client_id == client.id,
                    DBIndexingIssue.recheck_at.isnot(None),
                    DBIndexingIssue.recheck_at <= datetime.utcnow(),
                    DBIndexingIssue.status == IndexingStatus.SUBMITTED,
                ).limit(50).all()
                for issue in due:
                    recheck_issue(issue, client)
                    summary['rechecks_done'] += 1

            except Exception as e:
                summary['errors'] += 1
                logger.exception(f'weekly scan failed for client {client.id}: {e}')

    finally:
        if ctx is not None:
            ctx.pop()

    logger.info(f'[indexing] weekly scan complete: {summary}')
    return summary
