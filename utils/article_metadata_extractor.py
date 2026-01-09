# utils/article_metadata_extractor.py
"""
Article Metadata Extractor
Extracts structured metadata from scraped article content:
- Publication date
- Author/journalist name
- Article title
- Publication name

Uses GPT-4o-mini for intelligent extraction from various formats
"""

from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from urllib.parse import urlparse
import re
import json

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

from utils.logger import fact_logger


class ArticleMetadata(BaseModel):
    """Structured metadata extracted from an article"""
    url: str
    domain: str

    # Core metadata
    title: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[str] = None  # ISO format when possible
    publication_date_raw: Optional[str] = None  # Original format from article

    # Publication info
    publication_name: Optional[str] = None

    # Additional context
    article_type: Optional[str] = None  # news, opinion, analysis, press release, etc.
    section: Optional[str] = None  # politics, business, sports, etc.

    # Extraction metadata
    extraction_confidence: float = 0.0
    extraction_method: str = "ai"  # "ai", "structured_data", "fallback"


class ArticleMetadataExtractor:
    """
    Extract metadata from scraped article content using AI

    Flow:
    1. First try to extract from structured data patterns (JSON-LD, meta tags)
    2. If not found, use AI to extract from content
    3. Normalize dates to ISO format
    """

    def __init__(self, config=None):
        """
        Initialize extractor

        Args:
            config: Configuration object with API keys
        """
        self.config = config

        # Initialize LLM for extraction
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",  # Fast and cheap for extraction
            temperature=0
        ).bind(response_format={"type": "json_object"})

        # Cache for extracted metadata
        self.metadata_cache: Dict[str, ArticleMetadata] = {}

        # Build extraction prompt
        self._init_prompts()

        fact_logger.logger.info("✅ ArticleMetadataExtractor initialized")

    def _init_prompts(self):
        """Initialize extraction prompts"""
        self.extraction_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at extracting metadata from news articles and web content.

Your task: Extract structured metadata from the article content provided.

EXTRACT THESE FIELDS:
1. title: The main headline/title of the article
2. author: The journalist/writer name(s). Look for bylines like "By John Smith", "Written by...", "Author: ..."
3. publication_date: When the article was published. Look for dates near the title or byline.
4. publication_name: The name of the news outlet/publication
5. article_type: One of: news, opinion, editorial, analysis, press_release, blog, feature, interview, review
6. section: The section/category if visible (politics, business, sports, technology, etc.)

DATE EXTRACTION RULES:
- Convert dates to ISO format (YYYY-MM-DD) when possible
- If you see "January 15, 2024" → "2024-01-15"
- If you see "15/01/2024" → "2024-01-15" (assume DD/MM/YYYY for non-US sources)
- If you see "1 hour ago", "yesterday" → leave as-is in publication_date_raw, set publication_date to null
- Preserve the original date string in publication_date_raw

AUTHOR EXTRACTION RULES:
- Extract full names when available
- If multiple authors: "John Smith and Jane Doe" or "John Smith, Jane Doe"
- Remove prefixes like "By", "Written by", "Author:"
- If author is clearly a wire service (AP, Reuters, AFP), include it

CONFIDENCE SCORING (0.0 - 1.0):
- 1.0: All fields clearly found with high certainty
- 0.8: Most fields found, some uncertainty
- 0.5: Partial extraction, significant guessing
- 0.3: Only basic info extractable
- 0.0: Could not extract meaningful metadata

Return ONLY valid JSON."""),
            ("user", """Extract metadata from this article:

URL: {url}
Domain: {domain}

CONTENT:
{content}

