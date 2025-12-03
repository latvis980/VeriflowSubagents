# app.py
from flask import Flask, render_template, request, jsonify, Response
import os
import re
import threading
from typing import Optional
from dotenv import load_dotenv

# Import your components
from orchestrator.llm_output_orchestrator import LLMInterpretationOrchestrator
from orchestrator.web_search_orchestrator import WebSearchOrchestrator
from orchestrator.bias_check_orchestrator import BiasCheckOrchestrator
from orchestrator.lie_detector_orchestrator import LieDetectorOrchestrator
from orchestrator.key_claims_orchestrator import KeyClaimsOrchestrator
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.job_manager import job_manager
from utils.async_utils import run_async_in_thread, cleanup_thread_loop


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
        self.brave_api_key = os.getenv('BRAVE_API_KEY')
        self.langchain_project = os.getenv('LANGCHAIN_PROJECT', 'fact-checker')

        # Validate required env vars
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        if not self.brave_api_key:
            fact_logger.logger.warning("⚠️ BRAVE_API_KEY not set - web search pipeline will not work")

        fact_logger.logger.info("✅ Configuration loaded successfully")

config = Config()

# 1. LLM Interpretation Orchestrator (for LLM output with sources)
llm_interpretation_orchestrator: Optional[LLMInterpretationOrchestrator] = None
try:
    llm_interpretation_orchestrator = LLMInterpretationOrchestrator(config)
    fact_logger.logger.info("✅ LLM Interpretation Orchestrator initialized successfully")
except Exception as e:
    fact_logger.logger.error(f"❌ Failed to initialize LLM Interpretation Orchestrator: {e}")
    llm_interpretation_orchestrator = None

# 2. Web Search Orchestrator (for fact-checking any text via web search)
web_search_orchestrator: Optional[WebSearchOrchestrator] = None
if config.brave_api_key:
    try:
        web_search_orchestrator = WebSearchOrchestrator(config)
        fact_logger.logger.info("✅ Web Search Orchestrator initialized successfully")
    except Exception as e:
        fact_logger.logger.error(f"❌ Failed to initialize Web Search Orchestrator: {e}")
        fact_logger.logger.warning("⚠️ Web search pipeline will not be available")
        web_search_orchestrator = None
else:
    fact_logger.logger.warning("⚠️ BRAVE_API_KEY not set - web search will not work")

# 3. Bias Check Orchestrator (analyzes text for political/ideological bias)
bias_orchestrator: Optional[BiasCheckOrchestrator] = None
try:
    bias_orchestrator = BiasCheckOrchestrator(config)
    fact_logger.logger.info("✅ Bias Check Orchestrator initialized successfully")
except Exception as e:
    fact_logger.logger.error(f"❌ Failed to initialize Bias Check Orchestrator: {e}")
    bias_orchestrator = None

# 4. Lie Detector Orchestrator (detects linguistic markers of deception)
lie_detector_orchestrator: Optional[LieDetectorOrchestrator] = None
try:
    lie_detector_orchestrator = LieDetectorOrchestrator(config)
    fact_logger.logger.info("✅ Lie Detector Orchestrator initialized successfully")
except Exception as e:
    fact_logger.logger.error(f"❌ Failed to initialize Lie Detector Orchestrator: {e}")
    lie_detector_orchestrator = None

# 5. Key Claims Orchestrator (extracts and verifies 2-3 central thesis claims)
key_claims_orchestrator: Optional[KeyClaimsOrchestrator] = None
if config.brave_api_key:
    try:
        key_claims_orchestrator = KeyClaimsOrchestrator(config)
        fact_logger.logger.info("✅ Key Claims Orchestrator initialized successfully")
    except Exception as e:
        fact_logger.logger.error(f"❌ Failed to initialize Key Claims Orchestrator: {e}")
        key_claims_orchestrator = None

# Log summary
fact_logger.logger.info("📊 Orchestrator initialization complete:")
fact_logger.logger.info(f"  - LLM Interpretation: {'✅' if llm_interpretation_orchestrator else '❌'}")
fact_logger.logger.info(f"  - Web Search: {'✅' if web_search_orchestrator else '❌'}")
fact_logger.logger.info(f"  - Bias Check: {'✅' if bias_orchestrator else '❌'}")
fact_logger.logger.info(f"  - Lie Detection: {'✅' if lie_detector_orchestrator else '❌'}")

