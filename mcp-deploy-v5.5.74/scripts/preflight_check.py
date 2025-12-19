#!/usr/bin/env python3
"""
Karma Marketing + Media - Pre-Deploy Check
Run this BEFORE pushing to GitHub to catch common issues.

Usage:
    python scripts/preflight_check.py
"""
import os
import sys
import re

def green(text): return f"\033[92m✓ {text}\033[0m"
def red(text): return f"\033[91m✗ {text}\033[0m"
def yellow(text): return f"\033[93m⚠ {text}\033[0m"

def check_file(path, description):
    """Check if file exists"""
    if os.path.exists(path):
        print(green(description))
        return True
    else:
        print(red(f"{description} - MISSING: {path}"))
        return False

def check_no_secrets():
    """Check for hardcoded secrets"""
    issues = []
    patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API key'),
        (r'sk-ant-[a-zA-Z0-9]{20,}', 'Anthropic API key'),
        (r'SG\.[a-zA-Z0-9]{20,}', 'SendGrid API key'),
        (r'password\s*=\s*["\'][^"\']{4,}["\']', 'Hardcoded password'),
    ]
    
    files_to_check = []
    for root, dirs, files in os.walk('.'):
        # Skip directories
        dirs[:] = [d for d in dirs if d not in ['venv', '.git', '__pycache__', 'node_modules', 'instance']]
        for f in files:
            if f.endswith(('.py', '.html', '.js', '.json', '.yaml', '.yml')):
                files_to_check.append(os.path.join(root, f))
    
    for filepath in files_to_check:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for pattern, name in patterns:
                    if re.search(pattern, content):
                        # Exclude .env.example files and test files
                        if '.example' not in filepath and 'test' not in filepath.lower() and 'tests/' not in filepath:
                            issues.append(f"{filepath}: Possible {name}")
        except:
            pass
    
    return issues

def check_no_localhost_hardcoded():
    """Check for hardcoded localhost in HTML files"""
    issues = []
    for f in os.listdir('.'):
        if f.endswith('.html'):
            with open(f, 'r') as file:
                content = file.read()
                if 'localhost:' in content or '127.0.0.1:' in content:
                    if 'window.location' not in content[:content.find('localhost')]:
                        issues.append(f"{f}: Contains hardcoded localhost")
    return issues

def main():
    print("\n" + "="*60)
    print("  KARMA MARKETING + MEDIA")
    print("  Pre-Deploy Checklist")
    print("="*60 + "\n")
    
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    errors = 0
    warnings = 0
    
    # Required files
    print("📁 Required Files:")
    required = [
        ('requirements.txt', 'requirements.txt'),
        ('run.py', 'Entry point'),
        ('build.sh', 'Render build script'),
        ('render.yaml', 'Render blueprint'),
        ('app/__init__.py', 'Flask app'),
        ('app/config.py', 'Configuration'),
        ('app/database.py', 'Database setup'),
    ]
    
    for path, desc in required:
        if not check_file(path, desc):
            errors += 1
    
    print()
    
    # Check for secrets
    print("🔐 Secret Check:")
    secrets = check_no_secrets()
    if secrets:
        for s in secrets:
            print(red(s))
            errors += 1
    else:
        print(green("No hardcoded secrets found"))
    
    print()
    
    # Check for hardcoded URLs
    print("🌐 URL Check:")
    urls = check_no_localhost_hardcoded()
    if urls:
        for u in urls:
            print(yellow(u))
            warnings += 1
    else:
        print(green("No hardcoded localhost URLs"))
    
    print()
    
    # Check .env doesn't exist (shouldn't be committed)
    print("📋 Git Safety:")
    if os.path.exists('.env'):
        print(yellow(".env file exists - make sure it's in .gitignore"))
        warnings += 1
    else:
        print(green("No .env file (good - use env vars in production)"))
    
    if os.path.exists('.gitignore'):
        print(green(".gitignore exists"))
    else:
        print(red(".gitignore missing!"))
        errors += 1
    
    print()
    
    # Check instance folder
    print("🗄️ Database Check:")
    if os.path.exists('instance') and any(f.endswith('.db') for f in os.listdir('instance')):
        print(yellow("SQLite databases in instance/ - should not be committed"))
        warnings += 1
    else:
        print(green("No local databases to commit"))
    
    print()
    
    # Try importing the app
    print("🐍 Python Check:")
    try:
        sys.path.insert(0, '.')
        from app import create_app
        app = create_app('testing')
        print(green(f"App creates successfully"))
        with app.app_context():
            routes = len(list(app.url_map.iter_rules()))
            print(green(f"Routes: {routes}"))
    except Exception as e:
        print(red(f"App import failed: {e}"))
        errors += 1
    
    print()
    
    # Summary
    print("="*60)
    if errors == 0 and warnings == 0:
        print("  🚀 READY TO DEPLOY!")
        print("     Run: git add . && git commit -m 'Deploy' && git push")
    elif errors == 0:
        print(f"  ⚠️  {warnings} warning(s) - Review before deploying")
    else:
        print(f"  ❌ {errors} error(s), {warnings} warning(s)")
        print("     Fix errors before deploying!")
    print("="*60 + "\n")
    
    return errors == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
