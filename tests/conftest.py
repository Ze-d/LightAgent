from pathlib import Path
from uuid import uuid4

import pytest

import app.core.runner as runner_module


def pytest_configure() -> None:
    # Unit tests do not assert OpenTelemetry behavior. Disabling tracing here
    # keeps pytest output deterministic and avoids async exporter shutdown noise.
    runner_module.get_tracer = lambda: None


@pytest.fixture
def sqlite_db_path():
    path = Path("test-runtime") / f"pytest-{uuid4().hex}.sqlite3"
    path.parent.mkdir(exist_ok=True)
    yield path
    for candidate in (
        path,
        path.with_name(f"{path.name}-wal"),
        path.with_name(f"{path.name}-shm"),
    ):
        candidate.unlink(missing_ok=True)
