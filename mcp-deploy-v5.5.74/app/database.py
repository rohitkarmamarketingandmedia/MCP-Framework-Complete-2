"""
MCP Framework - Database Configuration
SQLAlchemy ORM setup for PostgreSQL
"""
from flask_sqlalchemy import SQLAlchemy
import logging
logger = logging.getLogger(__name__)
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def init_db(app):
    """Initialize database with app"""
    db.init_app(app)
    
    with app.app_context():
        # Import models to register them
        from app.models import db_models  # noqa
        from app.models.db_models import DBUser, UserRole
        
        # Create all tables
        db.create_all()
        
        logger.info("✓ Database tables created")
        
        # Auto-create admin user if none exists
        try:
            admin_exists = DBUser.query.filter_by(role=UserRole.ADMIN).first()
            if not admin_exists:
                import os
                admin_email = os.environ.get('ADMIN_EMAIL', 'admin@karma.local')
                admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
                admin_name = os.environ.get('ADMIN_NAME', 'Admin')
                
                admin = DBUser(
                    email=admin_email,
                    name=admin_name,
                    password=admin_password,
                    role=UserRole.ADMIN
                )
                db.session.add(admin)
                db.session.commit()
                logger.info(f"✓ Created default admin user: {admin_email}")
        except Exception as e:
            logger.warning(f"Could not check/create admin user: {e}")


def get_db():
    """Get database session"""
    return db.session
