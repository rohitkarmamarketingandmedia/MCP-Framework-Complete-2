#!/usr/bin/env python3
"""
WordPress Connection Diagnostic Tool
====================================

This script helps diagnose WordPress REST API connection issues.
Run this to test your WordPress credentials before using them in the MCP application.

Usage:
    python test_wordpress_connection.py

You'll be prompted for:
- WordPress Site URL
- WordPress Username
- Application Password
"""

import sys
import json
import base64
import requests
from typing import Dict, Any


def print_header():
    """Print a nice header"""
    print("\n" + "="*70)
    print("🔧 WordPress REST API Connection Diagnostics")
    print("="*70 + "\n")


def print_section(title: str):
    """Print a section header"""
    print(f"\n{'─'*70}")
    print(f"📋 {title}")
    print('─'*70)


def test_basic_connectivity(site_url: str) -> Dict[str, Any]:
    """Test if we can reach the WordPress site at all"""
    print_section("Step 1: Testing Basic Connectivity")
    
    try:
        print(f"  Connecting to: {site_url}")
        response = requests.get(site_url, timeout=10)
        
        if response.status_code < 400:
            print(f"  ✅ Site is reachable (HTTP {response.status_code})")
            return {'success': True, 'status_code': response.status_code}
        else:
            print(f"  ⚠️  Site returned HTTP {response.status_code}")
            return {'success': False, 'status_code': response.status_code}
            
    except requests.exceptions.Timeout:
        print("  ❌ Connection timeout - site took too long to respond")
        return {'success': False, 'error': 'timeout'}
    except requests.exceptions.ConnectionError:
        print("  ❌ Could not connect to site - check URL")
        return {'success': False, 'error': 'connection_failed'}
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {'success': False, 'error': str(e)}


def test_rest_api(site_url: str) -> Dict[str, Any]:
    """Test if REST API is enabled"""
    print_section("Step 2: Testing REST API Availability")
    
    api_url = f"{site_url.rstrip('/')}/wp-json/wp/v2"
    
    try:
        print(f"  Testing API endpoint: {api_url}/posts")
        response = requests.get(
            f"{api_url}/posts",
            params={'per_page': 1},
            timeout=10
        )
        
        if response.status_code == 200:
            print("  ✅ REST API is enabled and working!")
            posts = response.json()
            if posts:
                print(f"  📝 Found {len(posts)} public post(s)")
            return {'success': True, 'api_enabled': True}
            
        elif response.status_code == 401:
            print("  ✅ REST API is enabled (requires authentication)")
            return {'success': True, 'api_enabled': True, 'requires_auth': True}
            
        elif response.status_code == 404:
            print("  ❌ REST API not found")
            print("     → Check permalinks: Settings → Permalinks (must not be 'Plain')")
            return {'success': False, 'api_enabled': False}
            
        else:
            print(f"  ⚠️  Unexpected response: HTTP {response.status_code}")
            return {'success': False, 'status_code': response.status_code}
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {'success': False, 'error': str(e)}


def test_authentication(site_url: str, username: str, app_password: str) -> Dict[str, Any]:
    """Test authentication with provided credentials"""
    print_section("Step 3: Testing Authentication")
    
    api_url = f"{site_url.rstrip('/')}/wp-json/wp/v2"
    
    # Create auth header
    credentials = f"{username}:{app_password}"
    token = base64.b64encode(credentials.encode()).decode()
    headers = {
        'Authorization': f'Basic {token}',
        'Content-Type': 'application/json',
    }
    
    try:
        print(f"  Testing with username: {username}")
        print(f"  Password length: {len(app_password)} characters")
        
        # Try to get posts with auth
        response = requests.get(
            f"{api_url}/posts",
            headers=headers,
            params={'per_page': 1},
            timeout=15
        )
        
        if response.status_code == 200:
            print("  ✅ Authentication successful!")
            
            # Try to get user info
            try:
                user_response = requests.get(
                    f"{api_url}/users/me",
                    headers=headers,
                    timeout=10
                )
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    print(f"\n  👤 User Information:")
                    print(f"     • Name: {user_data.get('name')}")
                    print(f"     • Username: {user_data.get('slug')}")
                    print(f"     • ID: {user_data.get('id')}")
                    print(f"     • Roles: {', '.join(user_data.get('roles', []))}")
                    
                    caps = user_data.get('capabilities', {})
                    can_publish = 'edit_posts' in caps
                    can_edit_others = 'edit_others_posts' in caps
                    
                    print(f"\n  🔐 Permissions:")
                    print(f"     • Can publish posts: {'✅ Yes' if can_publish else '❌ No'}")
                    print(f"     • Can edit others posts: {'✅ Yes' if can_edit_others else '❌ No'}")
                    
                    return {
                        'success': True,
                        'authenticated': True,
                        'user': user_data.get('slug'),
                        'roles': user_data.get('roles', [])
                    }
            except Exception as e:
                print(f"  ⚠️  Could not fetch user details: {e}")
            
            return {'success': True, 'authenticated': True}
            
        elif response.status_code == 401:
            print("  ❌ Authentication FAILED - credentials are incorrect")
            print("\n  🔍 Common Issues:")
            print("     1. Username might be wrong - check Users → All Users in WordPress")
            print("     2. Application Password is incorrect - regenerate it")
            print("     3. Make sure to copy password WITH spaces: 'AbCd EfGh IjKl MnOp'")
            print("     4. You're using Application Password, not regular password, right?")
            return {'success': False, 'authenticated': False, 'error': 'invalid_credentials'}
            
        elif response.status_code == 403:
            print("  ❌ Authentication REJECTED")
            print("\n  🔍 Possible Issues:")
            print("     1. Application Passwords might not be enabled")
            print("     2. User lacks necessary permissions")
            print("     3. Security plugin blocking API access")
            print("     4. REST API disabled for this user")
            return {'success': False, 'authenticated': False, 'error': 'permission_denied'}
            
        else:
            print(f"  ❌ Unexpected response: HTTP {response.status_code}")
            return {'success': False, 'status_code': response.status_code}
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {'success': False, 'error': str(e)}


