# Changelog

## v5.5.76 (2025-12-19)

### Fixed
- Fixed dataclass crash: TypeError "non-default argument 'content_score' follows default argument" in client_health_service.py — reordered fields so non-defaults come first
- Added Procfile for Render port binding via $PORT env var

### Previously in v5.5.75
- Scheduler guarded by ENABLE_SCHEDULER env var (must be "1" to enable, default OFF)
- request.get_json(silent=True) in: pages.py, publish.py, webhooks.py, oauth.py, schema.py
- data_service singleton added to data_service.py

### Notes
- To enable scheduler on Render, set environment variable: ENABLE_SCHEDULER=1
- Only enable scheduler on ONE instance to prevent duplicate jobs
