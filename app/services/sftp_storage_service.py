"""
SFTP Storage Service
Handles file uploads to external SFTP server for persistent storage
"""

import os
import logging
import paramiko
from io import BytesIO
from typing import Optional, Tuple
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class SFTPStorageService:
    """Service for uploading and managing files on SFTP server"""
    
    def __init__(self):
        self.host = os.environ.get('SFTP_HOST')
        self.port = int(os.environ.get('SFTP_PORT', 22))
        self.username = os.environ.get('SFTP_USERNAME')
        self.password = os.environ.get('SFTP_PASSWORD')
        self.remote_path = os.environ.get('SFTP_REMOTE_PATH', '/public_html/uploads')
        self.base_url = os.environ.get('SFTP_BASE_URL')  # e.g., https://yourdomain.com/uploads
        
    def is_configured(self) -> bool:
        """Check if SFTP is properly configured"""
        return all([self.host, self.username, self.password, self.base_url])
    
    def _get_connection(self) -> Tuple[paramiko.SSHClient, paramiko.SFTPClient]:
        """Establish SFTP connection"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=30
            )
            sftp = ssh.open_sftp()
            return ssh, sftp
        except Exception as e:
            logger.error(f"SFTP connection failed: {e}")
            raise
    
    def _ensure_remote_directory(self, sftp: paramiko.SFTPClient, path: str):
        """Create remote directory if it doesn't exist"""
        dirs = path.split('/')
        current = ''
        for d in dirs:
            if not d:
                continue
            current += '/' + d
            try:
                sftp.stat(current)
            except FileNotFoundError:
                try:
                    sftp.mkdir(current)
                    logger.info(f"Created remote directory: {current}")
                except Exception as e:
                    logger.warning(f"Could not create directory {current}: {e}")
    
    def upload_file(self, file_data: bytes, filename: str, client_id: str, 
                    category: str = 'images') -> Optional[dict]:
        """
        Upload file to SFTP server
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            client_id: Client identifier for organizing files
            category: Subfolder category (images, featured, etc.)
            
        Returns:
            dict with file_url and file_path, or None on failure
        """
        if not self.is_configured():
            logger.warning("SFTP not configured, falling back to local storage")
            return None
        
        try:
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_hash = hashlib.md5(file_data[:1024]).hexdigest()[:8]
            ext = os.path.splitext(filename)[1].lower()
            safe_filename = f"{timestamp}_{file_hash}{ext}"
            
            # Build remote path
            remote_dir = f"{self.remote_path}/{client_id}/{category}"
            remote_file = f"{remote_dir}/{safe_filename}"
            
            # Upload file
            ssh, sftp = self._get_connection()
            try:
                self._ensure_remote_directory(sftp, remote_dir)
                
                # Upload using BytesIO
                file_obj = BytesIO(file_data)
                sftp.putfo(file_obj, remote_file)
                
                logger.info(f"Uploaded file to SFTP: {remote_file}")
                
                # Build public URL
                public_url = f"{self.base_url.rstrip('/')}/{client_id}/{category}/{safe_filename}"
                
                return {
                    'file_url': public_url,
                    'file_path': remote_file,
                    'filename': safe_filename,
                    'storage': 'sftp'
                }
            finally:
                sftp.close()
                ssh.close()
                
        except Exception as e:
            logger.error(f"SFTP upload failed: {e}")
            return None
    
    def upload_from_path(self, local_path: str, client_id: str, 
                         category: str = 'images') -> Optional[dict]:
        """Upload a local file to SFTP"""
        try:
            with open(local_path, 'rb') as f:
                file_data = f.read()
            filename = os.path.basename(local_path)
            return self.upload_file(file_data, filename, client_id, category)
        except Exception as e:
            logger.error(f"Failed to read local file for SFTP upload: {e}")
            return None
    
    def delete_file(self, remote_path: str) -> bool:
        """Delete a file from SFTP server"""
        if not self.is_configured():
            return False
        
        try:
            ssh, sftp = self._get_connection()
            try:
                sftp.remove(remote_path)
                logger.info(f"Deleted file from SFTP: {remote_path}")
                return True
            finally:
                sftp.close()
                ssh.close()
        except Exception as e:
            logger.error(f"SFTP delete failed: {e}")
            return False
    
    def list_files(self, client_id: str, category: str = 'images') -> list:
        """List files in a remote directory"""
        if not self.is_configured():
            return []
        
        try:
            ssh, sftp = self._get_connection()
            try:
                remote_dir = f"{self.remote_path}/{client_id}/{category}"
                files = []
                try:
                    for entry in sftp.listdir_attr(remote_dir):
                        if entry.filename.startswith('.'):
                            continue
                        files.append({
                            'filename': entry.filename,
                            'size': entry.st_size,
                            'modified': datetime.fromtimestamp(entry.st_mtime).isoformat(),
                            'url': f"{self.base_url.rstrip('/')}/{client_id}/{category}/{entry.filename}"
                        })
                except FileNotFoundError:
                    pass
                return files
            finally:
                sftp.close()
                ssh.close()
        except Exception as e:
            logger.error(f"SFTP list failed: {e}")
            return []
    
    def test_connection(self) -> dict:
        """Test SFTP connection and return status"""
        if not self.is_configured():
            return {
                'success': False,
                'error': 'SFTP not configured. Set SFTP_HOST, SFTP_USERNAME, SFTP_PASSWORD, and SFTP_BASE_URL environment variables.'
            }
        
        try:
            ssh, sftp = self._get_connection()
            try:
                # Try to list the remote path
                try:
                    sftp.listdir(self.remote_path)
                except FileNotFoundError:
                    # Try to create it
                    self._ensure_remote_directory(sftp, self.remote_path)
                
                return {
                    'success': True,
                    'host': self.host,
                    'remote_path': self.remote_path,
                    'base_url': self.base_url
                }
            finally:
                sftp.close()
                ssh.close()
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
_sftp_service = None

def get_sftp_service() -> SFTPStorageService:
    """Get or create SFTP service instance"""
    global _sftp_service
    if _sftp_service is None:
        _sftp_service = SFTPStorageService()
    return _sftp_service
