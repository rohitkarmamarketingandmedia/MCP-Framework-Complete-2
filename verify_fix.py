#!/usr/bin/env python3
"""
Run this script in your project directory to verify the fix is in place.
Usage: python3 verify_fix.py
"""

import os
import sys

def check_content_py():
    """Check if content.py has the BlogAISingle fix"""
    filepath = 'app/routes/content.py'
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check for OLD code (bad)
    if 'ai_service.generate_blog_post(' in content:
        print(f"❌ {filepath}: Still using OLD ai_service.generate_blog_post()")
        print("   This is the PROBLEM - the fix is NOT applied!")
        return False
    
    # Check for NEW code (good)
    if 'get_blog_ai_single()' in content and 'BlogRequest(' in content:
        print(f"✅ {filepath}: Using BlogAISingle (GOOD)")
        return True
    
    print(f"⚠️ {filepath}: Unknown state")
    return False

def check_blog_ai_single():
    """Check if blog_ai_single.py has the duplicate location fix"""
    filepath = 'app/services/blog_ai_single.py'
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    if '_fix_duplicate_locations' in content:
        print(f"✅ {filepath}: Has _fix_duplicate_locations function")
        
        # Check if it's being called
        if 'self._fix_duplicate_locations(result' in content:
            print(f"✅ {filepath}: _fix_duplicate_locations is being CALLED")
            return True
        else:
            print(f"❌ {filepath}: _fix_duplicate_locations EXISTS but is NOT being called!")
            return False
    else:
        print(f"❌ {filepath}: Missing _fix_duplicate_locations function")
        return False

def check_db_models():
    """Check if db_models.py has scheduled_for in to_dict"""
    filepath = 'app/models/db_models.py'
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    if "'scheduled_for':" in content and 'scheduled_for.isoformat()' in content:
        print(f"✅ {filepath}: Has scheduled_for in to_dict")
        return True
    else:
        print(f"❌ {filepath}: Missing scheduled_for in to_dict")
        return False

def main():
    print("=" * 60)
    print("VERIFYING CITY DUPLICATION FIX")
    print("=" * 60)
    print()
    
    results = []
    results.append(("content.py BlogAISingle", check_content_py()))
    results.append(("blog_ai_single.py fix", check_blog_ai_single()))
    results.append(("db_models.py scheduled_for", check_db_models()))
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_pass = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_pass = False
    
    print()
    if all_pass:
        print("🎉 All checks passed! The fix should be working.")
        print("   If still seeing issues, restart the server.")
    else:
        print("🚨 Some checks FAILED! The fix is NOT properly deployed.")
        print("   You need to replace the files that failed.")
    
    return 0 if all_pass else 1

if __name__ == '__main__':
    sys.exit(main())
