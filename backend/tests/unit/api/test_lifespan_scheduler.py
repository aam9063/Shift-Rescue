"""The app lifespan drives scheduled rescue work (timeouts, deadlines).

Until the Celery beat schedule lands (see the deploy feature), the API process
ticks the in-memory scheduler so wave timeouts and deadlines actually fire.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.workers.scheduler import SimScheduler


class StubService:
    def __init__(self, scheduler: SimScheduler) -> None:
        self.scheduler = scheduler


def test_lifespan_ticker_runs_due_jobs(monkeypatch) -> None:
    executed: list[dict] = []
    scheduler = SimScheduler()

    async def handler(payload: dict) -> None:
        executed.append(payload)

    scheduler.register("wave_timeout", handler)
    scheduler.schedule(
        datetime.now(UTC) - timedelta(seconds=1), "wave_timeout", {"case_id": "case_1"}
    )

    import app.api.webhooks_twilio as webhooks
    import app.main as main

    monkeypatch.setattr(main, "SCHEDULER_TICK_SECONDS", 0.05)
    monkeypatch.setattr(webhooks, "get_twilio_service", lambda: StubService(scheduler))

    app = main.create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        # The ticker runs in the background; give it a few cycles.
        for _ in range(100):
            if executed:
                break
            import time

            time.sleep(0.05)

    assert executed == [{"case_id": "case_1"}]
    assert scheduler.pending_count() == 0


def test_lifespan_ticker_survives_a_failing_job(monkeypatch) -> None:
    """A broken handler must not kill the ticker."""
    scheduler = SimScheduler()
    attempts: list[int] = []

    async def boom(payload: dict) -> None:
        attempts.append(1)
        raise RuntimeError("handler exploded")

    scheduler.register("wave_timeout", boom)
    scheduler.schedule(datetime.now(UTC) - timedelta(seconds=1), "wave_timeout", {})

    import app.api.webhooks_twilio as webhooks
    import app.main as main

    monkeypatch.setattr(main, "SCHEDULER_TICK_SECONDS", 0.05)
    monkeypatch.setattr(webhooks, "get_twilio_service", lambda: StubService(scheduler))

    app = main.create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        for _ in range(40):
            import time

            time.sleep(0.05)

    assert attempts  # it ran (and raised), the app stayed up
