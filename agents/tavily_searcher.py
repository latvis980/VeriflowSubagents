# agents/tavily_searcher.py
"""
Tavily Search Agent
Executes web searches using Tavily API for fact verification
"""

import asyncio
import time
from typing import List, Dict, Optional
from pydantic import BaseModel
from tavily import TavilyClient, AsyncTavilyClient
from langsmith import traceable

from utils.logger import fact_logger

class TavilySearchResult(BaseModel):
    """Single search result from Tavily"""
    url: str
    title: str
    content: str
    score: float
    published_date: Optional[str] = None

class TavilySearchResults:
    """Container for Tavily search results"""
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
        
        # Parse results
        self.results = []
        for r in results:
            self.results.append({
                'url': r.get('url', ''),
                'title': r.get('title', ''),
                'content': r.get('content', ''),
                'score': r.get('score', 0.0),
                'published_date': r.get('published_date')
            })
    
    def get_urls(self) -> List[str]:
        """Extract all URLs from results"""
        return [r['url'] for r in self.results]
    
    def get_top_results(self, n: int = 5) -> List[Dict]:
        """Get top N results sorted by score"""
        return sorted(self.results, key=lambda x: x['score'], reverse=True)[:n]

class TavilySearcher:
    """
    Web search agent using Tavily API
    
    Features:
    - Async search support
    - Configurable result limits
    - Search domain filtering
    - Result aggregation across queries
    """

    def __init__(self, config, max_results: int = 5):
        """
        Initialize Tavily searcher

        Args:
            config: Configuration object with tavily_api_key
            max_results: Maximum results per search (default: 5)
        """
        self.config = config
        self.max_results = max_results

        # Initialize Tavily clients
        try:
            self.client = TavilyClient(api_key=config.tavily_api_key)
            self.async_client = AsyncTavilyClient(api_key=config.tavily_api_key)
            fact_logger.logger.info("✅ Tavily client initialized")
        except Exception as e:
            fact_logger.logger.error(f"❌ Failed to initialize Tavily client: {e}")
            raise

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
            "TavilySearcher",
            max_results=max_results
        )

    @traceable(
        name="tavily_search",
        run_type="tool",
        tags=["web-search", "tavily"]
    )
    async def search(
        self,
        query: str,
        search_depth: str = "advanced",
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> TavilySearchResults:
        """
        Execute a single web search using Tavily

        Args:
            query: Search query string
            search_depth: "basic" or "advanced" (default: "advanced")
            include_domains: List of domains to include (optional)
            exclude_domains: List of domains to exclude (optional)

        Returns:
            TavilySearchResults object
        """
        start_time = time.time()
        self.stats["total_searches"] += 1

        fact_logger.logger.info(
            f"🔍 Tavily search: {query}",
            extra={
                "query": query,
                "search_depth": search_depth,
                "max_results": self.max_results
            }
        )

        try:
            # Build search parameters
            search_params = {
                "query": query,
                "search_depth": search_depth,
                "max_results": self.max_results,
                "include_answer": True,  # Get AI-generated answer
                "include_raw_content": False,  # We'll scrape ourselves
            }

            # Add domain filters if provided
            if include_domains:
                search_params["include_domains"] = include_domains
                fact_logger.logger.debug(f"Including domains: {include_domains}")

            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains
                fact_logger.logger.debug(f"Excluding domains: {exclude_domains}")

            # Execute search
            response = await self.async_client.search(**search_params)

            search_time = time.time() - start_time

            # Parse results
            results = TavilySearchResults(
                query=query,
                results=response.get('results', []),
                answer=response.get('answer'),
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
                    "search_time": search_time,
                    "has_answer": bool(results.answer)
                }
            )

            return results

        except Exception as e:
            search_time = time.time() - start_time
            self.stats["failed_searches"] += 1

            fact_logger.logger.error(
                f"❌ Tavily search failed: {e}",
                extra={
                    "query": query,
                    "search_time": search_time,
                    "error": str(e)
                }
            )

            # Return empty results on failure
            return TavilySearchResults(
                query=query,
                results=[],
                answer=None,
                search_time=search_time
            )

    @traceable(
        name="tavily_multi_search",
        run_type="chain",
        tags=["web-search", "tavily", "batch"]
    )
    async def search_multiple(
        self,
        queries: List[str],
        search_depth: str = "advanced",
        max_concurrent: int = 3
    ) -> Dict[str, TavilySearchResults]:
        """
        Execute multiple searches with concurrency control

        Args:
            queries: List of search query strings
            search_depth: "basic" or "advanced"
            max_concurrent: Maximum concurrent searches (default: 3)

        Returns:
            Dictionary mapping query to TavilySearchResults
        """
        fact_logger.logger.info(
            f"🔍 Executing {len(queries)} Tavily searches",
            extra={"num_queries": len(queries), "max_concurrent": max_concurrent}
        )

        # Use semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_with_semaphore(query: str):
            async with semaphore:
                return await self.search(query, search_depth=search_depth)

        # Execute all searches
        tasks = [search_with_semaphore(query) for query in queries]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Map queries to results
        results = {}
        for query, result in zip(queries, results_list):
            if isinstance(result, Exception):
                fact_logger.logger.error(
                    f"❌ Search failed for query: {query}",
                    extra={"query": query, "error": str(result)}
                )
                results[query] = TavilySearchResults(query=query, results=[])
            else:
                results[query] = result

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

    def aggregate_results(
        self,
        all_results: Dict[str, TavilySearchResults],
        max_urls: int = 20
    ) -> List[str]:
        """
        Aggregate URLs from multiple search results, removing duplicates

        Args:
            all_results: Dictionary of search results
            max_urls: Maximum number of unique URLs to return

        Returns:
            List of unique URLs, sorted by relevance score
        """
        fact_logger.logger.info(
            f"📊 Aggregating results from {len(all_results)} searches"
        )

        # Collect all results with their scores
        url_scores = {}

        for query, results in all_results.items():
            for result in results.results:
                url = result['url']
                score = result['score']

                # Keep highest score if URL appears in multiple searches
                if url not in url_scores or score > url_scores[url]:
                    url_scores[url] = score

        # Sort by score and limit
        sorted_urls = sorted(
            url_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:max_urls]

        unique_urls = [url for url, score in sorted_urls]

        fact_logger.logger.info(
            f"✅ Aggregated {len(unique_urls)} unique URLs from {sum(len(r.results) for r in all_results.values())} total results",
            extra={
                "unique_urls": len(unique_urls),
                "total_results": sum(len(r.results) for r in all_results.values())
            }
        )

        return unique_urls

    def get_stats(self) -> Dict:
        """Return search statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics counters"""
        self.stats = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "total_results": 0,
            "avg_search_time": 0.0,
            "total_search_time": 0.0
        }
        fact_logger.logger.info("📊 Search statistics reset")
