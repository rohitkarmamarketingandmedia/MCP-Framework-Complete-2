"""
MCP Framework - Configuration
Environment-based configuration for different deployment stages
"""
import os
from datetime import timedelta


class BaseConfig:
    """Base configuration"""
    
    # Flask - Secret key (required in production)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Warn if using dev key in production-like environment
    _is_production = os.environ.get('RENDER') or os.environ.get('FLASK_ENV') == 'production'
    if SECRET_KEY == 'dev-secret-key-change-in-production' and _is_production:
        import warnings
        warnings.warn("SECRET_KEY is using default dev value in production! Set SECRET_KEY env var.")
    
    # CORS
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    
    # Database - PostgreSQL for production, SQLite for local dev
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """Get database URI, handling Render's postgres:// prefix"""
        db_url = os.environ.get('DATABASE_URL', '')
        
        if db_url:
            # Render uses postgres:// but SQLAlchemy needs postgresql://
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
            elif db_url.startswith('postgresql://'):
                db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
            return db_url
        
        # Fallback to SQLite for local development
        return 'sqlite:///mcp_framework.db'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # API Keys
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')  # Only used for DALL-E image generation
    SEMRUSH_API_KEY = os.environ.get('SEMRUSH_API_KEY', '')

    # AI Model Settings — Claude only for all content generation
    DEFAULT_AI_MODEL = os.environ.get('DEFAULT_AI_MODEL', 'claude-sonnet-4-6')
    FAST_AI_MODEL = os.environ.get('FAST_AI_MODEL', 'claude-haiku-4-5-20251001')
    
    # WordPress
    WP_BASE_URL = os.environ.get('WP_BASE_URL', '')
    WP_USERNAME = os.environ.get('WP_USERNAME', '')
    WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD', '')
    
    # Google Business Profile
    GBP_LOCATION_ID = os.environ.get('GBP_LOCATION_ID', '')
    GBP_API_KEY = os.environ.get('GBP_API_KEY', '')
    
    # Google Analytics 4
    GA4_PROPERTY_ID = os.environ.get('GA4_PROPERTY_ID', '')
    GA4_CREDENTIALS_JSON = os.environ.get('GA4_CREDENTIALS_JSON', '')
    
    # Social Media
    FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN', '')
    FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID', '')
    INSTAGRAM_ACCESS_TOKEN = os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')
    LINKEDIN_ACCESS_TOKEN = os.environ.get('LINKEDIN_ACCESS_TOKEN', '')
    
    # Content generation defaults
    DEFAULT_BLOG_WORD_COUNT = int(os.environ.get('DEFAULT_BLOG_WORD_COUNT', '1000'))
    DEFAULT_TONE = os.environ.get('DEFAULT_TONE', 'professional')
    
    # Rate limiting
    RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'true').lower() == 'true'
    RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', '60'))
    
    # JWT Auth — key must be ≥ 32 bytes for HS256 (RFC 7518 §3.2)
    _jwt_raw = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
    # Pad short keys to at least 32 bytes so PyJWT doesn't emit InsecureKeyLengthWarning
    JWT_SECRET_KEY = _jwt_raw if len(_jwt_raw.encode()) >= 32 else (_jwt_raw + ('x' * (32 - len(_jwt_raw.encode()))))
    if len(_jwt_raw.encode()) < 32 and _is_production:
        import warnings
        warnings.warn(
            f"JWT_SECRET_KEY is only {len(_jwt_raw.encode())} bytes — set a random 32+ character "
            "JWT_SECRET_KEY env var in Render to silence this warning and improve security."
        )
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_EXPIRES_HOURS', '24')))


class DevelopmentConfig(BaseConfig):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """Get database URI - SQLite for local dev, or DATABASE_URL if set"""
        db_url = os.environ.get('DATABASE_URL', '')
        if db_url:
            # Handle Render postgres:// prefix, use psycopg v3 driver
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
            elif db_url.startswith('postgresql://'):
                db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
            return db_url
        return 'sqlite:///mcp_framework.db'


class ProductionConfig(BaseConfig):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """Get database URI, handling Render's postgres:// prefix"""
        db_url = os.environ.get('DATABASE_URL', '')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif db_url.startswith('postgresql://'):
            db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
        return db_url
    
    # Override with production requirements
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')


class TestingConfig(BaseConfig):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """Use DATABASE_URL if set, otherwise in-memory SQLite"""
        db_url = os.environ.get('DATABASE_URL', '')
        if db_url:
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
            elif db_url.startswith('postgresql://'):
                db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
            return db_url
        return 'sqlite:///:memory:'
    
    # Use test API keys
    OPENAI_API_KEY = 'test-key'
    ANTHROPIC_API_KEY = 'test-key'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get current config object"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
