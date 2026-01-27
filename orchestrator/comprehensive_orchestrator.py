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

STAGE 3: Synthesis
- Analyze all reports together
- Generate unified credibility assessment
- Flag contradictions and concerns
- Create final comprehensive report

✅ OPTIMIZED: All modes run in parallel for maximum speed
"""

from langsmith import traceable
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

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
from orchestrator.lie_detection_orchestrator import LieDetectionOrchestrator


class CancelledException(Exception):
    """Raised when job is cancelled"""
    pass


class ComprehensiveOrchestrator:
    """
    Master orchestrator for comprehensive analysis mode

    Coordinates:
    - Stage 1: Content classification, source verification, mode routing
    - Stage 2: Parallel execution of selected analysis modes
    - Stage 3: Synthesis of all findings (future)
    """

    def __init__(self, config):
        self.config = config
        self.file_manager = FileManager()

        # Stage 1 components
        self.content_classifier = ContentClassifier()
        self.source_verifier = SourceVerifier()
        self.mode_router = ModeRouter()

        # Stage 2 orchestrators (initialized on demand)
        self._key_claims_orchestrator = None
        self._bias_orchestrator = None
        self._manipulation_orchestrator = None
        self._lie_detection_orchestrator = None

        # R2 uploader for audit storage
        try:
            from utils.r2_uploader import R2Uploader
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
        except Exception as e:
            self.r2_enabled = False
            self.r2_uploader = None
            fact_logger.logger.warning(f"⚠️ R2 not available: {e}")

        fact_logger.logger.info("✅ ComprehensiveOrchestrator initialized")

    # =========================================================================
    # LAZY INITIALIZATION OF MODE ORCHESTRATORS
    # =========================================================================

    def _get_key_claims_orchestrator(self):
        """Lazy init for key claims orchestrator"""
        if self._key_claims_orchestrator is None:
            self._key_claims_orchestrator = KeyClaimsOrchestrator(self.config)
        return self._key_claims_orchestrator

    def _get_bias_orchestrator(self):
        """Lazy init for bias orchestrator"""
        if self._bias_orchestrator is None:
            self._bias_orchestrator = BiasCheckOrchestrator(self.config)
        return self._bias_orchestrator

    def _get_manipulation_orchestrator(self):
        """Lazy init for manipulation orchestrator"""
        if self._manipulation_orchestrator is None:
            self._manipulation_orchestrator = ManipulationOrchestrator(self.config)
        return self._manipulation_orchestrator

    def _get_lie_detection_orchestrator(self):
        """Lazy init for lie detection orchestrator"""
        if self._lie_detection_orchestrator is None:
            self._lie_detection_orchestrator = LieDetectionOrchestrator(self.config)
        return self._lie_detection_orchestrator

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _check_cancellation(self, job_id: str):
        """Check if job has been cancelled"""
        if job_manager.is_cancelled(job_id):
            raise CancelledException("Job cancelled by user")

    def _send_stage_update(self, job_id: str, stage: str, message: str = None):
        """Send a stage-specific progress update"""
        job_manager.add_progress(job_id, message or f"Stage: {stage}", extra={"stage": stage})

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

        1. Classify content (type, realm, LLM detection)
        2. Verify source credibility
        3. Route to appropriate modes
        """
        stage1_results = {
            "content_classification": None,
            "source_verification": None,
            "author_info": None,  # Future enhancement
            "mode_routing": None
        }

        try:
            # Step 1a: Content Classification
            self._send_stage_update(job_id, "content_classification", "📝 Classifying content type...")
            self._check_cancellation(job_id)

            classification_result = await self.content_classifier.classify(content, source_url)

            if classification_result.success:
                stage1_results["content_classification"] = classification_result.classification.model_dump()
                job_manager.add_progress(
                    job_id,
                    f"✅ Content classified as {classification_result.classification.content_type} ({classification_result.classification.realm})"
                )
            else:
                # Use default classification on error
                stage1_results["content_classification"] = {
                    "content_type": "other",
                    "realm": "other",
                    "is_likely_llm_output": False,
                    "reference_count": 0
                }
                job_manager.add_progress(job_id, f"⚠️ Classification error, using defaults")

            # Send partial result for progressive UI
            job_manager.add_progress(job_id, "", extra={
                "partial_result": {"content_classification": stage1_results["content_classification"]}
            })

            # Step 1b: Source Verification
            self._send_stage_update(job_id, "source_verification", "📰 Verifying source credibility...")
            self._check_cancellation(job_id)

            # Determine URL for verification
            verify_url = source_url
            if not verify_url and classification_result.classification:
                ref_urls = classification_result.classification.reference_urls
                if ref_urls:
                    verify_url = ref_urls[0]

            if verify_url:
                verification_result = await self.source_verifier.verify_source(
                    content=content,
                    provided_url=verify_url,
                    run_mbfc_if_missing=True
                )

                if verification_result.success:
                    stage1_results["source_verification"] = {
                        "domain": verification_result.report.domain,
                        "credibility_tier": verification_result.report.credibility_tier,
                        "tier_label": verification_result.report.tier_label,
                        "verification_source": verification_result.report.verification_source,
                        "mbfc_data": verification_result.report.mbfc_data,
                        "verification_successful": verification_result.report.verification_successful
                    }
                    job_manager.add_progress(
                        job_id,
                        f"✅ Source verified: Tier {verification_result.report.credibility_tier} ({verification_result.report.domain})"
                    )
                else:
                    stage1_results["source_verification"] = {
                        "error": verification_result.report.error if verification_result.report else "Verification failed"
                    }
            else:
                stage1_results["source_verification"] = {"status": "no_url_to_verify"}
                job_manager.add_progress(job_id, "ℹ️ No source URL to verify")

            # Send partial result
            job_manager.add_progress(job_id, "", extra={
                "partial_result": {"source_verification": stage1_results["source_verification"]}
            })

            # Step 1c: Mode Routing
            self._send_stage_update(job_id, "mode_routing", "🎯 Selecting analysis modes...")
            self._check_cancellation(job_id)

            routing_result = await self.mode_router.route(
                content_classification=stage1_results["content_classification"],
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
            job_manager.add_progress(job_id, "", extra={
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
            source_context = stage1_results.get("content_classification", {})
            source_credibility = stage1_results.get("source_verification", {})

            if mode_id == "key_claims_analysis":
                orchestrator = self._get_key_claims_orchestrator()
                # Use main job_id - modes share progress through main job
                result = await orchestrator.process_with_progress(
                    text_content=content,
                    job_id=job_id,
                    source_context=source_context,
                    source_credibility=source_credibility
                )
                return (mode_id, result, None)

            elif mode_id == "bias_analysis":
                orchestrator = self._get_bias_orchestrator()
                # Extract publication info if available
                publication_name = source_credibility.get("domain", "")

                result = await orchestrator.process_with_progress(
                    text_content=content,
                    job_id=job_id,
                    publication_name=publication_name
                )
                return (mode_id, result, None)

            elif mode_id == "manipulation_detection":
                orchestrator = self._get_manipulation_orchestrator()

                result = await orchestrator.process_with_progress(
                    text_content=content,
                    job_id=job_id,
                    source_context=source_context,
                    source_credibility=source_credibility
                )
                return (mode_id, result, None)

            elif mode_id == "lie_detection":
                orchestrator = self._get_lie_detection_orchestrator()

                result = await orchestrator.process_with_progress(
                    text_content=content,
                    job_id=job_id
                )
                return (mode_id, result, None)

            elif mode_id == "llm_output_verification":
                # LLM output verification uses a different pipeline
                from orchestrator.fact_check_orchestrator import FactCheckOrchestrator
                orchestrator = FactCheckOrchestrator(self.config)

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

    @traceable(name="comprehensive_stage2_execution", run_type="chain", tags=["comprehensive", "stage2", "parallel"])
    async def _run_stage2(
        self,
        content: str,
        job_id: str,
        stage1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Stage 2: Parallel Mode Execution

        Run all selected modes in parallel and collect results
        """
        self._send_stage_update(job_id, "mode_execution", "📊 Running selected analysis modes...")

        selected_modes = stage1_results.get("mode_routing", {}).get("selected_modes", ["key_claims_analysis"])

        job_manager.add_progress(
            job_id,
            f"⚡ Executing {len(selected_modes)} modes in parallel: {', '.join(selected_modes)}"
        )

        # Create tasks for parallel execution
        tasks = [
            self._run_single_mode(mode_id, content, job_id, stage1_results)
            for mode_id in selected_modes
        ]

        # Execute all modes in parallel
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        execution_time = time.time() - start_time

        # Process results
        mode_reports = {}
        mode_errors = {}

        for result in results:
            if isinstance(result, CancelledException):
                raise result
            elif isinstance(result, Exception):
                fact_logger.logger.error(f"❌ Mode execution error: {result}")
                continue

            mode_id, mode_result, error = result

            if error:
                mode_errors[mode_id] = error
                job_manager.add_progress(job_id, f"⚠️ {mode_id} failed: {error}")
            elif mode_result:
                mode_reports[mode_id] = mode_result
                job_manager.add_progress(job_id, f"✅ {mode_id} complete")

        fact_logger.logger.info(
            f"⚡ Stage 2 complete in {execution_time:.1f}s",
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
    # STAGE 3: SYNTHESIS (Placeholder for future implementation)
    # =========================================================================

    @traceable(name="comprehensive_stage3_synthesis", run_type="chain", tags=["comprehensive", "stage3"])
    async def _run_stage3(
        self,
        job_id: str,
        stage1_results: Dict[str, Any],
        stage2_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Stage 3: Synthesis

        Analyze all reports together and generate unified assessment

        TODO: Implement full synthesis with:
        - Cross-mode consistency checking
        - Contradiction detection
        - Overall credibility score
        - Key findings summary
        - Recommendations
        """
        self._send_stage_update(job_id, "synthesis", "🔬 Synthesizing final report...")

        # For now, create a basic synthesis
        mode_reports = stage2_results.get("mode_reports", {})

        # Extract key metrics from each mode
        synthesis = {
            "overall_assessment": "pending_full_implementation",
            "credibility_indicators": [],
            "key_findings": [],
            "flags": [],
            "recommendations": [],
            "mode_summaries": {}
        }

        # Summarize key claims results
        if "key_claims_analysis" in mode_reports:
            kc = mode_reports["key_claims_analysis"]
            summary = kc.get("summary", {})
            synthesis["mode_summaries"]["key_claims"] = {
                "claims_verified": summary.get("claims_verified", 0),
                "average_confidence": summary.get("average_confidence", 0),
                "claims_with_concerns": summary.get("claims_with_concerns", 0)
            }

            # Add to credibility indicators
            avg_conf = summary.get("average_confidence", 0)
            if avg_conf < 0.4:
                synthesis["flags"].append({
                    "severity": "high",
                    "source": "key_claims_analysis",
                    "message": f"Low fact verification confidence ({avg_conf:.0%})"
                })

        # Summarize bias results
        if "bias_analysis" in mode_reports:
            bias = mode_reports["bias_analysis"]
            analysis = bias.get("analysis", {})
            synthesis["mode_summaries"]["bias_analysis"] = {
                "consensus_score": analysis.get("consensus_bias_score", 0),
                "direction": analysis.get("consensus_direction", "Unknown"),
                "confidence": analysis.get("confidence", 0)
            }

            # Flag significant bias
            score = analysis.get("consensus_bias_score", 0)
            if abs(score) > 0.6:
                direction = analysis.get("consensus_direction", "Unknown")
                synthesis["flags"].append({
                    "severity": "medium",
                    "source": "bias_analysis",
                    "message": f"Significant {direction} bias detected (score: {score:.2f})"
                })

        # Summarize manipulation results
        if "manipulation_detection" in mode_reports:
            manip = mode_reports["manipulation_detection"]
            score = manip.get("manipulation_score", 0)
            synthesis["mode_summaries"]["manipulation_detection"] = {
                "score": score,
                "techniques_used": manip.get("report", {}).get("techniques_used", [])[:3]
            }

            if score > 0.6:
                synthesis["flags"].append({
                    "severity": "high",
                    "source": "manipulation_detection",
                    "message": f"High manipulation score ({score:.0%})"
                })

        # Summarize lie detection results
        if "lie_detection" in mode_reports:
            lie = mode_reports["lie_detection"]
            synthesis["mode_summaries"]["lie_detection"] = {
                "deception_score": lie.get("deception_score", 0),
                "markers_found": lie.get("markers_found", 0)
            }

        # Generate overall assessment based on flags
        if not synthesis["flags"]:
            synthesis["overall_assessment"] = "No significant concerns detected"
        elif any(f["severity"] == "high" for f in synthesis["flags"]):
            synthesis["overall_assessment"] = "Multiple significant concerns require attention"
        else:
            synthesis["overall_assessment"] = "Minor concerns detected, exercise caution"

        job_manager.add_progress(job_id, f"✅ Synthesis complete: {len(synthesis['flags'])} flags raised")

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
            # STAGE 3: Synthesis
            # ================================================================
            job_manager.add_progress(job_id, "🔬 Stage 3: Synthesizing results...")
            stage3_results = await self._run_stage3(job_id, stage1_results, stage2_results)

            job_manager.add_progress(job_id, "✅ Stage 3 complete")

            # ================================================================
            # COMPILE FINAL RESULT
            # ================================================================
            processing_time = time.time() - start_time

            final_result = {
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

                # Stage 3 results
                "synthesis_report": stage3_results,

                # Metadata
                "timestamp": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }

            # Complete the job
            job_manager.complete_job(job_id, final_result)

            fact_logger.logger.info(
                "✅ Comprehensive analysis complete",
                extra={
                    "session_id": session_id,
                    "processing_time": processing_time,
                    "modes_run": len(stage2_results.get("mode_reports", {})),
                    "flags_raised": len(stage3_results.get("flags", []))
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
        config = {
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "brave_api_key": os.getenv("BRAVE_API_KEY")
        }

        orchestrator = ComprehensiveOrchestrator(config)

        test_content = """
        According to recent reports, global temperatures have risen by 1.2°C since 
        pre-industrial times. Scientists warn that without immediate action, we could 
        see a 3°C increase by 2100, leading to catastrophic consequences including 
        more frequent extreme weather events, rising sea levels, and mass extinction 
        of species.

        The IPCC's latest assessment suggests that current policies put us on track 
        for 2.7°C of warming, well above the Paris Agreement target of 1.5°C. 
        However, some skeptics argue that climate models have consistently 
        overestimated warming trends.
        """

        # Create test job
        from utils.job_manager import job_manager
        job_id = job_manager.create_job()

        print(f"Testing with job_id: {job_id}")

        result = await orchestrator.process_with_progress(
            content=test_content,
            job_id=job_id
        )

        print(f"\n✅ Result:")
        print(f"  Session: {result['session_id']}")
        print(f"  Processing Time: {result['processing_time']}s")
        print(f"  Content Type: {result['content_classification'].get('content_type')}")
        print(f"  Selected Modes: {result['mode_routing'].get('selected_modes')}")
        print(f"  Mode Reports: {list(result['mode_reports'].keys())}")
        print(f"  Flags: {len(result['synthesis_report'].get('flags', []))}")

    asyncio.run(test())