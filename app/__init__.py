"""
MCP Framework - Marketing Control Platform
AI-powered SEO content automation engine

By Karma Marketing + Media
"""
from flask import Flask, send_from_directory
from flask_cors import CORS
import os

__version__ = "3.0.0"


def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__, static_folder=None)
    
    # Load config
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    from app.config import config
    # Use instance instead of class to support @property
    config_instance = config[config_name]()
    app.config.from_object(config_instance)
    
    # Enable CORS
    CORS(app, origins=app.config.get('CORS_ORIGINS', '*'))
    
    # Initialize database
    from app.database import init_db
    init_db(app)
    
    # Register blueprints
    from app.routes import register_routes
    register_routes(app)
    
    # Get the root directory (where dashboard.html lives)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Serve dashboard at root
    @app.route('/')
    def dashboard():
        return send_from_directory(root_dir, 'dashboard.html')
    
    # Serve intake dashboard
    @app.route('/intake')
    def intake_dashboard():
        return send_from_directory(root_dir, 'intake-dashboard.html')
    
    # Serve client content dashboard (for demos)
    @app.route('/client-dashboard')
    def client_dashboard():
        return send_from_directory(root_dir, 'client-dashboard.html')
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'healthy', 'version': __version__}
    
    # API info endpoint
    @app.route('/api')
    def api_info():
        return {
            'name': 'MCP Framework API',
            'version': __version__,
            'status': 'running',
            'endpoints': {
                'auth': '/api/auth',
                'intake': '/api/intake',
                'content': '/api/content',
                'schema': '/api/schema',
                'social': '/api/social',
                'publish': '/api/publish',
                'analytics': '/api/analytics',
                'clients': '/api/clients',
                'campaigns': '/api/campaigns',
                'semrush': '/api/semrush'
            }
        }
    
    return app
