# orchestrator/bias_check_orchestrator.py
"""
Bias Check Orchestrator - UPDATED FOR CLOUDFLARE R2
Coordinates the complete bias checking workflow with R2 uploads
"""

from langsmith import traceable
import time
import json
from typing import Optional, Dict

from agents.bias_checker import BiasChecker
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
# ✅ CHANGED: Import R2 uploader instead of Google Drive
from utils.r2_uploader import R2Uploader


class BiasCheckOrchestrator:
    """
    Orchestrates bias checking workflow with R2 storage
    
    Pipeline:
    1. Receive text + optional publication metadata
    2. Run multi-model bias analysis (GPT-4o + Claude)
    3. Combine analyses into comprehensive report
    4. Save reports locally
    5. Upload to Cloudflare R2
    6. Return combined assessment
    """
    
    def __init__(self, config):
        self.config = config
        self.bias_checker = BiasChecker(config)
        self.file_manager = FileManager()
        
        # ✅ CHANGED: Initialize R2 uploader instead of Google Drive
        try:
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
            fact_logger.logger.info("✅ Cloudflare R2 integration enabled")
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Cloudflare R2 not configured: {e}")
            self.r2_enabled = False
        
        fact_logger.log_component_start("BiasCheckOrchestrator")
    
    @traceable(
        name="bias_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "bias-checking", "multi-model", "r2-storage"]
    )
    async def process(
        self, 
        text: str, 
        publication_name: Optional[str] = None,
        save_to_r2: bool = True  # ✅ CHANGED: save_to_gdrive → save_to_r2
    ) -> dict:
        """
        Complete bias checking pipeline with R2 storage
        
        Args:
            text: Text to analyze for bias
            publication_name: Optional publication name for metadata
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
                "publication": publication_name,
                "r2_enabled": self.r2_enabled and save_to_r2
            }
        )
        
        try:
            # Step 1: Run bias analysis
            fact_logger.logger.info("📊 Step 1: Multi-model bias analysis")
            
            bias_results = await self.bias_checker.check_bias(
                text=text,
                publication_name=publication_name
            )
            
            # Step 2: Prepare report data
            fact_logger.logger.info("📝 Step 2: Preparing reports")
            
            report_data = {
                "session_id": session_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "publication": publication_name,
                "text_analyzed": text[:500] + "..." if len(text) > 500 else text,
                "gpt_analysis": bias_results["gpt_analysis"],
                "claude_analysis": bias_results["claude_analysis"],
                "combined_report": bias_results["combined_report"],
                "publication_profile": bias_results.get("publication_profile"),
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
            
            # ✅ CHANGED: Step 4: Upload to Cloudflare R2 instead of Google Drive
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
                            'publication': publication_name or 'unknown',
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
            
            output = {
                "session_id": session_id,
                "status": "completed",
                "processing_time": duration,
                
                # Main results
                "combined_report": bias_results["combined_report"],
                
                # Raw analyses (for reference)
                "raw_analyses": {
                    "gpt": bias_results["gpt_analysis"],
                    "claude": bias_results["claude_analysis"]
                },
                
                # Publication context
                "publication_profile": bias_results.get("publication_profile"),
                
                # File locations
                "local_files": {
                    "combined_report": combined_report_path,
                    "gpt_report": gpt_report_path,
                    "claude_report": claude_report_path
                },
                
                # ✅ NEW: R2 upload status (replaces gdrive_links)
                "r2_upload": r2_upload_status
            }
            
            fact_logger.log_component_complete(
                "BiasCheckOrchestrator",
                duration,
                session_id=session_id,
                consensus_score=bias_results["combined_report"]["consensus_bias_score"],
                r2_uploads=len(r2_links) if r2_links else 0
            )
            
            return output
            
        except Exception as e:
            fact_logger.log_component_error("BiasCheckOrchestrator", e)
            raise
    
    async def process_with_progress(
        self,
        text: str,
        publication_name: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> dict:
        """
        Process with real-time progress updates (for web interface)
        
        Args:
            text: Text to analyze
            publication_name: Optional publication name
            job_id: Optional job ID for progress tracking
            
        Returns:
            Complete bias analysis results with R2 upload status
        """
        if job_id:
            from utils.job_manager import job_manager
            
            job_manager.add_progress(job_id, "📊 Starting bias analysis...")
            job_manager.add_progress(job_id, "🤖 Analyzing with GPT-4o...")
            job_manager.add_progress(job_id, "🤖 Analyzing with Claude Sonnet...")
        
        result = await self.process(
            text=text,
            publication_name=publication_name,
            save_to_r2=True  # ✅ CHANGED: save_to_gdrive → save_to_r2
        )
        
        if job_id:
            from utils.job_manager import job_manager
            
            # ✅ NEW: Add progress message about R2 upload status
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
