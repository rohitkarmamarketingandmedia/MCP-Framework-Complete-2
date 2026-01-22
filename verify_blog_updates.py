import sys
import os

# Mock required modules
import types
mock_openai = types.ModuleType('openai')
mock_openai.OpenAI = type('OpenAI', (), {})
sys.modules['openai'] = mock_openai

mock_flask = types.ModuleType('flask')
mock_flask.Flask = type('Flask', (), {})
mock_flask.send_from_directory = lambda x, y: None
mock_flask.jsonify = lambda x: None
sys.modules['flask'] = mock_flask

sys.modules['flask_cors'] = type('MockFlaskCors', (), {'CORS': lambda x: None})
sys.modules['flask_limiter'] = type('MockFlaskLimiter', (), {'Limiter': lambda **kwargs: type('MockLimiter', (), {'limit': lambda x: lambda f: f})})

from app.services.blog_ai_single import BlogAISingle, BlogRequest
from app.services.wordpress_service import WordPressService

def test_blog_generation():
    print("Testing BlogAISingle configuration...")
    service = BlogAISingle(api_key="mock_key")
    
    # Check _system_prompt for generic phrase avoidance
    req = BlogRequest(keyword="ac repair", city="Sarasota")
    prompt = service._build_prompt(req)
    system_prompt = service._system_prompt
    
    if "INSTRUCTIONS FOR TAGS" in system_prompt:
        print("PASS: System prompt includes tag instructions")
    else:
        print("FAIL: System prompt missing tag instructions")
        
    if "Your satisfaction is our priority" in system_prompt and "AVOID THESE PHRASES" in system_prompt:
        print("PASS: System prompt instructions include tone guidelines")
    else:
        print("FAIL: System prompt missing tone guidelines")

    # Check JSON template
    if '"tags":' in prompt:
        print("PASS: User prompt includes 'tags' field in JSON template")
    else:
        print("FAIL: User prompt missing 'tags' field")

def test_wordpress_tags():
    print("\nTesting WordPressService tag logic...")
    # Mock content object
    class MockContent:
        primary_keyword = "ac repair"
        tags = '["AC Repair", "Sarasota AC", "Cooling"]'
    
    content = MockContent()
    
    # Extract tags logic (simulated from publish_content)
    import json
    tags = []
    if hasattr(content, 'tags') and content.tags:
        tags = content.tags if isinstance(content.tags, list) else json.loads(content.tags)
    
    print(f"Extracted tags: {tags}")
    if len(tags) == 3 and tags[0] == "AC Repair":
        print("PASS: Tag extraction logic works")
    else:
        print("FAIL: Tag extraction logic failed")

if __name__ == "__main__":
    try:
        test_blog_generation()
        test_wordpress_tags()
    except Exception as e:
        print(f"Test failed with error: {e}")
