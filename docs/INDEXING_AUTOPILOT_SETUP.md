# Indexing Autopilot — Setup Guide

The Indexing Autopilot detects unindexed pages, diagnoses them with Claude, and resubmits them to Google (via the Indexing API + sitemap ping) and to Bing/Yandex (via IndexNow).

This doc covers what needs to be configured **once** in your Google Cloud project and per-client before the feature works end-to-end.

---

## 1. One-time Google Cloud Console setup

You already have a Google OAuth app for Google Business Profile. Extend it:

### 1a. Enable the APIs

In the Google Cloud Console for the project that owns `GOOGLE_CLIENT_ID`:

- **Google Search Console API** — https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
- **Web Search Indexing API** — https://console.cloud.google.com/apis/library/indexing.googleapis.com
- **Google Search Console API (webmasters)** — may already be enabled under the legacy name

### 1b. Add the OAuth scopes

OAuth consent screen → Scopes → add:

```
https://www.googleapis.com/auth/webmasters.readonly
https://www.googleapis.com/auth/webmasters
https://www.googleapis.com/auth/indexing
```

If your consent screen is in **External** mode and not verified, only listed test users will be able to connect. Either add each client's Google account as a test user, or submit the app for verification (recommended for production).

### 1c. Add the callback URL

OAuth credentials → Edit the OAuth 2.0 Client ID → Authorized redirect URIs → add:

```
https://mcp.karmamarketingandmedia.com/api/indexing/oauth/callback
```

(adjust to whatever `APP_URL` env var is set to on staging / dev)

### 1d. Environment variables

The feature uses existing env vars — no new ones required:

```
GOOGLE_CLIENT_ID=<existing>
GOOGLE_CLIENT_SECRET=<existing>
APP_URL=https://mcp.karmamarketingandmedia.com
ANTHROPIC_API_KEY=<existing>
```

---

## 2. Per-client setup

For every client who should get indexing automation:

1. **Dashboard → Indexing tab → Connect Search Console** — the client's Google account (the one that verified the site in Search Console) authorizes our app.
2. **Select the property** — pick the Search Console property (domain or URL-prefix) from the dropdown.
3. **Indexing API requires the service account email as a Search Console Owner.** Since we use OAuth (not a service account), the person connecting must already be an Owner of the property. "Full" and "Restricted" permission levels can read coverage data but cannot call the Indexing API.
4. **IndexNow (optional but recommended)** — click "IndexNow Setup" → host `{key}.txt` at the site root → click "Verify Now."
   - For WordPress sites we already control, this can be served via a custom route or a static file upload. A simple static file works on any host.

---

## 3. What runs automatically

- **Weekly scan** (Monday 3 AM): iterates every client with `gsc_indexing_enabled = true` and `gsc_refresh_token` set, inspects their known blog URLs via URL Inspection API, logs any in a "Crawled / Discovered — not indexed" state as `DBIndexingIssue` rows.
- **Weekly re-check** (same job): for any issue in `submitted` status whose `recheck_at` has passed, re-inspects the URL. Up to 4 re-check cycles per issue, 7 days apart.

Manual buttons on the dashboard: "Scan Now," per-issue "Diagnose / Submit / Recheck / Ignore," and "Resubmit All Pending."

---

## 4. Cost accounting

Diagnose calls use `claude-haiku-4-5-20251001` and are tracked through `token_tracker.py` with `feature='indexing_diagnosis'`. Visible on the existing usage dashboard.

Typical per-client weekly cost: **well under $1** for clients with fewer than ~20 indexing issues.

---

## 5. Known limitations

- **GSC API has no "list all unindexed pages" endpoint.** We inspect the URLs we already know about (blog posts we published + URLs already in `DBIndexingIssue`). Pages we did not publish ourselves won't appear unless manually added. (Future: pull `Top Pages` from the existing GSC integration and feed into the scanner.)
- **Indexing API caveat.** Google documents it as Job Postings / Livestream only. It works for general URLs in practice and is widely used, but it is technically a gray area. If Google changes enforcement, we still have sitemap ping and IndexNow.
- **Refresh token.** On re-consent Google sometimes omits the refresh token. If a client hits auth errors, have them click "Disconnect" then reconnect to force a fresh consent (`prompt=consent` is set on our auth URL, which should force re-issuance).

---

## 6. DB changes applied automatically

On next app start, `run_migrations()` adds six columns to `clients` (gsc_access_token, gsc_refresh_token, gsc_token_expires_at, gsc_connected_at, gsc_indexing_enabled, gsc_last_scan_at) and `db.create_all()` creates two new tables: `indexing_issues` and `indexnow_keys`.

No manual SQL required.