Return JSON with these fields:
{{
    "title": "article title or null",
    "author": "author name(s) or null",
    "publication_date": "YYYY-MM-DD or null if unclear",
    "publication_date_raw": "original date string as found or null",
    "publication_name": "publication name or null",
    "article_type": "news/opinion/analysis/etc or null",
    "section": "section name or null",
    "extraction_confidence": 0.0-1.0
}}""")
        ])

    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _try_structured_extraction(self, content: str, url: str) -> Optional[Dict]:
        """
        Try to extract metadata from structured data patterns

        Args:
            content: Scraped content
            url: Article URL

        Returns:
            Dict with extracted metadata or None if not found
        """
        try:
            metadata = {}

            # Look for common date patterns in content
            date_patterns = [
                # ISO format
                r'(\d{4}-\d{2}-\d{2})',
                # US format: January 15, 2024
                r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
                # Short month: Jan 15, 2024
                r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4})',
                # European: 15 January 2024
                r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
            ]

            for pattern in date_patterns:
                match = re.search(pattern, content[:3000], re.IGNORECASE)
                if match:
                    metadata['publication_date_raw'] = match.group(1)
                    metadata['publication_date'] = self._normalize_date(match.group(1))
                    break

            # Look for author byline patterns
            byline_patterns = [
                r'[Bb]y\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
                r'[Aa]uthor:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
                r'[Ww]ritten\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            ]

            for pattern in byline_patterns:
                match = re.search(pattern, content[:5000])
                if match:
                    author = match.group(1).strip()
                    # Filter out common false positives
                    if author.lower() not in ['the', 'a', 'an', 'in', 'on', 'at']:
                        metadata['author'] = author
                        break

            # Check if we found anything useful
            if metadata.get('publication_date') or metadata.get('author'):
                metadata['extraction_method'] = 'structured_data'
                metadata['extraction_confidence'] = 0.6
                return metadata

            return None

        except Exception as e:
            fact_logger.logger.debug(f"Structured extraction failed: {e}")
            return None

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """
        Normalize date string to ISO format (YYYY-MM-DD)

        Args:
            date_str: Raw date string

        Returns:
            ISO formatted date or None
        """
        if not date_str:
            return None

        # Already ISO format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Common date formats to try
        formats = [
            '%B %d, %Y',      # January 15, 2024
            '%B %d %Y',       # January 15 2024
            '%b %d, %Y',      # Jan 15, 2024
            '%b %d %Y',       # Jan 15 2024
            '%b. %d, %Y',     # Jan. 15, 2024
            '%d %B %Y',       # 15 January 2024
            '%d %b %Y',       # 15 Jan 2024
            '%m/%d/%Y',       # 01/15/2024
            '%d/%m/%Y',       # 15/01/2024
            '%Y/%m/%d',       # 2024/01/15
        ]

        # Clean the date string
        clean_date = date_str.strip()

        for fmt in formats:
            try:
                parsed = datetime.strptime(clean_date, fmt)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return None

    async def extract_metadata(
        self, 
        url: str, 
        content: str,
        use_cache: bool = True
    ) -> ArticleMetadata:
        """
        Extract metadata from article content

        Args:
            url: Article URL
            content: Scraped article content
            use_cache: Whether to use cached results

        Returns:
            ArticleMetadata object with extracted information
        """
        # Check cache
        if use_cache and url in self.metadata_cache:
            fact_logger.logger.debug(f"📦 Using cached metadata for {url}")
            return self.metadata_cache[url]

        domain = self._extract_domain(url)

        # Initialize with basic info
        metadata = ArticleMetadata(
            url=url,
            domain=domain
        )

        if not content or len(content) < 50:
            fact_logger.logger.warning(f"⚠️ Content too short for metadata extraction: {url}")
            metadata.extraction_confidence = 0.0
            metadata.extraction_method = "fallback"
            return metadata

        try:
            # First try structured extraction (faster, no API call)
            structured = self._try_structured_extraction(content, url)

            # Use AI for full extraction
            fact_logger.logger.info(f"🔍 Extracting metadata from {domain}")

            # Limit content to avoid token limits
            content_sample = content[:8000]  # First ~8000 chars usually have metadata

            chain = self.extraction_prompt | self.llm

            result = await chain.ainvoke({
                "url": url,
                "domain": domain,
                "content": content_sample
            })

            # Parse JSON response
            extracted = json.loads(result.content)

            # Update metadata object
            metadata.title = extracted.get('title')
            metadata.author = extracted.get('author')
            metadata.publication_date = extracted.get('publication_date')
            metadata.publication_date_raw = extracted.get('publication_date_raw')
            metadata.publication_name = extracted.get('publication_name')
            metadata.article_type = extracted.get('article_type')
            metadata.section = extracted.get('section')
            metadata.extraction_confidence = extracted.get('extraction_confidence', 0.5)
            metadata.extraction_method = "ai"

            # Merge with structured data if we found some
            if structured:
                # Prefer structured date if AI didn't find one
                if not metadata.publication_date and structured.get('publication_date'):
                    metadata.publication_date = structured['publication_date']
                    metadata.publication_date_raw = structured.get('publication_date_raw')
                # Prefer structured author if AI didn't find one
                if not metadata.author and structured.get('author'):
                    metadata.author = structured['author']

            fact_logger.logger.info(
                f"✅ Metadata extracted for {domain}",
                extra={
                    "title": metadata.title[:50] if metadata.title else None,
                    "author": metadata.author,
                    "date": metadata.publication_date,
                    "confidence": metadata.extraction_confidence
                }
            )

            # Cache result
            self.metadata_cache[url] = metadata

            return metadata

        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Metadata extraction failed for {url}: {e}")

            # Return basic metadata with low confidence
            metadata.extraction_confidence = 0.1
            metadata.extraction_method = "fallback"

            # At least try to get title from first line
            lines = content.strip().split('\n')
            if lines:
                first_line = lines[0].strip()
                if first_line.startswith('#'):
                    metadata.title = first_line.lstrip('#').strip()[:200]

            return metadata

    async def extract_metadata_batch(
        self, 
        url_content_map: Dict[str, str]
    ) -> Dict[str, ArticleMetadata]:
        """
        Extract metadata from multiple articles

        Args:
            url_content_map: Dict mapping URL to content

        Returns:
            Dict mapping URL to ArticleMetadata
        """
        import asyncio

        results = {}

        # Process in parallel with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Limit concurrent extractions

        async def extract_with_semaphore(url: str, content: str):
            async with semaphore:
                return url, await self.extract_metadata(url, content)

        tasks = [
            extract_with_semaphore(url, content)
            for url, content in url_content_map.items()
        ]

        for coro in asyncio.as_completed(tasks):
            try:
                url, metadata = await coro
                results[url] = metadata
            except Exception as e:
                fact_logger.logger.error(f"❌ Batch extraction failed: {e}")

        return results


# Factory function
def get_metadata_extractor(config=None) -> ArticleMetadataExtractor:
    """Get a metadata extractor instance"""
    return ArticleMetadataExtractor(config)


# Test function
if __name__ == "__main__":
    import asyncio

    print("🧪 Testing Article Metadata Extractor\n")

    extractor = ArticleMetadataExtractor()

    # Test content
    test_content = """
    # Breaking: Tech Giants Report Record Earnings

    By Sarah Johnson | January 15, 2024

    Technology Reporter

    SAN FRANCISCO — Major technology companies reported record-breaking 
    quarterly earnings today, with combined revenues exceeding expectations...
    """

    async def test():
        result = await extractor.extract_metadata(
            url="https://example.com/tech-earnings-2024",
            content=test_content
        )
        print(f"Title: {result.title}")
        print(f"Author: {result.author}")
        print(f"Date: {result.publication_date}")
        print(f"Confidence: {result.extraction_confidence}")

    asyncio.run(test())