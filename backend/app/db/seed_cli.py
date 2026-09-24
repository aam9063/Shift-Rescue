"""CLI entrypoint: `uv run python -m app.db.seed`.

Runs pending migrations (alembic upgrade head) and seeds the demo data.
"""

import asyncio
import subprocess
import sys


async def _run_seed() -> None:
    from app.db.seed import seed_database
    from app.db.session import create_engine_and_session

    engine, session_factory = create_engine_and_session()
    async with session_factory() as session:
        await seed_database(session)
    await engine.dispose()


def main() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    asyncio.run(_run_seed())
    print("Seed complete: La Terraza del Puerto + demo manager.")


if __name__ == "__main__":
    main()
