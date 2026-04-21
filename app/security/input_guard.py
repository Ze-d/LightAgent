"""Input filtering middleware for security protection."""
import re
from app.core.middleware import BaseRunnerMiddleware, MiddlewareAbort
from app.obj.types import LLMContext


class InputGuardMiddleware(BaseRunnerMiddleware):
    def __init__(
        self,
        block_html: bool = True,
        block_scripts: bool = True,
        block_sql: bool = True,
        block_path_traversal: bool = True,
        max_length: int = 100000,
    ):
        self.block_html = block_html
        self.block_scripts = block_scripts
        self.block_sql = block_sql
        self.block_path_traversal = block_path_traversal
        self.max_length = max_length

        self._html_pattern = re.compile(
            r'<[^>]+>(?:.*?</[^>]+>)?',
            re.IGNORECASE | re.DOTALL
        )
        self._script_pattern = re.compile(
            r'(?:<script|javascript:|on\w+\s*=)',
            re.IGNORECASE
        )
        self._sql_pattern = re.compile(
            r'(?:union\s+select|select\s+.*\s+from|insert\s+into|'
            r'delete\s+from|drop\s+table|--|\/\*.*?\*\/)',
            re.IGNORECASE
        )
        self._path_pattern = re.compile(
            r'(?:\.\.\/|\.\.\\|%2e%2e|0x5c5c)',
            re.IGNORECASE
        )

    def before_llm(self, context: LLMContext) -> LLMContext:
        current_input = context.get("current_input")
        if not isinstance(current_input, list):
            return context

        sanitized = []
        for msg in current_input:
            if not isinstance(msg, dict):
                sanitized.append(msg)
                continue

            content = msg.get("content", "")
            if content:
                content = self._sanitize(content)
                if len(content) > self.max_length:
                    raise MiddlewareAbort(
                        f"Input too long ({len(content)} chars). Maximum: {self.max_length}"
                    )

            sanitized.append({**msg, "content": content})

        context["current_input"] = sanitized
        return context

    def _sanitize(self, text: str) -> str:
        if self.block_html:
            text = self._html_pattern.sub('[HTML_REMOVED]', text)
        if self.block_scripts:
            text = self._script_pattern.sub('[SCRIPT_REMOVED]', text)
        if self.block_sql:
            text = self._sql_pattern.sub('[SQL_REMOVED]', text)
        if self.block_path_traversal:
            text = self._path_pattern.sub('[PATH_REMOVED]', text)
        return text
