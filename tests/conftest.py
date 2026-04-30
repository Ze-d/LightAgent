import app.core.runner as runner_module


def pytest_configure() -> None:
    # Unit tests do not assert OpenTelemetry behavior. Disabling tracing here
    # keeps pytest output deterministic and avoids async exporter shutdown noise.
    runner_module.get_tracer = lambda: None