def test_application_passwords_feature(site_url: str) -> Dict[str, Any]:
    """Check if Application Passwords feature is available"""
    print_section("Step 4: Checking Application Passwords Feature")
    
    try:
        response = requests.get(f"{site_url.rstrip('/')}/wp-json", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            auth_available = 'authentication' in data
            
            if auth_available:
                print("  ✅ Application Passwords feature appears to be available")
            else:
                print("  ⚠️  Application Passwords feature might not be enabled")
                print("     → Ensure WordPress is version 5.6 or higher")
                print("     → Or add to wp-config.php: define('WP_APPLICATION_PASSWORDS', true);")
            
            return {'success': True, 'feature_available': auth_available}
    except Exception as e:
        print(f"  ⚠️  Could not check: {e}")
        return {'success': False}


def print_recommendations(results: Dict[str, Any]):
    """Print recommendations based on test results"""
    print_section("💡 Recommendations")
    
    if all(r.get('success') for r in results.values() if 'success' in r):
        print("\n  🎉 All tests passed! Your WordPress connection should work.")
        print("\n  ✅ You can use these credentials in the MCP application:")
        print(f"     • Site URL: {results['inputs']['site_url']}")
        print(f"     • Username: {results['inputs']['username']}")
        print(f"     • App Password: (the one you entered)")
        return
    
    print("\n  ⚠️  Some issues were detected. Here's what to do:\n")
    
    if not results['connectivity'].get('success'):
        print("  1. 🌐 Fix Site Connectivity:")
        print("     • Verify the URL is correct")
        print("     • Check if site is online")
        print("     • Try accessing it in a browser")
        print()
    
    if not results['rest_api'].get('api_enabled'):
        print("  2. 🔌 Enable REST API:")
        print("     • Go to: Settings → Permalinks")
        print("     • Choose ANY option except 'Plain'")
        print("     • Click 'Save Changes'")
        print("     • Check for plugins that disable REST API")
        print()
    
    if 'authentication' in results and not results['authentication'].get('authenticated'):
        print("  3. 🔑 Fix Authentication:")
        print("     • Log into WordPress admin")
        print("     • Go to: Users → Profile")
        print("     • Scroll to: Application Passwords")
        print("     • Create a NEW password")
        print("     • Copy it EXACTLY with spaces")
        print("     • Verify username is correct (not display name)")
        print()


def main():
    """Main function"""
    print_header()
    
    print("This tool will test your WordPress REST API connection.")
    print("You'll need:")
    print("  • WordPress site URL")
    print("  • WordPress username")
    print("  • Application Password (from WordPress → Users → Profile)")
    print()
    
    # Get inputs
    site_url = input("WordPress Site URL (e.g., https://example.com): ").strip()
    if not site_url:
        print("❌ Site URL is required!")
        sys.exit(1)
    
    username = input("WordPress Username: ").strip()
    if not username:
        print("❌ Username is required!")
        sys.exit(1)
    
    app_password = input("Application Password (with or without spaces): ").strip()
    if not app_password:
        print("❌ Application Password is required!")
        sys.exit(1)
    
    # Remove spaces from password if present (WordPress accepts both formats)
    app_password = app_password.replace(' ', '')
    
    # Store inputs for final report
    results = {
        'inputs': {
            'site_url': site_url,
            'username': username
        }
    }
    
    # Run tests
    results['connectivity'] = test_basic_connectivity(site_url)
    results['rest_api'] = test_rest_api(site_url)
    results['app_passwords'] = test_application_passwords_feature(site_url)
    results['authentication'] = test_authentication(site_url, username, app_password)
    
    # Print summary
    print_recommendations(results)
    
    print("\n" + "="*70)
    print("✅ Diagnostic complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)
