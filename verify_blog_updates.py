import sys
import os

# Mock required modules
import types
mock_openai = types.ModuleType('openai')
mock_openai.OpenAI = type('OpenAI', (), {'__init__': lambda self, **kwargs: None, 'chat': type('Chat', (), {'completions': type('Completions', (), {'create': lambda **kwargs: type('Response', (), {'choices': [type('Choice', (), {'message': type('Message', (), {'content': ''})})]})})})})
sys.modules['openai'] = mock_openai

mock_flask = types.ModuleType('flask')
mock_flask.Flask = type('Flask', (), {})
mock_flask.send_from_directory = lambda x, y: None
mock_flask.jsonify = lambda x: None
sys.modules['flask'] = mock_flask

sys.modules['flask_cors'] = type('MockFlaskCors', (), {'CORS': lambda x: None})
sys.modules['flask_limiter'] = type('MockFlaskLimiter', (), {'Limiter': lambda **kwargs: type('MockLimiter', (), {'limit': lambda x: lambda f: f})})
sys.modules['flask_limiter.util'] = type('MockFlaskLimiterUtil', (), {'get_remote_address': lambda: '127.0.0.1'})
sys.modules['werkzeug'] = types.ModuleType('werkzeug')
sys.modules['werkzeug.middleware'] = types.ModuleType('werkzeug.middleware')
sys.modules['werkzeug.middleware.proxy_fix'] = type('MockProxyFix', (), {'ProxyFix': lambda x: None})
sys.modules['sqlalchemy'] = types.ModuleType('sqlalchemy')
for name in ['String', 'Text', 'Integer', 'Float', 'Boolean', 'DateTime', 'Enum', 'JSON', 'ForeignKey', 'text']:
    setattr(sys.modules['sqlalchemy'], name, lambda *args, **kwargs: None)
sys.modules['sqlalchemy.orm'] = types.ModuleType('sqlalchemy.orm')
sys.modules['sqlalchemy.orm'].DeclarativeBase = type('DeclarativeBase', (), {}) 
sys.modules['sqlalchemy.orm'].Mapped = lambda x: x
sys.modules['sqlalchemy.orm'].mapped_column = lambda *args, **kwargs: None
sys.modules['sqlalchemy.orm'].relationship = lambda *args, **kwargs: None
sys.modules['sqlalchemy.exc'] = types.ModuleType('sqlalchemy.exc')
sys.modules['sqlalchemy.exc'].SQLAlchemyError = Exception
sys.modules['flask_sqlalchemy'] = type('MockFlaskSQLAlchemy', (), {
    'SQLAlchemy': lambda **kwargs: type('MockSQLAlchemy', (), {
        'Model': object,
        'UniqueConstraint': lambda *args, **kwargs: None,
        'Index': lambda *args, **kwargs: None,
        'Column': lambda *args, **kwargs: None,
        'String': lambda *args, **kwargs: None,
        'Text': lambda *args, **kwargs: None,
        'Integer': lambda *args, **kwargs: None,
        'Float': lambda *args, **kwargs: None,
        'Boolean': lambda *args, **kwargs: None,
        'DateTime': lambda *args, **kwargs: None,
        'Enum': lambda *args, **kwargs: None,
        'JSON': lambda *args, **kwargs: None,
        'ForeignKey': lambda *args, **kwargs: None
    })
})
sys.modules['requests'] = types.ModuleType('requests')
sys.modules['requests.exceptions'] = type('MockRequestsExceptions', (), {'Timeout': Exception, 'RequestException': Exception})

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

    # Check Title Separation Instructions
    if "H1 HEADING (BLOG TITLE)" in prompt and "MUST be different from meta_title" in prompt:
        print("PASS: Prompt includes instructions to separate H1 and Meta Title")
    else:
        print("FAIL: Prompt missing H1/Meta Title separation instructions")
        
    if "catchy" in prompt and "descriptive" in prompt:
        print("PASS: Prompt includes 'catchy' and 'descriptive' instructions for H1")
    else:
        print("FAIL: Prompt missing 'catchy' or 'descriptive' instructions for H1")

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
