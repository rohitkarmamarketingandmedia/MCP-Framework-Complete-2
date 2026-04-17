# Indexing Autopilot — Rate Limiting & Reliability

**Date:** 2026-04-17
**Status:** Approved
**Scope:** Sub-project B of three planned indexing autopilot improvements (B → C → A)

---

## What We're Building

Harden the GSC indexing autopilot against the 2,000/day URL Inspection API quota and transient API failures. When a scan hits the quota it pauses, saves its position, and resumes automatically the next day. All GSC calls retry up to 3 times on transient errors. Scan failures surface as a dismissible warning banner on the client dashboard.

---

## Data Model Changes

Three new columns on `DBClient`:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `gsc_daily_quota_used` | Integer | 0 | Inspection calls made today |
| `gsc_quota_reset_at` | DateTime | null | When quota counter resets (midnight UTC next day) |
| `gsc_scan_resume_cursor` | String(500) | null | URL after which scan will resume; cleared on scan completion |
| `gsc_scan_warning` | String(500) | null | Human-readable warning message shown in dashboard; cleared on scan completion |

Added via inline migration in `app/__init__.py` following the existing `ALTER TABLE` pattern.

---

## Retry Wrapper

New helper in `app/services/gsc_service.py`:

```
gsc_call_with_retry(fn, *args, max_retries=3, base_delay=1.0)
```

**Retry behavior by error type:**

| Error | Behavior |
|-------|---------|
| `429` or `503` | Retry up to 3 times; delay = `base_delay × 2^attempt` (1s → 2s → 4s) |
| `403` (quota exhausted) | Raise `QuotaExhaustedError` immediately — no retries, caller stops scan |
| Any other exception | Raise immediately — no retries, don't mask real errors |
| 3 retries all fail | Raise last exception; caller marks issue as `FAILED` |

Applied to all three GSC call sites: `inspect_url()`, `notify_url_updated()`, `ping_sitemap_public()`.

---

## Quota Tracking

Before each URL inspection in `scan_client()`:

1. If `gsc_quota_reset_at < now`: reset `gsc_daily_quota_used = 0`, set `gsc_quota_reset_at = tomorrow midnight UTC`
2. If `gsc_daily_quota_used >= 1900`: save cursor, write warning, stop scan (return with `paused=True`)
3. After successful inspection: increment `gsc_daily_quota_used`

The 1,900 threshold (not 2,000) provides a 100-call safety buffer for re-check and submission calls that also consume quota.

---

## Resume Logic

`scan_client()` changes:

1. Build full candidate URL list (same algorithm as today)
2. If `gsc_scan_resume_cursor` is set, find its index in the list and skip all URLs before it. If the cursor URL is no longer in the list (e.g., post deleted, sitemap changed), clear the cursor and start from the beginning.
3. Process from that index forward
4. On quota hit: set `gsc_scan_resume_cursor = last_processed_url`, set `gsc_scan_warning = "Scan paused: daily quota reached (1,900/2,000). Resuming tomorrow."`
5. On completion (all URLs processed): clear `gsc_scan_resume_cursor`, clear `gsc_scan_warning`

---

## Scheduler Changes

**Existing job** (Monday 3 AM — unchanged): starts a fresh scan, clears any stale cursor from a previous week.

**New job** (daily 3 AM, Tuesday–Sunday): for each client where `gsc_scan_resume_cursor IS NOT NULL` and `gsc_indexing_enabled = True` and `gsc_refresh_token IS NOT NULL`, call `scan_client()` to resume from cursor.

Added to `app/services/scheduler_service.py` alongside the existing `weekly_indexing_scan` job.

---

## Dashboard Alert

`GET /api/indexing/issues/<client_id>` response gains two new fields:

```json
{
  "scan_warning": "Scan paused: daily quota reached (1,900/2,000). Resuming tomorrow.",
  "scan_resume_pending": true
}
```

Both are `null`/`false` when no warning exists. No new endpoints required.

In `client-dashboard.html`, the indexing section renders a yellow warning banner when `scan_warning` is non-null:

```
⚠ Scan paused: daily quota reached (1,900/2,000). Resuming tomorrow.
```

Banner disappears automatically once the scan completes and the next issues fetch returns `scan_warning: null`.

---

## Error Handling

| Scenario | Behavior |
|----------|---------|
| Quota hit mid-scan | Pause, save cursor, set warning, return success with `paused: true` |
| Transient 429/503 | Retry 3× with backoff; if all fail, mark URL as `FAILED`, continue scan |
| Hard 403 (quota exhausted) | Same as quota hit — stop immediately |
| Page fetch timeout on diagnosis | Existing 20s timeout behavior unchanged |
| Scan completes with some FAILEDs | Dashboard shows failure count in issues list (existing behavior) |

---

## What This Does NOT Change

- Diagnosis, submission, and re-check pipelines are unchanged
- IndexNow key handling is unchanged
- OAuth flow is unchanged
- The 4-cycle re-check limit is unchanged
- No changes to `DBIndexingIssue` model
