# improved_orchestrator.py
"""
Improved Orchestrator - Global Source Checking Approach

Key Changes:
1. Extract facts without source mapping
2. Collect ALL source URLs
3. Scrape ALL sources once
4. Check each fact against ALL scraped content
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

# Import the improved analyzer
from improved_analyzer import ImprovedFactAnalyzer

class ImprovedFactCheckOrchestrator:
    """Orchestrator using global source checking approach"""

    def __init__(self, config):
        self.config = config
        self.parser = HTMLParser()
        self.analyzer = ImprovedFactAnalyzer(config)  # Use improved analyzer
        self.scraper = FactCheckScraper(config)
        self.checker = FactChecker(config)
        self.file_manager = FileManager()

        fact_logger.log_component_start("ImprovedFactCheckOrchestrator")

    @traceable(
        name="improved_fact_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "global-checking"]
    )
    async def process(self, html_content: str) -> dict:
        """
        Improved pipeline: scrape all sources, check all facts against all content
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            f"🚀 STARTING IMPROVED FACT-CHECK SESSION: {session_id}",
            extra={"session_id": session_id, "input_length": len(html_content)}
        )

        try:
            # Step 1: Parse input
            fact_logger.logger.info("📄 Step 1: Parsing HTML input")
            parsed = await self._traced_parse(html_content)

            # Step 2: Extract facts AND get all source URLs
            fact_logger.logger.info("🔍 Step 2: Extracting facts (improved method)")
            facts, all_source_urls = await self.analyzer.analyze(parsed)

            fact_logger.logger.info(
                f"✅ Extracted {len(facts)} facts from {len(all_source_urls)} total sources"
            )

            # Step 3: Scrape ALL sources once (no duplicates)
            unique_urls = list(set(all_source_urls))  # Remove duplicates
            fact_logger.logger.info(f"🌐 Step 3: Scraping {len(unique_urls)} unique sources")

            all_scraped_content = await self.scraper.scrape_urls_for_facts(unique_urls)
            successful_scrapes = len([v for v in all_scraped_content.values() if v])

            fact_logger.logger.info(
                f"✅ Successfully scraped {successful_scrapes}/{len(unique_urls)} sources"
            )

            # Step 4: Combine all scraped content into one large text corpus
            combined_content = self._combine_all_content(all_scraped_content)
            fact_logger.logger.info(
                f"📚 Combined content: {len(combined_content)} characters from all sources"
            )

            # Step 5: Check each fact against the combined content
            fact_logger.logger.info(f"⚖️ Step 5: Checking {len(facts)} facts against all sources")
            results = []

            for i, fact in enumerate(facts, 1):
                fact_logger.logger.info(f"Processing fact {i}/{len(facts)}: {fact.id}")

                # Create excerpts from the combined content for this fact
                excerpts = await self._extract_relevant_excerpts(fact, combined_content, all_scraped_content)

                # Check accuracy using your existing fact checker
                check_result = await self.checker.check_fact(fact, excerpts)
                results.append(check_result)

                fact_logger.logger.info(
                    f"✅ Fact {fact.id} checked: score={check_result.match_score:.2f}"
                )

            # Generate summary
            summary = self._generate_summary(results)
            duration = time.time() - start_time

            fact_logger.logger.info(
                f"🎉 IMPROVED SESSION COMPLETE: {session_id}",
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
                "methodology": "global_source_checking",
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            fact_logger.log_component_error("ImprovedFactCheckOrchestrator", e, session_id=session_id)
            raise

    def _combine_all_content(self, scraped_content: dict) -> str:
        """Combine all scraped content into one large text for global fact checking"""
        combined = []

        for url, content in scraped_content.items():
            if content:  # Only include successfully scraped content
                combined.append(f"=== SOURCE: {url} ===\n{content}\n")

        return "\n".join(combined)

    async def _extract_relevant_excerpts(self, fact, combined_content: str, scraped_content: dict) -> dict:
        """
        Extract relevant excerpts for a fact from the combined content
        This replaces the highlighter component for the global approach
        """
        # Simple implementation: search for relevant passages in the combined content
        # You could make this more sophisticated using semantic search, etc.

        excerpts_by_url = {}

        # For each source, find excerpts that mention the fact
        for url, content in scraped_content.items():
            if not content:
                continue

            # Simple keyword-based extraction (you could improve this)
            relevant_excerpts = self._find_relevant_excerpts_in_text(fact.statement, content)

            if relevant_excerpts:
                excerpts_by_url[url] = relevant_excerpts

        return excerpts_by_url

    def _find_relevant_excerpts_in_text(self, fact_statement: str, content: str) -> list:
        """
        Simple keyword-based excerpt extraction
        In a production system, you'd want more sophisticated semantic matching
        """
        import re

        # Extract key terms from the fact
        key_terms = self._extract_key_terms(fact_statement)

        excerpts = []
        paragraphs = content.split('\n\n')

        for para in paragraphs:
            if len(para.strip()) < 50:  # Skip very short paragraphs
                continue

            # Count how many key terms appear in this paragraph
            matches = sum(1 for term in key_terms if term.lower() in para.lower())

            if matches >= 1:  # At least one key term found
                relevance = min(0.9, matches * 0.3)  # Simple relevance scoring
                excerpts.append({
                    'quote': para.strip(),
                    'relevance': relevance
                })

        return excerpts[:3]  # Return top 3 most relevant excerpts

    def _extract_key_terms(self, fact_statement: str) -> list:
        """Extract key terms from a fact statement for matching"""
        import re

        # Remove common words and extract meaningful terms
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'was', 'are', 'were', 'has', 'have', 'had'}

        # Extract words, numbers, and dates
        words = re.findall(r'\b\w+\b', fact_statement.lower())

        # Filter out common words and keep meaningful terms
        key_terms = [word for word in words if word not in common_words and len(word) > 2]

        # Also extract numbers and dates
        numbers = re.findall(r'\b\d+\b', fact_statement)
        dates = re.findall(r'\b(january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\b', fact_statement.lower())

        return key_terms + numbers + dates

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