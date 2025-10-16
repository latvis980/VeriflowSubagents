# utils/async_utils.py
"""
Async utilities for mixing sync and async code in Flask

This module provides utilities to properly handle async code in a Flask (WSGI) environment
where we need to run async functions from sync contexts (like daemon threads).

Key utilities:
- track_async_task: Schedule async tasks and track them for graceful shutdown
- wait_for_pending_tasks: Wait for all tracked tasks to complete
- sync_to_async: Convert any callable (sync or async) into an awaitable
- run_async_in_thread: Run async code in a dedicated thread with proper event loop
"""

import asyncio
import inspect
from functools import wraps, partial
import threading
from typing import Any, Callable, Coroutine, TypeVar
import logging

logger = logging.getLogger(__name__)

# Track all pending async tasks for graceful shutdown
_PENDING_TASKS: set[asyncio.Task] = set()

# Store event loops per thread for reuse
_THREAD_LOOPS: dict[int, asyncio.AbstractEventLoop] = {}
_LOOP_LOCK = threading.Lock()

T = TypeVar('T')


def track_async_task(coro: Coroutine) -> asyncio.Task:
    """
    Schedule a coroutine in the current event loop and track it for shutdown.

    This ensures we can wait for all outstanding tasks when shutting down the app.

    Args:
        coro: Coroutine to schedule

    Returns:
        The scheduled Task, or result if no loop is running

    Usage:
        task = track_async_task(my_async_function())
    """
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:  # No loop running
        return asyncio.run(coro)

    _PENDING_TASKS.add(task)
    task.add_done_callback(_PENDING_TASKS.discard)
    return task


async def wait_for_pending_tasks():
    """
    Wait for all tasks registered via track_async_task() to complete.

    Call this during application shutdown to ensure graceful cleanup.
    """
    if _PENDING_TASKS:
        logger.info(f"Waiting for {len(_PENDING_TASKS)} pending tasks to complete...")
        try:
            await asyncio.gather(*_PENDING_TASKS, return_exceptions=True)
            logger.info("All pending tasks completed")
        except Exception as e:
            logger.error(f"Error waiting for pending tasks: {e}")


def sync_to_async(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    Convert any callable into an awaitable function.

    - If func is already async def → just await it
    - If func is sync → run it in ThreadPoolExecutor so event loop never blocks

    This is the key utility that allows mixing sync and async code without blocking.

    Args:
        func: Any callable (sync or async)

    Returns:
        Async wrapper function

    Usage:
        # Works with both sync and async functions
        result = await sync_to_async(my_function)(*args, **kwargs)

    Examples:
        # Sync function
        def slow_function(x):
            time.sleep(1)
            return x * 2

        result = await sync_to_async(slow_function)(5)  # Runs in executor

        # Async function  
        async def fast_function(x):
            await asyncio.sleep(1)
            return x * 2

        result = await sync_to_async(fast_function)(5)  # Just awaits it
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        # Fast path for proper coroutine functions
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)

        # Sync functions: run in default ThreadPoolExecutor
        # This prevents blocking the event loop
        loop = asyncio.get_running_loop()
        bound = partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, bound)

    return async_wrapper


def get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """
    Get or create an event loop for the current thread.

    This is crucial for daemon threads where each thread needs its own loop.
    Reuses the same loop for the same thread to avoid creating too many loops.

    Returns:
        Event loop for current thread
    """
    thread_id = threading.get_ident()

    with _LOOP_LOCK:
        # Check if this thread already has a loop
        if thread_id in _THREAD_LOOPS:
            loop = _THREAD_LOOPS[thread_id]
            if not loop.is_closed():
                return loop

        # Create new loop for this thread
        try:
            loop = asyncio.get_running_loop()
            logger.debug(f"Thread {thread_id}: Using existing running loop")
        except RuntimeError:
            # No loop running, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _THREAD_LOOPS[thread_id] = loop
            logger.debug(f"Thread {thread_id}: Created new event loop")

        return loop


def run_async_in_thread(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine in the current thread, handling event loop creation.

    This is the main function to call async code from sync contexts (like Flask routes
    running in daemon threads).

    Key features:
    - Creates/reuses event loop per thread
    - Handles loop lifecycle properly
    - Works with LangSmith callbacks
    - No need for asyncio.run() which causes the error

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine

    Usage:
        # In a sync context (like a daemon thread)
        result = run_async_in_thread(my_async_function(arg1, arg2))

    Example:
        def background_job(job_id: str, content: str):
            # This runs in a daemon thread
            result = run_async_in_thread(
                orchestrator.process_with_progress(content, job_id)
            )
            return result
    """
    loop = get_or_create_event_loop()

    # Use run_until_complete instead of asyncio.run()
    # This works because we manage the loop ourselves
    return loop.run_until_complete(coro)


def cleanup_thread_loop():
    """
    Cleanup the event loop for the current thread.

    Call this when a thread is done with async work to free resources.
    Usually not necessary as loops are reused, but useful for explicit cleanup.
    """
    thread_id = threading.get_ident()

    with _LOOP_LOCK:
        if thread_id in _THREAD_LOOPS:
            loop = _THREAD_LOOPS[thread_id]
            if not loop.is_closed():
                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()

                # Run one final iteration to process cancellations
                try:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as e:
                    logger.error(f"Error cleaning up tasks: {e}")

                loop.close()

            del _THREAD_LOOPS[thread_id]
            logger.debug(f"Thread {thread_id}: Cleaned up event loop")


# Graceful shutdown support
def shutdown_all_loops():
    """
    Shutdown all event loops across all threads.

    Call this during application shutdown for graceful cleanup.
    """
    with _LOOP_LOCK:
        for thread_id, loop in list(_THREAD_LOOPS.items()):
            try:
                if not loop.is_closed():
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    loop.close()
            except Exception as e:
                logger.error(f"Error shutting down loop for thread {thread_id}: {e}")

        _THREAD_LOOPS.clear()
        logger.info("All event loops shut down")