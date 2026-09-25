"""The API lifespan owns no scheduling: Celery beat does (spec §7.2/§7.3).

The former in-process scheduler ticker was removed when orchestration moved
into the worker; the lifespan only configures tracing and logs who owns time.
"""

from fastapi.testclient import TestClient
from structlog.testing import capture_logs

import app.main as main


def test_lifespan_reports_that_beat_owns_scheduling() -> None:
    app = main.create_app()
    with capture_logs() as logs, TestClient(app) as client:
        assert client.get("/health").status_code == 200

    events = [e for e in logs if e.get("event") == "scheduling_owned_by_worker"]
    assert len(events) == 1
    assert "Celery beat" in events[0]["detail"]


def test_the_api_owns_no_scheduler_ticker() -> None:
    """The removed ticker must not linger: no scheduling helper, no interval."""
    assert not hasattr(main, "_scheduler_ticker")
    assert not hasattr(main, "SCHEDULER_TICK_SECONDS")
