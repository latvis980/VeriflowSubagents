# utils/article_metadata_extractor.py
"""
Article Metadata Extractor
Extracts structured metadata from scraped article content using AI.

Clean architecture:
- Prompts stored in prompts/article_metadata_extractor_prompts.py
- AI handles all pattern recognition (dates, authors, titles)
- No hardcoded language-specific patterns
"""

from typing import Dict, Optional
from pydantic import BaseModel
from urllib.parse import urlparse
import json

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from prompts.article_metadata_extractor_prompts import get_metadata_extraction_prompts
from utils.logger import fact_logger


class ArticleMetadata(BaseModel):
    """Structured metadata extracted from an article"""
    url: str
    domain: str

    # Core metadata
    title: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[str] = None  # ISO format YYYY-MM-DD
    publication_date_raw: Optional[str] = None  # Original format from article

    # Publication info
    publication_name: Optional[str] = None

    # Additional context
    article_type: Optional[str] = None  # news, opinion, analysis, etc.
    section: Optional[str] = None  # politics, business, sports, etc.

    # Extraction metadata
    extraction_confidence: float = 0.0
    extraction_method: str = "ai"


class ArticleMetadataExtractor:
    """
    Extract metadata from scraped article content using AI.

    All pattern recognition (dates, bylines, titles) is handled by the LLM,
    making this scalable across languages and formats.
    """

    # Content limits
    CONTENT_SAMPLE_SIZE = 8000  # First ~8000 chars typically contain metadata
    MIN_CONTENT_LENGTH = 50

    def __init__(self, config=None):
        """
        Initialize extractor.

        Args:
            config: Configuration object with API keys
        """
        self.config = config

        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        # Load prompts from dedicated file
        prompts = get_metadata_extraction_prompts()
        self.extraction_prompt = ChatPromptTemplate.from_messages([
            ("system", prompts["system"]),
            ("user", prompts["user"])
        ])

        # In-memory cache
        self.metadata_cache: Dict[str, ArticleMetadata] = {}

        fact_logger.logger.info("✅ ArticleMetadataExtractor initialized")

    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    async def extract_metadata(
        self,
        url: str,
        content: str,
        use_cache: bool = True
    ) -> ArticleMetadata:
        """
        Extract metadata from article content.

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
        metadata = ArticleMetadata(url=url, domain=domain)

        # Validate content
        if not content or len(content) < self.MIN_CONTENT_LENGTH:
            fact_logger.logger.warning(f"⚠️ Content too short for metadata extraction: {url}")
            metadata.extraction_confidence = 0.0
            metadata.extraction_method = "fallback"
            return metadata

        try:
            fact_logger.logger.info(f"🔍 Extracting metadata from {domain}")

            # Sample content (metadata typically in header area)
            content_sample = content[:self.CONTENT_SAMPLE_SIZE]

            # Run AI extraction
            chain = self.extraction_prompt | self.llm
            result = await chain.ainvoke({
                "url": url,
                "domain": domain,
                "content": content_sample
            })

            # Parse response
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

            metadata.extraction_confidence = 0.1
            metadata.extraction_method = "fallback"
            return metadata

    async def extract_metadata_batch(
        self,
        url_content_map: Dict[str, str]
    ) -> Dict[str, ArticleMetadata]:
        """
        Extract metadata from multiple articles in parallel.

        Args:
            url_content_map: Dict mapping URL to content

        Returns:
            Dict mapping URL to ArticleMetadata
        """
        import asyncio

        results = {}
        semaphore = asyncio.Semaphore(5)  # Limit concurrent API calls

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


def get_metadata_extractor(config=None) -> ArticleMetadataExtractor:
    """Factory function to get a metadata extractor instance."""
    return ArticleMetadataExtractor(config)