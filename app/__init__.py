"""
MCP Framework - Marketing Control Platform
AI-powered SEO content automation engine

By Karma Marketing + Media
"""
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import logging

__version__ = "5.5.191"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(config_name=None):
    """Application factory pattern"""
    # Get the root directory (parent of app/)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(root_dir, 'static')
    
    app = Flask(__name__, static_folder=static_dir, static_url_path='/static')
    
    # Fix for running behind a reverse proxy (Render, Heroku, etc.)
    # This ensures request.url uses https:// when behind HTTPS proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
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

    # Rate limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    app.limiter = limiter  # Store for use in routes
    
    
    # Initialize database
    from app.database import init_db
    init_db(app)
    
    # Import intelligence automation models so tables auto-create
    try:
        from app.models.intelligence_models import DBClientInsight, DBAiSuggestion, DBRankAlert
        with app.app_context():
            from app.database import db
            db.create_all()

            # --- Lightweight column migrations (idempotent) ---
            from sqlalchemy import text, inspect
            try:
                inspector = inspect(db.engine)
                table_names = inspector.get_table_names()

                if 'blog_posts' in table_names:
                    bp_cols = [col['name'] for col in inspector.get_columns('blog_posts')]
                    if 'notes' not in bp_cols:
                        db.session.execute(text("ALTER TABLE blog_posts ADD COLUMN notes TEXT DEFAULT '[]'"))
                        db.session.commit()
                        logger.info("Migration: added 'notes' column to blog_posts")
            except Exception as mig_err:
                logger.warning(f"Column migration check (blog_posts): {mig_err}")

            # SEMrush project fields on clients — run separately so one failure doesn't block others
            try:
                _add_col_migrations = [
                    ("clients", "semrush_project_id", "VARCHAR(100)"),
                    ("clients", "semrush_project_name", "VARCHAR(255)"),
                ]
                for _tbl, _col, _typ in _add_col_migrations:
                    try:
                        db.session.execute(text(
                            f"ALTER TABLE {_tbl} ADD COLUMN IF NOT EXISTS {_col} {_typ}"
                        ))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                logger.info("Migration: SEMrush column check complete")
            except Exception as mig_err:
                logger.warning(f"Column migration check (semrush): {mig_err}")
    except Exception as e:
        logger.warning(f"Could not initialize intelligence models: {e}")
    
    # Register blueprints
    from app.routes import register_routes
    register_routes(app)

    # Create any tables defined inside route modules (e.g. gsc_oauth_states)
    with app.app_context():
        db.create_all()

    # Apply per-endpoint rate limits to chatbot (widget message endpoint gets stricter limit)
    # Note: Don't blanket-exempt chatbot_bp — the /widget/message endpoint calls AI and needs limiting
    from app.routes.chatbot import chatbot_bp
    # Only exempt read-only polling endpoints, not AI-calling ones
    # The widget message endpoint gets a specific rate limit via decorator in chatbot.py
    
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
    
    # Serve intake dashboard (new wizard)
    @app.route('/intake')
    def intake_dashboard():
        return send_from_directory(root_dir, 'intake-wizard.html')
    
    # Serve old intake dashboard (legacy)
    @app.route('/intake-legacy')
    def intake_legacy():
        return send_from_directory(root_dir, 'intake-dashboard.html')
    
    # Serve client content dashboard (for demos)
    @app.route('/client-dashboard')
    @app.route('/client')  # Alias
    def client_dashboard():
        from flask import make_response
        response = make_response(send_from_directory(root_dir, 'client-dashboard.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    # Serve elite monitoring dashboard (SEO Command Center)
    @app.route('/elite')
    def elite_dashboard():
        from flask import make_response
        response = make_response(send_from_directory(root_dir, 'elite-dashboard.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
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
    
    # Serve content calendar (admin cross-client view)
    @app.route('/content-calendar')
    def content_calendar():
        return send_from_directory(root_dir, 'content-calendar.html')
    
    # Public chat history page (no login required)
    @app.route('/chat/<share_token>')
    def public_chat_page(share_token):
        from app.routes.chatbot import public_chat_history
        return public_chat_history(share_token)
    
    # Public blog review page (no login required - client reviews via unique token)
    @app.route('/review/<review_token>')
    def public_review_page(review_token):
        try:
            from app.routes.content_schedule_page import render_review_page
            return render_review_page(review_token)
        except Exception as e:
            logger.error(f"Review page error: {e}")
            return f"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center;">
            <h2>Review Page Error</h2>
            <p style="color:#666;">Something went wrong loading the review page.</p>
            <pre style="background:#f3f4f6;padding:16px;border-radius:8px;text-align:left;max-width:600px;margin:20px auto;overflow:auto;">{str(e)}</pre>
            </body></html>
            """, 500
    
    # Health check
    @app.route('/health')
    def health():
        # Basic health check with database ping
        try:
            from app.database import db
            db.session.execute(db.text('SELECT 1'))
            db_status = 'connected'
        except Exception as e:
            db_status = f'error: {str(e)[:50]}'
        
        return {
            'status': 'healthy' if db_status == 'connected' else 'degraded',
            'version': __version__,
            'database': db_status
        }
    
    # Diagnostic endpoint - check configuration
    @app.route('/health/config')
    def health_config():
        """Check if critical environment variables are configured"""
        import os
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        semrush_key = os.environ.get('SEMRUSH_API_KEY', '')
        sendgrid_key = os.environ.get('SENDGRID_API_KEY', '')
        from_email = os.environ.get('FROM_EMAIL', '')

        # Debug: list all env vars with API or KEY in name (show lengths only for security)
        api_vars = {k: len(v) for k, v in os.environ.items() if 'API' in k.upper() or 'KEY' in k.upper()}

        # Check for missing recommended vars
        missing = []
        if not anthropic_key:
            missing.append('ANTHROPIC_API_KEY (required for all AI content generation)')
        if not from_email:
            missing.append('FROM_EMAIL (required for sending emails)')

        return {
            'status': 'ok' if anthropic_key else 'missing_ai_key',
            'version': __version__,
            'config': {
                'anthropic_configured': bool(anthropic_key),
                'semrush_configured': bool(semrush_key),
                'semrush_key_length': len(semrush_key),
                'sendgrid_configured': bool(sendgrid_key),
                'from_email_configured': bool(from_email),
                'database_configured': bool(os.environ.get('DATABASE_URL', '')),
            },
            'api_env_vars': api_vars,
            'total_env_vars': len(os.environ),
            'missing_recommended': missing,
            'message': 'All good!' if anthropic_key else 'Set ANTHROPIC_API_KEY in Render environment variables'
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
                'portal': '/portal',
                'content-calendar': '/content-calendar'
            }
        }
    
    # Initialize background scheduler (only when explicitly enabled)
    if not app.config.get('TESTING') and os.environ.get('ENABLE_SCHEDULER') == '1':
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
