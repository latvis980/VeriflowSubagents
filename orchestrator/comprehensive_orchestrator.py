# orchestrator/comprehensive_orchestrator.py
"""
Comprehensive Analysis Orchestrator
Coordinates the full 3-stage comprehensive analysis pipeline

STAGE 1: Pre-Analysis
- Content Classification (type, realm, LLM detection)
- Source Verification (credibility tier, MBFC check)
- Author Investigation (future enhancement)
- Mode Routing (decide which modes to run)

STAGE 2: Parallel Mode Execution
- Run selected modes simultaneously using asyncio.gather()
- Collect reports from each mode
- Stream progress updates

STAGE 3: AI-Powered Synthesis (NEW - Full Implementation)
- Uses ReportSynthesizer agent with GPT-4o
- Analyzes all reports together
- Generates unified credibility score (0-100) and rating
- Detects cross-mode contradictions
- Categorizes flags by type (credibility, bias, manipulation, factual accuracy)
- Extracts key findings prioritized by importance
- Provides actionable recommendations
- Creates human-readable narrative summary

✅ OPTIMIZED: All modes run in parallel for maximum speed
"""

from langsmith import traceable
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from utils.logger import fact_logger
from utils.file_manager import FileManager
from utils.job_manager import job_manager

# Stage 1 components
from agents.content_classifier import ContentClassifier
from utils.source_verifier import SourceVerifier
from agents.mode_router import ModeRouter

# Stage 2: Mode orchestrators
from orchestrator.key_claims_orchestrator import KeyClaimsOrchestrator
from orchestrator.bias_check_orchestrator import BiasCheckOrchestrator
from orchestrator.manipulation_orchestrator import ManipulationOrchestrator
from orchestrator.lie_detector_orchestrator import LieDetectorOrchestrator

# Stage 3: Report Synthesizer (NEW)
from agents.report_synthesizer import ReportSynthesizer


class CancelledException(Exception):
    """Raised when job is cancelled"""
    pass


