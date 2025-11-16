# utils/r2_uploader.py
"""
✅ Cloudflare R2 Storage Uploader
Replaces Google Drive with simple, reliable S3-compatible storage
No OAuth complexity, no token expiration, no authentication headaches!
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from loguru import logger


class R2Uploader:
    """
    Upload files to Cloudflare R2 Storage
    
    Much simpler than Google Drive:
    - No OAuth flow
    - No token expiration
    - No refresh token issues
    - Just simple API keys
    """
    
    def __init__(self):
        """Initialize R2 client with environment variables"""
        
        # Get credentials from environment
        self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('R2_BUCKET_NAME', 'factcheck-audit-sessions')
        self.account_id = os.getenv('R2_ACCOUNT_ID')
        self.endpoint = os.getenv('R2_ENDPOINT')
        
        # Validate required credentials
        missing_vars = []
        if not self.access_key_id:
            missing_vars.append('R2_ACCESS_KEY_ID')
        if not self.secret_access_key:
            missing_vars.append('R2_SECRET_ACCESS_KEY')
        if not self.account_id:
            missing_vars.append('R2_ACCOUNT_ID')
            
        if missing_vars:
            error_msg = f"❌ Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Build endpoint if not provided
        if not self.endpoint:
            self.endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
        
        # Initialize S3 client for R2
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name='auto'  # R2 uses 'auto' for region
            )
            logger.info(f"✅ R2 client initialized for bucket: {self.bucket_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize R2 client: {e}")
            raise
    
    def upload_file(
        self, 
        file_path: str, 
        r2_filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Upload a file to R2
        
        Args:
            file_path: Path to the local file to upload
            r2_filename: Name to use in R2 (defaults to original filename)
            metadata: Optional metadata dictionary to attach to the file
            
        Returns:
            Public URL if successful, None otherwise
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"❌ File not found: {file_path}")
            return None
        
        if not r2_filename:
            r2_filename = file_path.name
        
        logger.info(f"📤 Uploading to R2: {file_path.name} → {r2_filename}")
        
        try:
            # Prepare upload parameters
            extra_args = {}
            
            # Add metadata if provided
            if metadata:
                extra_args['Metadata'] = metadata
            
            # Add content type
            if file_path.suffix == '.txt':
                extra_args['ContentType'] = 'text/plain'
            elif file_path.suffix == '.json':
                extra_args['ContentType'] = 'application/json'
            
            # Upload the file
            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                r2_filename,
                ExtraArgs=extra_args if extra_args else None
            )
            
            # Construct public URL
            public_url = f"{self.endpoint}/{self.bucket_name}/{r2_filename}"
            
            logger.info(f"✅ Upload successful: {r2_filename}")
            logger.info(f"🔗 URL: {public_url}")
            
            return public_url
            
        except NoCredentialsError:
            logger.error("❌ No R2 credentials found")
            return None
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"❌ R2 upload failed [{error_code}]: {error_message}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error during upload: {e}")
            return None
    
    def generate_presigned_url(
        self, 
        r2_filename: str, 
        expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate a presigned URL for temporary access to a file
        
        Args:
            r2_filename: The file key in R2
            expiration: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL if successful, None otherwise
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': r2_filename
                },
                ExpiresIn=expiration
            )
            logger.info(f"🔗 Generated presigned URL (expires in {expiration}s)")
            return url
            
        except ClientError as e:
            logger.error(f"❌ Failed to generate presigned URL: {e}")
            return None
    
    def list_files(self, prefix: str = '', max_keys: int = 100) -> list:
        """
        List files in the R2 bucket
        
        Args:
            prefix: Filter files by prefix (e.g., '2025/11/')
            max_keys: Maximum number of files to return
            
        Returns:
            List of file information dictionaries
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            if 'Contents' not in response:
                logger.info(f"📂 No files found with prefix: {prefix}")
                return []
            
            files = []
            for obj in response['Contents']:
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'url': f"{self.endpoint}/{self.bucket_name}/{obj['Key']}"
                })
            
            logger.info(f"📂 Found {len(files)} files")
            return files
            
        except ClientError as e:
            logger.error(f"❌ Failed to list files: {e}")
            return []
    
    def delete_file(self, r2_filename: str) -> bool:
        """
        Delete a file from R2
        
        Args:
            r2_filename: The file key to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=r2_filename
            )
            logger.info(f"🗑️ Deleted: {r2_filename}")
            return True
            
        except ClientError as e:
            logger.error(f"❌ Failed to delete file: {e}")
            return False


def upload_session_to_r2(session_id: str, file_path: str) -> Optional[Dict[str, str]]:
    """
    Convenience function to upload a fact-check session file to R2
    
    Args:
        session_id: Unique session identifier
        file_path: Path to the session report file
        
    Returns:
        Dictionary with upload status and URL if successful, None otherwise
    """
    try:
        uploader = R2Uploader()
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        r2_filename = f"sessions/{session_id}/report_{timestamp}.txt"
        
        # Add metadata
        metadata = {
            'session-id': session_id,
            'upload-timestamp': timestamp,
            'content-type': 'factcheck-session-report'
        }
        
        logger.info(f"📤 Uploading session {session_id} to R2...")
        
        url = uploader.upload_file(
            file_path=file_path,
            r2_filename=r2_filename,
            metadata=metadata
        )
        
        if url:
            logger.info(f"✅ Session {session_id} uploaded successfully!")
            return {
                'success': True,
                'url': url,
                'filename': r2_filename,
                'session_id': session_id
            }
        else:
            logger.error(f"❌ Upload failed for session {session_id}")
            return {
                'success': False,
                'error': 'Upload failed',
                'session_id': session_id
            }
            
    except Exception as e:
        logger.error(f"❌ Error uploading session {session_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'session_id': session_id
        }


if __name__ == "__main__":
    """Test R2 connection"""
    print("🧪 Testing Cloudflare R2 Connection\n")
    
    try:
        uploader = R2Uploader()
        print("✅ R2 client initialized successfully!")
        
        # List files
        files = uploader.list_files()
        print(f"\n📂 Files in bucket: {len(files)}")
        for f in files[:5]:  # Show first 5
            print(f"  - {f['key']} ({f['size']} bytes)")
            
    except Exception as e:
        print(f"❌ R2 connection test failed: {e}")
