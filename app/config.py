"""
MCP Framework - Configuration
Environment-based configuration for different deployment stages
"""
import os
from datetime import timedelta


class BaseConfig:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
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
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    SEMRUSH_API_KEY = os.environ.get('SEMRUSH_API_KEY', '')
    
    # AI Model Settings
    DEFAULT_AI_MODEL = os.environ.get('DEFAULT_AI_MODEL', 'gpt-4o-mini')
    FALLBACK_AI_MODEL = os.environ.get('FALLBACK_AI_MODEL', 'claude-3-sonnet-20240229')
    
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
    DEFAULT_BLOG_WORD_COUNT = int(os.environ.get('DEFAULT_BLOG_WORD_COUNT', '1800'))
    DEFAULT_TONE = os.environ.get('DEFAULT_TONE', 'professional')
    
    # Rate limiting
    RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'true').lower() == 'true'
    RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', '60'))
    
    # JWT Auth
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
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
