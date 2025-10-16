# app.py - WITH STREAMING SUPPORT
from flask import Flask, render_template, request, jsonify, Response
import asyncio
import os
import re
import threading
from dotenv import load_dotenv

# Import your components
from orchestrator.llm_output_orchestrator import FactCheckOrchestrator
from orchestrator.web_search_orchestrator import WebSearchOrchestrator
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.job_manager import job_manager

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
web_search_orchestrator = WebSearchOrchestrator(config) if config.tavily_api_key else None

# Helper function for input detection
def detect_input_format(content: str) -> str:
    """
    Detect if input is HTML (LLM output with links) or plain text

    Args:
        content: Input content to analyze

    Returns:
        'html' or 'text'
    """
    # Check for HTML tags
    html_pattern = r'<\s*[a-z][^>]*>'

    # Check for common HTML elements
    has_html_tags = bool(re.search(html_pattern, content, re.IGNORECASE))

    # Check for anchor tags specifically (links)
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
    """
    ✅ NEW: Start async job and return job_id immediately
    """
    try:
        # Get content from request
        content = request.json.get('html_content') or request.json.get('content')

        if not content:
            return jsonify({
                "error": "No content provided"
            }), 400

        fact_logger.logger.info(
            f"📥 Received fact-check request",
            extra={"content_length": len(content)}
        )

        # ✅ Detect input format
        input_format = detect_input_format(content)

        # Check if web search orchestrator is available
        if input_format == 'text' and not web_search_orchestrator:
            return jsonify({
                "error": "Web search pipeline not available",
                "message": "TAVILY_API_KEY not configured. Please add it to use plain text verification."
            }), 503

        # ✅ Create job
        job_id = job_manager.create_job(content)

        fact_logger.logger.info(f"✅ Created job: {job_id}")

        # ✅ Start background processing
        threading.Thread(
            target=run_async_task,
            args=(job_id, content, input_format),
            daemon=True
        ).start()

        # ✅ Return job_id immediately
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
    """Create isolated event loop per thread"""
    try:
        # Fresh loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if input_format == 'html':
                result = loop.run_until_complete(
                    llm_orchestrator.process_with_progress(content, job_id)
                )
            else:
                result = loop.run_until_complete(
                    web_search_orchestrator.process(content, job_id)
                )
            job_manager.complete_job(job_id, result)
        finally:
            loop.close()  # Critical: cleanup

    except Exception as e:
        job_manager.fail_job(job_id, str(e))

@app.route('/api/job/<job_id>', methods=['GET'])
def get_job_status(job_id: str):
    """
    ✅ NEW: Get current job status and result
    """
    job = job_manager.get_job(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job_id,
        "status": job['status'],
        "result": job.get('result'),
        "error": job.get('error'),
        "progress_log": job.get('progress_log', [])
    })

@app.route('/api/job/<job_id>/stream')
def stream_job_progress(job_id: str):
    """
    ✅ NEW: Server-Sent Events stream for real-time progress
    """
    def generate():
        import time
        import json

        # Get the job
        job = job_manager.get_job(job_id)
        if not job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        # Get progress queue
        progress_queue = job_manager.get_progress_queue(job_id)
        if not progress_queue:
            yield f"data: {json.dumps({'error': 'Progress queue not found'})}\n\n"
            return

        # Send initial status
        yield f"data: {json.dumps({'message': 'Starting fact-check...', 'status': 'processing'})}\n\n"

        # Stream progress updates
        timeout = 1200  # 20 minutes
        start_time = time.time()

        while True:
            # Check timeout
            if time.time() - start_time > timeout:
                yield f"data: {json.dumps({'error': 'Timeout', 'done': True})}\n\n"
                break

            # Check if job is done
            current_job = job_manager.get_job(job_id)
            if current_job['status'] in ['completed', 'failed']:
                yield f"data: {json.dumps({'done': True, 'status': current_job['status']})}\n\n"
                break

            # Get next progress update (non-blocking with timeout)
            try:
                import queue
                progress_item = progress_queue.get(timeout=1)
                yield f"data: {json.dumps(progress_item)}\n\n"
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "langsmith_enabled": os.getenv('LANGCHAIN_TRACING_V2') == 'true',
        "browserless_configured": bool(os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE')),
        "tavily_configured": bool(os.getenv('TAVILY_API_KEY')),
        "pipelines": {
            "llm_output": True,
            "web_search": bool(web_search_orchestrator)
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
        fact_logger.logger.warning("⚠️ Only LLM Output pipeline available (add TAVILY_API_KEY for Web Search)")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )