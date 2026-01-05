# orchestrator/manipulation_orchestrator.py
"""
Opinion Manipulation Detection Orchestrator
Coordinates the full pipeline for detecting fact manipulation in articles

Pipeline:
1. Article Analysis - Detect agenda, political lean, summary
2. Fact Extraction - Extract facts with framing context
3. Web Search Verification - Verify facts via existing pipeline
4. Manipulation Analysis - Compare verified facts to presentation
5. Report Synthesis - Create comprehensive manipulation report
6. Save audit file to R2

Reuses existing components:
- QueryGenerator for search query creation
- BraveSearcher for web search
- CredibilityFilter for source filtering
- BrowserlessScraper for content scraping
- Highlighter for excerpt extraction
- FactChecker for verification
"""

from langsmith import traceable
import time
import asyncio
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
from utils.job_manager import job_manager
from utils.browserless_scraper import BrowserlessScraper
from utils.brave_searcher import BraveSearcher

# Import the manipulation detector agent
from agents.manipulation_detector import (
    ManipulationDetector,
    ArticleSummary,
    ExtractedFact,
    ManipulationFinding,
    ManipulationReport
)

# Import existing agents for fact verification
from agents.query_generator import QueryGenerator
from agents.credibility_filter import CredibilityFilter
from agents.highlighter import Highlighter
from agents.fact_checker import FactChecker

# Import search audit utilities
from utils.search_audit_builder import (
    build_session_search_audit,
    build_fact_search_audit,
    build_query_audit,
    save_search_audit,
    upload_search_audit_to_r2
)


class CancelledException(Exception):
    """Raised when job is cancelled"""
    pass


