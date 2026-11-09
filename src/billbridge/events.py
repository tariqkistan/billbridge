import json
import sqlite3
import time

from billbridge.config import EVENTS_DB
from billbridge.logger import get_logger

log = get_logger()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(EVENTS_DB)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS events '
        '(ts REAL, session_id TEXT, type TEXT, detail TEXT, latency_ms INTEGER)')
    return conn


def log_event(session_id: str, type_: str, detail: dict, latency_ms: int = 0) -> None:
    '''Never put customer message text or personal data in detail.'''
    log.info(type_, session_id=session_id, latency_ms=latency_ms, **detail)
    conn = _connect()
    try:
        conn.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?)',
                     (time.time(), session_id, type_, json.dumps(detail), latency_ms))
        conn.commit()
    finally:
        conn.close()
