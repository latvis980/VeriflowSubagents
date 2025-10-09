# app.py
from flask import Flask, render_template, request, jsonify
import asyncio
import os
from dotenv import load_dotenv

# Import your components
from orchestrator.llm_output_orchestrator import FactCheckOrchestrator
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Load configuration
class Config:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.browserless_endpoint = os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE')
        self.tavily_api_key = os.getenv('TAVILY_API_KEY')  # ✅ ADD THIS LINE
        self.langchain_project = os.getenv('LANGCHAIN_PROJECT', 'fact-checker')

        # Validate required env vars
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        # ✅ ADD THIS VALIDATION
        if not self.tavily_api_key:
            raise ValueError("TAVILY_API_KEY not set in environment")

        fact_logger.logger.info("✅ Configuration loaded successfully")

config = Config()

# Initialize orchestrator (singleton)
orchestrator = FactCheckOrchestrator(config)

@app.route('/')
def index():
    """Serve the main HTML interface"""
    return render_template('index.html')

@app.route('/api/check', methods=['POST'])
def check_facts():
    """
    Main API endpoint for fact checking
    Accepts HTML content and returns verification results
    """
    try:
        # Get HTML content from request
        html_content = request.json.get('html_content')

        if not html_content:
            return jsonify({
                "error": "No HTML content provided"
            }), 400

        fact_logger.logger.info(
            f"📥 Received fact-check request",
            extra={"content_length": len(html_content)}
        )

        # Run async orchestrator in new event loop
        # This is necessary because Flask is synchronous but our pipeline is async
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                orchestrator.process(html_content)
            )
        finally:
            loop.close()

        fact_logger.logger.info(
            f"📤 Fact-check complete",
            extra={
                "session_id": result.get('session_id'),
                "total_facts": result['summary']['total_facts']
            }
        )

        return jsonify(result)

    except Exception as e:
        fact_logger.log_component_error("Flask API", e)
        return jsonify({
            "error": str(e),
            "message": "An error occurred during fact checking"
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "langsmith_enabled": os.getenv('LANGCHAIN_TRACING_V2') == 'true',
        "browserless_configured": bool(os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE'))
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    fact_logger.logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    fact_logger.logger.info(f"🚀 Starting Flask server on port {port}")
    fact_logger.logger.info(f"🔍 Debug mode: {debug}")
    fact_logger.logger.info(f"📊 LangSmith project: {config.langchain_project}")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )