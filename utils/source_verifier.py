# utils/source_verifier.py
"""
Source Verifier Utility
Unified utility for extracting and verifying source credibility in Stage 1 of Comprehensive Analysis

This module provides a simplified interface that:
1. Extracts URLs from content (if not provided)
2. Extracts domain from URL
3. Checks source credibility via SourceCredibilityService
4. Returns a standardized SourceVerificationReport

Wraps existing services:
- SourceCredibilityService (MBFC + Supabase)
- BraveSearcher (for MBFC lookups)
- BrowserlessScraper (for scraping MBFC pages)
"""

import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from urllib.parse import urlparse

from utils.logger import fact_logger


# ============================================================================
# OUTPUT MODELS
# ============================================================================

class SourceVerificationReport(BaseModel):
    """
    Standardized report from source verification
    Used in Stage 1 of Comprehensive Analysis
    """
    
    # Source identification
    original_url: Optional[str] = Field(
        default=None,
        description="The URL that was verified"
    )
    domain: Optional[str] = Field(
        default=None,
        description="Extracted domain from URL"
    )
    publication_name: Optional[str] = Field(
        default=None,
        description="Name of the publication if identified"
    )
    
    # Credibility Assessment
    credibility_tier: int = Field(
        default=3,
        ge=1, le=5,
        description="Credibility tier: 1 (most credible) to 5 (least credible)"
    )
    tier_description: str = Field(
        default="Unknown credibility level",
        description="Human-readable tier description"
    )
    credibility_rating: Optional[str] = Field(
        default=None,
        description="Rating: HIGH, MEDIUM, LOW CREDIBILITY"
    )
    
    # Bias Information
    bias_rating: Optional[str] = Field(
        default=None,
        description="Political bias: LEFT, LEFT-CENTER, CENTER, RIGHT-CENTER, RIGHT, FAR-LEFT, FAR-RIGHT"
    )
    bias_score: Optional[float] = Field(
        default=None,
        description="Numeric bias score if available"
    )
    
    # Factual Reporting
    factual_reporting: Optional[str] = Field(
        default=None,
        description="Factual reporting level: HIGH, MOSTLY FACTUAL, MIXED, LOW, VERY LOW"
    )
    factual_score: Optional[float] = Field(
        default=None,
        description="Numeric factual score if available"
    )
    
    # Warning Flags
    is_propaganda: bool = Field(
        default=False,
        description="Whether source is flagged as propaganda"
    )
    special_tags: List[str] = Field(
        default_factory=list,
        description="Special tags: QUESTIONABLE SOURCE, CONSPIRACY-PSEUDOSCIENCE, etc."
    )
    failed_fact_checks: List[str] = Field(
        default_factory=list,
        description="Known failed fact checks for this source"
    )
    
    # Additional Context
    country: Optional[str] = Field(
        default=None,
        description="Country of origin"
    )
    country_freedom_rating: Optional[str] = Field(
        default=None,
        description="Press freedom rating for source country"
    )
    media_type: Optional[str] = Field(
        default=None,
        description="Type of media outlet"
    )
    ownership: Optional[str] = Field(
        default=None,
        description="Ownership information"
    )
    
    # Verification Metadata
    mbfc_url: Optional[str] = Field(
        default=None,
        description="URL to MBFC page for this source"
    )
    verification_source: str = Field(
        default="not_verified",
        description="Where data came from: mbfc, supabase_cache, propaganda_list, fallback, not_verified"
    )
    tier_reasoning: Optional[str] = Field(
        default=None,
        description="Explanation for tier assignment"
    )
    
    # Processing Metadata
    verified_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    verification_successful: bool = Field(
        default=False,
        description="Whether verification completed successfully"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if verification failed"
    )


class SourceVerifierResult(BaseModel):
    """Complete result from source verification"""
    report: SourceVerificationReport
    urls_found: List[str] = Field(default_factory=list)
    processing_time_ms: int = 0


# ============================================================================
# TIER DESCRIPTIONS
# ============================================================================

TIER_DESCRIPTIONS = {
    1: "Highly Credible - Official sources, major wire services, highly reputable news",
    2: "Credible - Reputable mainstream media with strong factual reporting",
    3: "Mixed - Requires verification, may have bias or mixed factual reporting",
    4: "Low Credibility - Significant bias issues or poor factual reporting",
    5: "Unreliable - Propaganda, conspiracy, or known disinformation source"
}


# ============================================================================
# SOURCE VERIFIER CLASS
# ============================================================================

