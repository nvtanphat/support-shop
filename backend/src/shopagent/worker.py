"""Worker background process entrypoint."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from shopagent.core.logging import setup_logging
from shopagent.infra.db.session import async_session_factory
from shopagent.infra.outbox.dispatcher import OutboxDispatcher
from shopagent.infra.outbox.reconciler import PaymentReconciler
from shopagent.infra.outbox.scheduler import BackgroundScheduler

logger = logging.getLogger("shopagent.worker")


async def main() -> None:
    setup_logging()
    logger.info("Initializing shop-support-agent worker process...")

    sf: Any = async_session_factory
    dispatcher = OutboxDispatcher(session_factory=sf, poll_interval_seconds=1.0)
    scheduler = BackgroundScheduler(session_factory=sf, interval_seconds=30.0)
    reconciler = PaymentReconciler(session_factory=sf, interval_seconds=300.0)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown() -> None:
        logger.info("Received termination signal, shutting down worker gracefully...")
        dispatcher.stop()
        scheduler.stop()
        reconciler.stop()
        stop_event.set()

    # Handle termination signals where supported
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown)

    tasks = [
        asyncio.create_task(dispatcher.start()),
        asyncio.create_task(scheduler.start()),
        asyncio.create_task(reconciler.start()),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Worker tasks cancelled.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker process exited via keyboard interrupt.")
