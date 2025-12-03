# orchestrator/bias_check_orchestrator.py
"""
Bias Check Orchestrator - WITH MBFC INTEGRATION
Coordinates the complete bias checking workflow with R2 uploads and MBFC lookup
"""

from langsmith import traceable
import time
import json
from typing import Optional, Dict

from agents.bias_checker import BiasChecker
from agents.publication_bias_detector import PublicationBiasDetector
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
from utils.r2_uploader import R2Uploader


class BiasCheckOrchestrator:
    """
    Orchestrates bias checking workflow with R2 storage and MBFC integration

    Pipeline:
    1. Receive text + optional publication URL
    2. If URL provided, look up publication on MBFC
    3. Run multi-model bias analysis (GPT-4o + Claude)
    4. Combine analyses into comprehensive report
    5. Save reports locally
    6. Upload to Cloudflare R2
    7. Return combined assessment
    """

    def __init__(self, config):
        self.config = config
        self.bias_checker = BiasChecker(config)
        self.file_manager = FileManager()

        # Initialize R2 uploader
        try:
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
            fact_logger.logger.info("✅ Cloudflare R2 integration enabled")
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Cloudflare R2 not configured: {e}")
            self.r2_enabled = False

        # Initialize MBFC lookup components
        self.mbfc_enabled = False
        self.brave_searcher = None
        self.scraper = None
        self.pub_detector = None

        try:
            # Check if Brave API is available
            if hasattr(config, 'brave_api_key') and config.brave_api_key:
                from utils.brave_searcher import BraveSearcher
                from utils.browserless_scraper import FactCheckScraper

                self.brave_searcher = BraveSearcher(config, max_results=5)
                self.scraper = FactCheckScraper(config)
                self.pub_detector = PublicationBiasDetector(
                    config=config,
                    brave_searcher=self.brave_searcher,
                    scraper=self.scraper
                )
                self.mbfc_enabled = True
                fact_logger.logger.info("✅ MBFC lookup integration enabled")
            else:
                # Fallback to local-only publication detector
                self.pub_detector = PublicationBiasDetector()
                fact_logger.logger.info("ℹ️ MBFC lookup disabled (no Brave API key) - using local database only")
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ MBFC integration failed: {e} - using local database only")
            self.pub_detector = PublicationBiasDetector()

        fact_logger.log_component_start(
            "BiasCheckOrchestrator",
            r2_enabled=self.r2_enabled,
            mbfc_enabled=self.mbfc_enabled
        )

    @traceable(
        name="bias_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "bias-checking", "multi-model", "r2-storage", "mbfc"]
    )
    async def process(
        self, 
        text: str, 
        publication_url: Optional[str] = None,
        publication_name: Optional[str] = None,  # Kept for backward compatibility
        save_to_r2: bool = True
    ) -> dict:
        """
        Complete bias checking pipeline with R2 storage and MBFC lookup

        Args:
            text: Text to analyze for bias
            publication_url: Optional publication URL for MBFC lookup (NEW - preferred)
            publication_name: Optional publication name for metadata (deprecated, backward compat)
            save_to_r2: Whether to save reports to Cloudflare R2

        Returns:
            Dictionary with complete bias analysis results
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        fact_logger.logger.info(
            f"🚀 STARTING BIAS CHECK SESSION: {session_id}",
            extra={
                "session_id": session_id,
                "text_length": len(text),
                "publication_url": publication_url,
                "publication_name": publication_name,
                "r2_enabled": self.r2_enabled and save_to_r2,
                "mbfc_enabled": self.mbfc_enabled
            }
        )

        try:
            # Step 0: MBFC Lookup (if URL provided)
            publication_profile = None
            mbfc_context = None
            resolved_publication_name = publication_name  # Use provided name as fallback

            if publication_url and self.mbfc_enabled and self.pub_detector:
                fact_logger.logger.info(f"📰 Step 0: Looking up publication on MBFC: {publication_url}")

                try:
                    publication_profile = await self.pub_detector.detect_publication_async(
                        publication_url=publication_url
                    )

                    if publication_profile:
                        resolved_publication_name = publication_profile.name
                        mbfc_context = self.pub_detector.get_publication_context(
                            profile=publication_profile
                        )
                        fact_logger.logger.info(
                            f"✅ MBFC data found: {publication_profile.name}",
                            extra={
                                "source": publication_profile.source,
                                "bias": publication_profile.political_leaning,
                                "factual_reporting": publication_profile.factual_reporting,
                                "credibility": publication_profile.credibility_rating
                            }
                        )
                    else:
                        fact_logger.logger.info(f"📭 No MBFC data found for: {publication_url}")

                except Exception as e:
                    fact_logger.logger.warning(f"⚠️ MBFC lookup failed: {e}")
                    # Continue without MBFC data

            # Fallback: Try local database lookup if no MBFC result
            elif publication_url and self.pub_detector:
                domain = self.pub_detector.clean_url_to_domain(publication_url)
                publication_profile = self.pub_detector.detect_publication(domain)
                if publication_profile:
                    resolved_publication_name = publication_profile.name
                    mbfc_context = self.pub_detector.get_publication_context(
                        publication_name=resolved_publication_name
                    )
                    fact_logger.logger.info(f"📰 Using local database for: {domain}")

            # Fallback: Name-based lookup (backward compatibility)
            elif publication_name and self.pub_detector:
                publication_profile = self.pub_detector.detect_publication(publication_name)
                if publication_profile:
                    mbfc_context = self.pub_detector.get_publication_context(
                        publication_name=publication_name
                    )

            # Step 1: Run bias analysis
            fact_logger.logger.info("📊 Step 1: Multi-model bias analysis")

            bias_results = await self.bias_checker.check_bias(
                text=text,
                publication_name=resolved_publication_name
            )

            # Step 2: Prepare report data
            fact_logger.logger.info("📝 Step 2: Preparing reports")

            # Serialize publication profile if available
            publication_profile_data = None
            if publication_profile:
                publication_profile_data = publication_profile.model_dump()

            report_data = {
                "session_id": session_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "publication_url": publication_url,
                "publication_name": resolved_publication_name,
                "text_analyzed": text[:500] + "..." if len(text) > 500 else text,
                "gpt_analysis": bias_results["gpt_analysis"],
                "claude_analysis": bias_results["claude_analysis"],
                "combined_report": bias_results["combined_report"],
                "publication_profile": publication_profile_data,
                "mbfc_context": mbfc_context,
                "processing_time": bias_results["processing_time"]
            }

            # Step 3: Save reports locally
            fact_logger.logger.info("💾 Step 3: Saving reports locally")

            # Save combined report
            combined_report_path = self.file_manager.save_session_file(
                session_id,
                "combined_bias_report.json",
                json.dumps(report_data, indent=2)
            )

            # Save individual model reports
            gpt_report_path = self.file_manager.save_session_file(
                session_id,
                "gpt_bias_analysis.json",
                json.dumps(bias_results["gpt_analysis"], indent=2)
            )

            claude_report_path = self.file_manager.save_session_file(
                session_id,
                "claude_bias_analysis.json",
                json.dumps(bias_results["claude_analysis"], indent=2)
            )

            # Step 4: Upload to Cloudflare R2
            r2_links = {}
            r2_upload_status = {"success": False, "error": None}

            if self.r2_enabled and save_to_r2:
                fact_logger.logger.info("☁️ Step 4: Uploading reports to Cloudflare R2")

                try:
                    # Upload combined report
                    combined_url = self.r2_uploader.upload_file(
                        file_path=combined_report_path,
                        r2_filename=f"bias-reports/{session_id}/combined_report.json",
                        metadata={
                            'session-id': session_id,
                            'report-type': 'combined',
                            'publication': resolved_publication_name or 'unknown',
                            'publication-url': publication_url or 'unknown',
                            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                    )
                    if combined_url:
                        r2_links["combined_report"] = combined_url

                    # Upload GPT report
                    gpt_url = self.r2_uploader.upload_file(
                        file_path=gpt_report_path,
                        r2_filename=f"bias-reports/{session_id}/gpt_analysis.json",
                        metadata={
                            'session-id': session_id,
                            'report-type': 'gpt-raw',
                            'model': 'gpt-4o'
                        }
                    )
                    if gpt_url:
                        r2_links["gpt_report"] = gpt_url

                    # Upload Claude report
                    claude_url = self.r2_uploader.upload_file(
                        file_path=claude_report_path,
                        r2_filename=f"bias-reports/{session_id}/claude_analysis.json",
                        metadata={
                            'session-id': session_id,
                            'report-type': 'claude-raw',
                            'model': 'claude-sonnet'
                        }
                    )
                    if claude_url:
                        r2_links["claude_report"] = claude_url

                    # Check if all uploads succeeded
                    if len(r2_links) == 3:
                        r2_upload_status = {
                            "success": True,
                            "files_uploaded": 3,
                            "urls": r2_links
                        }
                        fact_logger.logger.info(
                            "✅ All bias reports uploaded to R2",
                            extra={"num_uploads": len(r2_links), "session_id": session_id}
                        )
                    else:
                        r2_upload_status = {
                            "success": False,
                            "error": f"Only {len(r2_links)}/3 files uploaded successfully",
                            "urls": r2_links
                        }
                        fact_logger.logger.warning(
                            f"⚠️ Partial R2 upload: {len(r2_links)}/3 files",
                            extra={"session_id": session_id}
                        )

                except Exception as e:
                    error_msg = str(e)
                    fact_logger.logger.error(f"❌ R2 upload failed: {error_msg}")
                    r2_upload_status = {
                        "success": False,
                        "error": error_msg
                    }
                    r2_links["error"] = error_msg
            else:
                fact_logger.logger.info("⏭️ Step 4: Skipping R2 upload (disabled)")
                r2_upload_status = {
                    "success": False,
                    "error": "R2 upload disabled or not configured"
                }

            # Prepare final output
            duration = time.time() - start_time

            # ✅ CRITICAL FIX: Extract combined_report fields for easy frontend access
            combined = bias_results["combined_report"]

            # ✅ FIXED: Added success field and wrapped data in "analysis" object
            output = {
                "success": True,  # ← CRITICAL: Frontend checks this field!
                "session_id": session_id,
                "status": "completed",
                "processing_time": duration,

                # ✅ CRITICAL: Wrap everything in "analysis" object - frontend expects this!
                "analysis": {
                    # Raw model analyses
                    "gpt_analysis": bias_results["gpt_analysis"],
                    "claude_analysis": bias_results["claude_analysis"],

                    # Combined report (full object for reference)
                    "combined_report": combined,

                    # Publication context (enhanced with MBFC data)
                    "publication_profile": publication_profile_data,
                    "mbfc_context": mbfc_context,

                    # ✅ CRITICAL: Extract key fields to top level for easy access
                    # Frontend expects these directly under "analysis"
                    "consensus_bias_score": combined.get("consensus_bias_score", 0),
                    "consensus_direction": combined.get("consensus_direction", "Unknown"),
                    "confidence": combined.get("confidence", 0),
                    "areas_of_agreement": combined.get("areas_of_agreement", []),
                    "areas_of_disagreement": combined.get("areas_of_disagreement", []),
                    "gpt_unique_findings": combined.get("gpt_unique_findings", []),
                    "claude_unique_findings": combined.get("claude_unique_findings", []),
                    "publication_bias_context": combined.get("publication_bias_context") or mbfc_context,
                    "final_assessment": combined.get("final_assessment", ""),
                    "recommendations": combined.get("recommendations", [])
                },

                # File locations (kept for reference)
                "local_files": {
                    "combined_report": combined_report_path,
                    "gpt_report": gpt_report_path,
                    "claude_report": claude_report_path
                },

                # R2 upload status
                "r2_upload": r2_upload_status
            }

            fact_logger.log_component_complete(
                "BiasCheckOrchestrator",
                duration,
                session_id=session_id,
                consensus_score=combined.get("consensus_bias_score", 0),
                r2_uploads=len(r2_links) if r2_links else 0,
                mbfc_found=publication_profile is not None
            )

            return output

        except Exception as e:
            fact_logger.log_component_error("BiasCheckOrchestrator", e)
            raise

    def _check_cancellation(self, job_id: str):
        """Check if job has been cancelled and raise exception if so"""
        from utils.job_manager import job_manager
        if job_manager.is_cancelled(job_id):
            raise Exception("Job cancelled by user")

    async def process_with_progress(
        self,
        text: str,
        publication_url: Optional[str] = None,
        publication_name: Optional[str] = None,  # Kept for backward compatibility
        job_id: Optional[str] = None
    ) -> dict:
        """
        Process with real-time progress updates (for web interface)

        Args:
            text: Text to analyze
            publication_url: Optional publication URL for MBFC lookup (NEW - preferred)
            publication_name: Optional publication name (deprecated, backward compat)
            job_id: Optional job ID for progress tracking

        Returns:
            Complete bias analysis results with R2 upload status
        """
        if job_id:
            from utils.job_manager import job_manager

            job_manager.add_progress(job_id, "📊 Starting bias analysis...")
            self._check_cancellation(job_id)

            # MBFC lookup progress
            if publication_url and self.mbfc_enabled:
                job_manager.add_progress(job_id, f"📰 Looking up publication on MBFC: {publication_url}")
                self._check_cancellation(job_id)

            job_manager.add_progress(job_id, "🤖 Analyzing with GPT-4o...")
            self._check_cancellation(job_id)
            job_manager.add_progress(job_id, "🤖 Analyzing with Claude Sonnet...")
            self._check_cancellation(job_id)

        result = await self.process(
            text=text,
            publication_url=publication_url,
            publication_name=publication_name,
            save_to_r2=True  
        )

        if job_id:
            from utils.job_manager import job_manager

            # Add progress message about MBFC lookup result
            if result.get("analysis", {}).get("publication_profile"):
                profile = result["analysis"]["publication_profile"]
                source = profile.get("source", "local")
                name = profile.get("name", "Unknown")
                leaning = profile.get("political_leaning", "unknown")
                if source == "mbfc":
                    job_manager.add_progress(
                        job_id,
                        f"✅ MBFC data found: {name} ({leaning} bias)"
                    )
                else:
                    job_manager.add_progress(
                        job_id,
                        f"📚 Using local database: {name} ({leaning} bias)"
                    )
            elif publication_url:
                job_manager.add_progress(job_id, "📭 No publication bias data found")

            # Add progress message about R2 upload status
            if result.get("r2_upload", {}).get("success"):
                job_manager.add_progress(
                    job_id, 
                    "☁️ Bias reports uploaded to R2"
                )
            else:
                error_msg = result.get("r2_upload", {}).get("error", "Unknown error")
                job_manager.add_progress(
                    job_id, 
                    f"⚠️ R2 upload failed: {error_msg}"
                )

            job_manager.add_progress(job_id, "✅ Bias analysis complete!")
            job_manager.complete_job(job_id, result)

        return result

    async def close(self):
        """Clean up resources (scraper, searcher connections)"""
        if self.scraper:
            try:
                await self.scraper.close()
                fact_logger.logger.debug("✅ Scraper closed")
            except Exception as e:
                fact_logger.logger.debug(f"Scraper close error (non-critical): {e}")

        if self.brave_searcher:
            try:
                await self.brave_searcher.close()
                fact_logger.logger.debug("✅ Brave searcher closed")
            except Exception as e:
                fact_logger.logger.debug(f"Brave searcher close error (non-critical): {e}")