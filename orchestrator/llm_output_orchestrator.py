# orchestrator/llm_output_orchestrator.py
"""
Orchestrator - Fixed Version with Semantic Excerpt Extraction

KEY FIXES:
1. Uses Highlighter for semantic excerpt extraction (instead of keyword matching)
2. Removed the broken _find_relevant_excerpts_in_text() method
3. Increased context window for highlighter
"""

from langsmith import traceable
import time
import asyncio
import os

from utils.html_parser import HTMLParser
from utils.file_manager import FileManager
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

# Import your existing components
from agents.browserless_scraper import FactCheckScraper
from agents.fact_checker import FactChecker
from agents.analyser import FactAnalyzer
from agents.highlighter import Highlighter  # ✅ NEW: Import highlighter

class FactCheckOrchestrator:
    """Orchestrator using global source checking approach with semantic excerpt extraction"""

    def __init__(self, config):
        self.config = config
        self.parser = HTMLParser()
        self.analyzer = FactAnalyzer(config) 
        self.scraper = FactCheckScraper(config)
        self.checker = FactChecker(config)
        self.highlighter = Highlighter(config)  # ✅ NEW: Initialize highlighter
        self.file_manager = FileManager()

        fact_logger.log_component_start("FactCheckOrchestrator")

    @traceable(
        name="fact_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "global-checking", "semantic-extraction"]
    )
    async def process(self, html_content: str) -> dict:
        """
        Improved pipeline with semantic excerpt extraction
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            f"🚀 STARTING FACT-CHECK SESSION: {session_id}",
            extra={"session_id": session_id, "input_length": len(html_content)}
        )

        try:
            # Step 1: Parse input
            fact_logger.logger.info("📄 Step 1: Parsing HTML input")
            parsed = await self._traced_parse(html_content)

            # Step 2: Extract facts AND get all source URLs
            fact_logger.logger.info("🔍 Step 2: Extracting facts")
            facts, all_source_urls = await self.analyzer.analyze(parsed)

            fact_logger.logger.info(
                f"✅ Extracted {len(facts)} facts from {len(all_source_urls)} total sources"
            )

            # Step 3: Scrape ALL sources once (no duplicates)
            unique_urls = list(set(all_source_urls))
            fact_logger.logger.info(f"🌐 Step 3: Scraping {len(unique_urls)} unique sources")

            all_scraped_content = await self.scraper.scrape_urls_for_facts(unique_urls)
            successful_scrapes = len([v for v in all_scraped_content.values() if v])

            fact_logger.logger.info(
                f"✅ Successfully scraped {successful_scrapes}/{len(unique_urls)} sources"
            )

            # Step 4: Save session content
            fact_logger.logger.info("💾 Step 4: Saving session content")
            self.file_manager.save_session_content(
                session_id, 
                all_scraped_content,
                facts,
                upload_to_drive=True  # ✅ Enable Google Drive upload
            )

            # Step 5: Check each fact using SEMANTIC excerpt extraction
            fact_logger.logger.info(
                f"⚖️ Step 5: Checking {len(facts)} facts with semantic excerpt extraction"
            )
            results = []

            for i, fact in enumerate(facts, 1):
                fact_logger.logger.info(f"Processing fact {i}/{len(facts)}: {fact.id}")

                # ✅ NEW: Use highlighter for semantic excerpt extraction
                excerpts = await self._extract_relevant_excerpts_semantic(
                    fact, 
                    all_scraped_content
                )

                # Check accuracy using your existing fact checker
                check_result = await self.checker.check_fact(fact, excerpts)
                results.append(check_result)

                fact_logger.logger.info(
                    f"✅ Fact {fact.id} checked: score={check_result.match_score:.2f}",
                    extra={
                        "fact_id": fact.id,
                        "score": check_result.match_score,
                        "excerpts_found": sum(len(v) for v in excerpts.values())
                    }
                )

            # Sort facts by score (lowest first)
            results.sort(key=lambda x: x.match_score)

            # Generate summary
            summary = self._generate_summary(results)
            duration = time.time() - start_time

            fact_logger.logger.info(
                f"🎉 SESSION COMPLETE: {session_id}",
                extra={
                    "session_id": session_id,
                    "duration": duration,
                    "total_facts": len(results),
                    "total_sources": len(unique_urls),
                    "avg_score": summary['avg_score']
                }
            )

            return {
                "session_id": session_id,
                "facts": [r.dict() for r in results],
                "summary": summary,
                "duration": duration,
                "total_sources_scraped": len(unique_urls),
                "successful_scrapes": successful_scrapes,
                "methodology": "global_source_checking_semantic",
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            fact_logger.log_component_error("FactCheckOrchestrator", e, session_id=session_id)
            raise

    # orchestrator/llm_output_orchestrator.py - Add progress method

    async def process_with_progress(self, html_content: str, job_id: str) -> dict:
        """Process with real-time progress updates"""
        from utils.job_manager import job_manager

        session_id = self.file_manager.create_session()
        start_time = time.time()

        try:
            # Step 1: Parse
            job_manager.add_progress(job_id, "📄 Parsing HTML input...")
            parsed = await self._traced_parse(html_content)

            # Step 2: Extract facts
            job_manager.add_progress(job_id, "🔍 Extracting verifiable facts...")
            facts, all_source_urls = await self.analyzer.analyze(parsed)
            job_manager.add_progress(
                job_id, 
                f"✅ Found {len(facts)} facts from {len(all_source_urls)} sources"
            )

            # Step 3: Scrape sources
            unique_urls = list(set(all_source_urls))
            job_manager.add_progress(
                job_id, 
                f"🌐 Scraping {len(unique_urls)} sources..."
            )

            all_scraped_content = await self.scraper.scrape_urls_for_facts(unique_urls)
            successful_scrapes = len([v for v in all_scraped_content.values() if v])
            job_manager.add_progress(
                job_id,
                f"✅ Scraped {successful_scrapes}/{len(unique_urls)} sources"
            )

            # Step 4: Verify each fact
            results = []
            for i, fact in enumerate(facts, 1):
                job_manager.add_progress(
                    job_id,
                    f"⚖️ Verifying fact {i}/{len(facts)}: \"{fact.statement[:60]}...\"",
                    {'fact_id': fact.id, 'progress': f"{i}/{len(facts)}"}
                )

                excerpts = await self._extract_relevant_excerpts_semantic(fact, all_scraped_content)
                check_result = await self.checker.check_fact(fact, excerpts)
                results.append(check_result)

                # Show result
                emoji = "✅" if check_result.match_score >= 0.9 else "⚠️" if check_result.match_score >= 0.7 else "❌"
                job_manager.add_progress(
                    job_id,
                    f"{emoji} {fact.id}: Score {check_result.match_score:.2f}"
                )

            results.sort(key=lambda x: x.match_score)

            # Save and finish
            job_manager.add_progress(job_id, "💾 Saving results...")
            self.file_manager.save_session_content(session_id, all_scraped_content, facts, upload_to_drive=True)

            summary = self._generate_summary(results)
            duration = time.time() - start_time

            return {
                "session_id": session_id,
                "facts": [r.dict() for r in results],
                "summary": summary,
                "duration": duration,
                "total_sources_scraped": len(unique_urls),
                "successful_scrapes": successful_scrapes,
                "methodology": "global_source_checking_semantic",
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            job_manager.add_progress(job_id, f"❌ Error: {str(e)}")
            raise

    async def _extract_relevant_excerpts_semantic(
        self, 
        fact, 
        scraped_content: dict
    ) -> dict:
        """
        ✅ NEW: Extract relevant excerpts using semantic understanding via Highlighter

        This replaces the old keyword-based extraction with proper semantic matching.

        Args:
            fact: The Fact object to find excerpts for
            scraped_content: Dict of {url: content}

        Returns:
            Dict of {url: [excerpts]} with semantically matched excerpts
        """
        fact_logger.logger.info(
            f"🔦 Using semantic extraction for {fact.id}",
            extra={"fact_id": fact.id, "num_sources": len(scraped_content)}
        )

        # Use the highlighter's semantic extraction for each source
        excerpts_by_url = await self.highlighter.highlight(fact, scraped_content)

        # Log extraction results
        total_excerpts = sum(len(excerpts) for excerpts in excerpts_by_url.values())
        fact_logger.logger.info(
            f"✂️ Semantic extraction complete: {total_excerpts} excerpts from {len(excerpts_by_url)} sources",
            extra={
                "fact_id": fact.id,
                "total_excerpts": total_excerpts,
                "sources_with_matches": len(excerpts_by_url)
            }
        )

        return excerpts_by_url

    @traceable(name="parse_html", run_type="tool")
    async def _traced_parse(self, html_content: str) -> dict:
        """Parse HTML with tracing"""
        return self.parser.parse_input(html_content)

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