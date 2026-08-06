"""MDES Apple Pay provisioning - live synthetic log stream.

Continuously emits correlated MDES provisioning logs (APIGW nginx access,
PCF wallet-api, EPT web, token resolution) into Datadog, so both recreated
dashboards stay populated on rolling 15/30-minute windows like the Splunk
originals.

Run under `op run` so DD_API_KEY / DD_SITE are injected (see `make mc-apple-logs`):
    python run.py                 # default cadence
    MC_TX_PER_CYCLE=80 MC_CYCLE_SEC=10 python run.py
"""
from __future__ import annotations

import logging
import os
import time

from dd_log_emitter import LogEmitter
from event_model import build_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mc-mdes")

_TX_PER_CYCLE = int(os.getenv("MC_TX_PER_CYCLE", "60"))
_CYCLE_SEC = float(os.getenv("MC_CYCLE_SEC", "10"))
_ERROR_RATE = float(os.getenv("MC_ERROR_RATE", "0.10"))


def main() -> None:
    emitter = LogEmitter()
    log.info(
        "MDES log stream to Datadog (%s): %d tx/cycle, every %.0fs, err_rate=%.2f",
        emitter.site, _TX_PER_CYCLE, _CYCLE_SEC, _ERROR_RATE,
    )
    while True:
        start = time.monotonic()
        logs = build_cycle(transactions=_TX_PER_CYCLE, error_rate=_ERROR_RATE)
        n = emitter.submit(logs)
        log.info("emitted %d logs (%d transactions)", n, _TX_PER_CYCLE)
        time.sleep(max(0.0, _CYCLE_SEC - (time.monotonic() - start)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("stopped")
