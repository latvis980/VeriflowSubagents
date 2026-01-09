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
from orchestrator.manipulation_orchestrator import ManipulationOrchestrator

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

# 6. Manipulation Detection Orchestrator (detects agenda-driven fact manipulation)
manipulation_orchestrator: Optional[ManipulationOrchestrator] = None
if config.brave_api_key:
    try:
        manipulation_orchestrator = ManipulationOrchestrator(config)
        fact_logger.logger.info("✅ Manipulation Detection Orchestrator initialized successfully")
    except Exception as e:
        fact_logger.logger.error(f"❌ Failed to initialize Manipulation Orchestrator: {e}")
        manipulation_orchestrator = None
else:
    fact_logger.logger.warning("⚠️ Manipulation Detection requires BRAVE_API_KEY for fact verification")

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
        if key_claims_orchestrator is None:
            raise ValueError("Key claims orchestrator not initialized")

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

@app.route('/api/manipulation', methods=['POST'])
def check_manipulation():
    """Analyze article for opinion manipulation and agenda-driven fact distortion"""
    try:
        # Get content from request
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        content = request_json.get('content') or request_json.get('text')
        source_info = request_json.get('source_info', 'Unknown source')

        if not content:
            return jsonify({"error": "No content provided"}), 400

        if manipulation_orchestrator is None:
            return jsonify({
                "error": "Manipulation detection not available",
                "message": "Manipulation Orchestrator not initialized. Requires BRAVE_API_KEY."
            }), 503

        fact_logger.logger.info(
            "📥 Received manipulation detection request",
            extra={
                "content_length": len(content),
                "source_info": source_info
            }
        )

        # Create job
        job_id = job_manager.create_job(content)
        fact_logger.logger.info(f"✅ Created manipulation detection job: {job_id}")

        # Start background processing
        threading.Thread(
            target=run_manipulation_task,
            args=(job_id, content, source_info),
            daemon=True
        ).start()

        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": "Manipulation analysis started"
        })

    except Exception as e:
        fact_logger.log_component_error("Flask API - Manipulation Detection", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred during manipulation analysis"
        }), 500

def run_lie_detection_task(job_id: str, text: str, article_source: Optional[str], article_date: Optional[str]):
    """Background task runner for lie detection analysis."""
    try:
        if lie_detector_orchestrator is None:
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

def run_manipulation_task(job_id: str, content: str, source_info: str):
    """Background task runner for manipulation detection"""
    try:
        if manipulation_orchestrator is None:
            raise ValueError("Manipulation orchestrator not initialized")

        result = run_async_in_thread(
            manipulation_orchestrator.process_with_progress(content, job_id, source_info)
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:
        fact_logger.logger.error(f"Manipulation task error: {e}")
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
        if bias_orchestrator is None:
            raise ValueError("Bias orchestrator not initialized")

        fact_logger.logger.info(f"🔄 Starting bias check job: {job_id}")

        result = run_async_in_thread(
            bias_orchestrator.process_with_progress(
                text=text,
                publication_url=publication_url,  # NEW: pass URL for MBFC lookup
                job_id=job_id
            )
        )

        job_manager.complete_job(job_id, result)
        fact_logger.logger.info(f"✅ Bias check job {job_id} completed successfully")

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
    import json

    def generate():
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

# ============================================
# URL SCRAPING ENDPOINT
# ============================================

@app.route('/api/scrape-url', methods=['POST'])
def scrape_url():
    """
    Scrape, extract metadata, and check credibility for an article URL.

    NEW: Returns enriched data including:
    - Article content
    - Metadata (title, author, publication date)
    - Publication credibility (tier, bias, factual reporting)

    Request body:
        {
            "url": "https://example.com/article",
            "extract_metadata": true,      // optional, default true
            "check_credibility": true,     // optional, default true
            "run_mbfc_if_missing": true    // optional, default true
        }

    Returns:
        {
            "success": true,
            "url": "https://example.com/article",
            "domain": "example.com",

            // Content
            "content": "Cleaned article text...",
            "content_length": 5432,

            // Metadata
            "title": "Article Title",
            "author": "John Smith",
            "publication_date": "2024-01-15",
            "publication_date_raw": "January 15, 2024",
            "publication_name": "Example News",
            "article_type": "news",
            "metadata_confidence": 0.85,

            // Credibility
            "credibility": {
                "tier": 2,
                "tier_description": "Credible - Reputable mainstream media...",
                "rating": "HIGH CREDIBILITY",
                "bias_rating": "CENTER",
                "factual_reporting": "HIGH",
                "is_propaganda": false,
                "special_tags": [],
                "source": "supabase",
                "reasoning": "Tier 2 based on MBFC: Factual reporting: HIGH...",
                "mbfc_url": "https://mediabiasfactcheck.com/example-news/"
            },

            // Processing info
            "processing_time_ms": 2345,
            "errors": []
        }
    """
    try:
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        url = request_json.get('url')
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            return jsonify({
                "error": "Invalid URL format",
                "message": "URL must start with http:// or https://"
            }), 400

        # Get optional parameters
        extract_metadata = request_json.get('extract_metadata', True)
        check_credibility = request_json.get('check_credibility', True)
        run_mbfc_if_missing = request_json.get('run_mbfc_if_missing', True)

        fact_logger.logger.info(
            "🔗 Received enriched scrape request",
            extra={
                "url": url,
                "extract_metadata": extract_metadata,
                "check_credibility": check_credibility
            }
        )

        # Import the enriched content service
        from utils.enriched_content_service import EnrichedContentService

        # Run the async scrape operation
        async def scrape_and_enrich():
            service = EnrichedContentService(config)
            try:
                result = await service.scrape_and_enrich(
                    url=url,
                    extract_metadata=extract_metadata,
                    check_credibility=check_credibility,
                    run_mbfc_if_missing=run_mbfc_if_missing
                )
                return result
            finally:
                await service.close()

        result = run_async_in_thread(scrape_and_enrich())

        # Handle failure
        if not result.success or result.article is None:
            return jsonify({
                "error": "Could not extract content from URL",
                "message": result.error or "The page may be empty, paywalled, or use JavaScript rendering that we couldn't process."
            }), 422

        # Now article is guaranteed to be non-None
        article = result.article

        # Get tier description
        tier_descriptions = {
            1: "Highly Credible - Official sources, major wire services, highly reputable news",
            2: "Credible - Reputable mainstream media with strong factual reporting",
            3: "Mixed - Requires verification, may have bias or mixed factual reporting",
            4: "Low Credibility - Significant bias issues or poor factual reporting",
            5: "Unreliable - Propaganda, conspiracy, or known disinformation source"
        }

        # Build response
        response = {
            "success": True,
            "url": article.url,
            "domain": article.domain,

            # Content
            "content": article.content,
            "content_length": article.content_length,

            # Metadata
            "title": article.title,
            "author": article.author,
            "publication_date": article.publication_date,
            "publication_date_raw": article.publication_date_raw,
            "publication_name": article.publication_name,
            "article_type": article.article_type,
            "section": article.section,
            "metadata_confidence": article.metadata_confidence,

            # Credibility (nested for clarity)
            "credibility": {
                "tier": article.credibility_tier,
                "tier_description": tier_descriptions.get(article.credibility_tier, "Unknown"),
                "rating": article.credibility_rating,
                "bias_rating": article.bias_rating,
                "factual_reporting": article.factual_reporting,
                "is_propaganda": article.is_propaganda,
                "special_tags": article.special_tags,
                "source": article.credibility_source,
                "reasoning": article.tier_reasoning,
                "mbfc_url": article.mbfc_url
            },

            # Processing info
            "processing_time_ms": article.processing_time_ms,
            "scraped_at": article.scraped_at,
            "errors": article.errors
        }

        fact_logger.logger.info(
            "✅ Enriched scrape complete",
            extra={
                "url": url,
                "domain": article.domain,
                "content_length": article.content_length,
                "title": article.title[:50] if article.title else None,
                "author": article.author,
                "date": article.publication_date,
                "tier": article.credibility_tier,
                "processing_ms": article.processing_time_ms
            }
        )

        return jsonify(response)

    except Exception as e:
        fact_logger.log_component_error("Enriched URL Scraper API", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred while fetching the URL. Please try pasting the content directly."
        }), 500

