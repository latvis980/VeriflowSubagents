# utils/langsmith_config.py
from langsmith import Client
from langchain.callbacks import LangChainTracer
from langchain.callbacks.manager import CallbackManager
import os
from typing import Optional

class LangSmithConfig:
    """Configure LangSmith tracing for all LangChain operations"""

    def __init__(self):
        # Import logger here to avoid circular imports
        from utils.logger import fact_logger
        self.fact_logger = fact_logger

        self.client = Client()
        self.project_name = os.getenv("LANGCHAIN_PROJECT", "fact-checker")

        # Verify connection
        try:
            self.client.read_project(project_name=self.project_name)
            self.fact_logger.logger.info(f"✅ Connected to LangSmith project: {self.project_name}")
        except Exception:
            self.fact_logger.logger.warning(f"⚠️ LangSmith project not found, creating: {self.project_name}")
            try:
                self.client.create_project(project_name=self.project_name)
            except Exception as create_error:
                self.fact_logger.logger.error(f"❌ Failed to create LangSmith project: {create_error}")

    def get_callbacks(self, run_name: Optional[str] = None):
        """Get callback manager with LangSmith tracer"""
        tracer = LangChainTracer(
            project_name=self.project_name,
            client=self.client
        )

        # Only set name if run_name is provided (not None)
        if run_name is not None:
            tracer.name = run_name

        return CallbackManager([tracer])

    def create_session(self, session_id: str, metadata: Optional[dict] = None):
        """Create a LangSmith session for grouping related traces"""
        try:
            self.client.create_run(
                name=f"fact-check-session-{session_id}",
                run_type="chain",
                project_name=self.project_name,
                inputs={"session_id": session_id},
                extra=metadata or {}
            )

            self.fact_logger.logger.info(
                f"📊 Created LangSmith session: {session_id}",
                extra={"session_id": session_id, "metadata": metadata}
            )
        except Exception as e:
            self.fact_logger.logger.warning(
                f"⚠️ Failed to create LangSmith session: {e}",
                extra={"session_id": session_id}
            )

langsmith_config = LangSmithConfig()