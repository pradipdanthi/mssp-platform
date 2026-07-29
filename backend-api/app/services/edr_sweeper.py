"""
Background reconciler: sweeps EDR actions stuck in EXECUTING state past timeout.

Run as a background asyncio task started at app startup.
"""

import asyncio
import logging
import os

from app.db.session import db_conn

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = int(os.getenv("EDR_SWEEP_INTERVAL", "60"))
STUCK_TIMEOUT_SECONDS = int(os.getenv("EDR_STUCK_TIMEOUT", "120"))


async def edr_sweeper_loop() -> None:
    """Periodically transition stuck actions to TIMEOUT/FAILED."""
    logger.info("EDR sweeper started (interval=%ds, timeout=%ds)",
                SWEEP_INTERVAL_SECONDS, STUCK_TIMEOUT_SECONDS)
    while True:
        try:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            count = _sweep_stuck_actions()
            if count:
                logger.warning("EDR sweeper transitioned %d stuck actions to TIMEOUT", count)
        except asyncio.CancelledError:
            logger.info("EDR sweeper stopped")
            break
        except Exception:
            logger.exception("EDR sweeper error")


def _sweep_stuck_actions() -> int:
    """Find and transition actions stuck in 'executing' past the timeout."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE edr_action_executions
                SET status = 'timeout',
                    result_message = 'Action timed out (sweeper)',
                    updated_at = now()
                WHERE status = 'executing'
                  AND updated_at < now() - interval '%s seconds'
                RETURNING id::text;
                """,
                (STUCK_TIMEOUT_SECONDS,),
            )
            rows = cur.fetchall()
        conn.commit()
    return len(rows)
