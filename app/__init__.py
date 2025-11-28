"""
MCP Framework - Marketing Control Platform
AI-powered SEO content automation engine

By Karma Marketing + Media
"""
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
import os
import logging

__version__ = "4.5.0"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    
    # Enable CORS - IMPORTANT: Set CORS_ORIGINS env var in production!
    cors_origins = app.config.get('CORS_ORIGINS', '*')
    if cors_origins == '*' and app.config.get('ENV') == 'production':
        logger.warning("SECURITY: CORS_ORIGINS is set to '*' in production! Set specific origins.")
    CORS(app, origins=cors_origins)
    
    # Initialize database
    from app.database import init_db
    init_db(app)
    
    # Register blueprints
    from app.routes import register_routes
    register_routes(app)
    
    # ==========================================
    # GLOBAL ERROR HANDLERS
    # ==========================================
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error': 'Bad request',
            'message': str(error.description) if hasattr(error, 'description') else 'Invalid request'
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required'
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'error': 'Forbidden',
            'message': 'Access denied'
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not found',
            'message': 'The requested resource was not found'
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        """Catch-all for unhandled exceptions"""
        logger.error(f"Unhandled exception: {error}", exc_info=True)
        return jsonify({
            'error': 'Server error',
            'message': 'An unexpected error occurred'
        }), 500
    
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
    @app.route('/client')  # Alias
    def client_dashboard():
        return send_from_directory(root_dir, 'client-dashboard.html')
    
    # Serve elite monitoring dashboard (SEO Command Center)
    @app.route('/elite')
    def elite_dashboard():
        return send_from_directory(root_dir, 'elite-dashboard.html')
    
    # Serve agency command center (master dashboard)
    @app.route('/agency')
    def agency_dashboard():
        return send_from_directory(root_dir, 'agency-dashboard.html')
    
    # Serve admin panel
    @app.route('/admin')
    def admin_dashboard():
        return send_from_directory(root_dir, 'admin-dashboard.html')
    
    # Serve client portal
    @app.route('/portal')
    def portal_dashboard():
        return send_from_directory(root_dir, 'portal-dashboard.html')
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'healthy', 'version': __version__}
    
    # Diagnostic endpoint - check configuration
    @app.route('/health/config')
    def health_config():
        """Check if critical environment variables are configured"""
        import os
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        semrush_key = os.environ.get('SEMRUSH_API_KEY', '')
        
        return {
            'status': 'ok' if openai_key or anthropic_key else 'missing_ai_key',
            'version': __version__,
            'config': {
                'openai_configured': bool(openai_key) and openai_key.startswith('sk-'),
                'anthropic_configured': bool(anthropic_key),
                'semrush_configured': bool(semrush_key),
                'database_configured': bool(os.environ.get('DATABASE_URL', '')),
            },
            'message': 'All good!' if (openai_key or anthropic_key) else 'Set OPENAI_API_KEY in Render environment variables'
        }
    
    # API info endpoint
    @app.route('/api')
    def api_info():
        return {
            'name': 'Karma Marketing + Media API',
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
                'semrush': '/api/semrush',
                'monitoring': '/api/monitoring',
                'agency': '/api/agency',
                'scheduler': '/api/scheduler'
            },
            'dashboards': {
                'agency': '/agency',
                'intake': '/intake',
                'client': '/client-dashboard',
                'elite': '/elite',
                'admin': '/admin',
                'portal': '/portal'
            }
        }
    
    # Initialize background scheduler (only in production)
    if not app.config.get('TESTING') and os.environ.get('ENABLE_SCHEDULER', 'true').lower() == 'true':
        try:
            from app.services.scheduler_service import init_scheduler
            init_scheduler(app)
            app.logger.info("Background scheduler started")
        except Exception as e:
            app.logger.warning(f"Could not start scheduler: {e}")
    
    # Auto-initialize agents and check for admin user on startup
    if not app.config.get('TESTING'):
        with app.app_context():
            try:
                from app.services.agent_service import agent_service
                created = agent_service.initialize_default_agents()
                if created > 0:
                    app.logger.info(f"✓ Initialized {created} default AI agents")
            except Exception as e:
                app.logger.warning(f"Could not initialize agents: {e}")
            
            # Check if admin user exists, log warning if not
            try:
                from app.models.db_models import DBUser
                admin_count = DBUser.query.filter_by(role='admin').count()
                if admin_count == 0:
                    app.logger.warning("⚠ No admin user exists! Run: python scripts/create_admin.py")
            except Exception as e:
                app.logger.warning(f"Could not check admin users: {e}")
    
    return app
