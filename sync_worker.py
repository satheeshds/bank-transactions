from __future__ import annotations

import threading
from typing import Any

from app.config import load_config
from app.db import session as database
from app.services.service import TransactionImportService

# Thread lock to prevent concurrent sync runs
_sync_lock = threading.Lock()
_current_run_id: int | None = None


def is_sync_running() -> bool:
    """Checks if a sync process is currently running."""
    return _sync_lock.locked()


def get_current_run_id() -> int | None:
    """Gets the active sync run ID, if any."""
    return _current_run_id


def start_sync_background() -> int:
    """Starts the synchronization process in a background thread.
    
    Returns:
        int: The run ID of the sync process.
    Raises:
        RuntimeError: If a sync is already in progress.
    """
    global _current_run_id

    # Try to acquire lock. If already locked, raise error.
    if not _sync_lock.acquire(blocking=False):
        raise RuntimeError("Synchronization is already in progress.")

    try:
        # Initialize DB just in case
        database.init_db()

        # Start run in DB
        run_id = database.start_sync_run()
        _current_run_id = run_id

        # Launch background thread
        thread = threading.Thread(target=_run_sync_worker, args=(run_id,))
        thread.daemon = True
        thread.start()

        return run_id
    except Exception as e:
        # Release lock if database or startup actions failed
        _sync_lock.release()
        raise e


def _run_sync_worker(run_id: int) -> None:
    """Target function for background thread execution."""
    global _current_run_id
    
    status = "success"
    parsed_count = 0
    error_count = 0
    
    try:
        # Load config dynamically
        config = load_config()
        
        # Instantiate and run service
        service = TransactionImportService.from_config(config, run_id=run_id)
        service.run()
        
        parsed_count = service.parsed_count
        error_count = service.error_count
        
        database.log_sync_message(run_id, "INFO", f"Sync run completed. Parsed: {parsed_count}, Errors: {error_count}")
    except Exception as e:
        status = "failed"
        database.log_sync_message(run_id, "ERROR", f"Sync run failed with exception: {e}")
    finally:
        # End the sync run in the DB
        try:
            database.end_sync_run(run_id, status, parsed_count=parsed_count, error_count=error_count)
        except Exception as e:
            print(f"Failed to close sync run in database: {e}")
        
        # Clear state and release lock
        _current_run_id = None
        _sync_lock.release()
