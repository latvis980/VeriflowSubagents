# utils/brave_searcher.py
"""
Brave Search Agent
Executes web searches using Brave Search API for fact verification

FEATURES:
- Supports exact phrase matching with quotes ("Elon Musk")
- Full search operator support: +, -, site:, intitle:, inbody:
- Independent index (30B+ pages), not a Google scraper
- Privacy-focused, no tracking
"""

import asyncio
import time
import httpx
from typing import List, Dict, Optional
from pydantic import BaseModel
from langsmith import traceable

from utils.logger import fact_logger


class BraveSearchResult(BaseModel):
    """Single search result from Brave"""
    url: str
    title: str
    content: str
    score: float
    published_date: Optional[str] = None


class BraveSearchResults:
    """Container for Brave search results"""
    def __init__(
        self,
        query: str,
        results: List[Dict],
        answer: Optional[str] = None,
        search_time: float = 0.0
    ):
        self.query = query
        self.answer = answer
        self.search_time = search_time
        
        # Parse results from Brave's format
        self.results = []
        for i, r in enumerate(results):
            # Brave returns 'description' instead of 'content'
            # and doesn't have a relevance score, so we calculate one based on position
            self.results.append({
                'url': r.get('url', ''),
                'title': r.get('title', ''),
                'content': r.get('description', ''),
                'score': 1.0 - (i * 0.1),  # Position-based score: 1.0, 0.9, 0.8, ...
                'published_date': r.get('page_age') or r.get('age')
            })
    
    def get_urls(self) -> List[str]:
        """Extract all URLs from results"""
        return [r['url'] for r in self.results]
    
    def get_top_results(self, n: int = 5) -> List[Dict]:
        """Get top N results sorted by score"""
        return sorted(self.results, key=lambda x: x['score'], reverse=True)[:n]