# ============================================
# CREDIBILITY CHECK ENDPOINT
# ============================================
# Standalone endpoint to check credibility without scraping

@app.route('/api/check-credibility', methods=['POST'])
def check_credibility():
    """
    Check credibility of a publication without scraping content.

    Request body:
        {
            "url": "https://example.com/article",
            "run_mbfc_if_missing": true  // optional, default false for speed
        }

    Returns:
        {
            "success": true,
            "domain": "example.com",
            "credibility": {
                "tier": 2,
                "tier_description": "Credible...",
                "rating": "HIGH CREDIBILITY",
                ...
            }
        }
    """
    try:
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Invalid request format"}), 400

        url = request_json.get('url')
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        run_mbfc = request_json.get('run_mbfc_if_missing', False)

        from utils.source_credibility_service import SourceCredibilityService

        async def check():
            # Initialize with dependencies for MBFC lookup
            brave_searcher = None
            scraper = None

            if run_mbfc:
                try:
                    from utils.brave_searcher import BraveSearcher
                    from utils.browserless_scraper import BrowserlessScraper
                    brave_searcher = BraveSearcher(config)
                    scraper = BrowserlessScraper(config)
                except Exception:
                    pass

            service = SourceCredibilityService(
                config=config,
                brave_searcher=brave_searcher,
                scraper=scraper
            )

            cred_result = await service.check_credibility(
                url=url,
                run_mbfc_if_missing=run_mbfc
            )

            if scraper:
                await scraper.close()

            return cred_result

        cred_result = run_async_in_thread(check())

        tier_descriptions = {
            1: "Highly Credible - Official sources, major wire services, highly reputable news",
            2: "Credible - Reputable mainstream media with strong factual reporting",
            3: "Mixed - Requires verification, may have bias or mixed factual reporting",
            4: "Low Credibility - Significant bias issues or poor factual reporting",
            5: "Unreliable - Propaganda, conspiracy, or known disinformation source"
        }

        return jsonify({
            "success": True,
            "url": url,
            "domain": cred_result.domain,
            "publication_name": cred_result.publication_name,
            "credibility": {
                "tier": cred_result.credibility_tier,
                "tier_description": tier_descriptions.get(cred_result.credibility_tier, "Unknown"),
                "rating": cred_result.credibility_rating,
                "bias_rating": cred_result.bias_rating,
                "factual_reporting": cred_result.factual_reporting,
                "is_propaganda": cred_result.is_propaganda,
                "special_tags": cred_result.special_tags,
                "source": cred_result.source,
                "reasoning": cred_result.tier_reasoning,
                "mbfc_url": cred_result.mbfc_url
            }
        })

    except Exception as e:
        fact_logger.log_component_error("Credibility Check API", e)
        return jsonify({"error": str(e)}), 500

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