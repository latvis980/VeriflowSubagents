# orchestrator/llm_output_orchestrator.py
from langsmith import traceable
import time
import os
from typing import Dict, List

# Import all components with fixed paths
from utils.html_parser import HTMLParser
from agents.analyser import FactAnalyzer
from agents.browserless_scraper import FactCheckScraper
from agents.highlighter import Highlighter
from agents.fact_checker import FactChecker
from utils.file_manager import FileManager
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

class FactCheckOrchestrator:
    """Coordinate fact-checking pipeline with full LangSmith tracing"""

    def __init__(self, config):
        self.config = config
        self.parser = HTMLParser()
        self.analyzer = FactAnalyzer(config)
        self.scraper = FactCheckScraper(config)
        self.highlighter = Highlighter(config)
        self.checker = FactChecker(config)
        self.file_manager = FileManager()

        fact_logger.log_component_start("FactCheckOrchestrator")

    @traceable(
        name="fact_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "full-pipeline"]
    )
    async def process(self, html_content: str) -> Dict:
        """
        Main pipeline with comprehensive tracing and logging
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            f"🚀 STARTING FACT-CHECK SESSION: {session_id}",
            extra={
                "session_id": session_id,
                "input_length": len(html_content)
            }
        )

        # Create LangSmith session
        langsmith_config.create_session(
            session_id,
            metadata={
                "input_length": len(html_content),
                "timestamp": time.time()
            }
        )

        try:
            # Step 1: Parse input
            fact_logger.logger.info("📄 Step 1: Parsing HTML input")
            parsed = await self._traced_parse(html_content)

            # Step 2: Extract facts
            fact_logger.logger.info(f"🔍 Step 2: Extracting facts (found {len(parsed.get('links', []))} sources)")
            facts = await self.analyzer.analyze(parsed)
            fact_logger.logger.info(f"✅ Extracted {len(facts)} facts")

            # Step 3: Get unique URLs
            all_urls = list(set([url for fact in facts for url in fact.sources]))
            fact_logger.logger.info(f"🌐 Step 3: Preparing to scrape {len(all_urls)} unique URLs")

            # Step 4: Scrape sources
            fact_logger.logger.info("🕷️ Step 4: Scraping all sources")
            scraped_content = await self._traced_scrape(all_urls, session_id)
            successful_scrapes = len([v for v in scraped_content.values() if v])
            fact_logger.logger.info(f"✅ Successfully scraped {successful_scrapes}/{len(all_urls)} sources")

            # Step 5 & 6: Highlight and check
            fact_logger.logger.info(f"🔦 Step 5 & 6: Highlighting excerpts and checking {len(facts)} facts")
            results = []

            for i, fact in enumerate(facts, 1):
                fact_logger.logger.info(f"Processing fact {i}/{len(facts)}: {fact.id}")

                # Highlight
                excerpts = await self.highlighter.highlight(fact, scraped_content)

                # Save excerpts
                for url, url_excerpts in excerpts.items():
                    for excerpt in url_excerpts:
                        self.file_manager.save_excerpt(
                            session_id, fact.id, url, excerpt['quote']
                        )

                # Check accuracy
                check_result = await self.checker.check_fact(fact, excerpts)
                results.append(check_result)

                fact_logger.logger.info(
                    f"✅ Fact {fact.id} checked: score={check_result.match_score:.2f}"
                )

            # Generate summary
            summary = self._generate_summary(results)

            duration = time.time() - start_time

            fact_logger.logger.info(
                f"🎉 SESSION COMPLETE: {session_id}",
                extra={
                    "session_id": session_id,
                    "duration": duration,
                    "total_facts": len(results),
                    "avg_score": summary['avg_score'],
                    "accurate_facts": summary['accurate']
                }
            )

            return {
                "session_id": session_id,
                "facts": [r.dict() for r in results],
                "summary": summary,
                "duration": duration,
                "langsmith_url": f"https://smith.langchain.com/o/{os.getenv('LANGCHAIN_ORG_ID', 'your-org')}/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            fact_logger.log_component_error(
                "FactCheckOrchestrator",
                e,
                session_id=session_id
            )
            raise

    @traceable(name="parse_html", run_type="tool")
    async def _traced_parse(self, html_content: str) -> Dict:
        """Parse HTML with tracing"""
        return self.parser.parse_input(html_content)

    @traceable(name="scrape_all_sources", run_type="tool")
    async def _traced_scrape(self, urls: List[str], session_id: str) -> Dict[str, str]:
        """Scrape with tracing"""
        return await self.scraper.scrape_urls_for_facts(urls)

    def _generate_summary(self, results: List) -> Dict:
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