class SourceVerifier:
    """
    Unified source verification for Comprehensive Analysis Stage 1
    
    Provides simplified interface to:
    1. Extract URLs from content
    2. Check source credibility via existing services
    3. Return standardized SourceVerificationReport
    """
    
    def __init__(self, config=None):
        """
        Initialize Source Verifier
        
        Args:
            config: Configuration object with API keys
        """
        self.config = config
        self._credibility_service = None
        self._brave_searcher = None
        self._scraper = None
        
        fact_logger.logger.info("✅ SourceVerifier initialized")
    
    async def _get_credibility_service(self):
        """Lazy initialization of credibility service"""
        if self._credibility_service is None:
            from utils.source_credibility_service import SourceCredibilityService
            
            # Try to get brave searcher for MBFC lookups
            try:
                from utils.brave_searcher import BraveSearcher
                if self.config and hasattr(self.config, 'brave_api_key') and self.config.brave_api_key:
                    self._brave_searcher = BraveSearcher(self.config)
            except Exception as e:
                fact_logger.logger.warning(f"⚠️ BraveSearcher not available: {e}")
            
            # Try to get scraper for MBFC page scraping
            try:
                from utils.browserless_scraper import BrowserlessScraper
                if self.config:
                    self._scraper = BrowserlessScraper(self.config)
            except Exception as e:
                fact_logger.logger.warning(f"⚠️ BrowserlessScraper not available: {e}")
            
            self._credibility_service = SourceCredibilityService(
                config=self.config,
                brave_searcher=self._brave_searcher,
                scraper=self._scraper
            )
        
        return self._credibility_service
    
    def extract_urls_from_content(self, content: str) -> List[str]:
        """
        Extract all URLs from content
        
        Args:
            content: Text content to extract URLs from
            
        Returns:
            List of unique URLs found
        """
        urls = []
        
        # HTML anchor tags
        html_pattern = r'<\s*a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>'
        urls.extend(re.findall(html_pattern, content, re.IGNORECASE))
        
        # Markdown reference links: [1]: https://...
        markdown_ref_pattern = r'^\s*\[\d+\]\s*:\s*(https?://[^\s]+)'
        urls.extend(re.findall(markdown_ref_pattern, content, re.MULTILINE))
        
        # Inline markdown links: [text](url)
        inline_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        urls.extend([url for _, url in re.findall(inline_pattern, content)])
        
        # Plain URLs
        plain_url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\].,;:!?]'
        urls.extend(re.findall(plain_url_pattern, content))
        
        # Deduplicate and clean
        cleaned_urls = []
        for url in urls:
            url = url.strip()
            if url and url not in cleaned_urls:
                cleaned_urls.append(url)
        
        return cleaned_urls
    
    def extract_domain(self, url: str) -> Optional[str]:
        """
        Extract clean domain from URL
        
        Args:
            url: URL to extract domain from
            
        Returns:
            Domain string or None
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain if domain else None
        except Exception:
            return None
    
    def _get_primary_url(self, urls: List[str]) -> Optional[str]:
        """
        Determine the primary/most important URL from a list
        Prioritizes news domains and main article URLs
        
        Args:
            urls: List of URLs
            
        Returns:
            Primary URL or None
        """
        if not urls:
            return None
        
        # Priority domains (news/credible sources)
        priority_domains = [
            'reuters.com', 'apnews.com', 'bbc.com', 'bbc.co.uk',
            'nytimes.com', 'washingtonpost.com', 'wsj.com',
            'theguardian.com', 'cnn.com', 'foxnews.com',
            'politico.com', 'npr.org', 'bloomberg.com'
        ]
        
        # First, look for priority domains
        for url in urls:
            domain = self.extract_domain(url)
            if domain and any(pd in domain for pd in priority_domains):
                return url
        
        # Otherwise, return the first URL that looks like an article
        # (not social media, not generic homepage)
        social_domains = ['twitter.com', 'x.com', 'facebook.com', 'instagram.com', 'tiktok.com']
        for url in urls:
            domain = self.extract_domain(url)
            if domain and not any(sd in domain for sd in social_domains):
                # Check if it's not just a homepage
                parsed = urlparse(url)
                if parsed.path and len(parsed.path) > 5:
                    return url
        
        # Fallback to first URL
        return urls[0]
    
    async def verify_source(
        self,
        url: Optional[str] = None,
        content: Optional[str] = None,
        run_mbfc_if_missing: bool = True
    ) -> SourceVerifierResult:
        """
        Verify source credibility
        
        Args:
            url: URL to verify (if known)
            content: Content to extract URL from (if url not provided)
            run_mbfc_if_missing: Whether to run MBFC lookup if not in cache
            
        Returns:
            SourceVerifierResult with verification report
        """
        import time
        start_time = time.time()
        
        urls_found = []
        
        try:
            # Step 1: Get URL to verify
            if url:
                target_url = url
            elif content:
                urls_found = self.extract_urls_from_content(content)
                target_url = self._get_primary_url(urls_found)
                if not target_url:
                    fact_logger.logger.info("ℹ️ No URLs found in content for source verification")
                    return SourceVerifierResult(
                        report=SourceVerificationReport(
                            verification_source="not_verified",
                            verification_successful=False,
                            error="No URLs found in content"
                        ),
                        urls_found=urls_found,
                        processing_time_ms=int((time.time() - start_time) * 1000)
                    )
            else:
                return SourceVerifierResult(
                    report=SourceVerificationReport(
                        verification_source="not_verified",
                        verification_successful=False,
                        error="No URL or content provided"
                    ),
                    urls_found=[],
                    processing_time_ms=int((time.time() - start_time) * 1000)
                )
            
            # Step 2: Extract domain
            domain = self.extract_domain(target_url)
            if not domain:
                return SourceVerifierResult(
                    report=SourceVerificationReport(
                        original_url=target_url,
                        verification_source="not_verified",
                        verification_successful=False,
                        error="Could not extract domain from URL"
                    ),
                    urls_found=urls_found,
                    processing_time_ms=int((time.time() - start_time) * 1000)
                )
            
            fact_logger.logger.info(
                f"🔍 Verifying source: {domain}",
                extra={"url": target_url, "domain": domain}
            )
            
            # Step 3: Check credibility via service
            try:
                service = await self._get_credibility_service()
                cred_result = await service.check_credibility(
                    url=target_url,
                    run_mbfc_if_missing=run_mbfc_if_missing
                )
                
                # Convert to SourceVerificationReport
                report = SourceVerificationReport(
                    original_url=target_url,
                    domain=cred_result.domain,
                    publication_name=cred_result.publication_name,
                    
                    credibility_tier=cred_result.credibility_tier,
                    tier_description=TIER_DESCRIPTIONS.get(
                        cred_result.credibility_tier, 
                        "Unknown credibility level"
                    ),
                    credibility_rating=cred_result.credibility_rating,
                    
                    bias_rating=cred_result.bias_rating,
                    bias_score=cred_result.bias_score,
                    
                    factual_reporting=cred_result.factual_reporting,
                    factual_score=cred_result.factual_score,
                    
                    is_propaganda=cred_result.is_propaganda,
                    special_tags=cred_result.special_tags,
                    failed_fact_checks=cred_result.failed_fact_checks,
                    
                    country=cred_result.country,
                    country_freedom_rating=cred_result.country_freedom_rating,
                    media_type=cred_result.media_type,
                    ownership=cred_result.ownership,
                    
                    mbfc_url=cred_result.mbfc_url,
                    verification_source=cred_result.source,
                    tier_reasoning=cred_result.tier_reasoning,
                    
                    verification_successful=True
                )
                
                fact_logger.logger.info(
                    f"✅ Source verified: {domain} (Tier {cred_result.credibility_tier})",
                    extra={
                        "tier": cred_result.credibility_tier,
                        "source": cred_result.source,
                        "bias": cred_result.bias_rating
                    }
                )
                
            except Exception as e:
                fact_logger.logger.warning(f"⚠️ Credibility check failed, using fallback: {e}")
                
                # Return partial report with what we know
                report = SourceVerificationReport(
                    original_url=target_url,
                    domain=domain,
                    credibility_tier=3,
                    tier_description=TIER_DESCRIPTIONS[3],
                    verification_source="fallback",
                    verification_successful=False,
                    error=str(e)
                )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return SourceVerifierResult(
                report=report,
                urls_found=urls_found or [target_url],
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Source verification failed: {e}")
            
            return SourceVerifierResult(
                report=SourceVerificationReport(
                    verification_source="not_verified",
                    verification_successful=False,
                    error=str(e)
                ),
                urls_found=urls_found,
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
    
    async def close(self):
        """Clean up resources"""
        if self._scraper:
            try:
                await self._scraper.close()
            except Exception as e:
                fact_logger.logger.warning(f"⚠️ Error closing scraper: {e}")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def get_source_verifier(config=None) -> SourceVerifier:
    """
    Factory function to get a SourceVerifier instance
    
    Args:
        config: Configuration object
        
    Returns:
        SourceVerifier instance
    """
    return SourceVerifier(config)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def test():
        verifier = SourceVerifier()
        
        # Test URL extraction
        test_content = """
        According to recent reports from Reuters <a href="https://www.reuters.com/article/test">source</a>,
        the market is showing signs of recovery. The New York Times also reported similar findings
        [1]: https://www.nytimes.com/2024/test-article
        """
        
        print("Testing URL extraction...")
        urls = verifier.extract_urls_from_content(test_content)
        print(f"Found URLs: {urls}")
        
        # Test source verification
        print("\nTesting source verification...")
        result = await verifier.verify_source(url="https://www.reuters.com/article")
        
        print(f"Domain: {result.report.domain}")
        print(f"Tier: {result.report.credibility_tier}")
        print(f"Source: {result.report.verification_source}")
        print(f"Success: {result.report.verification_successful}")
        
        await verifier.close()
    
    asyncio.run(test())