class BraveSearcher:
    """
    Web search agent using Brave Search API
    
    Features:
    - Async search support
    - Exact phrase matching with quotes
    - Full search operator support (+, -, site:, intitle:, etc.)
    - Configurable result limits
    - Search domain filtering
    - Result aggregation across queries
    
    Search Operators Supported:
    - "phrase" : Exact phrase match
    - +term    : Must include term
    - -term    : Exclude term
    - site:    : Search within domain
    - intitle: : Term must be in title
    - inbody:  : Term must be in body
    """

    BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, config, max_results: int = 5):
        """
        Initialize Brave searcher

        Args:
            config: Configuration object with brave_api_key
            max_results: Maximum results per search (default: 5)
        """
        self.config = config
        self.max_results = max_results
        self.api_key = config.brave_api_key

        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not configured")

        # Initialize async HTTP client
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json"
            }
        )

        fact_logger.logger.info("✅ Brave Search client initialized")

        # Search statistics
        self.stats = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "total_results": 0,
            "avg_search_time": 0.0,
            "total_search_time": 0.0
        }

        fact_logger.log_component_start(
            "BraveSearcher",
            max_results=max_results
        )

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    @traceable(
        name="brave_search",
        run_type="tool",
        tags=["web-search", "brave"]
    )
    async def search(
        self,
        query: str,
        search_depth: str = "advanced",  # Kept for compatibility, not used by Brave
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        country: str = "us",
        search_lang: str = "en"
    ) -> BraveSearchResults:
        """
        Execute a single web search using Brave Search API

        Args:
            query: Search query string (supports operators like "exact phrase")
            search_depth: Ignored (kept for API compatibility with Tavily)
            include_domains: List of domains to include (converted to site: operators)
            exclude_domains: List of domains to exclude (converted to -site: operators)
            country: Country code for results (default: "us")
            search_lang: Language code (default: "en")

        Returns:
            BraveSearchResults object
        """
        start_time = time.time()
        self.stats["total_searches"] += 1

        # Build query with domain filters
        modified_query = query
        
        # Add site: operators for included domains
        if include_domains:
            # Use OR between multiple domains
            site_filter = " OR ".join([f"site:{domain}" for domain in include_domains])
            modified_query = f"({site_filter}) {query}"
            fact_logger.logger.debug(f"Including domains: {include_domains}")

        # Add -site: operators for excluded domains
        if exclude_domains:
            for domain in exclude_domains:
                modified_query = f"{modified_query} -site:{domain}"
            fact_logger.logger.debug(f"Excluding domains: {exclude_domains}")

        fact_logger.logger.info(
            f"🔍 Brave search: {modified_query}",
            extra={
                "query": modified_query,
                "original_query": query,
                "max_results": self.max_results
            }
        )

        try:
            # Build search parameters
            params = {
                "q": modified_query,
                "count": self.max_results,
                "country": country,
                "search_lang": search_lang,
                "text_decorations": False,  # Don't add <strong> tags
                "spellcheck": True
            }

            # Execute search
            response = await self.client.get(self.BRAVE_API_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            search_time = time.time() - start_time

            # Extract web results
            web_results = []
            if "web" in data and "results" in data["web"]:
                web_results = data["web"]["results"]

            # Parse results
            results = BraveSearchResults(
                query=query,
                results=web_results,
                answer=None,  # Brave doesn't provide AI answers in basic tier
                search_time=search_time
            )

            # Update statistics
            self.stats["successful_searches"] += 1
            self.stats["total_results"] += len(results.results)
            self.stats["total_search_time"] += search_time
            self.stats["avg_search_time"] = (
                self.stats["total_search_time"] / self.stats["successful_searches"]
            )

            fact_logger.logger.info(
                f"✅ Search complete: {len(results.results)} results in {search_time:.2f}s",
                extra={
                    "query": query,
                    "num_results": len(results.results),
                    "search_time": search_time
                }
            )

            return results

        except httpx.HTTPStatusError as e:
            search_time = time.time() - start_time
            self.stats["failed_searches"] += 1

            error_msg = f"Brave API error: {e.response.status_code}"
            if e.response.status_code == 429:
                error_msg = "Brave API rate limit exceeded"
            elif e.response.status_code == 401:
                error_msg = "Brave API authentication failed - check API key"

            fact_logger.logger.error(
                f"❌ {error_msg}",
                extra={
                    "query": query,
                    "search_time": search_time,
                    "status_code": e.response.status_code
                }
            )

            return BraveSearchResults(
                query=query,
                results=[],
                answer=None,
                search_time=search_time
            )

        except Exception as e:
            search_time = time.time() - start_time
            self.stats["failed_searches"] += 1

            fact_logger.logger.error(
                f"❌ Brave search failed: {e}",
                extra={
                    "query": query,
                    "search_time": search_time,
                    "error": str(e)
                }
            )

            return BraveSearchResults(
                query=query,
                results=[],
                answer=None,
                search_time=search_time
            )

    @traceable(
        name="brave_multi_search",
        run_type="chain",
        tags=["web-search", "brave", "batch"]
    )
    @traceable(
        name="brave_multi_search",
        run_type="chain",
        tags=["web-search", "brave", "batch"]
    )
    async def search_multiple(
        self,
        queries: List[str],
        search_depth: str = "advanced",
        max_concurrent: int = 1,
        rate_limit_delay: float = 1.1  # Seconds between requests (confirable — change to 0 for paid tier)
    ) -> Dict[str, BraveSearchResults]:
        """
        Execute multiple searches with configurable rate limiting

        Args:
            queries: List of search query strings
            search_depth: Ignored (kept for API compatibility)
            max_concurrent: Maximum concurrent searches
            rate_limit_delay: Seconds to wait between requests (1.1 for free tier, 0 for paid)

        Returns:
            Dictionary mapping query to BraveSearchResults
        """
        fact_logger.logger.info(
            f"🔍 Executing {len(queries)} Brave searches",
            extra={
                "num_queries": len(queries), 
                "rate_limit_delay": rate_limit_delay
            }
        )

        results = {}

        for i, query in enumerate(queries):
            # Rate limiting delay between requests
            if i > 0 and rate_limit_delay > 0:
                fact_logger.logger.debug(f"⏳ Rate limit delay: {rate_limit_delay}s")
                await asyncio.sleep(rate_limit_delay)

            try:
                result = await self.search(query, search_depth=search_depth)
                results[query] = result
            except Exception as e:
                fact_logger.logger.error(
                    f"❌ Search failed for query: {query}",
                    extra={"query": query, "error": str(e)}
                )
                results[query] = BraveSearchResults(query=query, results=[])

        successful = len([r for r in results.values() if r.results])
        fact_logger.logger.info(
            f"✅ Multi-search complete: {successful}/{len(queries)} successful",
            extra={
                "total_queries": len(queries),
                "successful": successful,
                "failed": len(queries) - successful
            }
        )

        return results


    def get_stats(self) -> Dict:
        """Get search statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset search statistics"""
        self.stats = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "total_results": 0,
            "avg_search_time": 0.0,
            "total_search_time": 0.0
        }
