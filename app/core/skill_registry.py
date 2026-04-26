import inspect
from typing import Any

from app.obj.types import SkillSpec


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec) -> None:
        name = spec["name"]
        if name in self._skills:
            raise ValueError(f"Skill already registered: {name}")
        self._skills[name] = spec

    def get(self, name: str) -> SkillSpec | None:
        return self._skills.get(name)

    def get_handler(self, name: str):
        spec = self._skills.get(name)
        return None if spec is None else spec["handler"]

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def get_skill_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec.get("parameters"),
            }
            for spec in self._skills.values()
        ]

    def call(self, name: str, **kwargs: Any) -> Any:
        handler = self.get_handler(name)
        if handler is None:
            raise ValueError(f"Unknown skill: {name}")
        return handler(**kwargs)

    async def call_async(self, name: str, **kwargs: Any) -> Any:
        handler = self.get_handler(name)
        if handler is None:
            raise ValueError(f"Unknown skill: {name}")
        if inspect.iscoroutinefunction(handler):
            return await handler(**kwargs)
        return handler(**kwargs)

    def is_async(self, name: str) -> bool:
        handler = self.get_handler(name)
        return handler is not None and inspect.iscoroutinefunction(handler)

    def parse_slash_command(self, raw_input: str) -> tuple[str, dict[str, Any]] | None:
        text = raw_input.strip()
        if not text.startswith("/"):
            return None

        parts = text[1:].split(None, 1)
        skill_name = parts[0]

        args: dict[str, Any] = {}
        if len(parts) > 1:
            for pair in parts[1].split():
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    args[key.strip()] = value.strip()

        return (skill_name, args)
