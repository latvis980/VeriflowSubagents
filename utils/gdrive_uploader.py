# utils/gdrive_uploader.py
"""
✅ FIXED Google Drive Uploader with Railway Environment Variable Support
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import os
import sys  # ✅ ADDED: Needed for checking interactive environment
import base64
from pathlib import Path
import json
from typing import Optional
from loguru import logger

class GoogleDriveUploader:
    """
    Upload files to Google Drive with Railway environment variable support

    Credentials can be provided via:
    1. credentials.json file (for local development)
    2. GOOGLE_CREDENTIALS_BASE64 environment variable (for Railway)
    """

    # Google Drive API scopes
    SCOPES = ['https://www.googleapis.com/auth/drive.file']

    def __init__(self, credentials_path: str = 'credentials.json'):
        """
        Initialize the Google Drive uploader

        Args:
            credentials_path: Path to OAuth credentials JSON file
        """
        # ✅ Set attributes FIRST
        self.credentials_path = credentials_path
        self.token_path = 'token.json'
        self.service = None

        # ✅ Then setup files from environment variables
        self._setup_credentials_file(credentials_path)
        self._setup_token_file()

        # Get folder ID from environment or use None (root)
        self.folder_id = os.getenv('GDRIVE_FOLDER_ID')

        if not self.folder_id:
            logger.warning("⚠️ GDRIVE_FOLDER_ID not set. Files will be uploaded to Drive root.")

        logger.info("🔧 Initializing Google Drive uploader")

    def _is_interactive_environment(self) -> bool:
        """
        ✅ NEW: Check if we're in an interactive environment

        Returns False for:
        - Railway deployments
        - Docker containers
        - Any environment without a TTY
        """
        # Check if stdin is a TTY (terminal)
        if not sys.stdin.isatty():
            logger.debug("Non-interactive: No TTY detected")
            return False

        # Check for Railway or similar deployment environments
        if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RENDER'):
            logger.debug("Non-interactive: Deployment environment detected")
            return False

        # Check if we're in a Docker container
        if os.path.exists('/.dockerenv'):
            logger.debug("Non-interactive: Docker environment detected")
            return False

        return True

    def _setup_credentials_file(self, credentials_path: str):
        """
        ✅ NEW: Create credentials.json from environment variable if needed

        This allows Railway to work without committing credentials.json to git
        """
        # If file already exists, use it
        if os.path.exists(credentials_path):
            logger.info("✅ Using existing credentials.json file")
            return

        # Try to load from environment variable (for Railway)
        creds_b64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
        if creds_b64:
            try:
                creds_json = base64.b64decode(creds_b64).decode('utf-8')
                with open(credentials_path, 'w') as f:
                    f.write(creds_json)
                logger.info("✅ Created credentials.json from GOOGLE_CREDENTIALS_BASE64 environment variable")
            except Exception as e:
                logger.error(f"❌ Failed to decode credentials from environment variable: {e}")
        else:
            logger.warning("⚠️ No credentials.json file and no GOOGLE_CREDENTIALS_BASE64 environment variable")

    def _setup_token_file(self):
        """
        ✅ NEW: Create token.json from environment variable if needed
        """
        # If file already exists, use it
        if os.path.exists(self.token_path):
            logger.info("✅ Using existing token.json file")
            return

        # Try to load from environment variable (for Railway)
        token_b64 = os.getenv('GOOGLE_TOKEN_BASE64')
        if token_b64:
            try:
                token_json = base64.b64decode(token_b64).decode('utf-8')
                with open(self.token_path, 'w') as f:
                    f.write(token_json)
                logger.info("✅ Created token.json from GOOGLE_TOKEN_BASE64 environment variable")
            except Exception as e:
                logger.error(f"❌ Failed to decode token from environment variable: {e}")
        else:
            logger.info("ℹ️ No token.json file and no GOOGLE_TOKEN_BASE64 environment variable (will authenticate when needed)")

    def authenticate(self) -> bool:
        """
        Authenticate with Google Drive using proper OAuth flow

        Returns:
            True if authentication successful, False otherwise
        """
        creds = None

        # Load existing token if available
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(
                    self.token_path, 
                    self.SCOPES
                )
                logger.info("✅ Loaded existing credentials from token.json")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load token.json: {e}")
                creds = None

        # Refresh expired token
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("🔄 Refreshing expired credentials")
                creds.refresh(Request())
                logger.info("✅ Credentials refreshed successfully")

                # ✅ NEW: Save refreshed token back to file
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
                logger.info("💾 Saved refreshed token")

            except Exception as e:
                logger.error(f"❌ Failed to refresh credentials: {e}")
                creds = None

        # Need new authentication
        if not creds or not creds.valid:

            # ✅ NEW: Check if we're in a non-interactive environment
            if not self._is_interactive_environment():
                logger.error("❌ Cannot authenticate in non-interactive environment (Railway/Docker)")
                logger.error("🔧 REQUIRED: Set GOOGLE_TOKEN_BASE64 environment variable")
                logger.error("📋 Generate token locally with: python setup_gdrive_token.py")
                return False

            logger.info("🔐 Starting OAuth flow")

            if not os.path.exists(self.credentials_path):
                logger.error(f"❌ Credentials file not found: {self.credentials_path}")
                logger.info("📋 Get credentials from: https://console.cloud.google.com/apis/credentials")
                return False

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path,
                    self.SCOPES
                )

                # Try local server first (works in most cases)
                logger.info("🔧 Attempting browser-based authentication")
                try:
                    creds = flow.run_local_server(
                        port=0,
                        authorization_prompt_message='',
                        success_message='Authentication successful! You can close this window.',
                        open_browser=True,
                        access_type='offline',  # ✅ ADDED: Get refresh token
                        prompt='consent'  # ✅ ADDED: Force consent for refresh token
                    )
                    logger.info("✅ Browser authentication successful")

                except Exception as server_error:
                    # Fallback: Manual authorization
                    logger.warning(f"⚠️ Browser authentication failed: {server_error}")
                    logger.info("🔄 Switching to manual authorization flow")

                    auth_url, _ = flow.authorization_url(
                        prompt='consent',
                        access_type='offline'  # ✅ ADDED: Get refresh token
                    )
                    print(f"\n🔗 Visit this URL:\n{auth_url}\n")

                    code = input('Enter the authorization code: ').strip()
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    logger.info("✅ Manual authorization successful")

                # Save credentials for future use
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"💾 Credentials saved to {self.token_path}")

            except Exception as e:
                logger.error(f"❌ Authentication failed: {e}")
                return False

        # Initialize Google Drive service
        try:
            self.service = build('drive', 'v3', credentials=creds)
            logger.info("✅ Google Drive service initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Drive service: {e}")
            return False

    def upload_file(
        self, 
        file_path: str, 
        drive_filename: Optional[str] = None,
        mime_type: str = 'text/plain'
    ) -> Optional[str]:
        """
        Upload a file to Google Drive

        Args:
            file_path: Path to the file to upload
            drive_filename: Name to use in Google Drive (defaults to original filename)
            mime_type: MIME type of the file

        Returns:
            File ID if successful, None otherwise
        """
        if not self.service:
            logger.error("❌ Not authenticated. Call authenticate() first.")
            return None

        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"❌ File not found: {file_path}")
            return None

        if not drive_filename:
            drive_filename = file_path.name

        logger.info(f"📤 Uploading: {file_path.name} → {drive_filename}")

        try:
            # File metadata
            file_metadata = {
                'name': drive_filename,
            }

            # Add folder if specified
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]
                logger.info(f"📁 Uploading to folder ID: {self.folder_id}")

            # Upload the file
            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()

            file_id = file.get('id')
            web_link = file.get('webViewLink')

            logger.info(f"✅ Upload successful!")
            logger.info(f"📄 File: {file.get('name')}")
            logger.info(f"🔗 ID: {file_id}")
            logger.info(f"🌐 Link: {web_link}")

            return file_id

        except HttpError as error:
            logger.error(f"❌ Upload failed: {error}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error during upload: {e}")
            return None

    def list_files(self, max_results: int = 10) -> list:
        """List files in Google Drive"""
        if not self.service:
            logger.error("❌ Not authenticated. Call authenticate() first.")
            return []

        try:
            query_parts = []
            if self.folder_id:
                query_parts.append(f"'{self.folder_id}' in parents")
            query_parts.append("trashed=false")

            query = " and ".join(query_parts)

            results = self.service.files().list(
                pageSize=max_results,
                q=query,
                fields="files(id, name, createdTime, modifiedTime, size, webViewLink)"
            ).execute()

            files = results.get('files', [])

            if not files:
                logger.info('📂 No files found')
                return []

            logger.info(f'📂 Found {len(files)} files')
            return files

        except HttpError as error:
            logger.error(f"❌ Failed to list files: {error}")
            return []


def upload_session_to_drive(session_id: str, file_path: str) -> Optional[str]:
    """
    Convenience function to upload a fact-check session file to Google Drive

    Args:
        session_id: Unique session identifier
        file_path: Path to the session report file

    Returns:
        File ID if successful, None otherwise
    """
    try:
        uploader = GoogleDriveUploader()

        if not uploader.authenticate():
            logger.error(f"❌ Authentication failed for session {session_id}")
            return None

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        drive_filename = f"FactCheck_Session_{session_id}_{timestamp}.txt"

        logger.info(f"📤 Uploading session {session_id} to Google Drive...")

        file_id = uploader.upload_file(
            file_path=file_path,
            drive_filename=drive_filename,
            mime_type="text/plain"
        )

        if file_id:
            logger.info(f"✅ Session {session_id} uploaded successfully!")
        else:
            logger.error(f"❌ Upload failed for session {session_id}")

        return file_id

    except Exception as e:
        logger.error(f"❌ Error uploading session {session_id}: {e}")
        return None


if __name__ == "__main__":
    print("🧪 Testing Google Drive Authentication\n")
    uploader = GoogleDriveUploader()

    if uploader.authenticate():
        print("✅ Authentication successful!")
        uploader.list_files()
    else:
        print("❌ Authentication failed")