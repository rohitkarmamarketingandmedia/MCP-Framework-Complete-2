"""
FTP/SFTP Storage Service
Handles file uploads to external FTP or SFTP server for persistent storage
Supports both regular FTP and SFTP (SSH-based)
"""

import os
import logging
import ftplib
from io import BytesIO
from typing import Optional
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

# Try to import paramiko for SFTP support
try:
    import paramiko
    SFTP_AVAILABLE = True
except ImportError:
    SFTP_AVAILABLE = False
    logger.info("Paramiko not installed, SFTP not available")


class FTPStorageService:
    """Service for uploading and managing files on FTP/SFTP server"""
    
    def __init__(self):
        # Support both FTP_ and SFTP_ prefixed env vars for backwards compatibility
        self.host = os.environ.get('FTP_HOST') or os.environ.get('SFTP_HOST')
        self.port = int(os.environ.get('FTP_PORT') or os.environ.get('SFTP_PORT') or 21)
        self.username = os.environ.get('FTP_USERNAME') or os.environ.get('SFTP_USERNAME')
        self.password = os.environ.get('FTP_PASSWORD') or os.environ.get('SFTP_PASSWORD')
        self.remote_path = os.environ.get('FTP_REMOTE_PATH') or os.environ.get('SFTP_REMOTE_PATH') or '/public_html/uploads'
        self.base_url = os.environ.get('FTP_BASE_URL') or os.environ.get('SFTP_BASE_URL')
        
        # Protocol: 'ftp', 'ftps', or 'sftp'
        self.protocol = (os.environ.get('FTP_PROTOCOL') or 'ftp').lower()
        
        # Use TLS for FTPS
        self.use_tls = os.environ.get('FTP_USE_TLS', 'false').lower() == 'true' or self.protocol == 'ftps'
        
    def is_configured(self) -> bool:
        """Check if FTP is properly configured"""
        return all([self.host, self.username, self.password, self.base_url])
    
    def _get_ftp_connection(self) -> ftplib.FTP:
        """Establish FTP connection"""
        try:
            if self.use_tls:
                ftp = ftplib.FTP_TLS()
                ftp.connect(self.host, self.port, timeout=30)
                ftp.login(self.username, self.password)
                ftp.prot_p()  # Enable data encryption
                logger.info(f"Connected to FTPS server: {self.host}")
            else:
                ftp = ftplib.FTP()
                ftp.connect(self.host, self.port, timeout=30)
                ftp.login(self.username, self.password)
                logger.info(f"Connected to FTP server: {self.host}")
            
            # Set binary mode
            ftp.voidcmd('TYPE I')
            return ftp
        except Exception as e:
            logger.error(f"FTP connection failed: {e}")
            raise
    
    def _get_sftp_connection(self):
        """Establish SFTP connection"""
        if not SFTP_AVAILABLE:
            raise Exception("SFTP not available - paramiko not installed")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            ssh.connect(
                hostname=self.host,
                port=self.port if self.port != 21 else 22,
                username=self.username,
                password=self.password,
                timeout=30
            )
            sftp = ssh.open_sftp()
            logger.info(f"Connected to SFTP server: {self.host}")
            return ssh, sftp
        except Exception as e:
            logger.error(f"SFTP connection failed: {e}")
            raise
    
    def _ensure_ftp_directory(self, ftp: ftplib.FTP, path: str):
        """Create FTP directory if it doesn't exist"""
        dirs = path.split('/')
        current = ''
        for d in dirs:
            if not d:
                continue
            current += '/' + d
            try:
                ftp.cwd(current)
            except ftplib.error_perm:
                try:
                    ftp.mkd(current)
                    logger.info(f"Created FTP directory: {current}")
                except ftplib.error_perm as e:
                    logger.warning(f"Could not create directory {current}: {e}")
        # Return to root
        ftp.cwd('/')
    
    def _ensure_sftp_directory(self, sftp, path: str):
        """Create SFTP directory if it doesn't exist"""
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
                    logger.info(f"Created SFTP directory: {current}")
                except Exception as e:
                    logger.warning(f"Could not create directory {current}: {e}")
    
    def upload_file(self, file_data: bytes, filename: str, client_id: str, 
                    category: str = 'images') -> Optional[dict]:
        """
        Upload file to FTP/SFTP server
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            client_id: Client identifier for organizing files
            category: Subfolder category (images, featured, etc.)
            
        Returns:
            dict with file_url and file_path, or None on failure
        """
        logger.info(f"FTP upload_file called: filename={filename}, client_id={client_id}, category={category}, data_size={len(file_data)} bytes")
        
        if not self.is_configured():
            logger.warning(f"FTP not configured. host={self.host}, username={self.username}, base_url={self.base_url}")
            return None
        
        logger.info(f"FTP is configured: host={self.host}, protocol={self.protocol}, remote_path={self.remote_path}")
        
        try:
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_hash = hashlib.md5(file_data[:1024]).hexdigest()[:8]
            ext = os.path.splitext(filename)[1].lower()
            safe_filename = f"{timestamp}_{file_hash}{ext}"
            
            # Build remote path
            remote_dir = f"{self.remote_path}/{client_id}/{category}"
            remote_file = f"{remote_dir}/{safe_filename}"
            
            logger.info(f"FTP upload target: remote_dir={remote_dir}, remote_file={remote_file}")
            
            if self.protocol == 'sftp':
                result = self._upload_sftp(file_data, remote_dir, remote_file, safe_filename, client_id, category)
            else:
                result = self._upload_ftp(file_data, remote_dir, remote_file, safe_filename, client_id, category)
            
            if result:
                logger.info(f"FTP upload SUCCESS: {result}")
            else:
                logger.error(f"FTP upload returned None")
            
            return result
                
        except Exception as e:
            logger.error(f"FTP upload failed with exception: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"FTP upload traceback: {traceback.format_exc()}")
            return None
    
    def _upload_ftp(self, file_data: bytes, remote_dir: str, remote_file: str, 
                    safe_filename: str, client_id: str, category: str) -> Optional[dict]:
        """Upload via FTP"""
        logger.info(f"_upload_ftp: Connecting to FTP server...")
        ftp = self._get_ftp_connection()
        try:
            logger.info(f"_upload_ftp: Creating directory {remote_dir}")
            self._ensure_ftp_directory(ftp, remote_dir)
            
            # Upload using BytesIO
            logger.info(f"_upload_ftp: Uploading {len(file_data)} bytes to {remote_file}")
            file_obj = BytesIO(file_data)
            ftp.storbinary(f'STOR {remote_file}', file_obj)
            
            logger.info(f"_upload_ftp: File uploaded successfully to FTP: {remote_file}")
            
            # Build public URL
            public_url = f"{self.base_url.rstrip('/')}/{client_id}/{category}/{safe_filename}"
            logger.info(f"_upload_ftp: Public URL will be: {public_url}")
            
            return {
                'file_url': public_url,
                'file_path': remote_file,
                'filename': safe_filename,
                'storage': 'ftp'
            }
        except Exception as e:
            logger.error(f"_upload_ftp: Upload error: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"_upload_ftp traceback: {traceback.format_exc()}")
            raise
        finally:
            try:
                ftp.quit()
            except:
                pass
    
    def _upload_sftp(self, file_data: bytes, remote_dir: str, remote_file: str,
                     safe_filename: str, client_id: str, category: str) -> Optional[dict]:
        """Upload via SFTP"""
        logger.info(f"_upload_sftp: Connecting to SFTP server...")
        ssh, sftp = self._get_sftp_connection()
        try:
            logger.info(f"_upload_sftp: Creating directory {remote_dir}")
            self._ensure_sftp_directory(sftp, remote_dir)
            
            # Upload using BytesIO
            logger.info(f"_upload_sftp: Uploading {len(file_data)} bytes to {remote_file}")
            file_obj = BytesIO(file_data)
            sftp.putfo(file_obj, remote_file)
            
            logger.info(f"_upload_sftp: File uploaded successfully to SFTP: {remote_file}")
            
            # Build public URL
            public_url = f"{self.base_url.rstrip('/')}/{client_id}/{category}/{safe_filename}"
            logger.info(f"_upload_sftp: Public URL will be: {public_url}")
            
            return {
                'file_url': public_url,
                'file_path': remote_file,
                'filename': safe_filename,
                'storage': 'sftp'
            }
        except Exception as e:
            logger.error(f"_upload_sftp: Upload error: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"_upload_sftp traceback: {traceback.format_exc()}")
            raise
        finally:
            try:
                sftp.close()
                ssh.close()
            except:
                pass
    
    def upload_from_path(self, local_path: str, client_id: str, 
                         category: str = 'images') -> Optional[dict]:
        """Upload a local file to FTP"""
        try:
            with open(local_path, 'rb') as f:
                file_data = f.read()
            filename = os.path.basename(local_path)
            return self.upload_file(file_data, filename, client_id, category)
        except Exception as e:
            logger.error(f"Failed to read local file for FTP upload: {e}")
            return None
    
    def delete_file(self, remote_path: str) -> bool:
        """Delete a file from FTP server"""
        if not self.is_configured():
            return False
        
        try:
            if self.protocol == 'sftp':
                ssh, sftp = self._get_sftp_connection()
                try:
                    sftp.remove(remote_path)
                    logger.info(f"Deleted file from SFTP: {remote_path}")
                    return True
                finally:
                    sftp.close()
                    ssh.close()
            else:
                ftp = self._get_ftp_connection()
                try:
                    ftp.delete(remote_path)
                    logger.info(f"Deleted file from FTP: {remote_path}")
                    return True
                finally:
                    ftp.quit()
        except Exception as e:
            logger.error(f"FTP delete failed: {e}")
            return False
    
    def list_files(self, client_id: str, category: str = 'images') -> list:
        """List files in a remote directory"""
        if not self.is_configured():
            return []
        
        remote_dir = f"{self.remote_path}/{client_id}/{category}"
        
        try:
            if self.protocol == 'sftp':
                return self._list_sftp(remote_dir, client_id, category)
            else:
                return self._list_ftp(remote_dir, client_id, category)
        except Exception as e:
            logger.error(f"FTP list failed: {e}")
            return []
    
    def _list_ftp(self, remote_dir: str, client_id: str, category: str) -> list:
        """List files via FTP"""
        ftp = self._get_ftp_connection()
        try:
            files = []
            try:
                ftp.cwd(remote_dir)
                file_list = ftp.nlst()
                for filename in file_list:
                    if filename.startswith('.'):
                        continue
                    files.append({
                        'filename': filename,
                        'url': f"{self.base_url.rstrip('/')}/{client_id}/{category}/{filename}"
                    })
            except ftplib.error_perm:
                pass  # Directory doesn't exist
            return files
        finally:
            ftp.quit()
    
    def _list_sftp(self, remote_dir: str, client_id: str, category: str) -> list:
        """List files via SFTP"""
        ssh, sftp = self._get_sftp_connection()
        try:
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
    
    def test_connection(self) -> dict:
        """Test FTP connection and return status"""
        if not self.is_configured():
            return {
                'success': False,
                'error': 'FTP not configured. Set FTP_HOST, FTP_USERNAME, FTP_PASSWORD, and FTP_BASE_URL environment variables.'
            }
        
        try:
            if self.protocol == 'sftp':
                ssh, sftp = self._get_sftp_connection()
                try:
                    try:
                        sftp.listdir(self.remote_path)
                    except FileNotFoundError:
                        self._ensure_sftp_directory(sftp, self.remote_path)
                finally:
                    sftp.close()
                    ssh.close()
            else:
                ftp = self._get_ftp_connection()
                try:
                    try:
                        ftp.cwd(self.remote_path)
                    except ftplib.error_perm:
                        self._ensure_ftp_directory(ftp, self.remote_path)
                finally:
                    ftp.quit()
            
            return {
                'success': True,
                'host': self.host,
                'protocol': self.protocol.upper(),
                'remote_path': self.remote_path,
                'base_url': self.base_url
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
_ftp_service = None

def get_ftp_service() -> FTPStorageService:
    """Get or create FTP service instance"""
    global _ftp_service
    if _ftp_service is None:
        _ftp_service = FTPStorageService()
    return _ftp_service


# Backwards compatibility - alias for SFTP imports
SFTPStorageService = FTPStorageService
get_sftp_service = get_ftp_service
