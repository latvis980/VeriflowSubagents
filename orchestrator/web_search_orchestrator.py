# orchestrator/web_search_orchestrator.py
"""
Web Search Orchestrator
Coordinates web search-based fact verification pipeline for text without links

Pipeline:
1. Extract facts from plain text
2. Generate search queries for each fact
3. Execute web searches via Tavily
4. Filter results by source credibility
5. Scrape credible sources
6. Combine content into verification corpus
7. Check facts against combined content
"""

from langsmith import traceable
import time
import asyncio
from typing import List, Dict, Any

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager

# Import existing agents
from agents.analyser import FactAnalyzer
from agents.browserless_scraper import FactCheckScraper
from agents.fact_checker import FactChecker

# Import new agents
from agents.query_generator import QueryGenerator
from agents.tavily_searcher import TavilySearcher
from agents.credibility_filter import CredibilityFilter


class WebSearchOrchestrator:
    """
    Orchestrator for web search-based fact verification
    
    For plain text input without provided sources
    """

    def __init__(self, config):
        self.config = config
        
        # Initialize all agents
        self.analyzer = FactAnalyzer(config)
        self.query_generator = QueryGenerator(config)
        self.searcher = TavilySearcher(config, max_results=10)
        self.credibility_filter = CredibilityFilter(config, min_credibility_score=0.70)
        self.scraper = FactCheckScraper(config)
        self.checker = FactChecker(config)
        self.file_manager = FileManager()

        # Configuration
        self.max_sources_per_fact = 10  # Maximum sources to scrape per fact
        self.max_concurrent_scrapes = 2  # Limit concurrent scraping

        fact_logger.log_component_start(
            "WebSearchOrchestrator",
            max_sources_per_fact=self.max_sources_per_fact
        )

    @traceable(
        name="web_search_fact_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "web-search", "fact-verification"]
    )
    async def process(self, text_content: str) -> dict:
        """
        Main pipeline for web search-based fact verification

        Args:
            text_content: Plain text to verify (no HTML, no links)

        Returns:
            Dictionary with verification results
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            f"🚀 STARTING WEB SEARCH FACT-CHECK SESSION: {session_id}",
            extra={
                "session_id": session_id,
                "input_length": len(text_content),
                "pipeline": "web_search"
            }
        )

        try:
            # ===== STEP 1: Extract Facts =====
            fact_logger.logger.info("📄 Step 1: Extracting facts from text")
            
            # Create parsed input format expected by analyzer
            parsed_input = {
                'text': text_content,
                'links': [],  # No links for web search pipeline
                'format': 'plain_text'
            }
            
            facts, _ = await self.analyzer.analyze(parsed_input)
            
            if not facts:
                fact_logger.logger.warning("⚠️ No facts extracted from text")
                return self._create_empty_result(session_id, "No verifiable facts found in text")

            fact_logger.logger.info(
                f"✅ Extracted {len(facts)} facts",
                extra={"num_facts": len(facts)}
            )

            # ===== STEP 2: Generate Search Queries =====
            fact_logger.logger.info("🔍 Step 2: Generating search queries for each fact")
            
            all_queries_by_fact = {}
            for fact in facts:
                queries = await self.query_generator.generate_queries(fact)
                all_queries_by_fact[fact.id] = queries
                
                fact_logger.logger.debug(
                    f"Generated queries for {fact.id}: {queries.primary_query}",
                    extra={"fact_id": fact.id, "num_queries": len(queries.all_queries)}
                )

            total_queries = sum(len(q.all_queries) for q in all_queries_by_fact.values())
            fact_logger.logger.info(
                f"✅ Generated {total_queries} total queries for {len(facts)} facts"
            )

            # ===== STEP 3: Execute Web Searches =====
            fact_logger.logger.info("🌐 Step 3: Executing web searches via Tavily")
            
            search_results_by_fact = {}
            
            for fact in facts:
                fact_logger.logger.info(f"Searching for {fact.id}")
                
                queries = all_queries_by_fact[fact.id]
                
                # Execute all queries for this fact
                search_results = await self.searcher.search_multiple(
                    queries=queries.all_queries,
                    search_depth="advanced",
                    max_concurrent=3
                )
                
                search_results_by_fact[fact.id] = search_results
                
                # Count total results
                total_results = sum(len(r.results) for r in search_results.values())
                fact_logger.logger.info(
                    f"Found {total_results} results for {fact.id}",
                    extra={"fact_id": fact.id, "total_results": total_results}
                )

            fact_logger.logger.info("✅ All web searches complete")

            # ===== STEP 4: Filter by Credibility =====
            fact_logger.logger.info("⭐ Step 4: Filtering sources by credibility")
            
            credible_urls_by_fact = {}
            credibility_results_by_fact = {}
            
            for fact in facts:
                fact_logger.logger.info(f"Filtering sources for {fact.id}")
                
                # Collect all search results for this fact
                all_results_for_fact = []
                for query, results in search_results_by_fact[fact.id].items():
                    all_results_for_fact.extend(results.results)
                
                if not all_results_for_fact:
                    fact_logger.logger.warning(
                        f"⚠️ No search results to filter for {fact.id}"
                    )
                    credible_urls_by_fact[fact.id] = []
                    continue
                
                # Evaluate credibility
                credibility_results = await self.credibility_filter.evaluate_sources(
                    fact=fact,
                    search_results=all_results_for_fact
                )
                
                credibility_results_by_fact[fact.id] = credibility_results
                
                # Get top credible URLs
                credible_urls = credibility_results.get_top_sources(
                    n=self.max_sources_per_fact
                )
                credible_urls_by_fact[fact.id] = [s.url for s in credible_urls]
                
                fact_logger.logger.info(
                    f"Filtered to {len(credible_urls)} credible sources for {fact.id}",
                    extra={
                        "fact_id": fact.id,
                        "original_count": len(all_results_for_fact),
                        "filtered_count": len(credible_urls)
                    }
                )

            total_credible_urls = sum(len(urls) for urls in credible_urls_by_fact.values())
            fact_logger.logger.info(
                f"✅ Filtered to {total_credible_urls} credible sources total"
            )

            # ===== STEP 5: Scrape Credible Sources =====
            fact_logger.logger.info("🌐 Step 5: Scraping credible sources")
            
            scraped_content_by_fact = {}
            
            for fact in facts:
                urls_to_scrape = credible_urls_by_fact.get(fact.id, [])
                
                if not urls_to_scrape:
                    fact_logger.logger.warning(
                        f"⚠️ No credible URLs to scrape for {fact.id}"
                    )
                    scraped_content_by_fact[fact.id] = {}
                    continue
                
                fact_logger.logger.info(
                    f"Scraping {len(urls_to_scrape)} URLs for {fact.id}"
                )
                
                # Scrape all URLs for this fact
                scraped_content = await self.scraper.scrape_urls_for_facts(urls_to_scrape)
                scraped_content_by_fact[fact.id] = scraped_content
                
                successful_scrapes = len([c for c in scraped_content.values() if c])
                fact_logger.logger.info(
                    f"✅ Scraped {successful_scrapes}/{len(urls_to_scrape)} sources for {fact.id}",
                    extra={
                        "fact_id": fact.id,
                        "successful": successful_scrapes,
                        "total": len(urls_to_scrape)
                    }
                )

            fact_logger.logger.info("✅ All scraping complete")

            # ===== STEP 6: Check Each Fact =====
            fact_logger.logger.info("⚖️ Step 6: Verifying facts against scraped content")
            
            results = []
            
            for i, fact in enumerate(facts, 1):
                fact_logger.logger.info(f"Checking fact {i}/{len(facts)}: {fact.id}")
                
                scraped_content = scraped_content_by_fact.get(fact.id, {})
                
                if not scraped_content or not any(scraped_content.values()):
                    fact_logger.logger.warning(
                        f"⚠️ No scraped content available for {fact.id}"
                    )
                    
                    # Create a result indicating no sources found
                    from agents.fact_checker import FactCheckResult
                    result = FactCheckResult(
                        fact_id=fact.id,
                        statement=fact.statement,
                        match_score=0.0,
                        assessment="Unable to verify - no credible sources found",
                        discrepancies="No sources available for verification",
                        confidence=0.0,
                        reasoning="Web search did not yield credible sources to verify this claim"
                    )
                    results.append(result)
                    continue
                
                # Use existing highlighter + checker approach
                # Import here to avoid circular imports
                from agents.highlighter import Highlighter
                highlighter = Highlighter(self.config)
                
                # Extract excerpts from scraped content
                excerpts = await highlighter.highlight(fact, scraped_content)
                
                # Check fact against excerpts
                check_result = await self.checker.check_fact(fact, excerpts)
                results.append(check_result)
                
                fact_logger.logger.info(
                    f"✅ Fact {fact.id} checked: score={check_result.match_score:.2f}",
                    extra={
                        "fact_id": fact.id,
                        "score": check_result.match_score,
                        "sources_used": len(scraped_content)
                    }
                )

            # Sort results by score (lowest first)
            results.sort(key=lambda x: x.match_score)

            # ===== STEP 7: Save Session Data =====
            fact_logger.logger.info("💾 Step 7: Saving session data")
            
            # Combine all scraped content for saving
            all_scraped_content = {}
            for fact_scraped in scraped_content_by_fact.values():
                all_scraped_content.update(fact_scraped)
            
            self.file_manager.save_session_content(
                session_id,
                all_scraped_content,
                facts,
                upload_to_drive=True  # ✅ Enable Google Drive upload
            )

            # ===== Generate Summary =====
            summary = self._generate_summary(results)
            duration = time.time() - start_time

            # Collect statistics
            total_searches = sum(
                len(search_results) 
                for search_results in search_results_by_fact.values()
            )
            total_sources_scraped = len(all_scraped_content)
            successful_scrapes = len([c for c in all_scraped_content.values() if c])

            fact_logger.logger.info(
                f"🎉 WEB SEARCH SESSION COMPLETE: {session_id}",
                extra={
                    "session_id": session_id,
                    "duration": duration,
                    "total_facts": len(results),
                    "total_searches": total_searches,
                    "total_sources": total_sources_scraped,
                    "avg_score": summary['avg_score']
                }
            )

            return {
                "session_id": session_id,
                "facts": [r.dict() for r in results],
                "summary": summary,
                "duration": duration,
                "methodology": "web_search_verification",
                "statistics": {
                    "total_searches": total_searches,
                    "total_sources_found": sum(
                        sum(len(r.results) for r in sr.values())
                        for sr in search_results_by_fact.values()
                    ),
                    "credible_sources_identified": total_credible_urls,
                    "sources_scraped": total_sources_scraped,
                    "successful_scrapes": successful_scrapes,
                    "scrape_success_rate": (
                        successful_scrapes / total_sources_scraped * 100
                        if total_sources_scraped > 0 else 0
                    )
                },
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            fact_logger.log_component_error(
                "WebSearchOrchestrator",
                e,
                session_id=session_id
            )
            raise

    def _generate_summary(self, results: list) -> dict:
        """Generate summary statistics"""
        if not results:
            return {
                "total_facts": 0,
                "accurate": 0,
                "good_match": 0,
                "questionable": 0,
                "avg_score": 0.0
            }

        total = len(results)
        accurate = len([r for r in results if r.match_score >= 0.9])
        good = len([r for r in results if 0.7 <= r.match_score < 0.9])
        questionable = len([r for r in results if r.match_score < 0.7])
        avg_score = sum(r.match_score for r in results) / total

        return {
            "total_facts": total,
            "accurate": accurate,
            "good_match": good,
            "questionable": questionable,
            "avg_score": round(avg_score, 3)
        }

    def _create_empty_result(self, session_id: str, message: str) -> dict:
        """Create empty result when no facts found"""
        return {
            "session_id": session_id,
            "facts": [],
            "summary": {
                "total_facts": 0,
                "accurate": 0,
                "good_match": 0,
                "questionable": 0,
                "avg_score": 0.0
            },
            "duration": 0.0,
            "methodology": "web_search_verification",
            "message": message,
            "statistics": {
                "total_searches": 0,
                "total_sources_found": 0,
                "credible_sources_identified": 0,
                "sources_scraped": 0,
                "successful_scrapes": 0,
                "scrape_success_rate": 0.0
            },
            "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
        }
