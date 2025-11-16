# utils/file_manager.py
"""
File Manager with Cloudflare R2 integration
Manages session files and uploads to R2 for audit purposes
"""

import os
from pathlib import Path
from datetime import datetime
import asyncio

# Import the separate publication name extractor
from utils.publication_name_extractor import get_publication_name_extractor


class FileManager:
    """Manage temporary storage of scraped content"""

    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

        # Track page titles for AI name extraction
        self.page_titles = {}

    def create_session(self) -> str:
        """Create unique session directory"""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = self.temp_dir / session_id
        session_path.mkdir(exist_ok=True)
        return session_id

    def set_page_title(self, url: str, title: str):
        """
        Store page title for a URL (optional, improves AI extraction quality)

        Args:
            url: The source URL
            title: The page title from <title> tag
        """
        self.page_titles[url] = title

    def save_session_content(
        self, 
        session_id: str, 
        all_scraped_content: dict, 
        facts: list = None,
        upload_to_r2: bool = True,  # ✅ CHANGED: upload_to_drive → upload_to_r2
        queries_by_fact: dict = None
    ):
        """
        Save all scraped content with metadata in one comprehensive file
        
        ✅ UPDATED: Now uploads to Cloudflare R2 instead of Google Drive

        Args:
            session_id: Unique session identifier
            all_scraped_content: Dict of scraped content
            facts: List of facts being verified
            upload_to_r2: If True, upload the report to R2 after saving
            queries_by_fact: Dict mapping fact_id to SearchQueries object (optional)
        """
        session_path = self.temp_dir / session_id
        filepath = session_path / "session_report.txt"

        # Extract publication names using AI
        publication_names = asyncio.run(self._extract_all_publication_names(all_scraped_content.keys()))

        with open(filepath, 'w', encoding='utf-8') as f:
            # Header with session metadata
            f.write("=" * 100 + "\n")
            f.write("FACT-CHECK SESSION REPORT\n")
            f.write(f"Session ID: {session_id}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Total Sources: {len(all_scraped_content)}\n")
            if facts:
                f.write(f"Total Facts Analyzed: {len(facts)}\n")
            f.write("=" * 100 + "\n\n")

            # Table of Contents
            f.write("TABLE OF CONTENTS:\n")
            f.write("-" * 50 + "\n")
            for i, url in enumerate(all_scraped_content.keys(), 1):
                publication_name = publication_names.get(url, "Unknown Source")
                f.write(f"{i:2d}. {publication_name}\n")
                f.write(f"    {url}\n")

            f.write("\n" + "=" * 100 + "\n\n")

            # Facts being verified (if provided)
            if facts:
                f.write("FACTS BEING VERIFIED:\n")
                f.write("-" * 50 + "\n")
                for i, fact in enumerate(facts, 1):
                    f.write(f"\n{i}. [{fact.id}] {fact.claim}\n")
                    f.write(f"   Context: {fact.context}\n")
                    
                    # Add search queries if available
                    if queries_by_fact and fact.id in queries_by_fact:
                        queries = queries_by_fact[fact.id]
                        f.write(f"\n   PRIMARY QUERY: {queries.primary_query}\n")
                        
                        if hasattr(queries, 'alternative_queries') and queries.alternative_queries:
                            f.write(f"   ALTERNATIVE QUERIES:\n")
                            for alt_query in queries.alternative_queries:
                                f.write(f"     - {alt_query}\n")
                        f.write("\n")

                    if hasattr(queries, 'search_focus') and queries.search_focus:
                        f.write(f"SEARCH FOCUS: {queries.search_focus}\n\n")

                    if hasattr(queries, 'key_terms') and queries.key_terms:
                        f.write(f"KEY TERMS: {', '.join(queries.key_terms)}\n\n")

                    if hasattr(queries, 'expected_sources') and queries.expected_sources:
                        f.write(f"EXPECTED SOURCE TYPES: {', '.join(queries.expected_sources)}\n\n")

                    f.write("=" * 80 + "\n\n")

                f.write("\n" + "=" * 100 + "\n\n")

            # Full scraped content for each source
            for i, (url, content) in enumerate(all_scraped_content.items(), 1):
                publication_name = publication_names.get(url, "Unknown Source")
                content_length = len(content) if content else 0

                f.write(f"SOURCE #{i}: {publication_name.upper()}\n")
                f.write("=" * 80 + "\n")
                f.write(f"Publication: {publication_name}\n")
                f.write(f"URL: {url}\n")
                f.write(f"Content Length: {content_length:,} characters\n")
                f.write(f"Domain: {self._extract_domain(url)}\n")
                f.write(f"Scraped: {datetime.now().isoformat()}\n")
                f.write("-" * 80 + "\n\n")

                if content and content.strip():
                    f.write("CONTENT:\n")
                    f.write(content)
                else:
                    f.write("❌ NO CONTENT SCRAPED (Check scraping logs for errors)\n")

                f.write("\n\n" + "=" * 100 + "\n\n")

            # Footer
            f.write("END OF SESSION REPORT\n")
            f.write("=" * 100 + "\n")

        # ✅ UPDATED: Upload to Cloudflare R2 instead of Google Drive
        upload_result = {'success': False, 'url': None, 'error': None}
        
        if upload_to_r2:
            try:
                from utils.r2_uploader import upload_session_to_r2
                from utils.logger import fact_logger

                fact_logger.logger.info(f"📤 Uploading session {session_id} to Cloudflare R2")
                upload_result = upload_session_to_r2(session_id, str(filepath))

                if upload_result and upload_result.get('success'):
                    fact_logger.logger.info(
                        f"✅ Session {session_id} uploaded to R2: {upload_result.get('url')}",
                        extra={
                            "session_id": session_id, 
                            "r2_url": upload_result.get('url'),
                            "r2_filename": upload_result.get('filename')
                        }
                    )
                else:
                    error_msg = upload_result.get('error', 'Unknown error') if upload_result else 'Upload function returned None'
                    fact_logger.logger.warning(
                        f"⚠️ Failed to upload session {session_id} to R2: {error_msg}",
                        extra={"session_id": session_id, "error": error_msg}
                    )
                    upload_result = {'success': False, 'url': None, 'error': error_msg}
                    
            except ImportError:
                from utils.logger import fact_logger
                error_msg = "R2 uploader not available. Install boto3."
                fact_logger.logger.warning(f"⚠️ {error_msg}")
                upload_result = {'success': False, 'url': None, 'error': error_msg}
                
            except Exception as e:
                from utils.logger import fact_logger
                error_msg = str(e)
                fact_logger.logger.error(
                    f"❌ Error uploading to R2: {e}",
                    extra={"session_id": session_id, "error": error_msg}
                )
                upload_result = {'success': False, 'url': None, 'error': error_msg}
        
        # Return upload result for use in responses
        return upload_result

    async def _extract_all_publication_names(self, urls: list) -> dict:
        """
        Extract publication names for all URLs using AI

        Args:
            urls: List of URLs to process

        Returns:
            Dict mapping URL to publication name
        """
        extractor = get_publication_name_extractor()
        results = {}

        # Process all URLs concurrently
        tasks = []
        for url in urls:
            page_title = self.page_titles.get(url)
            tasks.append((url, extractor.extract_name(url, page_title)))

        # Wait for all to complete
        for url, task in tasks:
            try:
                name = await task
                results[url] = name
            except Exception as e:
                print(f"⚠️ Failed to extract name for {url}: {e}")
                # Fallback to domain extraction
                results[url] = await extractor.extract_name(url, None)

        return results

    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        from urllib.parse import urlparse
        return urlparse(url).netloc

    def _sanitize_url(self, url: str) -> str:
        """Convert URL to safe filename"""
        return url.replace('https://', '').replace('http://', '')\
                  .replace('/', '_').replace(':', '_')[:50]

    def cleanup_old_sessions(self, days: int = 1):
        """Remove sessions older than specified days"""
        # Implementation for cleanup
        pass
