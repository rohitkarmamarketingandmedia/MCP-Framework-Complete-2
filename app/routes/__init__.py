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
    from app.routes.semrush import semrush_bp
    from app.routes.monitoring import monitoring_bp
    from app.routes.agency import agency_bp
    from app.routes.scheduler import scheduler_bp
    from app.routes.leads import leads_bp
    from app.routes.pages import pages_bp
    from app.routes.gbp import gbp_bp
    from app.routes.reviews import reviews_bp
    from app.routes.settings import settings_bp
    from app.routes.agents import agents_bp
    from app.routes.chatbot import chatbot_bp
    from app.routes.notifications import notifications_bp
    from app.routes.oauth import oauth_bp
    from app.routes.images import images_bp
    from app.routes.approval import approval_bp
    from app.routes.client_experience import client_exp_bp
    from app.routes.intelligence import intelligence_bp
    from app.routes.webhooks import webhooks_bp
    
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
    app.register_blueprint(semrush_bp, url_prefix='/api/semrush')
    app.register_blueprint(monitoring_bp, url_prefix='/api/monitoring')
    app.register_blueprint(agency_bp, url_prefix='/api/agency')
    app.register_blueprint(scheduler_bp, url_prefix='/api/scheduler')
    app.register_blueprint(leads_bp, url_prefix='/api/leads')
    app.register_blueprint(pages_bp, url_prefix='/api/pages')
    app.register_blueprint(gbp_bp, url_prefix='/api/gbp')
    app.register_blueprint(reviews_bp, url_prefix='/api/reviews')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(agents_bp, url_prefix='/api/agents')
    app.register_blueprint(chatbot_bp, url_prefix='/api/chatbot')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(oauth_bp, url_prefix='/api/oauth')
    app.register_blueprint(images_bp, url_prefix='/api/images')
    app.register_blueprint(approval_bp, url_prefix='/api/approval')
    app.register_blueprint(client_exp_bp, url_prefix='/api/client')
    app.register_blueprint(intelligence_bp, url_prefix='/api/intelligence')
    app.register_blueprint(webhooks_bp, url_prefix='/api/webhooks')
