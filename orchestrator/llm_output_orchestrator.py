# orchestrator/llm_interpretation_orchestrator.py
"""
LLM Interpretation Verification Orchestrator

PURPOSE: Verify if LLMs (ChatGPT, Perplexity) accurately interpreted their cited sources

PROCESS 1: LLM Output Verification
- Input: LLM output WITH embedded source links
- Goal: Check if LLM claims match what sources actually say
- Method: Compare LLM's interpretation against actual source content
- NO web search (sources already provided by LLM)
- NO tier filtering (sources already provided by LLM)
- NO fact-checking (just interpretation verification)

For fact-checking ANY text, use web_search_orchestrator.py instead.
"""

from langsmith import traceable
import time

from utils.html_parser import HTMLParser
from utils.file_manager import FileManager
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

from agents.browserless_scraper import FactCheckScraper
from agents.fact_extractor import FactAnalyzer
from agents.highlighter import Highlighter
from agents.llm_output_verifier import LLMOutputVerifier
from utils.job_manager import job_manager


class LLMInterpretationOrchestrator:
    """
    Verify LLM interpretation accuracy

    Pipeline:
    1. Parse LLM output (ChatGPT, Perplexity, etc.)
    2. Extract claims made by the LLM
    3. Scrape the sources that LLM cited
    4. Extract relevant excerpts from sources
    5. Verify if LLM interpreted those sources correctly

    Does NOT do fact-checking or web search.
    Does NOT evaluate source credibility (sources provided by LLM).

    Output: Interpretation quality scores only.
    """

    def __init__(self, config):
        self.config = config
        self.parser = HTMLParser()
        self.analyzer = FactAnalyzer(config)
        self.scraper = FactCheckScraper(config)
        self.highlighter = Highlighter(config)
        self.verifier = LLMOutputVerifier(config)  # ✅ Interpretation verifier
        self.file_manager = FileManager()

        fact_logger.log_component_start("LLMInterpretationOrchestrator")

    def _check_cancellation(self, job_id: str):
        """Check if job has been cancelled"""
        if job_manager.is_cancelled(job_id):
            raise Exception("Job cancelled by user")

    @traceable(
        name="llm_interpretation_verification",
        run_type="chain",
        tags=["llm-verification", "interpretation-only", "no-fact-checking"]
    )
    async def process_with_progress(self, html_content: str, job_id: str) -> dict:
        """
        Verify LLM interpretation with real-time progress

        Returns interpretation quality scores (NOT fact-checking scores)
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            f"🔍 STARTING LLM INTERPRETATION VERIFICATION: {session_id}",
            extra={"session_id": session_id, "process": "interpretation_verification"}
        )

        try:
            # Step 1: Parse LLM output
            job_manager.add_progress(job_id, "📄 Parsing LLM output...")
            self._check_cancellation(job_id)
            parsed = await self._traced_parse(html_content)

            # Step 2: Extract claims made by LLM
            job_manager.add_progress(job_id, "🔍 Extracting LLM claims...")
            self._check_cancellation(job_id)
            facts, all_source_urls = await self.analyzer.analyze(parsed)
            job_manager.add_progress(
                job_id,
                f"✅ Found {len(facts)} claims citing {len(all_source_urls)} sources"
            )

            # Step 3: Scrape cited sources
            unique_urls = list(set(all_source_urls))
            job_manager.add_progress(
                job_id,
                f"🌐 Scraping {len(unique_urls)} sources cited by LLM..."
            )
            self._check_cancellation(job_id)

            all_scraped_content = await self.scraper.scrape_urls_for_facts(unique_urls)
            successful_scrapes = len([v for v in all_scraped_content.values() if v])
            job_manager.add_progress(
                job_id,
                f"✅ Scraped {successful_scrapes}/{len(unique_urls)} cited sources"
            )

            # Step 4: Verify each claim's interpretation
            job_manager.add_progress(
                job_id,
                f"🔬 Verifying how accurately LLM interpreted sources..."
            )

            results = []
            for i, fact in enumerate(facts, 1):
                job_manager.add_progress(
                    job_id,
                    f"🔬 Checking claim {i}/{len(facts)}: \"{fact.statement[:60]}...\"",
                    {'fact_id': fact.id, 'progress': f"{i}/{len(facts)}"}
                )
                self._check_cancellation(job_id)

                # Extract relevant excerpts from sources
                excerpts = await self._extract_excerpts(fact, all_scraped_content)

                # ✅ VERIFY INTERPRETATION (this is the core step)
                verification = await self.verifier.verify_interpretation(
                    fact,
                    excerpts,
                    all_scraped_content
                )

                results.append(verification)

                # Show result
                emoji = "✅" if verification.verification_score >= 0.9 else "⚠️" if verification.verification_score >= 0.7 else "❌"
                job_manager.add_progress(
                    job_id,
                    f"{emoji} {fact.id}: {verification.verification_score:.2f} - {verification.assessment[:50]}..."
                )

                # Show interpretation issues if any
                if verification.interpretation_issues:
                    issues_text = ", ".join(verification.interpretation_issues[:2])
                    job_manager.add_progress(
                        job_id,
                        f"  ⚠️ Issues: {issues_text}"
                    )

                self._check_cancellation(job_id)

            # Sort by verification score
            results.sort(key=lambda x: x.verification_score)

            # Save session
            job_manager.add_progress(job_id, "💾 Saving verification report...")
            self._check_cancellation(job_id)

            upload_result = self.file_manager.save_session_content(
                session_id,
                all_scraped_content,
                facts,
                upload_to_r2=True
            )

            if upload_result and upload_result.get('success'):
                job_manager.add_progress(job_id, "☁️ Report uploaded to R2")
            else:
                error_msg = upload_result.get('error', 'Unknown error') if upload_result else 'Upload returned no result'
                job_manager.add_progress(job_id, f"⚠️ R2 upload failed: {error_msg}")

            # Generate summary
            summary = self._generate_summary(results)
            duration = time.time() - start_time

            job_manager.add_progress(
                job_id,
                f"✅ Verification complete! Avg interpretation score: {summary['avg_interpretation_score']:.2f}"
            )

            fact_logger.logger.info(
                f"🎉 INTERPRETATION VERIFICATION COMPLETE: {session_id}",
                extra={
                    "session_id": session_id,
                    "duration": duration,
                    "total_claims": len(results),
                    "avg_score": summary['avg_interpretation_score']
                }
            )

            return {
                "session_id": session_id,
                "claims": [r.dict() for r in results],
                "summary": summary,
                "duration": duration,
                "total_sources_scraped": len(unique_urls),
                "successful_scrapes": successful_scrapes,
                "process": "llm_interpretation_verification",
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}",
                "r2_upload": {
                    "success": upload_result.get('success', False) if upload_result else False,
                    "url": upload_result.get('url') if upload_result else None,
                    "filename": upload_result.get('filename') if upload_result else None,
                    "error": upload_result.get('error') if upload_result else None
                }
            }

        except Exception as e:
            if "cancelled" in str(e).lower():
                job_manager.add_progress(job_id, "🛑 Verification cancelled")
                job_manager.fail_job(job_id, "Cancelled by user")
            else:
                fact_logger.log_component_error(f"Job {job_id}", e)
                job_manager.fail_job(job_id, str(e))
            raise

    async def _extract_excerpts(self, fact, scraped_content: dict) -> dict:
        """Extract relevant excerpts using Highlighter"""
        fact_logger.logger.info(
            f"🔦 Extracting excerpts for {fact.id}",
            extra={"fact_id": fact.id, "num_sources": len(scraped_content)}
        )

        excerpts_by_url = await self.highlighter.highlight(fact, scraped_content)

        total_excerpts = sum(len(excerpts) for excerpts in excerpts_by_url.values())
        fact_logger.logger.info(
            f"✂️ Extracted {total_excerpts} excerpts from {len(excerpts_by_url)} sources",
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
        """
        Generate summary for interpretation verification results

        Args:
            results: List of LLMVerificationResult objects
        """
        if not results:
            return {
                "total_claims": 0,
                "accurate_interpretation": 0,
                "good_interpretation": 0,
                "poor_interpretation": 0,
                "avg_interpretation_score": 0.0,
                "common_issues": []
            }

        total = len(results)

        # Interpretation quality breakdown
        accurate = len([r for r in results if r.verification_score >= 0.9])
        good = len([r for r in results if 0.7 <= r.verification_score < 0.9])
        poor = len([r for r in results if r.verification_score < 0.7])
        avg_score = sum(r.verification_score for r in results) / total

        # Collect common interpretation issues
        all_issues = []
        for r in results:
            all_issues.extend(r.interpretation_issues)

        # Get most common issues (simple frequency count)
        from collections import Counter
        issue_counts = Counter(all_issues)
        common_issues = [issue for issue, count in issue_counts.most_common(5)]

        return {
            "total_claims": total,
            "accurate_interpretation": accurate,  # 0.9+
            "good_interpretation": good,          # 0.7-0.89
            "poor_interpretation": poor,          # <0.7
            "avg_interpretation_score": round(avg_score, 3),
            "common_issues": common_issues
        }