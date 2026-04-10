from app.core.hooks import BaseRunnerHooks
from app.configs.logger import logger


class LoggingHooks(BaseRunnerHooks):
    def on_run_start(self, event):
        logger.info(f"[run_start] {event}")

    def on_run_end(self, event):
        logger.info(f"[run_end] {event}")

    def on_llm_start(self, event):
        logger.info(f"[llm_start] {event}")

    def on_llm_end(self, event):
        logger.info(f"[llm_end] {event}")

    def on_tool_start(self, event):
        logger.info(f"[tool_start] {event}")

    def on_tool_end(self, event):
        logger.info(f"[tool_end] {event}")