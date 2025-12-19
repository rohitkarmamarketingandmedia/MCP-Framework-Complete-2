# Changelog

## v5.5.77 (2025-12-19)

### Fixed
- Fix competitor dashboard crash when DBRankHistory has no ranking_url attribute (monitoring.py lines 1245, 1300)

## v5.5.76 (2025-12-19)

### Fixed
- Fixed dataclass crash: TypeError "non-default argument 'content_score' follows default argument" in client_health_service.py
- Added Procfile for Render port binding via $PORT env var

## v5.5.75 (2025-12-19)

### Fixed
- Fixed ImportError in featured image route (added data_service singleton)
- Scheduler guarded by ENABLE_SCHEDULER env var (must be "1" to enable, default OFF)
- request.get_json(silent=True) in: pages.py, publish.py, webhooks.py, oauth.py, schema.py
