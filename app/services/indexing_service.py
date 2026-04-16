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
from datetime import datetime, timedelta
from typing import List, Optional, Dict

import requests

from app.database import db
from app.models.db_models import (
    DBClient, DBIndexingIssue, DBBlogPost, IndexingStatus
)
from app.services.gsc_service import GSCService, GSCError, for_client as gsc_for_client
from app.services import indexnow_service

logger = logging.getLogger(__name__)


# States where resubmission is worth attempting
ACTIONABLE_COVERAGE_STATES = {
    'Crawled - currently not indexed',
    'Discovered - currently not indexed',
    'Duplicate without user-selected canonical',
    'Duplicate, Google chose different canonical than user',
    'Page with redirect',
}

# States where we should NOT resubmit
NON_ACTIONABLE_COVERAGE_STATES = {
    'Submitted and indexed',
    'Indexed, not submitted in sitemap',
    'Excluded by ‘noindex’ tag',
    'Excluded by "noindex" tag',
    'Blocked by robots.txt',
    'Not found (404)',
}


# ---------------------------------------------------------------------------
# Candidate URL discovery
# ---------------------------------------------------------------------------

def _candidate_urls(client: DBClient, limit: int = 100) -> List[str]:
    """
    Build the list of URLs to inspect. Priority order:
    1. Blog posts this client has published via our platform (exact URLs we know)
    2. URLs already tracked in DBIndexingIssue (for re-check)

    GSC does not expose a public "coverage report" list endpoint — you must
    inspect URLs you already know. Our blog corpus + past indexing history is
    the best source we have.
    """
    urls: List[str] = []
    seen = set()

    # Blog posts with a known published URL
    blog_posts = DBBlogPost.query.filter(
        DBBlogPost.client_id == client.id,
        DBBlogPost.published_url.isnot(None),
    ).order_by(DBBlogPost.created_at.desc()).limit(limit).all()
    for post in blog_posts:
        if post.published_url and post.published_url not in seen:
            urls.append(post.published_url)
            seen.add(post.published_url)

    # Include any existing issues that still need a re-check
    due_issues = DBIndexingIssue.query.filter(
        DBIndexingIssue.client_id == client.id,
        DBIndexingIssue.status.in_([
            IndexingStatus.SUBMITTED,
            IndexingStatus.STILL_UNINDEXED,
        ]),
    ).limit(limit).all()
    for issue in due_issues:
        if issue.url not in seen:
            urls.append(issue.url)
            seen.add(issue.url)

    return urls


# ---------------------------------------------------------------------------
# Scan — pull inspection data for every candidate URL, persist issues
# ---------------------------------------------------------------------------

def scan_client(client: DBClient, max_urls: int = 100) -> Dict:
    """
    Inspect candidate URLs, create/update DBIndexingIssue rows for any in an
    actionable coverage state.
    """
    if not client.gsc_refresh_token or not client.gsc_site_url:
        return {'success': False, 'error': 'GSC not connected for this client'}

    gsc = gsc_for_client(client)
    urls = _candidate_urls(client, limit=max_urls)

    if not urls:
        return {'success': True, 'inspected': 0, 'new_issues': 0, 'cleared': 0}

    new_issues = 0
    cleared = 0
    inspected = 0
    errors = 0

    for url in urls:
        try:
            result = gsc.inspect_url(url)
            parsed = GSCService.parse_coverage_state(result)
            inspected += 1

            coverage = parsed['coverage_state'] or 'Unknown'
            last_crawl = parsed.get('last_crawl_time')

            existing = DBIndexingIssue.query.filter_by(
                client_id=client.id, url=url
            ).order_by(DBIndexingIssue.created_at.desc()).first()

            is_actionable = coverage in ACTIONABLE_COVERAGE_STATES

            # If coverage is now "indexed" and we had a tracked issue -> mark resolved
            if existing and coverage in NON_ACTIONABLE_COVERAGE_STATES and 'indexed' in coverage.lower():
                if existing.status != IndexingStatus.INDEXED:
                    existing.status = IndexingStatus.INDEXED
                    existing.resolved_at = datetime.utcnow()
                    cleared += 1
                continue

            if not is_actionable:
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
            logger.warning(f'[indexing_scan] inspect failed for {url}: {e}')
        except Exception as e:
            errors += 1
            logger.exception(f'[indexing_scan] unexpected error for {url}: {e}')

    client.gsc_last_scan_at = datetime.utcnow()
    db.session.commit()

    return {
        'success': True,
        'inspected': inspected,
        'new_issues': new_issues,
        'cleared': cleared,
        'errors': errors,
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
