"""
MCP Framework - Database Configuration
SQLAlchemy ORM setup for PostgreSQL
"""
from flask_sqlalchemy import SQLAlchemy
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
        
        # Create all tables
        db.create_all()
        
        print("✓ Database tables created")


def get_db():
    """Get database session"""
    return db.session
