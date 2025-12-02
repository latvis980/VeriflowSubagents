# utils/file_manager.py
"""
File Manager with Cloudflare R2 integration
Manages session files and uploads to R2 for audit purposes
"""

import os
from pathlib import Path
from datetime import datetime
import asyncio
from typing import Optional, Dict, Any

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

    def save_session_file(
        self, 
        session_id: str, 
        filename: str, 
        content,  # Can be string, dict, or list
        auto_serialize: bool = True
    ) -> str:
        """
        Save a file to a specific session directory with automatic JSON serialization

        Args:
            session_id: Session identifier
            filename: Name of file to save (e.g., "report.json")
            content: Content to write (string, dict, or list)
            auto_serialize: If True, automatically serialize dicts/lists to JSON

        Returns:
            str: Full path to saved file
        """
        import json

        session_path = self.temp_dir / session_id

        # Ensure session directory exists
        session_path.mkdir(exist_ok=True)

        # Create full file path
        filepath = session_path / filename

        # Determine content to write
        if auto_serialize and isinstance(content, (dict, list)):
            # Automatically serialize to JSON
            file_content = json.dumps(content, indent=2, ensure_ascii=False)
        elif isinstance(content, str):
            file_content = content
        else:
            # Fallback: convert to string
            file_content = str(content)

        # Write content to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(file_content)

        # Log the save operation
        from utils.logger import fact_logger
        fact_logger.logger.info(
            f"💾 Saved file: {filename}",
            extra={
                "session_id": session_id,
                "filename": filename,
                "size": len(file_content),
                "type": type(content).__name__
            }
        )

        # Return full path as string
        return str(filepath)

    def save_verification_report(
        self,
        session_id: str,
        report_text: str,
        original_content: str = None,
        upload_to_r2: bool = True
    ):
        """
        Save LLM verification report (simpler version for text-based reports)

        Used by: LLM Output Verification pipeline
        Different from save_session_content which handles web search scraped content

        Args:
            session_id: Session identifier
            report_text: Formatted verification report text
            original_content: Optional original LLM HTML input
            upload_to_r2: Whether to upload to Cloudflare R2

        Returns:
            Dict with upload status: {'success': bool, 'url': str, 'error': str}
        """
        from utils.logger import fact_logger

        session_path = self.temp_dir / session_id
        filepath = session_path / "verification_report.txt"

        # Write the formatted report
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_text)

            # Optionally append original LLM output for reference
            if original_content:
                f.write("\n\n" + "=" * 100 + "\n")
                f.write("ORIGINAL LLM OUTPUT:\n")
                f.write("=" * 100 + "\n\n")
                f.write(original_content)

        fact_logger.logger.info(
            f"💾 Saved verification report: verification_report.txt",
            extra={
                "session_id": session_id,
                "size": os.path.getsize(filepath)
            }
        )

        # Upload to R2 if enabled
        upload_result = {'success': False, 'url': None, 'error': 'R2 upload not attempted'}

        if upload_to_r2:
            try:
                from utils.r2_uploader import upload_session_to_r2

                fact_logger.logger.info(f"📤 Uploading verification report for {session_id} to R2")
                upload_result = upload_session_to_r2(session_id, str(filepath))

                if upload_result and upload_result.get('success'):
                    fact_logger.logger.info(
                        f"✅ Verification report uploaded to R2: {upload_result.get('url')}",
                        extra={
                            "session_id": session_id,
                            "r2_url": upload_result.get('url'),
                            "r2_filename": upload_result.get('filename')
                        }
                    )
                else:
                    error_msg = upload_result.get('error', 'Unknown error') if upload_result else 'Upload failed'
                    fact_logger.logger.warning(
                        f"⚠️ Failed to upload verification report: {error_msg}",
                        extra={"session_id": session_id, "error": error_msg}
                    )
                    upload_result = {'success': False, 'url': None, 'error': error_msg}

            except ImportError:
                error_msg = "R2 uploader not available. Install boto3."
                fact_logger.logger.warning(f"⚠️ {error_msg}")
                upload_result = {'success': False, 'url': None, 'error': error_msg}

            except Exception as e:
                error_msg = str(e)
                fact_logger.logger.error(
                    f"❌ Error uploading to R2: {e}",
                    extra={"session_id": session_id, "error": error_msg}
                )
                upload_result = {'success': False, 'url': None, 'error': error_msg}

        return upload_result

    def set_page_title(self, url: str, title: str):
        """
        Store page title for a URL (optional, improves AI extraction quality)

        Args:
            url: The source URL
            title: The page title from <title> tag
        """
        self.page_titles[url] = title

    def _format_queries_section(
        self, 
        fact, 
        queries, 
        content_location: Optional[Any] = None
    ) -> str:
        """
        Format search queries for a single fact in the audit report

        Args:
            fact: Fact object with id and statement
            queries: SearchQueries object
            content_location: Optional ContentLocation object

        Returns:
            Formatted string for the queries section
        """
        lines = []

        # Fact header
        lines.append(f"\n{'─' * 60}")
        lines.append(f"FACT: [{fact.id}] {fact.statement}")
        original_text = getattr(fact, 'original_text', '')
        if original_text:
            lines.append(f"Original Text: {original_text[:200]}..." if len(original_text) > 200 else f"Original Text: {original_text}")
        lines.append(f"{'─' * 60}")

        # Language/Location info if multilingual
        if queries.local_language_used:
            lines.append(f"\n🌍 MULTILINGUAL QUERIES ENABLED")
            lines.append(f"   Target Language: {queries.local_language_used.upper()}")
            if content_location:
                lines.append(f"   Detected Country: {content_location.country}")
                lines.append(f"   Detection Confidence: {content_location.confidence:.2f}")

        # Primary Query
        lines.append(f"\n📌 PRIMARY QUERY (English):")
        lines.append(f"   {queries.primary_query}")

        # Alternative Queries with language labeling
        if hasattr(queries, 'alternative_queries') and queries.alternative_queries:
            lines.append(f"\n🔍 ALTERNATIVE QUERIES:")
            for i, alt_query in enumerate(queries.alternative_queries, 1):
                # Try to detect if this query is in a foreign language
                is_foreign = self._detect_foreign_language_query(alt_query, queries.local_language_used)
                if is_foreign and queries.local_language_used:
                    lang_label = f" [{queries.local_language_used.upper()}]"
                else:
                    lang_label = " [English]"
                lines.append(f"   {i}. {alt_query}{lang_label}")

        # All queries combined (for easy copy-paste testing)
        lines.append(f"\n📋 ALL QUERIES (for Tavily/search):")
        for i, q in enumerate(queries.all_queries, 1):
            lines.append(f"   [{i}] {q}")

        # Search metadata
        if hasattr(queries, 'search_focus') and queries.search_focus:
            lines.append(f"\n🎯 Search Focus: {queries.search_focus}")

        if hasattr(queries, 'key_terms') and queries.key_terms:
            lines.append(f"🔑 Key Terms: {', '.join(queries.key_terms)}")

        if hasattr(queries, 'expected_sources') and queries.expected_sources:
            lines.append(f"📰 Expected Sources: {', '.join(queries.expected_sources)}")

        lines.append("")

        return "\n".join(lines)

    def _detect_foreign_language_query(self, query: str, expected_language: Optional[str]) -> bool:
        """
        Simple heuristic to detect if a query contains non-English text

        Args:
            query: The search query string
            expected_language: The expected foreign language (e.g., 'polish', 'german')

        Returns:
            True if query appears to contain foreign language text
        """
        if not expected_language:
            return False

        # Common non-ASCII characters that indicate foreign languages
        non_ascii_chars = sum(1 for c in query if ord(c) > 127)

        # If query has several non-ASCII chars, likely foreign
        if non_ascii_chars >= 2:
            return True

        # Check for common foreign language patterns
        foreign_indicators = {
            'polish': ['ą', 'ć', 'ę', 'ł', 'ń', 'ó', 'ś', 'ź', 'ż', 'PKB', 'wzrost'],
            'german': ['ä', 'ö', 'ü', 'ß', 'Verkauf', 'eröffnet'],
            'french': ['é', 'è', 'ê', 'à', 'ç', 'ô', 'î', 'û'],
            'spanish': ['ñ', 'á', 'í', 'ú', 'ü'],
            'italian': ['à', 'è', 'é', 'ì', 'ò', 'ù'],
            'portuguese': ['ã', 'õ', 'ç'],
            'russian': ['а', 'б', 'в', 'г', 'д'],  # Cyrillic
            'chinese': ['的', '是', '在'],  # Common Chinese characters
            'japanese': ['の', 'は', 'を'],  # Hiragana
            'korean': ['의', '은', '는'],  # Korean
        }

        lang_key = expected_language.lower()
        if lang_key in foreign_indicators:
            for indicator in foreign_indicators[lang_key]:
                if indicator.lower() in query.lower():
                    return True

        return False

    def save_session_content(
        self, 
        session_id: str, 
        all_scraped_content: dict, 
        facts: Optional[list] = None,
        upload_to_r2: bool = True,
        queries_by_fact: Optional[dict] = None,
        content_location: Optional[Any] = None
    ):
        """
        Save all scraped content with metadata in one comprehensive file

        ✅ UPDATED: Enhanced query logging with language information

        Args:
            session_id: Unique session identifier
            all_scraped_content: Dict of scraped content
            facts: List of facts being verified
            upload_to_r2: If True, upload the report to R2 after saving
            queries_by_fact: Dict mapping fact_id to SearchQueries object (optional)
            content_location: ContentLocation object with country/language info (optional)
        """
        from utils.logger import fact_logger

        session_path = self.temp_dir / session_id
        filepath = session_path / "session_report.txt"

        # Extract publication names using AI
        publication_names = asyncio.run(self._extract_all_publication_names(list(all_scraped_content.keys())))

        with open(filepath, 'w', encoding='utf-8') as f:
            # Header with session metadata
            f.write("=" * 100 + "\n")
            f.write("FACT-CHECK SESSION REPORT\n")
            f.write(f"Session ID: {session_id}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Total Sources: {len(all_scraped_content)}\n")
            if facts:
                f.write(f"Total Facts Analyzed: {len(facts)}\n")

            # Add content location info if available
            if content_location:
                f.write(f"\n📍 Content Location:\n")
                f.write(f"   Country: {content_location.country}\n")
                f.write(f"   Language: {content_location.language}\n")
                f.write(f"   Confidence: {content_location.confidence:.2f}\n")
                if content_location.language.lower() != 'english':
                    f.write(f"   ✨ Multilingual queries enabled for {content_location.language}\n")

            f.write("=" * 100 + "\n\n")

            # Table of Contents
            f.write("TABLE OF CONTENTS:\n")
            f.write("-" * 50 + "\n")
            for i, url in enumerate(all_scraped_content.keys(), 1):
                publication_name = publication_names.get(url, "Unknown Source")
                f.write(f"{i:2d}. {publication_name}\n")
                f.write(f"    {url}\n")

            f.write("\n" + "=" * 100 + "\n\n")

            # =========================================================
            # ENHANCED: Facts and Search Queries Section
            # =========================================================
            if facts:
                f.write("FACTS AND SEARCH QUERIES:\n")
                f.write("=" * 100 + "\n")

                # Summary of query generation
                if queries_by_fact:
                    total_queries = sum(len(q.all_queries) for q in queries_by_fact.values())
                    multilingual_facts = [
                        fid for fid, q in queries_by_fact.items() 
                        if q.local_language_used
                    ]

                    f.write(f"\n📊 Query Generation Summary:\n")
                    f.write(f"   Total Facts: {len(facts)}\n")
                    f.write(f"   Total Queries Generated: {total_queries}\n")
                    if multilingual_facts:
                        # Get the language from first multilingual fact
                        lang = queries_by_fact[multilingual_facts[0]].local_language_used
                        f.write(f"   Facts with {lang.upper()} queries: {len(multilingual_facts)}\n")
                    f.write("\n")

                # Detailed fact-by-fact queries
                for i, fact in enumerate(facts, 1):
                    if queries_by_fact and fact.id in queries_by_fact:
                        queries = queries_by_fact[fact.id]
                        f.write(self._format_queries_section(fact, queries, content_location))
                    else:
                        # Fallback if no queries available
                        f.write(f"\n{i}. [{fact.id}] {fact.statement}\n")
                        original_text = getattr(fact, 'original_text', '')
                        if original_text:
                            f.write(f"   Original Text: {original_text}\n")
                        f.write(f"   ⚠️ No search queries recorded\n\n")

                f.write("=" * 100 + "\n\n")

            # =========================================================
            # Scraped Content Section
            # =========================================================
            f.write("SCRAPED SOURCE CONTENT:\n")
            f.write("=" * 100 + "\n\n")

            for i, (url, content) in enumerate(all_scraped_content.items(), 1):
                publication_name = publication_names.get(url, "Unknown Source")

                f.write(f"{'─' * 80}\n")
                f.write(f"SOURCE {i}: {publication_name}\n")
                f.write(f"URL: {url}\n")
                f.write(f"Content Length: {len(content) if content else 0} characters\n")
                f.write(f"{'─' * 80}\n\n")

                if content:
                    # Truncate very long content
                    if len(content) > 10000:
                        f.write(content[:10000])
                        f.write(f"\n\n[... Content truncated. Total: {len(content)} chars ...]\n")
                    else:
                        f.write(content)
                else:
                    f.write("[No content scraped]\n")

                f.write("\n\n")

        fact_logger.logger.info(
            f"💾 Saved session report: {filepath}",
            extra={
                "session_id": session_id,
                "num_sources": len(all_scraped_content),
                "num_facts": len(facts) if facts else 0,
                "has_queries": bool(queries_by_fact),
                "multilingual": bool(content_location and content_location.language.lower() != 'english')
            }
        )

        # =========================================================
        # Also save queries as separate JSON for easier parsing
        # =========================================================
        if queries_by_fact:
            queries_json = self._serialize_queries_to_json(queries_by_fact, content_location)
            self.save_session_file(
                session_id,
                "search_queries.json",
                queries_json
            )

        # Upload to R2
        upload_result = {'success': False, 'url': None, 'error': 'R2 upload not attempted'}

        if upload_to_r2:
            try:
                from utils.r2_uploader import R2Uploader

                r2 = R2Uploader()

                # Upload session report
                r2_filename = f"fact-check-sessions/{session_id}/session_report.txt"
                url = r2.upload_file(
                    file_path=str(filepath),
                    r2_filename=r2_filename  # ✅ FIXED: Use r2_filename not r2_key
                )

                if url:
                    upload_result = {'success': True, 'url': url, 'error': None}
                    fact_logger.logger.info(f"☁️ Session report uploaded to R2: {url}")

                    # Also upload queries JSON if it exists
                    queries_json_path = session_path / "search_queries.json"
                    if queries_json_path.exists():
                        r2_queries_filename = f"fact-check-sessions/{session_id}/search_queries.json"
                        r2.upload_file(
                            file_path=str(queries_json_path),
                            r2_filename=r2_queries_filename  # ✅ FIXED: Use r2_filename not r2_key
                        )
                else:
                    upload_result = {'success': False, 'url': None, 'error': 'Upload returned no URL'}

            except ValueError as e:
                # R2Uploader raises ValueError if credentials are missing
                error_msg = str(e)
                fact_logger.logger.warning(f"⚠️ R2 not configured: {error_msg}")
                upload_result = {'success': False, 'url': None, 'error': error_msg}

            except ImportError:
                error_msg = "R2Uploader not available. Install boto3."
                fact_logger.logger.warning(f"⚠️ {error_msg}")
                upload_result = {'success': False, 'url': None, 'error': error_msg}

            except Exception as e:
                error_msg = str(e)
                fact_logger.logger.error(
                    f"❌ Error uploading to R2: {e}",
                    extra={"session_id": session_id, "error": error_msg}
                )
                upload_result = {'success': False, 'url': None, 'error': error_msg}

        return upload_result

    def _serialize_queries_to_json(
        self, 
        queries_by_fact: dict,
        content_location: Optional[Any] = None
    ) -> dict:
        """
        Serialize search queries to a JSON-friendly format

        Args:
            queries_by_fact: Dict mapping fact_id to SearchQueries
            content_location: Optional ContentLocation object

        Returns:
            JSON-serializable dictionary
        """
        result = {
            "generated_at": datetime.now().isoformat(),
            "content_location": None,
            "queries": {}
        }

        # Add content location if available
        if content_location:
            result["content_location"] = {
                "country": content_location.country,
                "country_code": getattr(content_location, 'country_code', ''),
                "language": content_location.language,
                "confidence": content_location.confidence,
                "multilingual_enabled": content_location.language.lower() != 'english'
            }

        # Serialize each fact's queries
        for fact_id, queries in queries_by_fact.items():
            result["queries"][fact_id] = {
                "fact_statement": queries.fact_statement,
                "primary_query": queries.primary_query,
                "alternative_queries": queries.alternative_queries,
                "all_queries": queries.all_queries,
                "search_focus": getattr(queries, 'search_focus', None),
                "key_terms": getattr(queries, 'key_terms', []),
                "expected_sources": getattr(queries, 'expected_sources', []),
                "local_language_used": queries.local_language_used,
                "query_count": len(queries.all_queries)
            }

        return result

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

        # Process all URLs - extract_name is async
        for url in urls:
            try:
                page_title = self.page_titles.get(url)
                name = await extractor.extract_name(url, page_title)
                results[url] = name
            except Exception as e:
                print(f"⚠️ Failed to extract name for {url}: {e}")
                # Fallback to domain extraction
                results[url] = self._extract_domain(url)

        return results

    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc
            return domain.replace('www.', '')
        except:
            return url[:50]

    def _sanitize_url(self, url: str) -> str:
        """Convert URL to safe filename"""
        return url.replace('https://', '').replace('http://', '')\
                  .replace('/', '_').replace(':', '_')[:50]

    def cleanup_old_sessions(self, days: int = 1):
        """Remove sessions older than specified days"""
        # Implementation for cleanup
        pass