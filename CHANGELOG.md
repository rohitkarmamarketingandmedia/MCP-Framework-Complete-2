# Changelog

## v5.5.78 (2025-12-19)

### Fixed
- **Repo-wide get_json fix**: Replaced all 118 occurrences of `request.get_json()` with `request.get_json(silent=True)` to prevent 415 Unsupported Media Type errors
- **Render port binding**: Changed default port from 5000 to 10000 in run.py to match Render defaults

### Previously Fixed (v5.5.75-77)
- Dataclass crash: reordered fields in HealthScoreBreakdown (content_score ordering)
- ImportError: added data_service singleton to data_service.py  
- Competitor dashboard crash: safe getattr fallback for ranking_url in monitoring.py
- Scheduler guarded by ENABLE_SCHEDULER env var (must be "1" to enable)
- Procfile for Render port binding via $PORT

### Deployment Notes
- Render port binding: Uses `$PORT` env var (Render sets this automatically)
- To enable scheduler: Set `ENABLE_SCHEDULER=1` on ONE Render instance only