class ComprehensiveOrchestrator:
    """
    Master orchestrator for comprehensive analysis mode

    Coordinates:
    - Stage 1: Content classification, source verification, mode routing
    - Stage 2: Parallel execution of selected analysis modes
    - Stage 3: AI-powered synthesis of all findings (NEW)
    """

    def __init__(self, config):
        self.config = config
        self.file_manager = FileManager()

        # Stage 1 components
        self.content_classifier = ContentClassifier()
        self.source_verifier = SourceVerifier(config)
        self.mode_router = ModeRouter()

        # Stage 2 orchestrators (initialized on demand)
        self._key_claims_orchestrator: Optional[KeyClaimsOrchestrator] = None
        self._bias_orchestrator: Optional[BiasCheckOrchestrator] = None
        self._manipulation_orchestrator: Optional[ManipulationOrchestrator] = None
        self._lie_detection_orchestrator: Optional[LieDetectorOrchestrator] = None

        # Stage 3: Report Synthesizer (NEW)
        self._report_synthesizer: Optional[ReportSynthesizer] = None

        # R2 uploader for audit storage
        try:
            from utils.r2_uploader import R2Uploader
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
        except Exception as e:
            self.r2_enabled = False
            self.r2_uploader = None
            fact_logger.logger.warning(f"⚠️ R2 not available: {e}")

        fact_logger.logger.info("✅ ComprehensiveOrchestrator initialized (with Stage 3 Synthesis)")

    # =========================================================================
    # LAZY INITIALIZATION OF MODE ORCHESTRATORS
    # =========================================================================

    def _get_key_claims_orchestrator(self) -> KeyClaimsOrchestrator:
        """Lazy init for key claims orchestrator"""
        if self._key_claims_orchestrator is None:
            self._key_claims_orchestrator = KeyClaimsOrchestrator(self.config)
        return self._key_claims_orchestrator

    def _get_bias_orchestrator(self) -> BiasCheckOrchestrator:
        """Lazy init for bias orchestrator"""
        if self._bias_orchestrator is None:
            self._bias_orchestrator = BiasCheckOrchestrator(self.config)
        return self._bias_orchestrator

    def _get_manipulation_orchestrator(self) -> ManipulationOrchestrator:
        """Lazy init for manipulation orchestrator"""
        if self._manipulation_orchestrator is None:
            self._manipulation_orchestrator = ManipulationOrchestrator(self.config)
        return self._manipulation_orchestrator

    def _get_lie_detection_orchestrator(self) -> LieDetectorOrchestrator:
        """Lazy init for lie detection orchestrator"""
        if self._lie_detection_orchestrator is None:
            self._lie_detection_orchestrator = LieDetectorOrchestrator(self.config)
        return self._lie_detection_orchestrator

    def _get_report_synthesizer(self) -> ReportSynthesizer:
        """Lazy init for report synthesizer (Stage 3)"""
        if self._report_synthesizer is None:
            self._report_synthesizer = ReportSynthesizer()
        return self._report_synthesizer

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _check_cancellation(self, job_id: str):
        """Check if job was cancelled and raise exception if so"""
        if job_manager.is_cancelled(job_id):
            raise CancelledException("Job cancelled by user")

    def _send_stage_update(self, job_id: str, stage: str, message: str):
        """Send a stage update progress message"""
        job_manager.add_progress(job_id, message, details={"stage": stage})

    # =========================================================================
    # STAGE 1: PRE-ANALYSIS
    # =========================================================================

    @traceable(name="comprehensive_stage1_preanalysis", run_type="chain", tags=["comprehensive", "stage1"])
    async def _run_stage1(
        self,
        content: str,
        job_id: str,
        source_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Stage 1: Pre-Analysis

        Steps:
        1a. Content Classification
        1b. Source Verification (if URL provided)
        1c. Mode Routing
        """
        stage1_results: Dict[str, Any] = {
            "content_classification": None,
            "source_verification": None,
            "author_info": None,  # Future enhancement
            "mode_routing": None
        }

        try:
            # Step 1a: Content Classification
            self._send_stage_update(job_id, "content_classification", "📋 Analyzing content type...")
            self._check_cancellation(job_id)

            classification_result = await self.content_classifier.classify(content)

            if classification_result.success:
                stage1_results["content_classification"] = classification_result.classification.model_dump()
                job_manager.add_progress(
                    job_id,
                    f"✅ Content classified: {classification_result.classification.content_type} ({classification_result.classification.realm})"
                )
            else:
                stage1_results["content_classification"] = {"error": classification_result.error}

            # Send partial result
            job_manager.add_progress(job_id, "Content classification complete", details={
                "partial_result": {"content_classification": stage1_results["content_classification"]}
            })

            # Step 1b: Source Verification
            self._send_stage_update(job_id, "source_verification", "🔍 Verifying source credibility...")
            self._check_cancellation(job_id)

            if source_url:
                verification_result = await self.source_verifier.verify_source(source_url)

                if verification_result.report.verification_successful:
                    stage1_results["source_verification"] = {
                        "domain": verification_result.report.domain,
                        "credibility_tier": verification_result.report.credibility_tier,
                        "tier_description": verification_result.report.tier_description,
                        "verification_source": verification_result.report.verification_source,
                        "bias_rating": verification_result.report.bias_rating,
                        "factual_reporting": verification_result.report.factual_reporting,
                        "is_propaganda": verification_result.report.is_propaganda,
                        "verification_successful": verification_result.report.verification_successful
                    }
                    job_manager.add_progress(
                        job_id,
                        f"✅ Source verified: Tier {verification_result.report.credibility_tier} ({verification_result.report.domain})"
                    )
                else:
                    stage1_results["source_verification"] = {
                        "error": verification_result.report.error if verification_result.report.error else "Verification failed"
                    }
            else:
                stage1_results["source_verification"] = {"status": "no_url_to_verify"}
                job_manager.add_progress(job_id, "ℹ️ No source URL to verify")

            # Send partial result
            job_manager.add_progress(job_id, "Source verification complete", details={
                "partial_result": {"source_verification": stage1_results["source_verification"]}
            })

            # Step 1c: Mode Routing
            self._send_stage_update(job_id, "mode_routing", "🎯 Selecting analysis modes...")
            self._check_cancellation(job_id)

            routing_result = await self.mode_router.route(
                content_classification=stage1_results["content_classification"] or {},
                source_verification=stage1_results["source_verification"],
                author_info=stage1_results["author_info"]
            )

            if routing_result.success:
                stage1_results["mode_routing"] = {
                    "selected_modes": routing_result.selection.selected_modes,
                    "excluded_modes": routing_result.selection.excluded_modes,
                    "exclusion_rationale": routing_result.selection.exclusion_rationale,
                    "routing_reasoning": routing_result.selection.routing_reasoning,
                    "routing_confidence": routing_result.selection.routing_confidence
                }
                job_manager.add_progress(
                    job_id,
                    f"✅ Selected modes: {', '.join(routing_result.selection.selected_modes)}"
                )
            else:
                # Default to key claims on routing error
                stage1_results["mode_routing"] = {
                    "selected_modes": ["key_claims_analysis"],
                    "excluded_modes": [],
                    "routing_reasoning": "Default selection due to routing error"
                }

            # Send partial result
            job_manager.add_progress(job_id, "Mode routing complete", details={
                "partial_result": {"mode_routing": stage1_results["mode_routing"]}
            })

            return stage1_results

        except CancelledException:
            raise
        except Exception as e:
            fact_logger.logger.error(f"❌ Stage 1 error: {e}")
            raise

    # =========================================================================
    # STAGE 2: PARALLEL MODE EXECUTION
    # =========================================================================

    async def _run_single_mode(
        self,
        mode_id: str,
        content: str,
        job_id: str,
        stage1_results: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Run a single analysis mode

        Returns: (mode_id, result_dict, error_message)
        """
        try:
            self._check_cancellation(job_id)

            # Get source context for modes that need it
            source_context = stage1_results.get("content_classification") or {}
            source_credibility = stage1_results.get("source_verification") or {}

            if mode_id == "key_claims_analysis":
                orchestrator = self._get_key_claims_orchestrator()
                result = await orchestrator.process_with_progress(
                    text_content=content,
                    job_id=job_id,
                    source_context=source_context,
                    source_credibility=source_credibility,
                    standalone=False  # ADD THIS
                )
                return (mode_id, result, None)

            elif mode_id == "bias_analysis":
                orchestrator = self._get_bias_orchestrator()
                publication_name = source_credibility.get("domain", "")

                result = await orchestrator.process_with_progress(
                    text=content,
                    publication_name=publication_name,
                    source_credibility=source_credibility if source_credibility else None,
                    job_id=job_id,
                    standalone=False  # ADD THIS
                )
                return (mode_id, result, None)

            elif mode_id == "manipulation_detection":
                orchestrator = self._get_manipulation_orchestrator()

                result = await orchestrator.process_with_progress(
                    content=content,
                    job_id=job_id,
                    source_info=source_credibility.get("domain", "Unknown"),
                    source_credibility=source_credibility if source_credibility else None,
                    standalone=False  # ADD THIS
                )
                return (mode_id, result, None)

            elif mode_id == "lie_detection":
                orchestrator = self._get_lie_detection_orchestrator()

                result = await orchestrator.process_with_progress(
                    text=content,
                    job_id=job_id,
                    source_credibility=source_credibility if source_credibility else None,
                    standalone=False  # ADD THIS
                )

            elif mode_id == "llm_output_verification":
                from orchestrator.llm_output_orchestrator import LLMInterpretationOrchestrator
                orchestrator = LLMInterpretationOrchestrator(self.config)

                result = await orchestrator.process_with_progress(
                    html_content=content,
                    job_id=job_id
                )
                return (mode_id, result, None)

            else:
                return (mode_id, None, f"Unknown mode: {mode_id}")

        except CancelledException:
            raise
        except Exception as e:
            fact_logger.logger.error(f"❌ Mode {mode_id} failed: {e}")
            return (mode_id, None, str(e))

    @traceable(name="comprehensive_stage2_execution", run_type="chain", tags=["comprehensive", "stage2"])
    async def _run_stage2(
        self,
        content: str,
        job_id: str,
        stage1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Stage 2: Mode Execution (SEQUENTIAL)

        ⚠️ FIX: Run modes sequentially instead of in parallel to avoid
        LangChain asyncio task context conflicts.

        The error "Leaving task does not match current task" happens when
        multiple LangChain LLM calls run simultaneously via asyncio.gather().
        """
        self._send_stage_update(job_id, "mode_execution", "📊 Running selected analysis modes...")

        mode_routing = stage1_results.get("mode_routing") or {}
        selected_modes = mode_routing.get("selected_modes", ["key_claims_analysis"])

        job_manager.add_progress(
            job_id,
            f"🔄 Executing {len(selected_modes)} modes: {', '.join(selected_modes)}"
        )

        # Process results
        mode_reports: Dict[str, Any] = {}
        mode_errors: Dict[str, str] = {}

        start_time = time.time()

        # ✅ FIX: Run modes SEQUENTIALLY to avoid asyncio task conflicts
        for i, mode_id in enumerate(selected_modes, 1):
            try:
                self._check_cancellation(job_id)

                job_manager.add_progress(
                    job_id,
                    f"▶️ Running mode {i}/{len(selected_modes)}: {mode_id}..."
                )

                # Run single mode and await it directly (no gather)
                result = await self._run_single_mode(
                    mode_id, content, job_id, stage1_results
                )

                # Unpack the result tuple
                if isinstance(result, tuple) and len(result) == 3:
                    mode_id_returned, mode_result, error = result

                    if error:
                        mode_errors[mode_id] = error
                        job_manager.add_progress(job_id, f"⚠️ {mode_id} failed: {error}")
                    elif mode_result:
                        mode_reports[mode_id] = mode_result
                        job_manager.add_progress(job_id, f"✅ {mode_id} complete")

            except CancelledException:
                raise
            except Exception as e:
                fact_logger.logger.error(f"❌ Mode {mode_id} failed: {e}")
                import traceback
                fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")
                mode_errors[mode_id] = str(e)
                job_manager.add_progress(job_id, f"❌ {mode_id} error: {str(e)}")

        execution_time = time.time() - start_time

        fact_logger.logger.info(
            f"⚡ Stage 2 complete in {execution_time:.1f}s (sequential execution)",
            extra={
                "modes_run": len(selected_modes),
                "modes_succeeded": len(mode_reports),
                "modes_failed": len(mode_errors)
            }
        )

        return {
            "mode_reports": mode_reports,
            "mode_errors": mode_errors,
            "execution_time_seconds": round(execution_time, 2)
        }

    # =========================================================================
    # STAGE 3: AI-POWERED SYNTHESIS (NEW FULL IMPLEMENTATION)
    # =========================================================================

    @traceable(name="comprehensive_stage3_synthesis", run_type="chain", tags=["comprehensive", "stage3"])
    async def _run_stage3(
        self,
        job_id: str,
        stage1_results: Dict[str, Any],
        stage2_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Stage 3: AI-Powered Synthesis

        Uses the ReportSynthesizer agent to analyze all reports from Stage 1 and 
        Stage 2 together and produce a unified credibility assessment.

        Output includes:
        - Overall credibility score (0-100) and rating
        - Confidence in assessment
        - Categorized flags (credibility, bias, manipulation, factual accuracy)
        - Cross-mode contradiction detection
        - Key findings prioritized by importance
        - Actionable recommendations
        - Human-readable narrative summary

        Args:
            job_id: Job ID for progress tracking
            stage1_results: Results from Stage 1 (classification, verification, routing)
            stage2_results: Results from Stage 2 (mode_reports, mode_errors)

        Returns:
            Complete synthesis report as dictionary
        """
        start_time = time.time()

        self._send_stage_update(job_id, "synthesis", "🔬 Synthesizing final report...")
        job_manager.add_progress(job_id, "🤖 Running AI-powered report synthesis...")

        try:
            # Get the synthesizer
            synthesizer = self._get_report_synthesizer()

            # Run AI synthesis
            synthesis_report = await synthesizer.synthesize(
                stage1_results=stage1_results,
                stage2_results=stage2_results
            )

            # Convert Pydantic model to dict for JSON serialization
            synthesis_dict = synthesis_report.model_dump()

            # Add processing metadata
            synthesis_dict["synthesis_time_seconds"] = round(time.time() - start_time, 2)

            # Count total concerns for progress message (using new simplified model)
            total_concerns = len(synthesis_report.key_concerns)

            job_manager.add_progress(
                job_id, 
                f"✅ Synthesis complete: Score {synthesis_report.overall_score}/100 "
                f"({synthesis_report.overall_rating}), "
                f"{total_concerns} concerns identified"
            )

            fact_logger.logger.info(
                "✅ Stage 3 synthesis complete",
                extra={
                    "overall_score": synthesis_report.overall_score,
                    "rating": synthesis_report.overall_rating,
                    "confidence": synthesis_report.confidence,
                    "concerns_count": total_concerns,
                    "positives_count": len(synthesis_report.positive_indicators),
                    "modes_analyzed": len(synthesis_report.modes_analyzed),
                    "synthesis_time": synthesis_dict["synthesis_time_seconds"]
                }
            )

            return synthesis_dict

        except Exception as e:
            fact_logger.logger.error(f"❌ Stage 3 synthesis failed: {e}")
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")

            # Fallback to basic synthesis on error
            job_manager.add_progress(job_id, f"⚠️ AI synthesis failed, using basic synthesis: {str(e)[:100]}")

            return await self._run_stage3_fallback(job_id, stage1_results, stage2_results)

    async def _run_stage3_fallback(
        self,
        job_id: str,
        stage1_results: Dict[str, Any],
        stage2_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fallback Stage 3: Basic synthesis when AI synthesis fails

        Extracts key metrics from available reports and creates a basic
        synthesis without AI processing.
        """
        self._send_stage_update(job_id, "synthesis", "🔬 Running basic synthesis (fallback)...")

        mode_reports = stage2_results.get("mode_reports", {})
        mode_errors = stage2_results.get("mode_errors", {})

        # Initialize synthesis structure matching the new schema
        synthesis: Dict[str, Any] = {
            "overall_credibility_score": 50.0,
            "overall_credibility_rating": "Mixed",
            "confidence_in_assessment": 40.0,
            "score_breakdown": {"method": "fallback_calculation"},
            "credibility_flags": [],
            "bias_flags": [],
            "manipulation_flags": [],
            "factual_accuracy_flags": [],
            "contradictions": [],
            "key_findings": [],
            "recommendations": [
                "Review individual mode reports for detailed findings",
                "Consider re-running analysis for full AI synthesis"
            ],
            "narrative_summary": "",
            "modes_analyzed": list(mode_reports.keys()),
            "modes_failed": list(mode_errors.keys()),
            "limitations": ["AI synthesis unavailable - using basic metric extraction"]
        }

        score = 50.0

        # Process key claims results
        if "key_claims_analysis" in mode_reports:
            kc = mode_reports["key_claims_analysis"]
            summary = kc.get("summary", {})
            avg_conf = summary.get("average_confidence", 0.5)

            synthesis["score_breakdown"]["key_claims_confidence"] = avg_conf

            if avg_conf >= 0.7:
                score += 15
            elif avg_conf < 0.4:
                score -= 20
                synthesis["factual_accuracy_flags"].append({
                    "severity": "high",
                    "description": f"Low fact verification confidence ({avg_conf:.0%})",
                    "source_mode": "key_claims_analysis"
                })

        # Process bias results
        if "bias_analysis" in mode_reports:
            bias = mode_reports["bias_analysis"]
            analysis = bias.get("analysis", {})
            bias_score = abs(analysis.get("consensus_bias_score", 0))
            direction = analysis.get("consensus_direction", "Unknown")

            synthesis["score_breakdown"]["bias_score"] = bias_score

            if bias_score > 6:
                score -= 15
                synthesis["bias_flags"].append({
                    "severity": "medium" if bias_score <= 7 else "high",
                    "description": f"Significant {direction} bias detected (score: {bias_score:.1f}/10)",
                    "source_mode": "bias_analysis"
                })
            elif bias_score <= 3:
                score += 10

        # Process manipulation results
        if "manipulation_detection" in mode_reports:
            manip = mode_reports["manipulation_detection"]
            manip_score = manip.get("manipulation_score", 0)

            synthesis["score_breakdown"]["manipulation_score"] = manip_score

            if manip_score > 6:
                score -= 20
                synthesis["manipulation_flags"].append({
                    "severity": "high",
                    "description": f"High manipulation score ({manip_score:.1f}/10)",
                    "source_mode": "manipulation_detection"
                })

        # Process lie detection results
        if "lie_detection" in mode_reports:
            lie = mode_reports["lie_detection"]
            deception_score = lie.get("deception_likelihood_score", lie.get("overall_score", 0))

            synthesis["score_breakdown"]["deception_score"] = deception_score

            if deception_score > 6:
                score -= 10
                synthesis["manipulation_flags"].append({
                    "severity": "medium",
                    "description": f"Elevated deception indicators ({deception_score}/10)",
                    "source_mode": "lie_detection"
                })

        # Check source verification
        source_verification = stage1_results.get("source_verification", {})
        if source_verification and not source_verification.get("error"):
            tier = source_verification.get("credibility_tier", 3)
            if tier == 1:
                score += 15
            elif tier >= 4:
                score -= 15
                synthesis["credibility_flags"].append({
                    "severity": "high",
                    "description": f"Source has low credibility tier ({tier})",
                    "source_mode": "source_verification"
                })

        # Clamp and determine rating
        score = max(0, min(100, score))
        synthesis["overall_credibility_score"] = score

        if score >= 80:
            synthesis["overall_credibility_rating"] = "Highly Credible"
        elif score >= 65:
            synthesis["overall_credibility_rating"] = "Credible"
        elif score >= 45:
            synthesis["overall_credibility_rating"] = "Mixed"
        elif score >= 25:
            synthesis["overall_credibility_rating"] = "Low Credibility"
        else:
            synthesis["overall_credibility_rating"] = "Unreliable"

        # Generate basic narrative
        total_flags = (
            len(synthesis["credibility_flags"]) +
            len(synthesis["bias_flags"]) +
            len(synthesis["manipulation_flags"]) +
            len(synthesis["factual_accuracy_flags"])
        )

        if total_flags == 0:
            synthesis["narrative_summary"] = (
                f"Based on automated analysis, this content appears to have {synthesis['overall_credibility_rating'].lower()} "
                f"credibility. No major concerns were flagged, though detailed AI synthesis was unavailable."
            )
        else:
            synthesis["narrative_summary"] = (
                f"Our analysis raised {total_flags} concern(s) about this content, resulting in a "
                f"{synthesis['overall_credibility_rating'].lower()} credibility rating. "
                f"Please review the individual findings below for details."
            )

        # Add a key finding summarizing the analysis
        synthesis["key_findings"].append({
            "finding": f"Content analyzed with {len(mode_reports)} modes completed and {len(mode_errors)} failed",
            "importance": "medium",
            "source_modes": list(mode_reports.keys())
        })

        job_manager.add_progress(
            job_id, 
            f"✅ Basic synthesis complete: {synthesis['overall_credibility_score']:.0f}/100 "
            f"({synthesis['overall_credibility_rating']}), {total_flags} flags"
        )

        return synthesis

    # =========================================================================
    # MAIN PIPELINE
    # =========================================================================

    @traceable(
        name="comprehensive_analysis_pipeline",
        run_type="chain",
        tags=["comprehensive", "full-pipeline"]
    )
    async def process_with_progress(
        self,
        content: str,
        job_id: str,
        source_url: Optional[str] = None,
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run the complete comprehensive analysis pipeline

        Args:
            content: Text content to analyze
            job_id: Job ID for progress tracking
            source_url: Optional URL of the content source
            user_preferences: Optional user mode preferences

        Returns:
            Complete comprehensive analysis result
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            "🔬 Starting comprehensive analysis pipeline",
            extra={
                "session_id": session_id,
                "job_id": job_id,
                "content_length": len(content),
                "has_source_url": source_url is not None
            }
        )

        try:
            # ================================================================
            # STAGE 1: Pre-Analysis
            # ================================================================
            job_manager.add_progress(job_id, "📋 Stage 1: Pre-analysis starting...")
            stage1_results = await self._run_stage1(content, job_id, source_url)

            self._check_cancellation(job_id)
            job_manager.add_progress(job_id, "✅ Stage 1 complete")

            # ================================================================
            # STAGE 2: Parallel Mode Execution
            # ================================================================
            job_manager.add_progress(job_id, "📊 Stage 2: Mode execution starting...")
            stage2_results = await self._run_stage2(content, job_id, stage1_results)

            self._check_cancellation(job_id)
            job_manager.add_progress(job_id, "✅ Stage 2 complete")

            # ================================================================
            # STAGE 3: AI-Powered Synthesis (NEW)
            # ================================================================
            job_manager.add_progress(job_id, "🔬 Stage 3: Synthesizing results...")
            stage3_results = await self._run_stage3(job_id, stage1_results, stage2_results)

            job_manager.add_progress(job_id, "✅ Stage 3 complete")

            # ================================================================
            # COMPILE FINAL RESULT
            # ================================================================
            processing_time = time.time() - start_time

            final_result: Dict[str, Any] = {
                "success": True,
                "session_id": session_id,
                "processing_time": round(processing_time, 2),

                # Stage 1 results
                "content_classification": stage1_results.get("content_classification"),
                "source_verification": stage1_results.get("source_verification"),
                "author_info": stage1_results.get("author_info"),
                "mode_routing": stage1_results.get("mode_routing"),

                # Stage 2 results
                "mode_reports": stage2_results.get("mode_reports", {}),
                "mode_errors": stage2_results.get("mode_errors", {}),
                "mode_execution_time": stage2_results.get("execution_time_seconds"),

                # Stage 3 results (NEW - Full synthesis)
                "synthesis_report": stage3_results,

                # Metadata
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "2.0.0"  # Updated version for Stage 3
            }

            # Complete the job
            job_manager.complete_job(job_id, final_result)

            fact_logger.logger.info(
                "✅ Comprehensive analysis complete",
                extra={
                    "session_id": session_id,
                    "processing_time": processing_time,
                    "modes_run": len(stage2_results.get("mode_reports", {})),
                    "overall_score": stage3_results.get("overall_credibility_score"),
                    "overall_rating": stage3_results.get("overall_credibility_rating"),
                    "flags_raised": (
                        len(stage3_results.get("credibility_flags", [])) +
                        len(stage3_results.get("bias_flags", [])) +
                        len(stage3_results.get("manipulation_flags", [])) +
                        len(stage3_results.get("factual_accuracy_flags", []))
                    )
                }
            )

            return final_result

        except CancelledException:
            job_manager.add_progress(job_id, "🛑 Analysis cancelled by user")
            raise

        except Exception as e:
            fact_logger.logger.error(f"❌ Comprehensive analysis failed: {e}")
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")

            job_manager.fail_job(job_id, str(e))
            raise


# ============================================================================
# STANDALONE TESTING
# ============================================================================

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    async def test():
        config = type('Config', (), {
            'openai_api_key': os.getenv("OPENAI_API_KEY"),
            'brave_api_key': os.getenv("BRAVE_API_KEY"),
            'browserless_endpoint': os.getenv("BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE")
        })()

        orchestrator = ComprehensiveOrchestrator(config)

        test_content = """
        According to recent reports, global temperatures have risen by 1.2°C since 
        pre-industrial times. Scientists warn that without immediate action, we could 
        see a 3°C increase by 2100, leading to catastrophic consequences including 
        more frequent extreme weather events, rising sea levels, and mass extinction 
        of species.

        The IPCC's latest assessment suggests that current policies put us on track 
        for 2.7°C of warming, well above the Paris Agreement target of 1.5°C.
        """

        # Create a test job
        test_job_id = "test_comprehensive_stage3"
        job_manager.create_job(test_job_id)

        try:
            result = await orchestrator.process_with_progress(
                content=test_content,
                job_id=test_job_id,
                source_url=None
            )

            print("\n" + "="*70)
            print("COMPREHENSIVE ANALYSIS RESULT")
            print("="*70)
            print(f"Success: {result.get('success')}")
            print(f"Processing Time: {result.get('processing_time')}s")

            # Stage 3 Synthesis Results
            synthesis = result.get("synthesis_report", {})
            print("\n--- STAGE 3: SYNTHESIS ---")
            print(f"Overall Score: {synthesis.get('overall_credibility_score')}/100")
            print(f"Rating: {synthesis.get('overall_credibility_rating')}")
            print(f"Confidence: {synthesis.get('confidence_in_assessment')}%")
            print(f"\nNarrative Summary:\n{synthesis.get('narrative_summary')}")

            print(f"\nKey Findings ({len(synthesis.get('key_findings', []))}):")
            for finding in synthesis.get('key_findings', []):
                print(f"  [{finding.get('importance')}] {finding.get('finding')}")

            print(f"\nRecommendations ({len(synthesis.get('recommendations', []))}):")
            for rec in synthesis.get('recommendations', []):
                print(f"  - {rec}")

            total_flags = (
                len(synthesis.get('credibility_flags', [])) +
                len(synthesis.get('bias_flags', [])) +
                len(synthesis.get('manipulation_flags', [])) +
                len(synthesis.get('factual_accuracy_flags', []))
            )
            print(f"\nFlags: {total_flags} total")
            print(f"  Credibility: {len(synthesis.get('credibility_flags', []))}")
            print(f"  Bias: {len(synthesis.get('bias_flags', []))}")
            print(f"  Manipulation: {len(synthesis.get('manipulation_flags', []))}")
            print(f"  Factual Accuracy: {len(synthesis.get('factual_accuracy_flags', []))}")

            print(f"\nContradictions: {len(synthesis.get('contradictions', []))}")

        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(test())