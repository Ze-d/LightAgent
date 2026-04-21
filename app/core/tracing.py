"""OpenTelemetry tracing setup and utilities for agent observability."""
import os
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Status, StatusCode

from app.configs.logger import logger


_tracer: trace.Tracer | None = None


def init_tracing(service_name: str = "myagent") -> trace.Tracer:
    """Initialize OpenTelemetry tracing.

    Configures a tracer provider with batch export to OTLP endpoint.
    Falls back to console export if OTLP endpoint is not configured.

    Args:
        service_name: Name of the service for resource identification

    Returns:
        Configured tracer instance
    """
    global _tracer

    if _tracer is not None:
        return _tracer

    resource = Resource(attributes={
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })

    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"Tracing enabled with OTLP endpoint: {otlp_endpoint}")
        except ImportError:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.warning("OTLP exporter not available, using console export")
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("Tracing enabled with console export (set OTEL_EXPORTER_OTLP_ENDPOINT for OTLP)")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)
    return _tracer


def get_tracer() -> trace.Tracer:
    """Get the initialized tracer, initializing if necessary."""
    global _tracer
    if _tracer is None:
        return init_tracing()
    return _tracer


class AgentSpan:
    """Context manager for creating agent execution spans with nested structure.

    Creates a hierarchy:
        agent_run
            └── step_{n}
                    ├── llm_call
                    └── tool_{name}
    """

    def __init__(self, tracer: trace.Tracer):
        self._tracer = tracer
        self._root_span: Any = None
        self._current_span: Any = None

    def start_run_span(
        self,
        agent_name: str,
        model: str,
        max_steps: int,
        session_id: str | None = None,
    ) -> "AgentSpan":
        """Start the root agent run span."""
        self._root_span = self._tracer.start_span(
            "agent_run",
            attributes={
                "agent.name": agent_name,
                "agent.model": model,
                "agent.max_steps": max_steps,
                "session.id": session_id or "",
            },
        )
        self._current_span = self._root_span
        return self

    def start_step_span(self, step: int) -> "AgentSpan":
        """Start a step span as child of current."""
        if self._root_span is None:
            raise RuntimeError("Must call start_run_span first")
        ctx = trace.set_span_in_context(self._current_span)
        self._current_span = self._tracer.start_span(
            f"step_{step}",
            context=ctx,
            attributes={"step": step},
        )
        return self

    def start_llm_span(self, input_length: int) -> "AgentSpan":
        """Start an LLM call span as child of current step."""
        ctx = trace.set_span_in_context(self._current_span)
        self._current_span = self._tracer.start_span(
            "llm_call",
            context=ctx,
            attributes={
                "llm.input_length": input_length,
            },
        )
        return self

    def start_tool_span(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> "AgentSpan":
        """Start a tool execution span as child of current step."""
        ctx = trace.set_span_in_context(self._current_span)
        self._current_span = self._tracer.start_span(
            f"tool_{tool_name}",
            context=ctx,
            attributes={
                "tool.name": tool_name,
                "tool.arguments": str(arguments) if arguments else "",
            },
        )
        return self

    def end_current_span(self, error: Exception | None = None) -> None:
        """End the current span, optionally setting error status."""
        if self._current_span is None:
            return
        if error:
            self._current_span.set_status(Status(StatusCode.ERROR, str(error)))
            self._current_span.record_exception(error)
        else:
            self._current_span.set_status(Status(StatusCode.OK))
        self._current_span.end()
        self._current_span = self._current_span.parent

    def end_all(self, error: Exception | None = None) -> None:
        """End all spans, starting from root."""
        if self._root_span is not None:
            if error:
                self._root_span.set_status(Status(StatusCode.ERROR, str(error)))
                self._root_span.record_exception(error)
            else:
                self._root_span.set_status(Status(StatusCode.OK))
            self._root_span.end()
            self._root_span = None
            self._current_span = None

    def __enter__(self) -> "AgentSpan":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.end_all(error=exc_val)
