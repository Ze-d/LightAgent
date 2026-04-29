from typing import Any

from app.configs.logger import logger
from app.core.hooks import BaseRunnerHooks


class LoggingHooks(BaseRunnerHooks):
    """Emit concise lifecycle logs without dumping user or tool payloads."""

    def _log(self, event_name: str, **fields: Any) -> None:
        pairs = " ".join(
            f"{key}={self._format_value(value)}"
            for key, value in fields.items()
            if value is not None
        )
        logger.info("hook event=%s %s", event_name, pairs)

    def _format_value(self, value: Any) -> str:
        text = str(value)
        return text.replace("\n", "\\n")

    def _argument_keys(self, event: dict[str, Any]) -> str:
        arguments = event.get("arguments")
        if not isinstance(arguments, dict) or not arguments:
            return ""
        return ",".join(sorted(str(key) for key in arguments.keys()))

    def on_run_start(self, event):
        self._log(
            "run_start",
            agent=event.get("agent_name"),
            model=event.get("model"),
            history_length=event.get("history_length"),
        )

    def on_run_end(self, event):
        self._log(
            "run_end",
            agent=event.get("agent_name"),
            success=event.get("success"),
            steps=event.get("steps"),
            error=event.get("error") or "",
        )

    def on_llm_start(self, event):
        self._log(
            "llm_start",
            agent=event.get("agent_name"),
            step=event.get("step"),
            model=event.get("model"),
            input_length=event.get("input_length"),
        )

    def on_llm_end(self, event):
        self._log(
            "llm_end",
            agent=event.get("agent_name"),
            step=event.get("step"),
            output_items_count=event.get("output_items_count"),
        )

    def on_tool_start(self, event):
        self._log(
            "tool_start",
            agent=event.get("agent_name"),
            step=event.get("step"),
            tool=event.get("tool_name"),
            argument_keys=self._argument_keys(event),
        )

    def on_tool_end(self, event):
        result = event.get("result")
        error = event.get("error")
        self._log(
            "tool_end",
            agent=event.get("agent_name"),
            step=event.get("step"),
            tool=event.get("tool_name"),
            status=event.get("status"),
            result_chars=len(str(result)) if result is not None else None,
            error_present=bool(error),
        )