def detect_input_format(content: str) -> str:
    """
    Detect if input is HTML/Markdown (LLM output with links) or plain text
    """
    # Check for HTML tags
    html_pattern = r'<\s*[a-z][^>]*>'
    has_html_tags = bool(re.search(html_pattern, content, re.IGNORECASE))
    has_html_links = bool(re.search(r'<\s*a\s+[^>]*href\s*=', content, re.IGNORECASE))

    # Check for markdown reference links: [1]: https://...
    markdown_ref_pattern = r'^\s*\[\d+\]\s*:\s*https?://'
    has_markdown_refs = bool(re.search(markdown_ref_pattern, content, re.MULTILINE))

    # Check for markdown inline links: [text](https://...)
    markdown_inline_pattern = r'\[([^\]]+)\]\(https?://[^\)]+\)'
    has_markdown_inline = bool(re.search(markdown_inline_pattern, content))

    # Check for plain URLs (need at least 2)
    url_pattern = r'https?://[^\s]+'
    url_matches = re.findall(url_pattern, content)
    has_multiple_urls = len(url_matches) >= 2

    if has_html_tags or has_html_links or has_markdown_refs or has_markdown_inline or has_multiple_urls:
        fact_logger.logger.info("📋 Detected HTML/Markdown input format (LLM output with links)")
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
    Start async fact-check job and return job_id immediately

    Accepts optional 'input_type' parameter to explicitly specify pipeline:
    - 'html': Use LLM output pipeline (scrapes provided source links)
    - 'text': Use web search pipeline (searches web for verification)

    If input_type is not provided, auto-detects based on content.
    """
    try:
        # Get content from request
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        content = request_json.get('html_content') or request_json.get('content')
        if not content:
            return jsonify({"error": "No content provided"}), 400

        # Check for explicit input_type from frontend
        explicit_type = request_json.get('input_type')

        fact_logger.logger.info(
            "📥 Received fact-check request",
            extra={
                "content_length": len(content),
                "explicit_type": explicit_type
            }
        )

        # Determine input format: use explicit type if provided, otherwise auto-detect
        if explicit_type in ['html', 'text']:
            input_format = explicit_type
            fact_logger.logger.info(f"📋 Using explicit input type: {input_format}")
        else:
            input_format = detect_input_format(content)
            fact_logger.logger.info(f"📋 Auto-detected input type: {input_format}")

        # Type-safe check for web search orchestrator
        if input_format == 'text' and web_search_orchestrator is None:
            return jsonify({
                "error": "Web search pipeline not available",
                "message": "BRAVE_API_KEY not configured or initialization failed. Please use LLM Output mode with content that has source links."
            }), 503

        # Create job
        job_id = job_manager.create_job(content)
        fact_logger.logger.info(f"✅ Created job: {job_id} (format: {input_format})")

        # Start background processing
        threading.Thread(
            target=run_async_task,
            args=(job_id, content, input_format),
            daemon=True
        ).start()

        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": f"Fact-checking started ({input_format} pipeline)",
            "pipeline": input_format
        })

    except Exception as e:
        fact_logger.log_component_error("Flask API", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred during fact checking"
        }), 500

@app.route('/api/key-claims', methods=['POST'])
def check_key_claims():
    """Extract and verify key claims from text"""
    try:
        request_json = request.get_json()
        content = request_json.get('content')

        if not content:
            return jsonify({"error": "No content provided"}), 400

        if key_claims_orchestrator is None:
            return jsonify({"error": "Key claims pipeline not available"}), 503

        job_id = job_manager.create_job(content)

        thread = threading.Thread(
            target=run_key_claims_task,
            args=(job_id, content)
        )
        thread.start()

        return jsonify({"job_id": job_id, "status": "started"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_key_claims_task(job_id: str, content: str):
    """Background task runner for key claims verification"""
    try:
        result = run_async_in_thread(
            key_claims_orchestrator.process_with_progress(content, job_id)
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:
        job_manager.fail_job(job_id, str(e))
    finally:
        cleanup_thread_loop()


@app.route('/api/check-bias', methods=['POST'])
def check_bias():
    '''Check text for political and other biases using multiple LLMs'''
    try:
        # Get content from request
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        text = request_json.get('text') or request_json.get('content')
        publication_url = request_json.get('publication_url')  # NEW: changed from publication_name

        if not text:
            return jsonify({"error": "No text provided"}), 400

        if not bias_orchestrator:
            return jsonify({
                "error": "Bias analysis not available",
                "message": "Bias Check Orchestrator not initialized"
            }), 503

        fact_logger.logger.info(
            "📥 Received bias check request",
            extra={
                "text_length": len(text),
                "publication_url": publication_url  # NEW
            }
        )

        # Create job
        job_id = job_manager.create_job(text)
        fact_logger.logger.info(f"✅ Created bias check job: {job_id}")

        # Start background processing
        threading.Thread(
            target=run_bias_task,
            args=(job_id, text, publication_url),  # NEW: pass URL instead of name
            daemon=True
        ).start()

        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": "Bias analysis started"
        })

    except Exception as e:
        fact_logger.log_component_error("Flask API - Bias Check", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred during bias analysis"
        }), 500

@app.route('/api/check-lie-detection', methods=['POST'])
def check_lie_detection():
    """Analyze text for linguistic markers of deception/fake news"""
    try:
        # Get content from request
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        text = request_json.get('text') or request_json.get('content')
        article_source = request_json.get('article_source')  # Optional: publication name
        article_date = request_json.get('article_date')      # Optional: publication date

        if not text:
            return jsonify({"error": "No text provided"}), 400

        if not lie_detector_orchestrator:
            return jsonify({
                "error": "Lie detection not available",
                "message": "Lie Detector Orchestrator not initialized"
            }), 503

        fact_logger.logger.info(
            "🕵️ Received lie detection request",
            extra={
                "text_length": len(text),
                "has_source": bool(article_source),
                "has_date": bool(article_date)
            }
        )

        # Create job
        job_id = job_manager.create_job(text)
        fact_logger.logger.info(f"✅ Created lie detection job: {job_id}")

        # Start background processing
        threading.Thread(
            target=run_lie_detection_task,
            args=(job_id, text, article_source, article_date),
            daemon=True
        ).start()

        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": "Lie detection analysis started"
        })

    except Exception as e:
        fact_logger.log_component_error("Flask API - Lie Detection", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred during lie detection"
        }), 500


def run_lie_detection_task(job_id: str, text: str, article_source: Optional[str], article_date: Optional[str]):
    """Background task runner for lie detection analysis."""
    try:
        if lie_detector_orchestrator is None:  # ← ADD THIS CHECK
            raise ValueError("Lie detector orchestrator not initialized")
            
        fact_logger.logger.info(f"🕵️ Job {job_id}: Starting lie detection analysis")

        result = run_async_in_thread(
            lie_detector_orchestrator.process(
                text, 
                job_id, 
                article_source, 
                article_date
            )
        )

        job_manager.complete_job(job_id, result)
        fact_logger.logger.info(f"✅ Lie detection job {job_id} completed successfully")

    except Exception as e:
        fact_logger.log_component_error(f"Lie Detection Job {job_id}", e)
        job_manager.fail_job(job_id, str(e))

    finally:
        cleanup_thread_loop()


def run_async_task(job_id: str, content: str, input_format: str):
    """
    Background task runner for fact checking.
    Routes to appropriate orchestrator based on input format:
    - 'html' → LLM Interpretation Orchestrator (checks if LLM interpreted sources correctly)
    - 'text' → Web Search Orchestrator (fact-checks via web search)
    """
    try:
        if input_format == 'html':
            # LLM output with sources → Interpretation verification
            if llm_interpretation_orchestrator is None:
                raise ValueError("LLM Interpretation orchestrator not initialized")

            fact_logger.logger.info(f"🔍 Job {job_id}: LLM Interpretation Verification pipeline")
            result = run_async_in_thread(
                llm_interpretation_orchestrator.process_with_progress(content, job_id)
            )

        else:  # input_format == 'text'
            # Plain text → Fact-checking via web search
            if web_search_orchestrator is None:
                raise ValueError("Web search orchestrator not initialized - BRAVE_API_KEY may be missing")

            fact_logger.logger.info(f"🔎 Job {job_id}: Web Search Fact-Checking pipeline")
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
        cleanup_thread_loop()

def run_bias_task(job_id: str, text: str, publication_url: Optional[str] = None):
    """Background task for bias checking with MBFC lookup"""
    try:
        fact_logger.logger.info(f"🔄 Starting bias check job: {job_id}")

        result = run_async_in_thread(
            bias_orchestrator.process_with_progress(
                text=text,
                publication_url=publication_url,  # NEW: pass URL for MBFC lookup
                job_id=job_id
            )
        )

    except Exception as e:
        fact_logger.logger.error(f"❌ Bias check failed: {e}")
        job_manager.fail_job(job_id, str(e))
    finally:
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
                if current_job and current_job.get('status') in ['completed', 'failed', 'cancelled']:
                    # Send final status
                    final_data = {
                        'status': current_job['status'],
                        'result': current_job.get('result'),
                        'error': current_job.get('error')
                    }
                    yield f"data: {json.dumps(final_data)}\n\n"
                    return

                # Check for progress updates
                try:
                    progress = queue.get(timeout=1)
                    yield f"data: {json.dumps(progress)}\n\n"
                except Exception:
                    # Send heartbeat
                    yield f"data: {json.dumps({'heartbeat': True})}\n\n"

            except GeneratorExit:
                return
            except Exception as e:
                fact_logger.logger.error(f"SSE Error: {e}")
                return

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/job/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id: str):
    """Cancel a running job"""
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    job_manager.cancel_job(job_id)
    return jsonify({
        "job_id": job_id,
        "status": "cancelled",
        "message": "Job cancellation requested"
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "llm_orchestrator": llm_interpretation_orchestrator is not None,
        "web_search_orchestrator": web_search_orchestrator is not None,
        "bias_orchestrator": bias_orchestrator is not None
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'

    fact_logger.logger.info(f"🚀 Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)