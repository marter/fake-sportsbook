"""Background worker: keeps odds fresh and settles bets without anyone opening the app.

Runs as its own container (see deploy/docker-compose.prod.yml):

    python -m app.worker

Every `worker_interval_seconds` (15 min) it runs the same cached checks the API runs on page
load, so it only spends API credits when they're due: odds once a day per in-season sport, and
scores only for a sport with an open bet waiting on a game that should be over.
"""

import logging
import signal
import threading

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services import odds, settlement

logger = logging.getLogger("app.worker")


def run_once() -> None:
    """One cycle. Each step gets its own session so a failure in one doesn't skip the other."""
    for sport in odds.enabled_sports():
        with SessionLocal() as db:
            odds.ensure_fresh_odds(db, sport)  # skips out-of-season sports and fresh caches
    with SessionLocal() as db:
        settled = settlement.settle_if_due(db)
        if settled:
            logger.info("Settled %d bet(s)", settled)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs every request URL at INFO, and The Odds API takes its key as a query
    # parameter, so keep HTTP client logs to warnings and up.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    interval = get_settings().worker_interval_seconds
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    logger.info("Worker started, running every %ds", interval)
    while not stop.is_set():
        try:
            run_once()
        except Exception:
            # Keep going: a transient DB or API error shouldn't stop settlement for good.
            logger.exception("Worker cycle failed")
        stop.wait(interval)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
