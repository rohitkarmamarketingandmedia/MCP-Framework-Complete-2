# Changelog

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
