"""
Karma Marketing + Media - Audit Logging Service
Track all system actions for compliance and debugging
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from flask import request, has_request_context

from app.database import db
from app.models.db_models import DBAuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Service for logging and querying audit events"""
    
    # Action types
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_VIEW = 'view'
    ACTION_EXPORT = 'export'
    ACTION_GENERATE = 'generate'
    ACTION_PUBLISH = 'publish'
    ACTION_APPROVE = 'approve'
    ACTION_REJECT = 'reject'
    
    # Resource types
    RESOURCE_USER = 'user'
    RESOURCE_CLIENT = 'client'
    RESOURCE_LEAD = 'lead'
    RESOURCE_CONTENT = 'content'
    RESOURCE_BLOG = 'blog'
    RESOURCE_SOCIAL = 'social'
    RESOURCE_CAMPAIGN = 'campaign'
    RESOURCE_COMPETITOR = 'competitor'
    RESOURCE_REVIEW = 'review'
    RESOURCE_SETTING = 'setting'
    RESOURCE_WEBHOOK = 'webhook'
    RESOURCE_PAGE = 'page'
    
    def log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        client_id: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        metadata: Optional[Dict] = None,
        status: str = 'success',
        error_message: Optional[str] = None
    ) -> DBAuditLog:
        """
        Log an audit event
        
        Args:
            action: The action performed (create, update, delete, etc.)
            resource_type: Type of resource affected (user, client, lead, etc.)
            resource_id: ID of the affected resource
            resource_name: Human-readable name of the resource
            description: Description of what happened
            user_id: ID of user who performed action
            user_email: Email of user who performed action
            client_id: Related client ID if applicable
            old_value: Previous state (will be JSON serialized)
            new_value: New state (will be JSON serialized)
            metadata: Additional metadata (will be JSON serialized)
            status: success, failure, or error
            error_message: Error message if status is not success
            
        Returns:
            The created audit log entry
        """
        try:
            # Extract request context if available
            ip_address = None
            user_agent = None
            endpoint = None
            http_method = None
            
            if has_request_context():
                ip_address = request.remote_addr
                user_agent = request.headers.get('User-Agent', '')[:500]
                endpoint = request.path
                http_method = request.method
            
            # Serialize complex values
            old_value_json = None
            new_value_json = None
            metadata_json = None
            
            if old_value is not None:
                try:
                    old_value_json = json.dumps(old_value, default=str)
                except:
                    old_value_json = str(old_value)
            
            if new_value is not None:
                try:
                    new_value_json = json.dumps(new_value, default=str)
                except:
                    new_value_json = str(new_value)
            
            if metadata is not None:
                try:
                    metadata_json = json.dumps(metadata, default=str)
                except:
                    metadata_json = str(metadata)
            
            # Create log entry
            log_entry = DBAuditLog(
                user_id=user_id,
                user_email=user_email,
                ip_address=ip_address,
                user_agent=user_agent,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                description=description,
                old_value=old_value_json,
                new_value=new_value_json,
                extra_data=metadata_json,
                client_id=client_id,
                endpoint=endpoint,
                http_method=http_method,
                status=status,
                error_message=error_message,
                created_at=datetime.utcnow()
            )
            
            db.session.add(log_entry)
            db.session.commit()
            
            logger.debug(f"Audit: {action} {resource_type} {resource_id} by {user_email}")
            
            return log_entry
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            db.session.rollback()
            return None
    
    def log_login(self, user_id: str, user_email: str, success: bool = True, error: str = None):
        """Log a login attempt"""
        return self.log(
            action=self.ACTION_LOGIN,
            resource_type=self.RESOURCE_USER,
            resource_id=user_id,
            resource_name=user_email,
            user_id=user_id,
            user_email=user_email,
            description=f"User {'logged in successfully' if success else 'failed to log in'}",
            status='success' if success else 'failure',
            error_message=error
        )
    
    def log_logout(self, user_id: str, user_email: str):
        """Log a logout"""
        return self.log(
            action=self.ACTION_LOGOUT,
            resource_type=self.RESOURCE_USER,
            resource_id=user_id,
            resource_name=user_email,
            user_id=user_id,
            user_email=user_email,
            description="User logged out"
        )
    
    def log_create(
        self, 
        resource_type: str, 
        resource_id: str, 
        resource_name: str,
        user_id: str = None,
        user_email: str = None,
        client_id: str = None,
        new_value: Any = None
    ):
        """Log a resource creation"""
        return self.log(
            action=self.ACTION_CREATE,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            user_id=user_id,
            user_email=user_email,
            client_id=client_id,
            new_value=new_value,
            description=f"Created {resource_type}: {resource_name}"
        )
    
    def log_update(
        self,
        resource_type: str,
        resource_id: str,
        resource_name: str,
        user_id: str = None,
        user_email: str = None,
        client_id: str = None,
        old_value: Any = None,
        new_value: Any = None,
        changes: str = None
    ):
        """Log a resource update"""
        return self.log(
            action=self.ACTION_UPDATE,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            user_id=user_id,
            user_email=user_email,
            client_id=client_id,
            old_value=old_value,
            new_value=new_value,
            description=changes or f"Updated {resource_type}: {resource_name}"
        )
    
    def log_delete(
        self,
        resource_type: str,
        resource_id: str,
        resource_name: str,
        user_id: str = None,
        user_email: str = None,
        client_id: str = None,
        old_value: Any = None
    ):
        """Log a resource deletion"""
        return self.log(
            action=self.ACTION_DELETE,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            user_id=user_id,
            user_email=user_email,
            client_id=client_id,
            old_value=old_value,
            description=f"Deleted {resource_type}: {resource_name}"
        )
    
    def log_content_generated(
        self,
        content_type: str,
        content_id: str,
        content_title: str,
        client_id: str,
        user_id: str = None,
        user_email: str = None,
        keyword: str = None
    ):
        """Log content generation"""
        return self.log(
            action=self.ACTION_GENERATE,
            resource_type=content_type,
            resource_id=content_id,
            resource_name=content_title,
            user_id=user_id,
            user_email=user_email,
            client_id=client_id,
            metadata={'keyword': keyword},
            description=f"Generated {content_type}: {content_title}"
        )
    
    def get_logs(
        self,
        action: str = None,
        resource_type: str = None,
        resource_id: str = None,
        user_id: str = None,
        client_id: str = None,
        status: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DBAuditLog]:
        """
        Query audit logs with filters
        
        Returns list of audit log entries
        """
        query = DBAuditLog.query
        
        if action:
            query = query.filter(DBAuditLog.action == action)
        if resource_type:
            query = query.filter(DBAuditLog.resource_type == resource_type)
        if resource_id:
            query = query.filter(DBAuditLog.resource_id == resource_id)
        if user_id:
            query = query.filter(DBAuditLog.user_id == user_id)
        if client_id:
            query = query.filter(DBAuditLog.client_id == client_id)
        if status:
            query = query.filter(DBAuditLog.status == status)
        if start_date:
            query = query.filter(DBAuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(DBAuditLog.created_at <= end_date)
        
        return query.order_by(DBAuditLog.created_at.desc()).offset(offset).limit(limit).all()
    
    def get_user_activity(self, user_id: str, days: int = 30, limit: int = 100) -> List[DBAuditLog]:
        """Get recent activity for a specific user"""
        start_date = datetime.utcnow() - timedelta(days=days)
        return self.get_logs(user_id=user_id, start_date=start_date, limit=limit)
    
    def get_client_activity(self, client_id: str, days: int = 30, limit: int = 100) -> List[DBAuditLog]:
        """Get recent activity for a specific client"""
        start_date = datetime.utcnow() - timedelta(days=days)
        return self.get_logs(client_id=client_id, start_date=start_date, limit=limit)
    
    def get_resource_history(self, resource_type: str, resource_id: str, limit: int = 50) -> List[DBAuditLog]:
        """Get history of changes to a specific resource"""
        return self.get_logs(resource_type=resource_type, resource_id=resource_id, limit=limit)
    
    def get_stats(self, days: int = 30) -> Dict:
        """Get audit statistics"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Count by action
        action_counts = db.session.query(
            DBAuditLog.action,
            db.func.count(DBAuditLog.id)
        ).filter(
            DBAuditLog.created_at >= start_date
        ).group_by(DBAuditLog.action).all()
        
        # Count by resource type
        resource_counts = db.session.query(
            DBAuditLog.resource_type,
            db.func.count(DBAuditLog.id)
        ).filter(
            DBAuditLog.created_at >= start_date
        ).group_by(DBAuditLog.resource_type).all()
        
        # Recent failures
        failures = DBAuditLog.query.filter(
            DBAuditLog.status != 'success',
            DBAuditLog.created_at >= start_date
        ).count()
        
        # Active users
        active_users = db.session.query(
            db.func.count(db.func.distinct(DBAuditLog.user_id))
        ).filter(
            DBAuditLog.created_at >= start_date,
            DBAuditLog.user_id.isnot(None)
        ).scalar()
        
        return {
            'period_days': days,
            'total_events': sum(c[1] for c in action_counts),
            'by_action': {a: c for a, c in action_counts},
            'by_resource': {r: c for r, c in resource_counts},
            'failures': failures,
            'active_users': active_users
        }
    
    def cleanup_old_logs(self, days: int = 90) -> int:
        """Delete audit logs older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = DBAuditLog.query.filter(DBAuditLog.created_at < cutoff).delete()
        db.session.commit()
        logger.info(f"Cleaned up {deleted} audit logs older than {days} days")
        return deleted


# Singleton instance
audit_service = AuditService()
