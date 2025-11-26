# orchestrator/llm_output_orchestrator_updated.py
"""
LLM Interpretation Verification Orchestrator

PURPOSE: Verify if LLMs (ChatGPT, Perplexity) accurately interpreted their cited sources

PROCESS: LLM Output Verification
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
from agents.llm_fact_extractor import LLMFactExtractor  # ✅ New extractor
from agents.highlighter import Highlighter
# We'll update the verifier import after creating the updated file
from utils.job_manager import job_manager


class LLMInterpretationOrchestrator:
    """
    Verify LLM interpretation accuracy

    Pipeline:
    1. Parse LLM output (ChatGPT, Perplexity, etc.)
    2. Extract claim segments (preserving LLM wording)
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
        self.extractor = LLMFactExtractor(config)  # ✅ Use new extractor
        self.scraper = FactCheckScraper(config)
        self.highlighter = Highlighter(config)
        # Will import updated verifier
        from agents.llm_output_verifier_updated import LLMOutputVerifier
        self.verifier = LLMOutputVerifier(config)
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

            # Step 2: Extract claim segments (with source mapping)
            job_manager.add_progress(job_id, "🔍 Extracting LLM claim segments...")
            self._check_cancellation(job_id)

            # ✅ Use new extractor that preserves wording and maps sources
            claims, all_source_urls = await self.extractor.extract_claims(parsed)

            job_manager.add_progress(
                job_id,
                f"✅ Found {len(claims)} claim segments citing {len(all_source_urls)} sources"
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
            for i, claim in enumerate(claims, 1):
                job_manager.add_progress(
                    job_id,
                    f"🔬 Checking claim {i}/{len(claims)}: \"{claim.claim_text[:60]}...\"",
                    {'claim_id': claim.id, 'progress': f"{i}/{len(claims)}"}
                )
                self._check_cancellation(job_id)

                # Extract relevant excerpts from the cited source
                excerpts = await self._extract_excerpts(claim, all_scraped_content)

                # ✅ VERIFY INTERPRETATION
                verification = await self.verifier.verify_interpretation(
                    claim,
                    excerpts,
                    all_scraped_content
                )

                results.append(verification)

                # Update progress with score
                score_emoji = self._get_score_emoji(verification.verification_score)
                job_manager.add_progress(
                    job_id,
                    f"{score_emoji} {claim.id}: {verification.verification_score:.2f} - {verification.assessment[:50]}...",
                    {
                        'claim_id': claim.id,
                        'score': verification.verification_score,
                        'assessment': verification.assessment
                    }
                )

            # Step 5: Create summary
            job_manager.add_progress(job_id, "📊 Creating verification summary...")
            summary = self._create_summary(results, claims, all_source_urls)

            # Step 6: Save results
            job_manager.add_progress(job_id, "💾 Saving results...")
            await self._save_results(session_id, results, summary, html_content)

            duration = time.time() - start_time
            job_manager.add_progress(
                job_id,
                f"✅ Verification complete in {duration:.1f}s - {len(results)} claims analyzed"
            )

            fact_logger.logger.info(
                f"🎉 INTERPRETATION VERIFICATION COMPLETE: {session_id}",
                extra={
                    "session_id": session_id,
                    "num_claims": len(results),
                    "duration": duration,
                    "avg_score": summary['average_score']
                }
            )

            return {
                'session_id': session_id,
                'results': results,
                'summary': summary,
                'duration': duration
            }

        except Exception as e:
            fact_logger.log_component_error("LLMInterpretationOrchestrator", e)
            job_manager.add_progress(
                job_id,
                f"❌ Error: {str(e)}",
                {'error': str(e)}
            )
            raise

    @traceable(name="parse_llm_output", run_type="parser")
    async def _traced_parse(self, html_content: str) -> dict:
        """Parse LLM output with tracing"""
        return self.parser.parse(html_content)

    @traceable(name="extract_excerpts_for_claim", run_type="chain")
    async def _extract_excerpts(self, claim, scraped_content: dict) -> dict:
        """Extract relevant excerpts for a specific claim"""

        fact_logger.logger.info(
            f"🔦 Extracting excerpts for {claim.id}",
            extra={"claim_id": claim.id, "cited_source": claim.cited_source}
        )

        # Only extract from the cited source
        cited_url = claim.cited_source

        if cited_url not in scraped_content or not scraped_content[cited_url]:
            fact_logger.logger.warning(
                f"⚠️ Cited source not available: {cited_url}",
                extra={"claim_id": claim.id, "url": cited_url}
            )
            return {}

        # Highlight excerpts from the cited source
        excerpts = await self.highlighter.highlight(
            claim.claim_text,  # ✅ Use claim_text
            cited_url,
            scraped_content[cited_url]
        )

        fact_logger.logger.info(
            f"✂️ Extracted {len(excerpts)} excerpts from cited source",
            extra={"claim_id": claim.id, "num_excerpts": len(excerpts)}
        )

        return {cited_url: excerpts}

    def _get_score_emoji(self, score: float) -> str:
        """Get emoji based on verification score"""
        if score >= 0.9:
            return "✅"
        elif score >= 0.75:
            return "✔️"
        elif score >= 0.6:
            return "⚠️"
        elif score >= 0.3:
            return "❌"
        else:
            return "🚫"

    def _create_summary(self, results: list, claims: list, sources: list) -> dict:
        """Create summary statistics"""
        scores = [r.verification_score for r in results]

        return {
            'total_claims': len(claims),
            'total_sources': len(sources),
            'average_score': sum(scores) / len(scores) if scores else 0.0,
            'accurate_count': len([s for s in scores if s >= 0.9]),
            'mostly_accurate_count': len([s for s in scores if 0.75 <= s < 0.9]),
            'partially_accurate_count': len([s for s in scores if 0.6 <= s < 0.75]),
            'misleading_count': len([s for s in scores if 0.3 <= s < 0.6]),
            'false_count': len([s for s in scores if s < 0.3]),
            'score_distribution': {
                'min': min(scores) if scores else 0.0,
                'max': max(scores) if scores else 0.0,
                'median': sorted(scores)[len(scores)//2] if scores else 0.0
            }
        }

    async def _save_results(self, session_id: str, results: list, summary: dict, original_content: str):
        """Save verification results"""

        # Format results for saving
        report_lines = [
            "=" * 80,
            "LLM INTERPRETATION VERIFICATION REPORT",
            "=" * 80,
            f"\nSession ID: {session_id}",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"\nSUMMARY:",
            f"  Total Claims Analyzed: {summary['total_claims']}",
            f"  Sources Cited: {summary['total_sources']}",
            f"  Average Verification Score: {summary['average_score']:.2f}",
            f"\n  Accuracy Breakdown:",
            f"    ✅ Accurate (0.9+): {summary['accurate_count']}",
            f"    ✔️  Mostly Accurate (0.75-0.89): {summary['mostly_accurate_count']}",
            f"    ⚠️  Partially Accurate (0.6-0.74): {summary['partially_accurate_count']}",
            f"    ❌ Misleading (0.3-0.59): {summary['misleading_count']}",
            f"    🚫 False (0.0-0.29): {summary['false_count']}",
            "\n" + "=" * 80,
            "DETAILED RESULTS:",
            "=" * 80,
        ]

        for result in results:
            emoji = self._get_score_emoji(result.verification_score)
            report_lines.extend([
                f"\n{emoji} {result.claim_id} - Score: {result.verification_score:.2f}",
                f"Claim: {result.claim_text}",
                f"Assessment: {result.assessment}",
                f"Confidence: {result.confidence:.2f}",
            ])

            if result.interpretation_issues:
                report_lines.append("Issues Found:")
                for issue in result.interpretation_issues:
                    report_lines.append(f"  - {issue}")

            report_lines.append("-" * 80)

        report_text = "\n".join(report_lines)

        # Save to file manager
        await self.file_manager.save_session_content(
            session_id,
            report_text,
            original_content
        )

        fact_logger.logger.info(
            f"✅ Session {session_id} saved",
            extra={"session_id": session_id}
        )