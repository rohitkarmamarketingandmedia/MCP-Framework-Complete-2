# WordPress Authentication Issue - Troubleshooting & Fix Guide

## Problem Summary
Based on your screenshots, the WordPress integration is showing:
- **Error**: "The REST API is accessible but authentication failed. Try regenerating the Application Password in WordPress."
- **Status**: The WordPress REST API is reachable (good sign), but authentication credentials are rejected

## Root Causes

The authentication failure at line 96-114 in `wordpress_service.py` means:
1. ✅ The WordPress site URL is correct
2. ✅ The REST API is enabled and accessible
3. ❌ The username/password combination is incorrect or invalid

### Most Common Causes:

1. **Application Password is incorrect or expired**
   - Application Passwords can be revoked or expire
   - Copy-paste errors (spaces matter!)
   - Wrong format (should have spaces: `xxxx xxxx xxxx xxxx`)

2. **Username doesn't match**
   - Using display name instead of username
   - Wrong user account
   - Case sensitivity issues

3. **WordPress security plugins blocking API access**
   - WordFence, iThemes Security, etc.
   - IP whitelist restrictions
   - REST API disabled for specific users

## Step-by-Step Fix

### Step 1: Verify WordPress Username
```
1. Log into WordPress admin panel
2. Go to: Users → All Users
3. Find the user you want to use (should have Administrator or Editor role)
4. Click "Edit" on that user
5. The username is shown at the top (NOT the display name)
6. Copy this exact username (case-sensitive)
```

### Step 2: Generate Fresh Application Password

```
1. In WordPress admin, go to: Users → Profile
   (Or directly edit your user from Users → All Users)

2. Scroll down to "Application Passwords" section
   - If you don't see this section, Application Passwords might be disabled
   - See "Troubleshooting" section below

3. Enter a name for the application (e.g., "MCP Framework")

4. Click "Add New Application Password"

5. WordPress will generate a password like: "AbCd EfGh IjKl MnOp QrSt UvWx"
   - IMPORTANT: Copy this immediately - you won't see it again!
   - Keep the spaces - they're part of the password

6. Save this password somewhere secure
```

### Step 3: Update Credentials in Your Application

```javascript
// Use these exact values:
wordpress_url: "https://mcp.karmamarketing.com"  // No trailing slash
wordpress_user: "automation_agent"                // Exact username from Step 1
wordpress_app_password: "AbCd EfGh IjKl MnOp"    // From Step 2, with spaces
```

### Step 4: Test Connection

1. In your MCP application settings, enter:
   - **WordPress Site URL**: `https://mcp.karmamarketing.com`
   - **WordPress Username**: `automation_agent` (verify this is correct)
   - **App Password**: The newly generated password with spaces

2. Click "Test Connection"

3. Expected result: ✅ Connected as automation_agent

## Troubleshooting

### Issue: "Application Passwords" section not visible in WordPress

**Cause**: Application Passwords are disabled or your WordPress version is too old

**Fix**:
```php
// Add to wp-config.php to enable Application Passwords:
define('WP_APPLICATION_PASSWORDS', true);
```

Or update WordPress to version 5.6+ (Application Passwords are built-in since 5.6)

### Issue: Still getting 401 or 403 after generating new password

**Check these**:

1. **Security Plugin Configuration**:
   ```
   - WordFence: Security → All Options → "Should WordFence block the execution of application passwords"
   - iThemes Security: Settings → WordPress Tweaks → Enable REST API
   ```

2. **htaccess Basic Auth Conflict**:
   ```
   Some servers have basic auth in .htaccess that conflicts.
   Add this to .htaccess:
   
   SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1
   ```

3. **Permalink Settings**:
   ```
   - Go to: Settings → Permalinks
   - Choose any option EXCEPT "Plain"
   - Click "Save Changes"
   ```

4. **REST API Disabled**:
   ```php
   // Check if REST API is accessible by visiting:
   https://mcp.karmamarketing.com/wp-json/wp/v2/posts
   
   // If you see JSON data, REST API is working
   // If you see error or redirect, REST API might be disabled
   ```

### Issue: "Permission denied" error in settings page

**This is a different issue** - shown in your second screenshot. This is related to the MCP application's permission system, not WordPress authentication.

**Fix**:
```
This indicates the logged-in user (client) doesn't have permission to modify settings.
Two options:
1. Log in with an admin account to test integrations
2. Grant the client user permission to modify their own integrations
```

## Code-Level Fixes

### Fix 1: Improve Error Messages

The current error message could be more specific. Here's an enhanced version:

