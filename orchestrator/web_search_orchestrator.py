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
from typing import List, Dict, Any, Optional

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
from utils.job_manager import job_manager

# Import existing agents
from agents.fact_extractor import FactAnalyzer
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
        self.searcher = TavilySearcher(config, max_results=5)
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

    async def process_with_progress(self, text_content: str, job_id: str) -> dict:
        """Process with real-time progress updates"""
        from utils.job_manager import job_manager

        session_id = self.file_manager.create_session()
        start_time = time.time()

        try:
            # Step 1: Extract Facts
            job_manager.add_progress(job_id, "📄 Extracting facts from text...")

            parsed_input = {
                'text': text_content,
                'links': [],
                'format': 'plain_text'
            }

            facts, _ = await self.analyzer.analyze(parsed_input)

            if not facts:
                job_manager.add_progress(job_id, "⚠️ No verifiable facts found")
                return self._create_empty_result(session_id, "No verifiable facts found in text")

            job_manager.add_progress(job_id, f"✅ Extracted {len(facts)} facts")

            # Step 2: Generate Search Queries
            job_manager.add_progress(job_id, "🔍 Generating search queries...")

            all_queries_by_fact = {}
            for fact in facts:
                queries = await self.query_generator.generate_queries(fact)
                all_queries_by_fact[fact.id] = queries

            total_queries = sum(len(q.all_queries) for q in all_queries_by_fact.values())
            job_manager.add_progress(job_id, f"✅ Generated {total_queries} search queries")

            # Step 3: Execute Web Searches
            job_manager.add_progress(job_id, "🌐 Searching the web...")

            search_results_by_fact = {}
            for i, fact in enumerate(facts, 1):
                job_manager.add_progress(
                    job_id,
                    f"🔎 Searching for fact {i}/{len(facts)}: \"{fact.statement[:60]}...\""
                )

                queries = all_queries_by_fact[fact.id]
                search_results = await self.searcher.search_multiple(
                    queries=queries.all_queries,
                    search_depth="advanced",
                    max_concurrent=3
                )
                search_results_by_fact[fact.id] = search_results

            job_manager.add_progress(job_id, "✅ Web searches complete")

            # Step 4: Filter by Credibility
            job_manager.add_progress(job_id, "⭐ Filtering sources by credibility...")

            credible_urls_by_fact = {}
            credibility_results_by_fact = {}

            for fact in facts:
                all_results_for_fact = []
                for query, results in search_results_by_fact[fact.id].items():
                    all_results_for_fact.extend(results.results)

                if not all_results_for_fact:
                    credible_urls_by_fact[fact.id] = []
                    continue

                credibility_results = await self.credibility_filter.evaluate_sources(
                    fact=fact,
                    search_results=all_results_for_fact
                )
                credibility_results_by_fact[fact.id] = credibility_results

                credible_urls = credibility_results.get_top_sources(self.max_sources_per_fact)
                credible_urls_by_fact[fact.id] = [s.url for s in credible_urls]

            total_credible = sum(len(urls) for urls in credible_urls_by_fact.values())
            job_manager.add_progress(job_id, f"✅ Found {total_credible} credible sources")

            # Step 5: Scrape Sources
            job_manager.add_progress(job_id, f"🌐 Scraping {total_credible} sources...")

            scraped_content_by_fact = {}
            for fact in facts:
                urls_to_scrape = credible_urls_by_fact.get(fact.id, [])
                if urls_to_scrape:
                    scraped_content = await self.scraper.scrape_urls_for_facts(urls_to_scrape)
                    scraped_content_by_fact[fact.id] = scraped_content

            job_manager.add_progress(job_id, "✅ Scraping complete")

            # Step 6: Verify Facts
            results = []
            for i, fact in enumerate(facts, 1):
                job_manager.add_progress(
                    job_id,
                    f"⚖️ Verifying fact {i}/{len(facts)}: \"{fact.statement[:60]}...\"",
                    {'fact_id': fact.id, 'progress': f"{i}/{len(facts)}"}
                )

                scraped_content = scraped_content_by_fact.get(fact.id, {})

                if not scraped_content or not any(scraped_content.values()):
                    from agents.fact_checker import FactCheckResult
                    result = FactCheckResult(
                        fact_id=fact.id,
                        statement=fact.statement,
                        match_score=0.0,
                        assessment="Unable to verify - no credible sources found",
                        discrepancies="No sources available for verification",
                        confidence=0.0,
                        reasoning="Web search did not yield credible sources"
                    )
                    results.append(result)
                    job_manager.add_progress(job_id, f"⚠️ {fact.id}: No sources found")
                    continue

                from agents.highlighter import Highlighter
                highlighter = Highlighter(self.config)

                excerpts = await highlighter.highlight(fact, scraped_content)
                check_result = await self.checker.check_fact(fact, excerpts)
                results.append(check_result)

                emoji = "✅" if check_result.match_score >= 0.9 else "⚠️" if check_result.match_score >= 0.7 else "❌"
                job_manager.add_progress(
                    job_id,
                    f"{emoji} {fact.id}: Score {check_result.match_score:.2f}"
                )

            results.sort(key=lambda x: x.match_score)

            # Save and upload to R2
            job_manager.add_progress(job_id, "💾 Saving results...")
            all_scraped_content = {}
            for fact_scraped in scraped_content_by_fact.values():
                all_scraped_content.update(fact_scraped)

            # ✅ CHANGED: Capture upload result and use upload_to_r2
            upload_result = self.file_manager.save_session_content(
                session_id,
                all_scraped_content,
                facts,
                upload_to_r2=True,  
                queries_by_fact=all_queries_by_fact
            )

            # ✅ NEW: Add progress message about upload status
            if upload_result and upload_result.get('success'):
                job_manager.add_progress(job_id, "☁️ Report uploaded to R2")
            else:
                error_msg = upload_result.get('error', 'Unknown error') if upload_result else 'Upload returned no result'
                job_manager.add_progress(job_id, f"⚠️ R2 upload failed: {error_msg}")

            summary = self._generate_summary(results)
            duration = time.time() - start_time

            return {
                "session_id": session_id,
                "facts": [r.dict() for r in results],
                "summary": summary,
                "duration": duration,
                "methodology": "web_search_verification",
                "statistics": {
                    "total_searches": total_queries,
                    "total_sources_found": sum(
                        sum(len(r.results) for r in sr.values())
                        for sr in search_results_by_fact.values()
                    ),
                    "credible_sources_identified": total_credible,
                    "sources_scraped": len(all_scraped_content),
                    "successful_scrapes": len([c for c in all_scraped_content.values() if c])
                },
                "r2_upload": {
                    "success": upload_result.get('success', False) if upload_result else False,
                    "url": upload_result.get('url') if upload_result else None,
                    "filename": upload_result.get('filename') if upload_result else None,
                    "error": upload_result.get('error') if upload_result else None
                },
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            job_manager.add_progress(job_id, f"❌ Error: {str(e)}")
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
