"""
MCP Framework - Routes
API endpoint registration
"""
from flask import Flask


def register_routes(app: Flask):
    """Register all API blueprints"""
    
    from app.routes.auth import auth_bp
    from app.routes.content import content_bp
    from app.routes.schema import schema_bp
    from app.routes.social import social_bp
    from app.routes.publish import publish_bp
    from app.routes.analytics import analytics_bp
    from app.routes.clients import clients_bp
    from app.routes.campaigns import campaigns_bp
    from app.routes.intake import intake_bp
    
    # Register with /api prefix
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(content_bp, url_prefix='/api/content')
    app.register_blueprint(schema_bp, url_prefix='/api/schema')
    app.register_blueprint(social_bp, url_prefix='/api/social')
    app.register_blueprint(publish_bp, url_prefix='/api/publish')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(clients_bp, url_prefix='/api/clients')
    app.register_blueprint(campaigns_bp, url_prefix='/api/campaigns')
    app.register_blueprint(intake_bp, url_prefix='/api/intake')
