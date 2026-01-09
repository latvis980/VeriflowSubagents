# utils/enriched_content_service.py
"""
Enriched Content Service
Combines scraping, metadata extraction, and credibility verification
into a single unified pipeline.

Returns comprehensive article data including:
- Scraped content
- Article metadata (title, author, date)
- Publication credibility information
"""

from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field
from datetime import datetime
from urllib.parse import urlparse
import asyncio

from utils.logger import fact_logger


class EnrichedArticle(BaseModel):
    """Complete enriched article data"""
    
    # Basic info
    url: str
    domain: str
    
    # Scraped content
    content: str
    content_length: int = 0
    
    # Extracted metadata
    title: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[str] = None  # ISO format
    publication_date_raw: Optional[str] = None
    publication_name: Optional[str] = None
    article_type: Optional[str] = None
    section: Optional[str] = None
    metadata_confidence: float = 0.0
    
    # Credibility information
    credibility_tier: int = 3
    credibility_rating: Optional[str] = None
    bias_rating: Optional[str] = None
    factual_reporting: Optional[str] = None
    is_propaganda: bool = False
    special_tags: List[str] = Field(default_factory=list)
    credibility_source: str = "unknown"  # where credibility data came from
    tier_reasoning: Optional[str] = None
    mbfc_url: Optional[str] = None
    
    # Processing metadata
    scraped_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    processing_time_ms: int = 0
    errors: List[str] = Field(default_factory=list)


class EnrichedScrapeResult(BaseModel):
    """Result of enriched scraping operation"""
    success: bool
    article: Optional[EnrichedArticle] = None
    error: Optional[str] = None


