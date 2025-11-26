"""
MCP Framework - Data Service
Data persistence layer - JSON file storage or database
"""
import os
import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path


class DataService:
    """
    Data persistence service
    
    Uses JSON files for simple deployments, can be extended for database
    """
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or os.environ.get('DATA_DIR', './data'))
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create data directories if they don't exist"""
        directories = ['users', 'clients', 'content', 'social', 'schemas', 'campaigns']
        for dir_name in directories:
            (self.data_dir / dir_name).mkdir(parents=True, exist_ok=True)
    
    def _generate_id(self, prefix: str = '') -> str:
        """Generate unique ID"""
        uid = uuid.uuid4().hex[:12]
        return f'{prefix}_{uid}' if prefix else uid
    
    def _load_json(self, filepath: Path) -> Optional[Dict]:
        """Load JSON file"""
        try:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    
    def _save_json(self, filepath: Path, data: Dict):
        """Save JSON file"""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    # ==================== USER METHODS ====================
    
    def get_user(self, user_id: str):
        """Get user by ID"""
        from app.models.user import User
        
        filepath = self.data_dir / 'users' / f'{user_id}.json'
        data = self._load_json(filepath)
        
        if data:
            return User.from_dict(data)
        return None
    
    def get_user_by_email(self, email: str):
        """Get user by email"""
        from app.models.user import User
        
        users_dir = self.data_dir / 'users'
        for filepath in users_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('email', '').lower() == email.lower():
                return User.from_dict(data)
        return None
    
    def get_user_by_api_key(self, api_key: str):
        """Get user by API key"""
        from app.models.user import User
        
        users_dir = self.data_dir / 'users'
        for filepath in users_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('api_key') == api_key:
                return User.from_dict(data)
        return None
    
    def save_user(self, user):
        """Save user"""
        if not user.id:
            user.id = self._generate_id('user')
        
        filepath = self.data_dir / 'users' / f'{user.id}.json'
        self._save_json(filepath, user.to_dict())
        return user
    
    def get_all_users(self) -> List:
        """Get all users"""
        from app.models.user import User
        
        users = []
        users_dir = self.data_dir / 'users'
        for filepath in users_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data:
                users.append(User.from_dict(data))
        return users
    
    def delete_user(self, user_id: str) -> bool:
        """Delete user file"""
        filepath = self.data_dir / 'users' / f'{user_id}.json'
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    # ==================== CLIENT METHODS ====================
    
    def get_client(self, client_id: str):
        """Get client by ID"""
        from app.models.client import Client
        
        filepath = self.data_dir / 'clients' / f'{client_id}.json'
        data = self._load_json(filepath)
        
        if data:
            return Client.from_dict(data)
        return None
    
    def save_client(self, client):
        """Save client"""
        if not client.id:
            client.id = self._generate_id('client')
        
        filepath = self.data_dir / 'clients' / f'{client.id}.json'
        self._save_json(filepath, client.to_dict())
        return client
    
    def get_all_clients(self) -> List:
        """Get all clients"""
        from app.models.client import Client
        
        clients = []
        clients_dir = self.data_dir / 'clients'
        for filepath in clients_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('is_active', True):
                clients.append(Client.from_dict(data))
        return clients
    
    def delete_client(self, client_id: str) -> bool:
        """Delete client file"""
        filepath = self.data_dir / 'clients' / f'{client_id}.json'
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    # ==================== CONTENT METHODS ====================
    
    def get_content(self, content_id: str):
        """Get content by ID"""
        from app.models.content import BlogPost
        
        filepath = self.data_dir / 'content' / f'{content_id}.json'
        data = self._load_json(filepath)
        
        if data:
            return BlogPost.from_dict(data)
        return None
    
    def save_content(self, content):
        """Save content"""
        if not content.id:
            content.id = self._generate_id('content')
        
        filepath = self.data_dir / 'content' / f'{content.id}.json'
        self._save_json(filepath, content.to_dict())
        return content
    
    def get_content_by_client(
        self,
        client_id: str,
        status: str = None,
        content_type: str = None
    ) -> List:
        """Get all content for a client"""
        from app.models.content import BlogPost
        
        content_list = []
        content_dir = self.data_dir / 'content'
        
        for filepath in content_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('client_id') == client_id:
                if status and data.get('status') != status:
                    continue
                if content_type and data.get('content_type') != content_type:
                    continue
                content_list.append(BlogPost.from_dict(data))
        
        # Sort by created_at desc
        content_list.sort(key=lambda x: x.created_at, reverse=True)
        return content_list
    
    def delete_content(self, content_id: str) -> bool:
        """Delete content file"""
        filepath = self.data_dir / 'content' / f'{content_id}.json'
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    # ==================== SOCIAL POST METHODS ====================
    
    def get_social_post(self, post_id: str):
        """Get social post by ID"""
        from app.models.content import SocialPost
        
        filepath = self.data_dir / 'social' / f'{post_id}.json'
        data = self._load_json(filepath)
        
        if data:
            return SocialPost.from_dict(data)
        return None
    
    def save_social_post(self, post):
        """Save social post"""
        if not post.id:
            post.id = self._generate_id('social')
        
        filepath = self.data_dir / 'social' / f'{post.id}.json'
        self._save_json(filepath, post.to_dict())
        return post
    
    def get_social_posts_by_client(
        self,
        client_id: str,
        platform: str = None,
        status: str = None
    ) -> List:
        """Get all social posts for a client"""
        from app.models.content import SocialPost
        
        posts = []
        social_dir = self.data_dir / 'social'
        
        for filepath in social_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('client_id') == client_id:
                if platform and data.get('platform') != platform:
                    continue
                if status and data.get('status') != status:
                    continue
                posts.append(SocialPost.from_dict(data))
        
        posts.sort(key=lambda x: x.created_at, reverse=True)
        return posts
    
    def delete_social_post(self, post_id: str) -> bool:
        """Delete social post file"""
        filepath = self.data_dir / 'social' / f'{post_id}.json'
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    # ==================== SCHEMA METHODS ====================
    
    def get_schema(self, schema_id: str):
        """Get schema by ID"""
        from app.models.content import SchemaMarkup
        
        filepath = self.data_dir / 'schemas' / f'{schema_id}.json'
        data = self._load_json(filepath)
        
        if data:
            return SchemaMarkup.from_dict(data)
        return None
    
    def save_schema(self, schema):
        """Save schema"""
        if not schema.id:
            schema.id = self._generate_id('schema')
        
        filepath = self.data_dir / 'schemas' / f'{schema.id}.json'
        self._save_json(filepath, schema.to_dict())
        return schema
    
    def get_schemas_by_client(self, client_id: str) -> List:
        """Get all schemas for a client"""
        from app.models.content import SchemaMarkup
        
        schemas = []
        schemas_dir = self.data_dir / 'schemas'
        
        for filepath in schemas_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('client_id') == client_id:
                schemas.append(SchemaMarkup.from_dict(data))
        
        return schemas
    
    # ==================== CAMPAIGN METHODS ====================
    
    def get_campaign(self, campaign_id: str):
        """Get campaign by ID"""
        from app.models.campaign import Campaign
        
        filepath = self.data_dir / 'campaigns' / f'{campaign_id}.json'
        data = self._load_json(filepath)
        
        if data:
            return Campaign.from_dict(data)
        return None
    
    def save_campaign(self, campaign):
        """Save campaign"""
        if not campaign.id:
            campaign.id = self._generate_id('campaign')
        
        filepath = self.data_dir / 'campaigns' / f'{campaign.id}.json'
        self._save_json(filepath, campaign.to_dict())
        return campaign
    
    def get_campaigns_by_client(self, client_id: str) -> List:
        """Get all campaigns for a client"""
        from app.models.campaign import Campaign
        
        campaigns = []
        campaigns_dir = self.data_dir / 'campaigns'
        
        for filepath in campaigns_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data and data.get('client_id') == client_id:
                campaigns.append(Campaign.from_dict(data))
        
        campaigns.sort(key=lambda x: x.created_at, reverse=True)
        return campaigns
    
    def get_all_campaigns(self) -> List:
        """Get all campaigns"""
        from app.models.campaign import Campaign
        
        campaigns = []
        campaigns_dir = self.data_dir / 'campaigns'
        
        for filepath in campaigns_dir.glob('*.json'):
            data = self._load_json(filepath)
            if data:
                campaigns.append(Campaign.from_dict(data))
        
        campaigns.sort(key=lambda x: x.created_at, reverse=True)
        return campaigns
    
    def delete_campaign(self, campaign_id: str) -> bool:
        """Delete campaign file"""
        filepath = self.data_dir / 'campaigns' / f'{campaign_id}.json'
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    # ==================== UTILITY METHODS ====================
    
    def backup_all(self, backup_path: str = None) -> str:
        """Create backup of all data"""
        import shutil
        
        backup_path = backup_path or f'./backups/backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}'
        shutil.copytree(self.data_dir, backup_path)
        return backup_path
    
    def get_stats(self) -> Dict[str, int]:
        """Get data statistics"""
        return {
            'users': len(list((self.data_dir / 'users').glob('*.json'))),
            'clients': len(list((self.data_dir / 'clients').glob('*.json'))),
            'content': len(list((self.data_dir / 'content').glob('*.json'))),
            'social_posts': len(list((self.data_dir / 'social').glob('*.json'))),
            'schemas': len(list((self.data_dir / 'schemas').glob('*.json'))),
            'campaigns': len(list((self.data_dir / 'campaigns').glob('*.json')))
        }
