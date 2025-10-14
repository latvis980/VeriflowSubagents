# utils/job_manager.py
"""
Job Manager for Background Fact-Checking Tasks
Handles asynchronous job processing with real-time progress streaming
"""

import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import uuid
import queue
import threading

class JobManager:
    """Manage background fact-checking jobs with real-time updates"""

    def __init__(self):
        self.jobs: Dict[str, dict] = {}
        self.progress_queues: Dict[str, queue.Queue] = {}
        self._cleanup_lock = threading.Lock()

    def create_job(self, content: str) -> str:
        """
        Create a new job and return job ID

        Args:
            content: Input content to fact-check

        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            'status': 'pending',
            'created_at': datetime.now(),
            'content': content,
            'result': None,
            'error': None,
            'progress_log': []
        }
        self.progress_queues[job_id] = queue.Queue()
        return job_id

    def add_progress(self, job_id: str, message: str, details: dict = None):
        """
        Add progress update to job

        Args:
            job_id: Job identifier
            message: Progress message to display
            details: Optional additional details (dict)
        """
        if job_id in self.jobs:
            progress_item = {
                'timestamp': datetime.now().isoformat(),
                'message': message,
                'details': details or {}
            }
            self.jobs[job_id]['progress_log'].append(progress_item)

            # Add to queue for streaming
            if job_id in self.progress_queues:
                try:
                    self.progress_queues[job_id].put(progress_item, block=False)
                except queue.Full:
                    pass  # Queue full, skip this update

    def get_progress_queue(self, job_id: str) -> Optional[queue.Queue]:
        """
        Get progress queue for streaming

        Args:
            job_id: Job identifier

        Returns:
            Queue object or None if not found
        """
        return self.progress_queues.get(job_id)

    def complete_job(self, job_id: str, result: dict):
        """
        Mark job as complete with result

        Args:
            job_id: Job identifier
            result: Final result dictionary
        """
        if job_id in self.jobs:
            self.jobs[job_id]['status'] = 'completed'
            self.jobs[job_id]['result'] = result
            self.jobs[job_id]['completed_at'] = datetime.now()
            self.add_progress(job_id, "✅ Fact-checking complete!")

    def fail_job(self, job_id: str, error: str):
        """
        Mark job as failed

        Args:
            job_id: Job identifier
            error: Error message
        """
        if job_id in self.jobs:
            self.jobs[job_id]['status'] = 'failed'
            self.jobs[job_id]['error'] = error
            self.jobs[job_id]['failed_at'] = datetime.now()
            self.add_progress(job_id, f"❌ Error: {error}")

    def get_job(self, job_id: str) -> Optional[dict]:
        """
        Get job status and data

        Args:
            job_id: Job identifier

        Returns:
            Job dictionary or None if not found
        """
        return self.jobs.get(job_id)

    def get_job_status(self, job_id: str) -> Optional[str]:
        """
        Get just the job status

        Args:
            job_id: Job identifier

        Returns:
            Status string or None
        """
        job = self.jobs.get(job_id)
        return job['status'] if job else None

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Remove old completed/failed jobs

        Args:
            max_age_hours: Maximum age in hours before cleanup
        """
        with self._cleanup_lock:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)
            jobs_to_remove = []

            for job_id, job in self.jobs.items():
                if job['status'] in ['completed', 'failed']:
                    job_time = job.get('completed_at') or job.get('failed_at') or job['created_at']
                    if job_time < cutoff:
                        jobs_to_remove.append(job_id)

            for job_id in jobs_to_remove:
                del self.jobs[job_id]
                if job_id in self.progress_queues:
                    del self.progress_queues[job_id]

    def get_all_jobs(self) -> List[dict]:
        """
        Get all jobs (for admin/debugging)

        Returns:
            List of job summaries
        """
        return [
            {
                'job_id': job_id,
                'status': job['status'],
                'created_at': job['created_at'].isoformat(),
                'progress_count': len(job['progress_log'])
            }
            for job_id, job in self.jobs.items()
        ]

    def cancel_job(self, job_id: str):
        """
        Cancel a running job

        Args:
            job_id: Job identifier
        """
        if job_id in self.jobs:
            if self.jobs[job_id]['status'] == 'pending':
                self.jobs[job_id]['status'] = 'cancelled'
                self.add_progress(job_id, "🚫 Job cancelled by user")

# Global job manager instance
job_manager = JobManager()