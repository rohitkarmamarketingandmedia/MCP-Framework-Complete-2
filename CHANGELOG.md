# Changelog

## v5.5.75 (2025-12-19)

### Fixed
- Fixed ImportError in featured image route (added data_service singleton to data_service.py)
- Scheduler guarded by ENABLE_SCHEDULER env var (must be "1" to enable, default OFF)
- request.get_json made tolerant (silent=True) in: pages.py, publish.py, webhooks.py, oauth.py, schema.py

### Notes
- To enable scheduler on Render, set environment variable: ENABLE_SCHEDULER=1
- Only enable scheduler on ONE instance to prevent duplicate jobs
