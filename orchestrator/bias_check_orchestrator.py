# orchestrator/bias_check_orchestrator.py
"""
Bias Check Orchestrator
Coordinates the complete bias checking workflow including Google Drive uploads
"""

from langsmith import traceable
import time
import json
from typing import Optional, Dict

from agents.bias_checker import BiasChecker
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
from utils.gdrive_uploader import GoogleDriveUploader


class BiasCheckOrchestrator:
    """
    Orchestrates bias checking workflow
    
    Pipeline:
    1. Receive text + optional publication metadata
    2. Run multi-model bias analysis (GPT-4o + Claude)
    3. Combine analyses into comprehensive report
    4. Save raw reports to Google Drive
    5. Return combined assessment
    """
    
    def __init__(self, config):
        self.config = config
        self.bias_checker = BiasChecker(config)
        self.file_manager = FileManager()
        
        # Initialize Google Drive uploader
        try:
            self.gdrive_uploader = GoogleDriveUploader()
            self.gdrive_enabled = True
            fact_logger.logger.info("✅ Google Drive integration enabled")
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Google Drive not configured: {e}")
            self.gdrive_enabled = False
        
        fact_logger.log_component_start("BiasCheckOrchestrator")
    
    @traceable(
        name="bias_check_pipeline",
        run_type="chain",
        tags=["orchestrator", "bias-checking", "multi-model"]
    )
    async def process(
        self, 
        text: str, 
        publication_name: Optional[str] = None,
        save_to_gdrive: bool = True
    ) -> dict:
        """
        Complete bias checking pipeline with Google Drive integration
        
        Args:
            text: Text to analyze for bias
            publication_name: Optional publication name for metadata
            save_to_gdrive: Whether to save raw reports to Google Drive
            
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
                "gdrive_enabled": self.gdrive_enabled and save_to_gdrive
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
                "text_analyzed": text[:500] + "..." if len(text) > 500 else text,  # First 500 chars
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
            
            # Step 4: Upload to Google Drive (if enabled)
            gdrive_links = {}
            
            if self.gdrive_enabled and save_to_gdrive:
                fact_logger.logger.info("☁️ Step 4: Uploading reports to Google Drive")
                
                try:
                    # Upload combined report
                    combined_link = await self.gdrive_uploader.upload_file(
                        file_path=combined_report_path,
                        file_name=f"bias_report_{session_id}_combined.json",
                        mime_type="application/json",
                        folder_name="Bias Analysis Reports"
                    )
                    gdrive_links["combined_report"] = combined_link
                    
                    # Upload GPT report
                    gpt_link = await self.gdrive_uploader.upload_file(
                        file_path=gpt_report_path,
                        file_name=f"bias_report_{session_id}_gpt.json",
                        mime_type="application/json",
                        folder_name="Bias Analysis Reports/Raw GPT Reports"
                    )
                    gdrive_links["gpt_report"] = gpt_link
                    
                    # Upload Claude report
                    claude_link = await self.gdrive_uploader.upload_file(
                        file_path=claude_report_path,
                        file_name=f"bias_report_{session_id}_claude.json",
                        mime_type="application/json",
                        folder_name="Bias Analysis Reports/Raw Claude Reports"
                    )
                    gdrive_links["claude_report"] = claude_link
                    
                    fact_logger.logger.info(
                        "✅ Reports uploaded to Google Drive",
                        extra={"num_uploads": len(gdrive_links)}
                    )
                    
                except Exception as e:
                    fact_logger.logger.error(f"❌ Google Drive upload failed: {e}")
                    gdrive_links["error"] = str(e)
            else:
                fact_logger.logger.info("⏭️ Step 4: Skipping Google Drive upload (disabled)")
            
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
                
                # Google Drive links (if available)
                "gdrive_links": gdrive_links if gdrive_links else None
            }
            
            fact_logger.log_component_complete(
                "BiasCheckOrchestrator",
                duration,
                session_id=session_id,
                consensus_score=bias_results["combined_report"]["consensus_bias_score"],
                gdrive_uploads=len(gdrive_links)
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
            Complete bias analysis results
        """
        if job_id:
            from utils.job_manager import job_manager
            
            job_manager.add_progress(job_id, "📊 Starting bias analysis...")
            
            job_manager.add_progress(job_id, "🤖 Analyzing with GPT-4o...")
            job_manager.add_progress(job_id, "🤖 Analyzing with Claude Sonnet...")
            
        result = await self.process(
            text=text,
            publication_name=publication_name,
            save_to_gdrive=True
        )
        
        if job_id:
            job_manager.add_progress(job_id, "✅ Bias analysis complete!")
            job_manager.complete_job(job_id, result)
        
        return result
