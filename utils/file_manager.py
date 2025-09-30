import os
from pathlib import Path
from datetime import datetime

class FileManager:
    """Manage temporary storage of scraped content"""

    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

    def create_session(self) -> str:
        """Create unique session directory"""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = self.temp_dir / session_id
        session_path.mkdir(exist_ok=True)
        return session_id

    def save_session_content(self, session_id: str, all_scraped_content: dict, facts: list = None):
        """Save all scraped content with metadata in one comprehensive file"""
        session_path = self.temp_dir / session_id
        filepath = session_path / "session_report.txt"

        with open(filepath, 'w', encoding='utf-8') as f:
            # Header with session metadata
            f.write("=" * 100 + "\n")
            f.write(f"FACT-CHECK SESSION REPORT\n")
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
                publication_name = self._extract_publication_name(url)
                f.write(f"{i:2d}. {publication_name}\n")
                f.write(f"    URL: {url}\n")
            f.write("\n" + "=" * 100 + "\n\n")

            # Facts being checked (if provided)
            if facts:
                f.write("FACTS BEING VERIFIED:\n")
                f.write("-" * 50 + "\n")
                for fact in facts:
                    f.write(f"• {fact.id}: {fact.statement}\n")
                f.write("\n" + "=" * 100 + "\n\n")

            # Full scraped content for each source
            for i, (url, content) in enumerate(all_scraped_content.items(), 1):
                publication_name = self._extract_publication_name(url)
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

    def _extract_publication_name(self, url: str) -> str:
        """Extract a readable publication name from URL"""
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.lower()

        # Clean up common patterns
        domain = domain.replace('www.', '')

        # Map known domains to proper names
        # Later add AI verification and name extraction for sources + database integration
        domain_map = {
            'nytimes.com': 'The New York Times',
            'washingtonpost.com': 'The Washington Post',
            'wsj.com': 'The Wall Street Journal',
            'reuters.com': 'Reuters',
            'bbc.com': 'BBC News',
            'cnn.com': 'CNN',
            'forbes.com': 'Forbes',
            'bloomberg.com': 'Bloomberg',
            'theguardian.com': 'The Guardian',
            'ft.com': 'Financial Times',
        }

        return domain_map.get(domain, domain.title())

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