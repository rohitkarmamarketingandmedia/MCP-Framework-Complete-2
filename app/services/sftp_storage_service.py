"""
SFTP Storage Service - Backwards Compatibility Module
Now supports both FTP and SFTP via the unified FTPStorageService
"""

# Import everything from the new FTP service for backwards compatibility
from app.services.ftp_storage_service import (
    FTPStorageService,
    FTPStorageService as SFTPStorageService,
    get_ftp_service,
    get_ftp_service as get_sftp_service,
)

__all__ = ['SFTPStorageService', 'get_sftp_service', 'FTPStorageService', 'get_ftp_service']
