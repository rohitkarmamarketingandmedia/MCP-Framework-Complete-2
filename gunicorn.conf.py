# Gunicorn configuration for MCP Framework
# Handles long-running AI content generation requests

# Worker settings
workers = 2
worker_class = 'sync'  # Use sync for reliability

# Timeout settings - generous for AI API calls
timeout = 300  # 5 minutes for main timeout
graceful_timeout = 300  # 5 minutes for graceful shutdown
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Request handling
max_requests = 1000  # Restart workers after 1000 requests to prevent memory leaks
max_requests_jitter = 50  # Random jitter to prevent all workers restarting at once

# Bind
bind = '0.0.0.0:5000'
