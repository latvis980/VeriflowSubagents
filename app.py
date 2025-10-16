# app.py
from flask import Flask, render_template, request, jsonify, Response
import os
import re
import threading
from typing import Optional
from dotenv import load_dotenv

# Import your components
from orchestrator.llm_output_orchestrator import FactCheckOrchestrator
from orchestrator.web_search_orchestrator import WebSearchOrchestrator
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.job_manager import job_manager
from utils.async_utils import run_async_in_thread, cleanup_thread_loop  # ✅ NEW

import nest_asyncio
nest_asyncio.apply()

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Load configuration
class Config:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.browserless_endpoint = os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE')
        self.tavily_api_key = os.getenv('TAVILY_API_KEY')
        self.langchain_project = os.getenv('LANGCHAIN_PROJECT', 'fact-checker')

        # Validate required env vars
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        if not self.tavily_api_key:
            fact_logger.logger.warning("⚠️ TAVILY_API_KEY not set - web search pipeline will not work")

        fact_logger.logger.info("✅ Configuration loaded successfully")

config = Config()

# Initialize orchestrators (singleton)
llm_orchestrator = FactCheckOrchestrator(config)

# Better error handling for web search orchestrator
web_search_orchestrator: Optional[WebSearchOrchestrator] = None
if config.tavily_api_key:
    try:
        web_search_orchestrator = WebSearchOrchestrator(config)
        fact_logger.logger.info("✅ Web Search Orchestrator initialized successfully")
    except Exception as e:
        fact_logger.logger.error(f"❌ Failed to initialize Web Search Orchestrator: {e}")
        fact_logger.logger.warning("⚠️ Web search pipeline will not be available")
        web_search_orchestrator = None

# Helper function for input detection
def detect_input_format(content: str) -> str:
    """
    Detect if input is HTML (LLM output with links) or plain text
    """
    # Check for HTML tags
    html_pattern = r'<\s*[a-z][^>]*>'
    has_html_tags = bool(re.search(html_pattern, content, re.IGNORECASE))
    has_links = bool(re.search(r'<\s*a\s+[^>]*href\s*=', content, re.IGNORECASE))

    if has_html_tags or has_links:
        fact_logger.logger.info("📋 Detected HTML input format (LLM output with links)")
        return 'html'
    else:
        fact_logger.logger.info("📄 Detected plain text input format (no links)")
        return 'text'

@app.route('/')
def index():
    """Serve the main HTML interface"""
    return render_template('index.html')

@app.route('/api/check', methods=['POST'])
def check_facts():
    """Start async job and return job_id immediately"""
    try:
        # Get content from request
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        content = request_json.get('html_content') or request_json.get('content')
        if not content:
            return jsonify({"error": "No content provided"}), 400

        fact_logger.logger.info(
            "📥 Received fact-check request",
            extra={"content_length": len(content)}
        )

        # Detect input format
        input_format = detect_input_format(content)

        # Type-safe check for web search orchestrator
        if input_format == 'text' and web_search_orchestrator is None:
            return jsonify({
                "error": "Web search pipeline not available",
                "message": "TAVILY_API_KEY not configured or initialization failed."
            }), 503

        # Create job
        job_id = job_manager.create_job(content)
        fact_logger.logger.info(f"✅ Created job: {job_id}")

        # ✅ Start background processing
        threading.Thread(
            target=run_async_task,
            args=(job_id, content, input_format),
            daemon=True
        ).start()

        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": "Fact-checking started"
        })

    except Exception as e:
        fact_logger.log_component_error("Flask API", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred during fact checking"
        }), 500

def run_async_task(job_id: str, content: str, input_format: str):
    """
    ✅ FIXED: Uses async_utils pattern - no asyncio.run() errors!

    This matches your other working app's pattern.
    """
    try:
        if input_format == 'html':
            fact_logger.logger.info(f"🔗 Job {job_id}: LLM Output pipeline")
            # ✅ Use run_async_in_thread instead of loop.run_until_complete
            result = run_async_in_thread(
                llm_orchestrator.process_with_progress(content, job_id)
            )
        else:
            if web_search_orchestrator is None:
                raise ValueError("Web search orchestrator not initialized")

            fact_logger.logger.info(f"📝 Job {job_id}: Web Search pipeline")
            # ✅ Use run_async_in_thread instead of loop.run_until_complete
            result = run_async_in_thread(
                web_search_orchestrator.process_with_progress(content, job_id)
            )

        # Store successful result
        job_manager.complete_job(job_id, result)
        fact_logger.logger.info(f"✅ Job {job_id} completed successfully")

    except Exception as e:
        fact_logger.log_component_error(f"Job {job_id}", e)
        job_manager.fail_job(job_id, str(e))

    finally:
        # ✅ Cleanup event loop after job completes
        cleanup_thread_loop()

@app.route('/api/job/<job_id>', methods=['GET'])
def get_job_status(job_id: str):
    """Get current job status and result"""
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job_id,
        "status": job.get('status', 'unknown'),
        "result": job.get('result'),
        "error": job.get('error'),
        "progress_log": job.get('progress_log', [])
    })

@app.route('/api/job/<job_id>/stream')
def stream_job_progress(job_id: str):
    """Server-Sent Events stream for real-time progress"""
    def generate():
        import time
        import json

        job = job_manager.get_job(job_id)
        if not job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        yield f"data: {json.dumps({'status': job.get('status', 'unknown')})}\n\n"

        queue = job_manager.get_progress_queue(job_id)
        if not queue:
            return

        while True:
            try:
                current_job = job_manager.get_job(job_id)
                if current_job and current_job.get('status') in ['completed', 'failed']:
                    yield f"data: {json.dumps({
                        'status': current_job['status'],
                        'result': current_job.get('result'),
                        'error': current_job.get('error')
                    })}\n\n"
                    break

                try:
                    progress = queue.get(timeout=1)
                    yield f"data: {json.dumps(progress)}\n\n"
                except:
                    yield f"data: {json.dumps({'heartbeat': True})}\n\n"

            except GeneratorExit:
                break
            except Exception as e:
                fact_logger.logger.error(f"Stream error: {e}")
                break

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/health')
def health():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "langsmith_enabled": os.getenv('LANGCHAIN_TRACING_V2') == 'true',
        "browserless_configured": bool(os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE')),
        "tavily_configured": bool(os.getenv('TAVILY_API_KEY')),
        "pipelines": {
            "llm_output": True,
            "web_search": web_search_orchestrator is not None
        }
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    fact_logger.logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

@app.route('/api/jobs/debug', methods=['GET'])
def debug_jobs():
    """Debug endpoint to see all jobs"""
    all_jobs = job_manager.get_all_jobs()
    return jsonify({
        "total_jobs": len(all_jobs),
        "jobs": all_jobs
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    fact_logger.logger.info(f"🚀 Starting Flask server on port {port}")
    fact_logger.logger.info(f"🔍 Debug mode: {debug}")
    fact_logger.logger.info(f"📊 LangSmith project: {config.langchain_project}")

    if web_search_orchestrator:
        fact_logger.logger.info("✅ Both pipelines available: LLM Output & Web Search")
    else:
        fact_logger.logger.warning("⚠️ Only LLM Output pipeline available (check TAVILY_API_KEY)")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )