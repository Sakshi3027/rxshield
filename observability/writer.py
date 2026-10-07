"""Background telemetry writer: requests never wait on telemetry inserts."""
import atexit
import queue
import threading
import warnings
from collections import defaultdict
from functools import lru_cache

from sqlalchemy import text

from tenancy.db import get_app_engine

BATCH_SIZE = 200
FLUSH_INTERVAL_SECONDS = 1.0
QUEUE_LIMIT = 10_000

_queue = queue.Queue(maxsize=QUEUE_LIMIT)
_start_lock = threading.Lock()
_thread = None
_synchronous = False


@lru_cache(maxsize=1)
def _engine():
    return get_app_engine()


def set_synchronous(value):
    global _synchronous
    _synchronous = value


def submit(statement, params):
    if _synchronous:
        _write_batch([(statement, params)])
        return
    _ensure_started()
    try:
        _queue.put_nowait((statement, params))
    except queue.Full:
        warnings.warn("telemetry queue full; record dropped")


def flush():
    if _thread is not None:
        _queue.join()


def _write_batch(items):
    grouped = defaultdict(list)
    for statement, params in items:
        grouped[statement].append(params)
    try:
        with _engine().begin() as conn:
            for statement, rows in grouped.items():
                conn.execute(text(statement), rows)
    except Exception as exc:
        warnings.warn(f"telemetry batch of {len(items)} not recorded: {type(exc).__name__}")


def _next_batch():
    items = [_queue.get(timeout=FLUSH_INTERVAL_SECONDS)]
    while len(items) < BATCH_SIZE:
        try:
            items.append(_queue.get_nowait())
        except queue.Empty:
            break
    return items


def _run():
    while True:
        try:
            items = _next_batch()
        except queue.Empty:
            continue
        _write_batch(items)
        for _ in items:
            _queue.task_done()


def _ensure_started():
    global _thread
    if _thread is not None:
        return
    with _start_lock:
        if _thread is None:
            _thread = threading.Thread(target=_run, name="telemetry-writer", daemon=True)
            _thread.start()
            atexit.register(flush)