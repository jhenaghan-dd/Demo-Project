"""MDES synthetic logs to Datadog Logs Intake.

Posts the correlated log bundles from ``event_model`` to the v2 logs intake
(``https://http-intake.logs.<site>/api/v2/logs``). Reuses the toolkit's
``DatadogAPIClient`` only to resolve the site + API key (retry/site/auth
policy lives there); the intake host differs from the app API host, so the POST
is done here.

Credentials come from the process environment (``DD_API_KEY`` / ``DD_SITE``),
populated by ``op run`` in the Make target - per the repo secret policy, no
plain secrets on disk.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import time
from typing import Any, Dict, List

import requests

from dd_demo_toolkit.utils.dd_api import DatadogAPIClient

log = logging.getLogger("mc-mdes-emitter")

# Site domain to logs intake base. Mirrors DatadogAPIClient.SITE_MAPPING but for
# the http-intake.logs.* host family.
_LOGS_INTAKE = {
    "datadoghq.com": "https://http-intake.logs.datadoghq.com",
    "us3.datadoghq.com": "https://http-intake.logs.us3.datadoghq.com",
    "us5.datadoghq.com": "https://http-intake.logs.us5.datadoghq.com",
    "datadoghq.eu": "https://http-intake.logs.datadoghq.eu",
    "ap1.datadoghq.com": "https://http-intake.logs.ap1.datadoghq.com",
    "ddog-gov.com": "https://http-intake.logs.ddog-gov.com",
}

# Intake accepts up to 1000 logs / 5MB per request; keep batches comfortably under.
_BATCH = 500
_TIMEOUT = 15


class LogEmitter:
    def __init__(self) -> None:
        # DatadogAPIClient validates + resolves DD_API_KEY / DD_SITE (fail loud).
        client = DatadogAPIClient()
        self.api_key = client.api_key
        self.site = client.site
        if self.site not in _LOGS_INTAKE:
            raise ValueError(f"No logs-intake host mapping for DD_SITE={self.site}")
        self.url = f"{_LOGS_INTAKE[self.site]}/api/v2/logs"
        self._session = requests.Session()

    def submit(self, logs: List[Dict[str, Any]]) -> int:
        """POST logs in batches. Returns the number successfully accepted."""
        accepted = 0
        for i in range(0, len(logs), _BATCH):
            batch = logs[i:i + _BATCH]
            body = gzip.compress(json.dumps(batch).encode("utf-8"))
            try:
                resp = self._session.post(
                    self.url,
                    # No ddsource/service query params - those OVERRIDE the
                    # per-log service/ddsource in the body, collapsing apigw /
                    # wallet-api / ept-web into one service. Body values win.
                    data=body,
                    headers={
                        "DD-API-KEY": self.api_key,
                        "Content-Type": "application/json",
                        "Content-Encoding": "gzip",
                    },
                    timeout=_TIMEOUT,
                )
                if resp.status_code in (200, 202):
                    accepted += len(batch)
                else:
                    log.warning("intake %s: %s", resp.status_code, resp.text[:200])
            except requests.RequestException as e:
                log.warning("intake POST failed: %s", e)
        return accepted
