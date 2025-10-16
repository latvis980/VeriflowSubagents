# utils/langsmith_config.py
from langsmith import Client
from langchain.callbacks import LangChainTracer
from langchain.callbacks.manager import CallbackManager
import os
import threading
import asyncio
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
        """
        Get callback manager with LangSmith tracer

        ✅ FIX: Disable callbacks in daemon threads to avoid asyncio.run() conflicts

        Note: To set custom run names, pass them in the config when calling ainvoke():
        chain.ainvoke({...}, config={"run_name": "MyCustomName", "callbacks": callbacks.handlers})
        """
        # Check if we're in a daemon thread (background job)
        current_thread = threading.current_thread()
        is_daemon = current_thread.daemon

        # Also check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            in_event_loop = True
        except RuntimeError:
            in_event_loop = False

        # ✅ CRITICAL FIX: Return empty callbacks in daemon threads
        # This prevents LangSmith from trying to call asyncio.run() while
        # we're already in an async context
        if is_daemon or in_event_loop:
            self.fact_logger.logger.debug(
                f"📊 Skipping LangSmith callbacks (daemon={is_daemon}, in_loop={in_event_loop})"
            )
            return CallbackManager([])

        # Normal callback creation for main thread
        tracer = LangChainTracer(
            project_name=self.project_name,
            client=self.client
        )

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