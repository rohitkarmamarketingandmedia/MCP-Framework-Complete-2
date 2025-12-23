# Changelog

## v5.5.81 (2025-12-23)

### Fixed - Comprehensive Bug Fixes

1. **Social posts disappearing when switching tabs**
   - Root cause: `/api/content/client/<id>?type=social` was ignoring the `type` parameter
   - Fix: Updated endpoint to properly return social posts when `type=social`
   - Social posts now persist correctly across tab switches

2. **SEMrush still showing "Demo Mode" after setting API key**
   - Fixed ALL services to read env vars at RUNTIME (not import time):
     - `rank_tracking_service.py` - SEMrush rankings
     - `seo_service.py` - SEO analysis
     - `ai_service.py` - OpenAI/Anthropic
     - `social_service.py` - Social media tokens
     - `analytics_service.py` - GA4
     - `callrail_service.py` - CallRail
     - `semrush_service.py` - SEMrush API
     - `interaction_intelligence_service.py` - OpenAI
   - All services now use `@property` decorators for env var access
   - **No app restart required** after setting any env var

3. **Traffic Value showing "$NaN"**
   - Root cause: `traffic_value` returns a dict, not a number
   - Fix: Frontend now correctly accesses `traffic_value.estimated_monthly_value`
   - Proper fallback to $0 if value is missing or invalid

4. **AI Chatbot embed code showing HTTP instead of HTTPS**
   - Added automatic HTTP→HTTPS conversion for non-localhost URLs
   - Production embed codes now always use HTTPS

5. **Social posts showing "undefined" platform**
   - Added fallback to "Social Post" when platform is null/undefined
   - Added LinkedIn to platform name mappings

6. **Improved error messages**
   - Leads tab now shows HTTP status code on errors
   - Better console logging for debugging

### Technical Changes
- All env var reads now use `@property` decorators
- Removed instance variable caching of env vars at init time
- CallRail creates fresh session per request with current credentials
- Services are now truly dynamic - pick up env changes immediately

### Notes
- After deploying, SEMrush/CallRail/AI will work immediately when env vars are set
- No more "restart required" after configuration changes
- Social posts properly persist in database and reload correctly

---

## v5.5.80 (2025-12-23)

### Fixed - Runtime Environment Variables & UI Fixes

1. **SEMrush API key not detected after setting env var**
   - Changed `api_key` from instance variable to property
   - Now reads `SEMRUSH_API_KEY` at runtime, not import time
   - App restart no longer required after setting env var

2. **CallRail API key not detected after setting env var**
   - Same fix as SEMrush - properties instead of class variables
   - `CallRailConfig` now uses getter methods for API_KEY and ACCOUNT_ID
   - Session created fresh for each request with current credentials

3. **Social posts showing "undefined" platform**
   - Added fallback in `getPlatformName()` function
   - Returns "Social Post" instead of undefined/null
   - Added LinkedIn to platform names

4. **Improved error messages for Leads tab**
   - Now shows HTTP status code on failure
   - Shows actual error message instead of generic text
   - Better debugging info in console

### Notes
- SEMrush will now show real data immediately after setting SEMRUSH_API_KEY
- CallRail will now show real data immediately after setting CALLRAIL_API_KEY + CALLRAIL_ACCOUNT_ID
- No app restart required for API key changes

---

## v5.5.79 (2025-12-19)

### Fixed - Crash Prevention & Performance

1. **Health Score DBAuditLog.timestamp crash**
   - Replaced all `DBAuditLog.timestamp` with `DBAuditLog.created_at`
   - Added try/except wrappers around all scoring functions
   - App now returns empty score instead of 500 on any error

2. **Long request timeout (Gunicorn worker killed)**
   - Added query limits: competitors (10), pages (50), rankings (200)
   - Competitor dashboard now limits to 5 competitors processed
   - Health score functions wrapped in defensive error handling

3. **CallRail API 404 spam**
   - Reduced timeout from 30s to 15s
   - 4xx errors logged at DEBUG level (not ERROR)
   - Timeout errors handled gracefully
   - Returns empty result on failure, doesn't block rendering

4. **Safe attribute access pattern**
   - All DBAuditLog field access uses getattr() fallback
   - All DBRankHistory.ranking_url uses getattr() fallback
   - No direct attribute access on DB objects with uncertain schema

### Notes
- App survives missing fields + external API failures without 500s
- No single request should block >10s now
