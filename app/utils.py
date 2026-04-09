"""
MCP Framework - Request Utilities
Safe parsing helpers for request parameters
"""


def safe_int(value, default=0, min_val=None, max_val=None):
    """
    Safely parse an integer from a request parameter.
    
    Args:
        value: The value to parse (string or None)
        default: Default value if parsing fails
        min_val: Minimum allowed value (optional)
        max_val: Maximum allowed value (optional)
    
    Returns:
        int: Parsed integer or default
    """
    try:
        result = int(value) if value is not None else default
    except (ValueError, TypeError):
        result = default
    
    if min_val is not None:
        result = max(result, min_val)
    if max_val is not None:
        result = min(result, max_val)
    
    return result


def safe_float(value, default=0.0, min_val=None, max_val=None):
    """
    Safely parse a float from a request parameter.
    """
    try:
        result = float(value) if value is not None else default
    except (ValueError, TypeError):
        result = default
    
    if min_val is not None:
        result = max(result, min_val)
    if max_val is not None:
        result = min(result, max_val)
    
    return result


def safe_bool(value, default=False):
    """
    Safely parse a boolean from a request parameter.
    Accepts: true, false, 1, 0, yes, no (case insensitive)
    """
    if value is None:
        return default
    
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    
    return bool(value)


def get_pagination_params(request, default_limit=50, max_limit=200):
    """
    Get pagination parameters from request.
    
    Returns:
        tuple: (limit, offset, page)
    """
    limit = safe_int(request.args.get('limit'), default_limit, min_val=1, max_val=max_limit)
    offset = safe_int(request.args.get('offset'), 0, min_val=0)
    page = safe_int(request.args.get('page'), 1, min_val=1)
    
    # If page is provided but not offset, calculate offset
    if request.args.get('page') and not request.args.get('offset'):
        offset = (page - 1) * limit
    
    return limit, offset, page


def get_date_range_params(request, default_days=30, max_days=365):
    """
    Get date range parameters from request.
    
    Returns:
        int: Number of days for the range
    """
    return safe_int(request.args.get('days'), default_days, min_val=1, max_val=max_days)


# ==========================================
# AI Prompt Injection Defense
# ==========================================

import re as _re

def sanitize_for_prompt(text: str, max_length: int = 500) -> str:
    """
    Sanitize user-supplied text before inserting into AI prompts.
    Strips common prompt injection patterns while keeping natural text.

    Use this for: keywords, company names, city/state, industry,
    review text, FAQ questions, and any other user-controlled strings
    that get interpolated into Claude API prompts.

    Args:
        text: Raw user input
        max_length: Maximum allowed length (default 500)

    Returns:
        Sanitized string safe for prompt interpolation
    """
    if not text:
        return ''

    text = str(text).strip()

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]

    # Remove common prompt injection patterns (case-insensitive)
    # These patterns attempt to override system instructions
    injection_patterns = [
        r'(?i)\bignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)\b',
        r'(?i)\b(system|admin|root|developer)\s*:\s*',
        r'(?i)\bnew\s+instructions?\s*:',
        r'(?i)\byou\s+are\s+now\b',
        r'(?i)\bact\s+as\s+(if|though)\b',
        r'(?i)\bpretend\s+(you\s+are|to\s+be)\b',
        r'(?i)\bforget\s+(all|everything|your)\b',
        r'(?i)\boverride\s+(your|the|all)\b',
        r'(?i)\b(disregard|bypass)\s+(the|your|all|above|previous)\b',
        r'(?i)\bdo\s+not\s+follow\s+(the|your)\b',
        r'(?i)\[SYSTEM\]',
        r'(?i)\[INST\]',
        r'(?i)<<SYS>>',
    ]

    for pattern in injection_patterns:
        text = _re.sub(pattern, '[filtered]', text)

    # Remove excessive newlines (potential delimiter injection)
    text = _re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
