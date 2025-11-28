# orchestrator/llm_output_orchestrator_updated.py
"""
LLM Interpretation Verification Orchestrator

PURPOSE: Verify if LLMs (ChatGPT and Perplexity) accurately interpreted their cited sources

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
import asyncio

from utils.html_parser import HTMLParser
from utils.file_manager import FileManager
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

from agents.browserless_scraper import FactCheckScraper
from agents.llm_fact_extractor import LLMFactExtractor  # ✅ New extractor
from agents.highlighter import Highlighter
# We'll update the verifier import after creating the updated file
from utils.job_manager import job_manager

class SimpleFact:
    """Simple Fact-like object for Highlighter compatibility"""
    def __init__(self, id: str, statement: str):
        self.id = id
        self.statement = statement

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
        from agents.llm_output_verifier import LLMOutputVerifier
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

            # Step 4: Verify each claim's interpretation (✅ OPTIMIZED: Parallel processing)
            job_manager.add_progress(
                job_id,
                f"🔬 Verifying {len(claims)} claims in parallel..."
            )
            self._check_cancellation(job_id)

            # ✅ NEW: Create verification tasks for parallel execution
            async def verify_single_claim(claim, claim_index):
                """Verify a single claim and return result"""
                try:
                    # Extract relevant excerpts from the cited sources
                    excerpts = await self._extract_excerpts(claim, all_scraped_content)

                    # Verify interpretation
                    verification = await self.verifier.verify_interpretation(
                        claim,
                        excerpts,
                        all_scraped_content
                    )

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

                    return verification

                except Exception as e:
                    fact_logger.logger.error(f"❌ Error verifying {claim.id}: {e}")
                    # Return a failed verification result
                    from agents.llm_output_verifier import LLMVerificationResult
                    return LLMVerificationResult(
                        claim_id=claim.id,
                        claim_text=claim.claim_text,
                        verification_score=0.0,
                        assessment=f"Verification error: {str(e)}",
                        interpretation_issues=["Error during verification"],
                        wording_comparison={},
                        confidence=0.0,
                        reasoning=str(e),
                        excerpts=[],
                        cited_source_urls=claim.cited_sources
                    )

            # ✅ Execute all verifications in parallel
            verification_tasks = [
                verify_single_claim(claim, i)
                for i, claim in enumerate(claims, 1)
            ]

            results = await asyncio.gather(*verification_tasks, return_exceptions=False)

            job_manager.add_progress(job_id, "✅ All claims verified")

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

            # ✅ Convert Pydantic objects to dicts for JSON serialization
            return {
                'session_id': session_id,
                'results': [result.model_dump() for result in results],  # Convert to dict
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
        return self.parser.parse_input(html_content)

    @traceable(name="extract_excerpts_for_claim", run_type="chain")
    async def _extract_excerpts(self, claim, scraped_content: dict) -> dict:
        """
        Extract relevant excerpts for a claim from ALL its cited sources

        ✅ UPDATED: Now handles multiple cited sources per claim
        """

        fact_logger.logger.info(
            f"🔦 Extracting excerpts for {claim.id} from {len(claim.cited_sources)} source(s)",
            extra={
                "claim_id": claim.id, 
                "num_cited_sources": len(claim.cited_sources),
                "cited_sources": claim.cited_sources
            }
        )

        # ✅ Extract excerpts from ALL cited sources
        all_excerpts_by_url = {}

        for cited_url in claim.cited_sources:
            if cited_url not in scraped_content or not scraped_content[cited_url]:
                fact_logger.logger.warning(
                    f"⚠️ Cited source not available: {cited_url}",
                    extra={"claim_id": claim.id, "url": cited_url}
                )
                all_excerpts_by_url[cited_url] = []
                continue

            # ✅ Create a Fact-like object for Highlighter
            simple_fact = SimpleFact(
                id=claim.id,
                statement=claim.claim_text
            )

            # ✅ Create proper dict format: {url: content}
            cited_content = {cited_url: scraped_content[cited_url]}

            # ✅ Call highlighter with correct signature (2 args)
            excerpts_dict = await self.highlighter.highlight(simple_fact, cited_content)

            # Extract excerpts list for this URL
            excerpts = excerpts_dict.get(cited_url, [])
            all_excerpts_by_url[cited_url] = excerpts

            fact_logger.logger.debug(
                f"✂️ Extracted {len(excerpts)} excerpts from {cited_url}",
                extra={
                    "claim_id": claim.id, 
                    "url": cited_url,
                    "num_excerpts": len(excerpts)
                }
            )

        total_excerpts = sum(len(e) for e in all_excerpts_by_url.values())
        fact_logger.logger.info(
            f"✅ Total excerpts for {claim.id}: {total_excerpts} from {len(all_excerpts_by_url)} sources",
            extra={"claim_id": claim.id, "total_excerpts": total_excerpts}
        )

        return all_excerpts_by_url

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

            # ✅ Add wording comparison section
            if result.wording_comparison:
                report_lines.append("\nWORDING COMPARISON:")
                wc = result.wording_comparison
                if wc.get('llm_claim'):
                    report_lines.append(f"  LLM Said: \"{wc.get('llm_claim')}\"")
                if wc.get('source_says'):
                    report_lines.append(f"  Source Says: \"{wc.get('source_says')}\"")
                if 'faithful' in wc:
                    faithful_status = "✓ Faithful" if wc.get('faithful') else "✗ Not Faithful"
                    report_lines.append(f"  {faithful_status}")

            # ✅ Add highlighted excerpts section
            if result.excerpts:
                report_lines.append(f"\nHIGHLIGHTED EXCERPTS FROM SOURCE ({len(result.excerpts)} found):")
                for i, excerpt in enumerate(result.excerpts[:3], 1):  # Show top 3 excerpts
                    relevance = excerpt.get('relevance', 0)
                    quote = excerpt.get('quote', '').strip()
                    if quote:
                        # Truncate long quotes
                        if len(quote) > 300:
                            quote = quote[:300] + "..."
                        report_lines.append(f"  [{i}] Relevance: {relevance:.2f}")
                        report_lines.append(f"      \"{quote}\"")
                if len(result.excerpts) > 3:
                    report_lines.append(f"  ... and {len(result.excerpts) - 3} more excerpts")
                # ✅ Display all checked sources (now a list)
                if result.cited_source_urls:
                    if len(result.cited_source_urls) == 1:
                        report_lines.append(f"  Source: {result.cited_source_urls[0]}")
                    else:
                        report_lines.append(f"  Sources ({len(result.cited_source_urls)} checked):")
                        for i, url in enumerate(result.cited_source_urls, 1):
                            report_lines.append(f"    [{i}] {url}")

            # ✅ Add detailed reasoning section
            if result.reasoning:
                report_lines.append("\nREASONING:")
                # Format reasoning with proper indentation
                reasoning_lines = result.reasoning.split('\n')
                for line in reasoning_lines:
                    report_lines.append(f"  {line}")

            if result.interpretation_issues:
                report_lines.append("\nISSUES FOUND:")
                for issue in result.interpretation_issues:
                    report_lines.append(f"  - {issue}")

            report_lines.append("-" * 80)

        report_text = "\n".join(report_lines)

        # ✅ FIXED: Use the new save_verification_report method
        upload_result = self.file_manager.save_verification_report(
            session_id,
            report_text,
            original_content,
            upload_to_r2=True
        )

        fact_logger.logger.info(
            f"✅ Session {session_id} saved",
            extra={
                "session_id": session_id,
                "r2_upload_success": upload_result.get('success', False),
                "r2_url": upload_result.get('url')
            }
        )

        return upload_result