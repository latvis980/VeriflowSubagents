# orchestrator/lie_detector_orchestrator.py
"""
Lie Detector Orchestrator
Manages the lie detection workflow with file management and R2 storage

Workflow:
1. Receive text + optional URL + optional publication date
2. Run linguistic deception marker analysis with Claude
3. Save reports locally
4. Upload to Cloudflare R2
5. Return analysis results
"""

from langsmith import traceable
from typing import Optional
import time
import json

from agents.lie_detector import LieDetector
from utils.file_manager import FileManager
from utils.r2_uploader import R2Uploader
from utils.logger import fact_logger


class LieDetectorOrchestrator:
    """
    Orchestrates lie detection analysis with storage
    
    Similar to BiasCheckOrchestrator but for linguistic deception analysis
    """
    
    def __init__(self, config):
        self.config = config
        self.lie_detector = LieDetector(config)
        self.file_manager = FileManager()
        
        # Initialize R2 uploader
        try:
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
            fact_logger.logger.info("✅ Cloudflare R2 integration enabled")
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Cloudflare R2 not configured: {e}")
            self.r2_enabled = False
        
        fact_logger.log_component_start("LieDetectorOrchestrator")
    
    @traceable(
        name="lie_detection_pipeline",
        run_type="chain",
        tags=["orchestrator", "lie-detection", "deception-analysis", "r2-storage"]
    )
    async def process(
        self, 
        text: str,
        url: Optional[str] = None,
        publication_date: Optional[str] = None,
        save_to_r2: bool = True
    ) -> dict:
        """
        Complete lie detection pipeline with R2 storage
        
        Args:
            text: Text to analyze for deception markers
            url: Optional URL of the article
            publication_date: Optional publication date
            save_to_r2: Whether to save reports to Cloudflare R2
            
        Returns:
            Dictionary with complete lie detection analysis results
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()
        
        fact_logger.logger.info(
            f"🚀 STARTING LIE DETECTION SESSION: {session_id}",
            extra={
                "session_id": session_id,
                "text_length": len(text),
                "has_url": bool(url),
                "has_publication_date": bool(publication_date),
                "r2_enabled": self.r2_enabled and save_to_r2
            }
        )
        
        try:
            # Step 1: Run lie detection analysis
            fact_logger.logger.info("🔍 Step 1: Analyzing deception markers with Claude")
            
            analysis_result = await self.lie_detector.analyze(
                text=text,
                url=url,
                publication_date=publication_date
            )
            
            # Step 2: Prepare report data
            fact_logger.logger.info("📝 Step 2: Preparing analysis report")
            
            report_data = {
                "session_id": session_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "text_length": len(text),
                    "url": url,
                    "publication_date": publication_date
                },
                "analysis": analysis_result.dict(),
                "metadata": {
                    "model": "claude-sonnet-4-20250514",
                    "processing_time_seconds": time.time() - start_time
                }
            }
            
            # Step 3: Save reports locally
            fact_logger.logger.info("💾 Step 3: Saving reports locally")
            
            # Save full analysis report
            analysis_report_path = self.file_manager.save_session_file(
                data=report_data,
                filename=f"lie_detection_{session_id}.json"
            )
            fact_logger.logger.info(f"✅ Saved analysis report: {analysis_report_path}")
            
            # Step 4: Upload to R2 if enabled
            r2_upload_status = {"success": False, "error": "R2 disabled"}
            r2_link = None
            
            if self.r2_enabled and save_to_r2:
                fact_logger.logger.info("☁️ Step 4: Uploading to Cloudflare R2")
                
                try:
                    r2_link = self.r2_uploader.upload_file(
                        file_path=analysis_report_path,
                        r2_filename=f"lie-detection-reports/{session_id}/analysis.json",
                        metadata={
                            'session-id': session_id,
                            'report-type': 'lie-detection',
                            'model': 'claude-sonnet-4',
                            'risk-level': analysis_result.risk_level.lower(),
                            'credibility-score': str(analysis_result.credibility_score),
                            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                    )
                    
                    if r2_link:
                        r2_upload_status = {
                            "success": True,
                            "url": r2_link
                        }
                        fact_logger.logger.info(
                            "✅ Analysis report uploaded to R2",
                            extra={"session_id": session_id}
                        )
                    else:
                        r2_upload_status = {
                            "success": False,
                            "error": "Upload returned no URL"
                        }
                        
                except Exception as e:
                    fact_logger.logger.error(f"❌ R2 upload failed: {e}")
                    r2_upload_status = {
                        "success": False,
                        "error": str(e)
                    }
            else:
                fact_logger.logger.info("⏭️ Step 4: Skipping R2 upload (disabled or not requested)")
            
            # Step 5: Calculate processing time
            processing_time = time.time() - start_time
            
            fact_logger.log_component_complete(
                "LieDetectorOrchestrator",
                duration=processing_time,
                extra={
                    "session_id": session_id,
                    "risk_level": analysis_result.risk_level,
                    "credibility_score": analysis_result.credibility_score,
                    "r2_upload": r2_upload_status["success"]
                }
            )
            
            # Return comprehensive results
            return {
                "session_id": session_id,
                "success": True,
                "analysis": analysis_result.dict(),
                "processing_time": processing_time,
                "local_report_path": analysis_report_path,
                "r2_upload": r2_upload_status,
                "r2_url": r2_link
            }
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Lie detection pipeline failed: {e}", exc_info=True)
            
            return {
                "session_id": session_id,
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time
            }
