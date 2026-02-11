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
            
            # Check if target_city column exists in blog_posts
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'blog_posts' AND column_name = 'target_city'
            """))
            if not result.fetchone():
                logger.info("Adding target_city column to blog_posts table...")
                db.session.execute(text("""
                    ALTER TABLE blog_posts 
                    ADD COLUMN target_city VARCHAR(100)
                """))
                db.session.commit()
                logger.info("✓ Added target_city column")
            
            # Check if tags column exists in blog_posts
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'blog_posts' AND column_name = 'tags'
            """))
            if not result.fetchone():
                logger.info("Adding missing columns to blog_posts table...")
                db.session.execute(text("ALTER TABLE blog_posts ADD COLUMN tags TEXT DEFAULT '[]'"))
                db.session.commit()
                logger.info("✓ Added tags column")
            
            # Check if revision_notes column exists in blog_posts
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'blog_posts' AND column_name = 'revision_notes'
            """))
            if not result.fetchone():
                logger.info("Adding revision_notes column to blog_posts table...")
                db.session.execute(text("ALTER TABLE blog_posts ADD COLUMN revision_notes TEXT"))
                db.session.commit()
                logger.info("✓ Added revision_notes column")
            
            # Check if approved_at column exists in blog_posts
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'blog_posts' AND column_name = 'approved_at'
            """))
            if not result.fetchone():
                logger.info("Adding approval columns to blog_posts table...")
                db.session.execute(text("ALTER TABLE blog_posts ADD COLUMN approved_at TIMESTAMP"))
                db.session.execute(text("ALTER TABLE blog_posts ADD COLUMN approved_by VARCHAR(50)"))
                db.session.commit()
                logger.info("✓ Added approval columns")
            
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
            
            # Widen meta_title and meta_description columns in blog_posts
            # (PostgreSQL will reject inserts if AI-generated titles exceed old limits)
            try:
                result = db.session.execute(text("""
                    SELECT character_maximum_length FROM information_schema.columns 
                    WHERE table_name = 'blog_posts' AND column_name = 'meta_title'
                """))
                row = result.fetchone()
                if row and row[0] and row[0] < 500:
                    logger.info("Widening meta_title/meta_description columns in blog_posts...")
                    db.session.execute(text("ALTER TABLE blog_posts ALTER COLUMN meta_title TYPE VARCHAR(500)"))
                    db.session.execute(text("ALTER TABLE blog_posts ALTER COLUMN meta_description TYPE VARCHAR(500)"))
                    db.session.commit()
                    logger.info("✓ Widened blog_posts meta columns to 500")
            except Exception as e:
                logger.debug(f"blog_posts meta column check: {e}")
                try:
                    db.session.rollback()
                except:
                    pass
            
            # Same for content_queue table
            try:
                result = db.session.execute(text("""
                    SELECT character_maximum_length FROM information_schema.columns 
                    WHERE table_name = 'content_queue' AND column_name = 'meta_title'
                """))
                row = result.fetchone()
                if row and row[0] and row[0] < 500:
                    logger.info("Widening meta_title/meta_description columns in content_queue...")
                    db.session.execute(text("ALTER TABLE content_queue ALTER COLUMN meta_title TYPE VARCHAR(500)"))
                    db.session.execute(text("ALTER TABLE content_queue ALTER COLUMN meta_description TYPE VARCHAR(500)"))
                    db.session.commit()
                    logger.info("✓ Widened content_queue meta columns to 500")
            except Exception as e:
                logger.debug(f"content_queue meta column check: {e}")
                try:
                    db.session.rollback()
                except:
                    pass
            
            # Same for service_pages table
            try:
                result = db.session.execute(text("""
                    SELECT character_maximum_length FROM information_schema.columns 
                    WHERE table_name = 'service_pages' AND column_name = 'meta_title'
                """))
                row = result.fetchone()
                if row and row[0] and row[0] < 500:
                    logger.info("Widening meta_title/meta_description columns in service_pages...")
                    db.session.execute(text("ALTER TABLE service_pages ALTER COLUMN meta_title TYPE VARCHAR(500)"))
                    db.session.execute(text("ALTER TABLE service_pages ALTER COLUMN meta_description TYPE VARCHAR(500)"))
                    db.session.commit()
                    logger.info("✓ Widened service_pages meta columns to 500")
            except Exception as e:
                logger.debug(f"service_pages meta column check: {e}")
                try:
                    db.session.rollback()
                except:
                    pass
            
            # Check if share_token column exists in chat_conversations
            try:
                result = db.session.execute(text("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'chat_conversations' AND column_name = 'share_token'
                """))
                if not result.fetchone():
                    logger.info("Adding share_token column to chat_conversations table...")
                    db.session.execute(text("ALTER TABLE chat_conversations ADD COLUMN share_token VARCHAR(64)"))
                    db.session.commit()
                    logger.info("✓ Added share_token column")
                    
                    # Backfill existing conversations with share tokens
                    import uuid as _uuid
                    existing = db.session.execute(text(
                        "SELECT id FROM chat_conversations WHERE share_token IS NULL"
                    )).fetchall()
                    for row in existing:
                        token = _uuid.uuid4().hex + _uuid.uuid4().hex[:8]
                        db.session.execute(text(
                            "UPDATE chat_conversations SET share_token = :token WHERE id = :cid"
                        ), {"token": token, "cid": row[0]})
                    db.session.commit()
                    logger.info(f"✓ Backfilled {len(existing)} conversations with share tokens")
            except Exception as e:
                logger.debug(f"share_token migration: {e}")
                try:
                    db.session.rollback()
                except:
                    pass
            
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
