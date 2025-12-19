"""
MCP Framework - User Model
Handles user authentication and permissions for the dashboard
"""
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import secrets


class UserRole(Enum):
    ADMIN = "admin"           # Full access - Karma Marketing team
    MANAGER = "manager"       # Can manage clients, generate content
    CLIENT = "client"         # Can view their own dashboard only
    VIEWER = "viewer"         # Read-only access


@dataclass
class User:
    """User model for MCP dashboard authentication"""
    
    id: str
    email: str
    name: str
    role: UserRole = UserRole.VIEWER
    password_hash: str = ""
    api_key: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    # Permissions
    is_active: bool = True
    can_generate_content: bool = False
    can_publish: bool = False
    can_view_analytics: bool = True
    
    # Client association (for CLIENT role users)
    client_ids: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Generate API key if not provided"""
        if not self.api_key:
            self.api_key = self._generate_api_key()
        self._set_permissions_by_role()
    
    def _generate_api_key(self) -> str:
        """Generate a secure API key for the user"""
        return f"mcp_{secrets.token_urlsafe(32)}"
    
    def _set_permissions_by_role(self):
        """Set default permissions based on user role"""
        if self.role == UserRole.ADMIN:
            self.can_generate_content = True
            self.can_publish = True
            self.can_view_analytics = True
        elif self.role == UserRole.MANAGER:
            self.can_generate_content = True
            self.can_publish = True
            self.can_view_analytics = True
        elif self.role == UserRole.CLIENT:
            self.can_generate_content = False
            self.can_publish = False
            self.can_view_analytics = True
        else:  # VIEWER
            self.can_generate_content = False
            self.can_publish = False
            self.can_view_analytics = True
    
    def set_password(self, password: str) -> None:
        """Hash and store password"""
        salt = secrets.token_hex(16)
        self.password_hash = f"{salt}${self._hash_password(password, salt)}"
        self.updated_at = datetime.utcnow()
    
    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash"""
        if not self.password_hash or '$' not in self.password_hash:
            return False
        salt, stored_hash = self.password_hash.split('$', 1)
        return self._hash_password(password, salt) == stored_hash
    
    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Create password hash with salt"""
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert user to dictionary"""
        data = {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role.value,
            "is_active": self.is_active,
            "can_generate_content": self.can_generate_content,
            "can_publish": self.can_publish,
            "can_view_analytics": self.can_view_analytics,
            "client_ids": self.client_ids,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
            data["api_key"] = self.api_key
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Create User from dictionary"""
        # Parse dates
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        last_login = data.get('last_login')
        if isinstance(last_login, str):
            last_login = datetime.fromisoformat(last_login.replace('Z', '+00:00'))
        
        user = cls(
            id=data.get('id', ''),
            email=data.get('email', ''),
            name=data.get('name', ''),
            role=UserRole(data.get('role', 'viewer')),
            password_hash=data.get('password_hash', ''),
            api_key=data.get('api_key', ''),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow(),
            last_login=last_login,
            is_active=data.get('is_active', True),
            can_generate_content=data.get('can_generate_content', False),
            can_publish=data.get('can_publish', False),
            can_view_analytics=data.get('can_view_analytics', True),
            client_ids=data.get('client_ids', [])
        )
        return user
    
    def update_login(self) -> None:
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
    
    def add_client(self, client_id: str) -> None:
        """Associate user with a client"""
        if client_id not in self.client_ids:
            self.client_ids.append(client_id)
            self.updated_at = datetime.utcnow()
    
    def remove_client(self, client_id: str) -> None:
        """Remove client association"""
        if client_id in self.client_ids:
            self.client_ids.remove(client_id)
            self.updated_at = datetime.utcnow()
    
    def has_access_to_client(self, client_id: str) -> bool:
        """Check if user can access a specific client's data"""
        if self.role in [UserRole.ADMIN, UserRole.MANAGER]:
            return True
        return client_id in self.client_ids


# Factory functions for creating users
def create_admin_user(email: str, name: str, password: str) -> User:
    """Create an admin user"""
    user = User(
        id=secrets.token_urlsafe(16),
        email=email,
        name=name,
        role=UserRole.ADMIN
    )
    user.set_password(password)
    return user


def create_client_user(email: str, name: str, password: str, client_ids: List[str]) -> User:
    """Create a client portal user"""
    user = User(
        id=secrets.token_urlsafe(16),
        email=email,
        name=name,
        role=UserRole.CLIENT,
        client_ids=client_ids
    )
    user.set_password(password)
    return user
