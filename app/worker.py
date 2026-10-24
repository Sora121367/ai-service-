"""Background worker (stub). The job queue is not chosen yet (ADR-0003), so it only waits.

Logs IDs and settings names only, never values (docs/conventions.md, Logging and privacy).
"""

import logging
import signal
import threading

from app.config import get_settings

logger = logging.getLogger("insighthub.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    get_settings()  # fail fast on missing configuration

    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK exists on Windows only
        if (sig := getattr(signal, name, None)) is not None:
            signal.signal(sig, lambda *_: stop.set())

    logger.info("worker started, no job queue configured yet")
    while not stop.wait(timeout=0.5):  # a timed wait lets signals run on Windows
        pass
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
