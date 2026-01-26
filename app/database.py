"""
MCP Framework - Database Configuration
SQLAlchemy ORM setup for PostgreSQL
"""
from flask_sqlalchemy import SQLAlchemy
import logging
logger = logging.getLogger(__name__)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from datetime import datetime


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def run_migrations(app):
    """Run any pending database migrations"""
    with app.app_context():
        try:
            # Check if service_cities column exists in clients table
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'clients' AND column_name = 'service_cities'
            """))
            if not result.fetchone():
                logger.info("Adding service_cities column to clients table...")
                db.session.execute(text("""
                    ALTER TABLE clients 
                    ADD COLUMN service_cities TEXT DEFAULT '[]'
                """))
                db.session.commit()
                logger.info("✓ Added service_cities column")
            
            # Check if blog_url column exists
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'clients' AND column_name = 'blog_url'
            """))
            if not result.fetchone():
                logger.info("Adding blog_url column to clients table...")
                db.session.execute(text("""
                    ALTER TABLE clients 
                    ADD COLUMN blog_url VARCHAR(500)
                """))
                db.session.commit()
                logger.info("✓ Added blog_url column")
            
            # Check if contact_url column exists
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'clients' AND column_name = 'contact_url'
            """))
            if not result.fetchone():
                logger.info("Adding contact_url column to clients table...")
                db.session.execute(text("""
                    ALTER TABLE clients 
                    ADD COLUMN contact_url VARCHAR(500)
                """))
                db.session.commit()
                logger.info("✓ Added contact_url column")
            
            # Add blog_tasks table if not exists
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS blog_tasks (
                    task_id VARCHAR(100) PRIMARY KEY,
                    task_data TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.session.commit()
            
        except Exception as e:
            logger.warning(f"Migration check: {e}")
            try:
                db.session.rollback()
            except:
                pass


def init_db(app):
    """Initialize database with app"""
    db.init_app(app)
    
    with app.app_context():
        # Import models to register them
        from app.models import db_models  # noqa
        
        # Create all tables
        db.create_all()
        
        logger.info("✓ Database tables created")
    
    # Run migrations for new columns
    run_migrations(app)


def get_db():
    """Get database session"""
    return db.session