class ManipulationOrchestrator:
    """
    Orchestrator for opinion manipulation detection pipeline

    Coordinates:
    1. ManipulationDetector agent (4 stages)
    2. Existing fact-checking components (verification)
    3. Job management and progress streaming
    4. Audit file generation
    """

    def __init__(self, config):
        """
        Initialize the ManipulationOrchestrator

        Args:
            config: Configuration object with API keys and settings.
                   Can be a Config object (with attributes) or a dict.
        """
        self.config = config

        # Initialize the manipulation detector agent
        self.detector = ManipulationDetector(config)

        # Initialize existing fact-checking components
        # FIX: Pass config to BraveSearcher and BrowserlessScraper
        self.query_generator = QueryGenerator(config)
        self.brave_searcher = BraveSearcher(config, max_results=5)
        self.credibility_filter = CredibilityFilter(config)
        self.scraper = BrowserlessScraper(config)
        self.highlighter = Highlighter(config)
        self.fact_checker = FactChecker(config)

        # File manager for audit files
        self.file_manager = FileManager()

        # FIX: Handle config as either dict or object
        if isinstance(config, dict):
            self.max_sources_per_fact = config.get('max_sources_per_fact', 5)
            self.max_facts = config.get('max_facts', 5)
        else:
            self.max_sources_per_fact = getattr(config, 'max_sources_per_fact', 5)
            self.max_facts = getattr(config, 'max_facts', 5)

        # Initialize R2 uploader for audit files
        try:
            from utils.r2_uploader import R2Uploader
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
            fact_logger.logger.info("✅ R2 uploader initialized for manipulation audits")
        except Exception as e:
            self.r2_enabled = False
            self.r2_uploader = None
            fact_logger.logger.warning(f"⚠️ R2 not available for audits: {e}")

        fact_logger.log_component_start(
            "ManipulationOrchestrator",
            max_sources_per_fact=self.max_sources_per_fact,
            max_facts=self.max_facts
        )

    def _check_cancellation(self, job_id: str):
        """Check if job has been cancelled and raise exception if so"""
        if job_manager.is_cancelled(job_id):
            fact_logger.logger.info(f"🛑 Job {job_id} was cancelled")
            raise CancelledException(f"Job {job_id} was cancelled by user")

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        import random
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))
        return f"manip_{timestamp}_{random_suffix}"

    @traceable(
        name="manipulation_detection_pipeline",
        run_type="chain",
        tags=["manipulation-detection", "full-pipeline"]
    )
    async def process_with_progress(
        self,
        content: str,
        job_id: str,
        source_info: str = "Unknown source"
    ) -> Dict[str, Any]:
        """
        Run the full manipulation detection pipeline with progress updates

        Args:
            content: Article text to analyze
            job_id: Job ID for progress tracking
            source_info: URL or source name

        Returns:
            Dict with manipulation report and metadata
        """
        start_time = time.time()
        session_id = self._generate_session_id()

        fact_logger.logger.info(
            "🚀 Starting manipulation detection pipeline",
            extra={
                "job_id": job_id,
                "session_id": session_id,
                "content_length": len(content)
            }
        )

        try:
            # ================================================================
            # STAGE 1: Article Analysis
            # ================================================================
            job_manager.add_progress(job_id, "📰 Analyzing article for agenda and bias...")
            self._check_cancellation(job_id)

            article_summary = await self.detector.analyze_article(content, source_info)

            job_manager.add_progress(
                job_id, 
                f"✅ Detected agenda: {article_summary.detected_agenda[:50]}..."
            )
            job_manager.add_progress(
                job_id,
                f"📊 Political lean: {article_summary.political_lean} | Opinion ratio: {article_summary.opinion_fact_ratio:.0%}"
            )

            # ================================================================
            # STAGE 2: Fact Extraction
            # ================================================================
            job_manager.add_progress(job_id, "🔍 Extracting key facts with framing analysis...")
            self._check_cancellation(job_id)

            facts = await self.detector.extract_facts(content, article_summary)

            if not facts:
                job_manager.add_progress(job_id, "⚠️ No verifiable facts found")
                return self._build_no_facts_result(session_id, article_summary, start_time)

            # Limit facts if needed
            if len(facts) > self.max_facts:
                facts = facts[:self.max_facts]

            job_manager.add_progress(job_id, f"✅ Extracted {len(facts)} key facts for verification")

            # Initialize session audit
            session_audit = build_session_search_audit(
                session_id=session_id,
                pipeline_type="manipulation_detection",
                content_country="international",
                content_language="english"
            )

            # ================================================================
            # STAGE 3: Fact Verification (using existing pipeline)
            # ================================================================
            job_manager.add_progress(job_id, "🌐 Starting fact verification via web search...")
            self._check_cancellation(job_id)

            verification_results = {}
            source_excerpts_by_fact = {}
            query_audits_by_fact = {}

            for i, fact in enumerate(facts, 1):
                job_manager.add_progress(
                    job_id, 
                    f"🔎 Verifying fact {i}/{len(facts)}: {fact.statement[:40]}..."
                )
                self._check_cancellation(job_id)

                # Run verification pipeline for this fact
                verification, excerpts, query_audits = await self._verify_fact(
                    fact=fact,
                    job_id=job_id,
                    article_summary=article_summary
                )

                verification_results[fact.id] = verification
                source_excerpts_by_fact[fact.id] = excerpts
                query_audits_by_fact[fact.id] = query_audits

                # Add to session audit - FIX: Use correct parameters
                fact_audit = build_fact_search_audit(
                    fact_id=fact.id,
                    fact_statement=fact.statement,
                    query_audits=query_audits,
                    credibility_results=None,  # Not available in this context
                    scraped_urls=[],
                    scrape_errors={}
                )
                session_audit.add_fact_audit(fact_audit)

            job_manager.add_progress(job_id, "✅ Fact verification complete")

            # ================================================================
            # STAGE 4: Manipulation Analysis
            # ================================================================
            job_manager.add_progress(job_id, "🔬 Analyzing manipulation patterns...")
            self._check_cancellation(job_id)

            manipulation_findings = []

            for fact in facts:
                self._check_cancellation(job_id)

                verification = verification_results.get(fact.id, {})
                excerpts = source_excerpts_by_fact.get(fact.id, "No excerpts available")

                finding = await self.detector.analyze_manipulation(
                    fact=fact,
                    article_summary=article_summary,
                    verification_result=verification,
                    source_excerpts=excerpts
                )
                manipulation_findings.append(finding)

                if finding.manipulation_detected:
                    job_manager.add_progress(
                        job_id,
                        f"⚠️ Manipulation detected in fact {fact.id}: {finding.manipulation_severity} severity"
                    )

            job_manager.add_progress(job_id, "✅ Manipulation analysis complete")

            # ================================================================
            # STAGE 5: Report Synthesis
            # ================================================================
            job_manager.add_progress(job_id, "📊 Synthesizing final report...")
            self._check_cancellation(job_id)

            processing_time = time.time() - start_time

            report = await self.detector.synthesize_report(
                article_summary=article_summary,
                facts=facts,
                manipulation_findings=manipulation_findings,
                processing_time=processing_time
            )

            job_manager.add_progress(
                job_id,
                f"✅ Manipulation score: {report.overall_manipulation_score:.1f}/10"
            )

            # ================================================================
            # STAGE 6: Save Audit File
            # ================================================================
            job_manager.add_progress(job_id, "💾 Saving audit report...")

            # Save search audit - FIX: Use correct parameters
            audit_path = save_search_audit(
                session_audit=session_audit,
                file_manager=self.file_manager,
                session_id=session_id,
                filename="search_audit.json"
            )

            r2_url = None

            # FIX: Use correct parameters for upload_search_audit_to_r2
            if audit_path and self.r2_enabled and self.r2_uploader:
                r2_url = await upload_search_audit_to_r2(
                    session_audit=session_audit,
                    session_id=session_id,
                    r2_uploader=self.r2_uploader,
                    pipeline_type="manipulation-detection"
                )
                if r2_url:
                    job_manager.add_progress(job_id, "☁️ Audit saved to cloud")

            # Build final result
            result = self._build_result(
                session_id=session_id,
                report=report,
                facts=facts,
                verification_results=verification_results,
                r2_url=r2_url,
                start_time=start_time
            )

            job_manager.add_progress(job_id, "✅ Analysis complete!")

            fact_logger.logger.info(
                "✅ Manipulation detection pipeline complete",
                extra={
                    "session_id": session_id,
                    "manipulation_score": report.overall_manipulation_score,
                    "processing_time": round(time.time() - start_time, 2)
                }
            )

            return result

        except CancelledException:
            job_manager.add_progress(job_id, "🛑 Analysis cancelled by user")
            raise

        except Exception as e:
            fact_logger.logger.error(f"❌ Pipeline failed: {e}")
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")
            job_manager.add_progress(job_id, f"❌ Error: {str(e)}")
            raise

    async def _verify_fact(
        self,
        fact: ExtractedFact,
        job_id: str,
        article_summary: ArticleSummary
    ) -> tuple:
        """
        Verify a single fact using the existing fact-checking pipeline

        Returns:
            Tuple of (verification_result, formatted_excerpts, query_audits)
        """
        query_audits = []

        try:
            # Step 1: Generate search queries
            # Create a fact-like object for the query generator
            fact_obj = type('Fact', (), {
                'id': fact.id,
                'statement': fact.statement
            })()

            queries = await self.query_generator.generate_queries(
                fact=fact_obj,
                context=f"Article agenda: {article_summary.detected_agenda}"
            )

            if not queries or not queries.primary_query:
                return self._empty_verification("No queries generated"), "", []

            # Step 2: Execute web search
            all_search_results = []

            # Search with primary query
            primary_results = await self.brave_searcher.search(
                queries.primary_query
            )

            if primary_results and primary_results.results:
                all_search_results.extend(primary_results.results)

                # FIX: Use correct parameters for build_query_audit
                query_audit = build_query_audit(
                    query=queries.primary_query,
                    brave_results=primary_results,
                    query_type="primary",
                    language="en"
                )
                query_audits.append(query_audit)

            # Search with alternative queries if available
            if hasattr(queries, 'alternative_queries') and queries.alternative_queries:
                for alt_query in queries.alternative_queries[:2]:
                    alt_results = await self.brave_searcher.search(alt_query)
                    if alt_results and alt_results.results:
                        all_search_results.extend(alt_results.results)

                        # FIX: Use correct parameters for build_query_audit
                        query_audit = build_query_audit(
                            query=alt_query,
                            brave_results=alt_results,
                            query_type="alternative",
                            language="en"
                        )
                        query_audits.append(query_audit)

            if not all_search_results:
                return self._empty_verification("No search results found"), "", query_audits

            # Step 3: Filter by credibility
            credibility_results = await self.credibility_filter.evaluate_sources(
                fact=fact_obj,
                search_results=all_search_results
            )

            if not credibility_results:
                return self._empty_verification("No credible sources found"), "", query_audits

            credible_urls = credibility_results.get_recommended_urls(min_score=0.70)
            if not credible_urls:
                return self._empty_verification("No credible sources found"), "", query_audits

            source_metadata = credibility_results.source_metadata

            # Step 4: Scrape credible sources
            scraped_content = await self.scraper.scrape_urls_for_facts(
                credible_urls[:self.max_sources_per_fact]
            )

            if not scraped_content or not any(scraped_content.values()):
                return self._empty_verification("Failed to scrape sources"), "", query_audits

            # Step 5: Extract relevant excerpts
            # FIX: Use correct method name - highlighter.highlight() not extract_excerpts()
            all_excerpts = []

            for url, content in scraped_content.items():
                if not content:
                    continue

                # Create a simple fact object for the highlighter
                simple_fact = type('Fact', (), {
                    'id': fact.id,
                    'statement': fact.statement
                })()

                # FIX: Use the correct method - highlight() returns {url: [excerpts]}
                excerpts_dict = await self.highlighter.highlight(
                    fact=simple_fact,
                    scraped_content={url: content}
                )

                excerpts_for_url = excerpts_dict.get(url, [])

                if excerpts_for_url:
                    # FIX: Get tier from source_metadata properly (it's a dict of SourceMetadata objects)
                    tier = 'unknown'
                    if source_metadata and url in source_metadata:
                        metadata_obj = source_metadata[url]
                        # SourceMetadata is an object, not a dict
                        tier = getattr(metadata_obj, 'credibility_tier', 'unknown')

                    for excerpt in excerpts_for_url:
                        all_excerpts.append({
                            'url': url,
                            'tier': tier,
                            'quote': excerpt.get('quote', '') if isinstance(excerpt, dict) else str(excerpt),
                            'relevance': excerpt.get('relevance', 0.5) if isinstance(excerpt, dict) else 0.5
                        })

            if not all_excerpts:
                return self._empty_verification("No relevant excerpts found"), "", query_audits

            # Step 6: Verify fact
            # Sort excerpts by tier and relevance
            tier_order = {'tier1': 0, 'tier2': 1, 'tier3': 2, 'unknown': 3}
            all_excerpts.sort(key=lambda x: (
                tier_order.get(x['tier'], 3),
                -x['relevance']
            ))

            # Format excerpts for fact checker
            formatted_excerpts = self._format_excerpts_for_checker(all_excerpts)

            # Convert all_excerpts list to the dict format that check_fact expects
            excerpts_by_url = {}
            for excerpt in all_excerpts:
                url = excerpt.get('url', '')
                if url not in excerpts_by_url:
                    excerpts_by_url[url] = []
                excerpts_by_url[url].append({
                    'quote': excerpt.get('quote', ''),
                    'relevance': excerpt.get('relevance', 0.5),
                    'context': excerpt.get('context', ''),
                    'tier': excerpt.get('tier', 'unknown')
                })

            verification_result = await self.fact_checker.check_fact(
                fact=fact_obj,
                excerpts=excerpts_by_url,  # Properly formatted: {url: [excerpt_dicts]}
                source_metadata=source_metadata
            )

            # Build result
            result = {
                'match_score': verification_result.match_score if verification_result else 0.5,
                'confidence': verification_result.confidence if verification_result else 0.5,
                'report': verification_result.report if verification_result else "Verification incomplete",
                'sources_used': credible_urls,
                'excerpts': formatted_excerpts
            }

            return result, formatted_excerpts, query_audits

        except Exception as e:
            fact_logger.logger.error(f"❌ Fact verification failed: {e}")
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")
            return self._empty_verification(f"Error: {str(e)}"), "", query_audits

    def _empty_verification(self, reason: str) -> Dict[str, Any]:
        """Return empty verification result"""
        return {
            'match_score': 0.5,
            'confidence': 0.0,
            'report': reason,
            'sources_used': [],
            'excerpts': ""
        }

    def _format_excerpts_for_checker(self, excerpts: List[Dict]) -> str:
        """Format excerpts for the fact checker"""
        lines = []

        for excerpt in excerpts[:10]:  # Limit to 10 excerpts
            tier_label = excerpt['tier'].upper() if excerpt['tier'] else 'UNKNOWN'
            quote = excerpt.get('quote', '')
            url = excerpt.get('url', 'Unknown URL')

            lines.append(f"[{tier_label}] {url}")
            if len(quote) > 500:
                lines.append(f"  \"{quote[:500]}...\"")
            else:
                lines.append(f"  \"{quote}\"")
            lines.append("")

        return "\n".join(lines)

    def _build_no_facts_result(
        self,
        session_id: str,
        article_summary: ArticleSummary,
        start_time: float
    ) -> Dict[str, Any]:
        """Build result when no facts were extracted"""
        return {
            'success': True,
            'session_id': session_id,
            'article_summary': {
                'main_thesis': article_summary.main_thesis,
                'political_lean': article_summary.political_lean,
                'detected_agenda': article_summary.detected_agenda,
                'opinion_fact_ratio': article_summary.opinion_fact_ratio,
                'emotional_tone': article_summary.emotional_tone
            },
            'manipulation_score': 0.0,
            'facts_analyzed': [],
            'manipulation_findings': [],
            'report': {
                'overall_score': 0.0,
                'justification': "No verifiable facts could be extracted from the article",
                'techniques_used': [],
                'what_got_right': ["Article may be purely opinion-based"],
                'misleading_elements': [],
                'recommendation': "This article appears to contain no verifiable factual claims."
            },
            'processing_time': time.time() - start_time,
            'r2_url': None
        }

    def _build_result(
        self,
        session_id: str,
        report: ManipulationReport,
        facts: List[ExtractedFact],
        verification_results: Dict[str, Dict],
        r2_url: Optional[str],
        start_time: float
    ) -> Dict[str, Any]:
        """Build the final result dictionary"""

        # Format facts for response
        facts_data = []
        for fact in facts:
            verification = verification_results.get(fact.id, {})
            facts_data.append({
                'id': fact.id,
                'statement': fact.statement,
                'original_text': fact.original_text,
                'framing': fact.framing,
                'context_given': fact.context_given,
                'context_potentially_omitted': fact.context_potentially_omitted,
                'manipulation_potential': fact.manipulation_potential,
                'verification': {
                    'match_score': verification.get('match_score', 0.5),
                    'sources_used': verification.get('sources_used', [])
                }
            })

        # Format manipulation findings
        findings_data = []
        for finding in report.facts_analyzed:
            findings_data.append({
                'fact_id': finding.fact_id,
                'fact_statement': finding.fact_statement,
                'truthfulness': finding.truthfulness,
                'truth_score': finding.truth_score,
                'manipulation_detected': finding.manipulation_detected,
                'manipulation_types': finding.manipulation_types,
                'manipulation_severity': finding.manipulation_severity,
                'what_was_omitted': finding.what_was_omitted,
                'how_it_serves_agenda': finding.how_it_serves_agenda,
                'corrected_context': finding.corrected_context,
                'sources_used': finding.sources_used
            })

        return {
            'success': True,
            'session_id': session_id,
            'article_summary': {
                'main_thesis': report.article_summary.main_thesis,
                'political_lean': report.article_summary.political_lean,
                'detected_agenda': report.article_summary.detected_agenda,
                'opinion_fact_ratio': report.article_summary.opinion_fact_ratio,
                'emotional_tone': report.article_summary.emotional_tone,
                'target_audience': report.article_summary.target_audience,
                'rhetorical_strategies': report.article_summary.rhetorical_strategies,
                'summary': report.article_summary.summary
            },
            'manipulation_score': report.overall_manipulation_score,
            'facts_analyzed': facts_data,
            'manipulation_findings': findings_data,
            'report': {
                'overall_score': report.overall_manipulation_score,
                'justification': report.score_justification,
                'techniques_used': report.manipulation_techniques_used,
                'what_got_right': report.what_article_got_right,
                'misleading_elements': report.key_misleading_elements,
                'agenda_alignment': report.agenda_alignment_analysis,
                'recommendation': report.reader_recommendation,
                'confidence': report.confidence
            },
            'processing_time': report.processing_time,
            'r2_url': r2_url
        }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_manipulation_orchestrator(config=None) -> ManipulationOrchestrator:
    """
    Factory function to create a ManipulationOrchestrator instance

    Args:
        config: Configuration object or dictionary

    Returns:
        Configured ManipulationOrchestrator instance
    """
    if config is None:
        config = {}

    return ManipulationOrchestrator(config)