class EnrichedContentService:
    """
    Unified service for fetching and enriching article content
    
    Pipeline:
    1. Scrape URL content using BrowserlessScraper
    2. Extract metadata (title, author, date) using ArticleMetadataExtractor
    3. Check publication credibility using SourceCredibilityService
    4. Return complete EnrichedArticle
    """
    
    def __init__(self, config=None):
        """
        Initialize the enriched content service
        
        Args:
            config: Configuration object with API keys
        """
        self.config = config
        
        # Initialize scraper
        try:
            from utils.browserless_scraper import BrowserlessScraper
            self.scraper = BrowserlessScraper(config)
            self.scraper_available = True
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ BrowserlessScraper not available: {e}")
            self.scraper = None
            self.scraper_available = False
        
        # Initialize metadata extractor
        try:
            from utils.article_metadata_extractor import ArticleMetadataExtractor
            self.metadata_extractor = ArticleMetadataExtractor(config)
            self.metadata_available = True
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ ArticleMetadataExtractor not available: {e}")
            self.metadata_extractor = None
            self.metadata_available = False
        
        # Initialize credibility service (will try to load Brave and MBFC dependencies)
        try:
            from utils.source_credibility_service import SourceCredibilityService
            
            # Try to get brave searcher for MBFC lookups
            brave_searcher = None
            try:
                from agents.brave_searcher import BraveSearcher
                brave_searcher = BraveSearcher(config) if config else None
            except Exception:
                pass
            
            self.credibility_service = SourceCredibilityService(
                config=config,
                brave_searcher=brave_searcher,
                scraper=self.scraper
            )
            self.credibility_available = True
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ SourceCredibilityService not available: {e}")
            self.credibility_service = None
            self.credibility_available = False
        
        fact_logger.logger.info(
            "🚀 EnrichedContentService initialized",
            extra={
                "scraper": self.scraper_available,
                "metadata": self.metadata_available,
                "credibility": self.credibility_available
            }
        )
    
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
    
    async def scrape_and_enrich(
        self,
        url: str,
        extract_metadata: bool = True,
        check_credibility: bool = True,
        run_mbfc_if_missing: bool = True
    ) -> EnrichedScrapeResult:
        """
        Scrape a URL and enrich with metadata and credibility data
        
        Args:
            url: URL to scrape
            extract_metadata: Whether to extract article metadata
            check_credibility: Whether to check publication credibility
            run_mbfc_if_missing: Whether to run MBFC lookup if not in cache
            
        Returns:
            EnrichedScrapeResult with complete article data
        """
        import time
        start_time = time.time()
        
        domain = self._extract_domain(url)
        errors = []
        
        # Initialize result
        article = EnrichedArticle(
            url=url,
            domain=domain,
            content=""
        )
        
        try:
            # Step 1: Scrape content
            fact_logger.logger.info(f"📄 Scraping content from {domain}")
            
            if not self.scraper_available or not self.scraper:
                return EnrichedScrapeResult(
                    success=False,
                    error="Scraper not available"
                )
            
            # Initialize browser pool if needed
            await self.scraper._initialize_browser_pool()
            
            # Scrape the URL
            results = await self.scraper.scrape_urls_for_facts([url])
            content = results.get(url, "")
            
            if not content or len(content.strip()) < 100:
                return EnrichedScrapeResult(
                    success=False,
                    error="Could not extract meaningful content from URL"
                )
            
            article.content = content
            article.content_length = len(content)
            
            # Step 2: Extract metadata (parallel with credibility check)
            metadata_task = None
            credibility_task = None
            
            if extract_metadata and self.metadata_available:
                metadata_task = asyncio.create_task(
                    self.metadata_extractor.extract_metadata(url, content)
                )
            
            # Step 3: Check credibility
            if check_credibility and self.credibility_available:
                credibility_task = asyncio.create_task(
                    self.credibility_service.check_credibility(
                        url, 
                        run_mbfc_if_missing=run_mbfc_if_missing
                    )
                )
            
            # Wait for both tasks
            if metadata_task:
                try:
                    metadata = await metadata_task
                    article.title = metadata.title
                    article.author = metadata.author
                    article.publication_date = metadata.publication_date
                    article.publication_date_raw = metadata.publication_date_raw
                    article.publication_name = metadata.publication_name
                    article.article_type = metadata.article_type
                    article.section = metadata.section
                    article.metadata_confidence = metadata.extraction_confidence
                except Exception as e:
                    fact_logger.logger.warning(f"⚠️ Metadata extraction failed: {e}")
                    errors.append(f"Metadata extraction failed: {str(e)}")
            
            if credibility_task:
                try:
                    credibility = await credibility_task
                    article.credibility_tier = credibility.credibility_tier
                    article.credibility_rating = credibility.credibility_rating
                    article.bias_rating = credibility.bias_rating
                    article.factual_reporting = credibility.factual_reporting
                    article.is_propaganda = credibility.is_propaganda
                    article.special_tags = credibility.special_tags
                    article.credibility_source = credibility.source
                    article.tier_reasoning = credibility.tier_reasoning
                    article.mbfc_url = credibility.mbfc_url
                    
                    # Use credibility service's publication name if we didn't extract one
                    if not article.publication_name and credibility.publication_name:
                        article.publication_name = credibility.publication_name
                        
                except Exception as e:
                    fact_logger.logger.warning(f"⚠️ Credibility check failed: {e}")
                    errors.append(f"Credibility check failed: {str(e)}")
            
            # Calculate processing time
            article.processing_time_ms = int((time.time() - start_time) * 1000)
            article.errors = errors
            
            fact_logger.logger.info(
                f"✅ Enriched scrape complete for {domain}",
                extra={
                    "content_length": article.content_length,
                    "title": article.title[:50] if article.title else None,
                    "author": article.author,
                    "date": article.publication_date,
                    "tier": article.credibility_tier,
                    "processing_ms": article.processing_time_ms
                }
            )
            
            return EnrichedScrapeResult(
                success=True,
                article=article
            )
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Enriched scrape failed: {e}")
            return EnrichedScrapeResult(
                success=False,
                error=str(e)
            )
    
    async def scrape_and_enrich_batch(
        self,
        urls: List[str],
        extract_metadata: bool = True,
        check_credibility: bool = True,
        run_mbfc_if_missing: bool = False  # Disable for batch performance
    ) -> Dict[str, EnrichedScrapeResult]:
        """
        Scrape multiple URLs and enrich with metadata and credibility
        
        Args:
            urls: List of URLs to process
            extract_metadata: Whether to extract metadata
            check_credibility: Whether to check credibility
            run_mbfc_if_missing: Whether to run MBFC lookups
            
        Returns:
            Dict mapping URL to EnrichedScrapeResult
        """
        import time
        start_time = time.time()
        
        if not urls:
            return {}
        
        fact_logger.logger.info(f"📦 Starting batch enriched scrape of {len(urls)} URLs")
        
        results = {}
        
        # Step 1: Batch scrape all URLs
        if not self.scraper_available or not self.scraper:
            return {url: EnrichedScrapeResult(success=False, error="Scraper not available") for url in urls}
        
        await self.scraper._initialize_browser_pool()
        scraped_content = await self.scraper.scrape_urls_for_facts(urls)
        
        # Step 2: Batch extract metadata
        metadata_results = {}
        if extract_metadata and self.metadata_available:
            valid_content = {url: content for url, content in scraped_content.items() if content and len(content) > 100}
            if valid_content:
                metadata_results = await self.metadata_extractor.extract_metadata_batch(valid_content)
        
        # Step 3: Batch check credibility
        credibility_results = {}
        if check_credibility and self.credibility_available:
            credibility_results = await self.credibility_service.check_credibility_batch(
                list(scraped_content.keys()),
                run_mbfc_if_missing=run_mbfc_if_missing
            )
        
        # Step 4: Combine results
        for url in urls:
            content = scraped_content.get(url, "")
            
            if not content or len(content.strip()) < 100:
                results[url] = EnrichedScrapeResult(
                    success=False,
                    error="Could not extract meaningful content"
                )
                continue
            
            domain = self._extract_domain(url)
            article = EnrichedArticle(
                url=url,
                domain=domain,
                content=content,
                content_length=len(content)
            )
            
            # Add metadata
            if url in metadata_results:
                metadata = metadata_results[url]
                article.title = metadata.title
                article.author = metadata.author
                article.publication_date = metadata.publication_date
                article.publication_date_raw = metadata.publication_date_raw
                article.publication_name = metadata.publication_name
                article.article_type = metadata.article_type
                article.section = metadata.section
                article.metadata_confidence = metadata.extraction_confidence
            
            # Add credibility
            if url in credibility_results:
                cred = credibility_results[url]
                article.credibility_tier = cred.credibility_tier
                article.credibility_rating = cred.credibility_rating
                article.bias_rating = cred.bias_rating
                article.factual_reporting = cred.factual_reporting
                article.is_propaganda = cred.is_propaganda
                article.special_tags = cred.special_tags
                article.credibility_source = cred.source
                article.tier_reasoning = cred.tier_reasoning
                article.mbfc_url = cred.mbfc_url
                
                if not article.publication_name and cred.publication_name:
                    article.publication_name = cred.publication_name
            
            results[url] = EnrichedScrapeResult(
                success=True,
                article=article
            )
        
        elapsed = time.time() - start_time
        successful = sum(1 for r in results.values() if r.success)
        
        fact_logger.logger.info(
            f"✅ Batch enriched scrape complete: {successful}/{len(urls)} successful in {elapsed:.1f}s"
        )
        
        return results
    
    async def close(self):
        """Clean up resources"""
        if self.scraper:
            await self.scraper.close()


# Factory function
def get_enriched_content_service(config=None) -> EnrichedContentService:
    """Get an enriched content service instance"""
    return EnrichedContentService(config)


# Test function
if __name__ == "__main__":
    import asyncio
    
    print("🧪 Testing Enriched Content Service\n")
    
    service = EnrichedContentService()
    
    async def test():
        result = await service.scrape_and_enrich(
            url="https://www.reuters.com/",
            check_credibility=True,
            run_mbfc_if_missing=False
        )
        
        if result.success:
            print(f"✅ Success!")
            print(f"Title: {result.article.title}")
            print(f"Author: {result.article.author}")
            print(f"Date: {result.article.publication_date}")
            print(f"Tier: {result.article.credibility_tier}")
            print(f"Content: {result.article.content_length} chars")
        else:
            print(f"❌ Failed: {result.error}")
        
        await service.close()
    
    asyncio.run(test())
