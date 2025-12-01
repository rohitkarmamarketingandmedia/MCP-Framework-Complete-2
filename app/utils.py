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