```python
# In wordpress_service.py, line 96-114
elif response.status_code == 403:
    # Enhanced diagnostic
    public_check = requests.get(
        f"{self.site_url}/wp-json/wp/v2/posts",
        params={'per_page': 1},
        timeout=10
    )
    
    if public_check.status_code == 200:
        return {
            'success': False,
            'error': 'Authentication failed',
            'message': 'The Application Password is invalid. Please regenerate it in WordPress: Users → Profile → Application Passwords. Make sure to copy it exactly with spaces.',
            'troubleshooting': [
                'Verify username is correct (not display name)',
                'Regenerate Application Password',
                'Check for security plugins blocking API',
                'Ensure user has Administrator or Editor role'
            ]
        }
    return {
        'success': False,
        'error': 'Access denied',
        'message': 'REST API access is blocked. Check WordPress security settings and plugins (WordFence, iThemes, etc.)'
    }
```

### Fix 2: Add Diagnostic Endpoint

Add this helper endpoint to help debug issues:

```python
# In publish.py or content.py
@content_bp.route('/wordpress/diagnose', methods=['POST'])
@token_required
def diagnose_wordpress(current_user):
    """
    Diagnose WordPress connection issues
    """
    data = request.get_json() or {}
    wp_url = data.get('wordpress_url', '').strip()
    
    if not wp_url:
        return jsonify({'error': 'URL required'}), 400
    
    checks = {}
    
    # Check 1: Can we reach the site?
    try:
        resp = requests.get(wp_url, timeout=10)
        checks['site_reachable'] = resp.status_code < 500
    except:
        checks['site_reachable'] = False
    
    # Check 2: Is REST API accessible?
    try:
        resp = requests.get(f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts", 
                          params={'per_page': 1}, timeout=10)
        checks['rest_api_enabled'] = resp.status_code in [200, 401]
        checks['rest_api_status_code'] = resp.status_code
    except:
        checks['rest_api_enabled'] = False
    
    # Check 3: Application Passwords endpoint exists?
    try:
        resp = requests.get(f"{wp_url.rstrip('/')}/wp-json/wp/v2/users/me",
                          timeout=10)
        checks['app_passwords_available'] = resp.status_code in [200, 401]
    except:
        checks['app_passwords_available'] = False
    
    return jsonify({
        'checks': checks,
        'recommendations': get_recommendations(checks)
    })

def get_recommendations(checks):
    recommendations = []
    
    if not checks.get('site_reachable'):
        recommendations.append('Cannot reach WordPress site - check URL')
    
    if not checks.get('rest_api_enabled'):
        recommendations.append('REST API not accessible - check permalinks and security plugins')
    
    if not checks.get('app_passwords_available'):
        recommendations.append('Application Passwords may not be enabled - update WordPress or add define(WP_APPLICATION_PASSWORDS, true) to wp-config.php')
    
    return recommendations
```

### Fix 3: Client Permission Issue

For the "Permission denied" error in the settings page:

```python
# In routes/clients.py or appropriate route
# Ensure clients can update their own WordPress settings

@clients_bp.route('/<client_id>/wordpress', methods=['PUT'])
@token_required
def update_client_wordpress(current_user, client_id):
    """
    Allow clients to update their own WordPress settings
    """
    client = data_service.get_client(client_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Check permission - admin OR client's own user
    if current_user.role != 'admin' and current_user.client_id != client_id:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    
    if 'wordpress_url' in data:
        client.wordpress_url = data['wordpress_url']
    if 'wordpress_user' in data:
        client.wordpress_user = data['wordpress_user']
    if 'wordpress_app_password' in data:
        client.wordpress_app_password = data['wordpress_app_password']
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'WordPress settings updated'
    })
```

## Quick Checklist

For the client experiencing this issue, have them verify:

- [ ] WordPress username is `automation_agent` (not "Automation Agent")
- [ ] Generate a fresh Application Password from WordPress admin
- [ ] Copy the password exactly with spaces: `xxxx xxxx xxxx xxxx`
- [ ] Site URL is `https://mcp.karmamarketing.com` (no trailing slash)
- [ ] User `automation_agent` has Administrator or Editor role
- [ ] WordPress is version 5.6 or higher
- [ ] Permalinks are not set to "Plain"
- [ ] No security plugins blocking REST API

## Testing the Fix

After implementing the fixes:

```bash
# Test REST API directly with curl:
curl -u "automation_agent:AbCd EfGh IjKl MnOp" \
  https://mcp.karmamarketing.com/wp-json/wp/v2/posts?per_page=1

# Should return JSON with posts data
```

## Additional Resources

- [WordPress Application Passwords Documentation](https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/)
- [REST API Handbook](https://developer.wordpress.org/rest-api/)
- [Common REST API Issues](https://developer.wordpress.org/rest-api/frequently-asked-questions/)

## Summary

**Most likely fix**: The client needs to:
1. Verify the WordPress username is exactly `automation_agent`
2. Generate a fresh Application Password in WordPress
3. Enter it with spaces in the MCP application
4. Test the connection

The code is working correctly - it's detecting that authentication is failing. The issue is with the credentials themselves.
