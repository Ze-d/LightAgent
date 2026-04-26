import asyncio
from typing import Any

from app.core.hooks import BaseRunnerHooks
from app.core.skill_registry import SkillRegistry


class SkillDispatcher:
    def __init__(
        self,
        skill_registry: SkillRegistry,
        hooks: BaseRunnerHooks | None = None,
    ):
        self.registry = skill_registry
        self.hooks = hooks

    def try_invoke(self, raw_input: str, agent_name: str = "agent") -> tuple[bool, Any]:
        parsed = self.registry.parse_slash_command(raw_input)
        if parsed is None:
            return (False, None)

        skill_name, args = parsed
        spec = self.registry.get(skill_name)
        if spec is None:
            return (False, None)

        if self.hooks:
            self.hooks.on_skill_invoke({
                "agent_name": agent_name,
                "skill_name": skill_name,
                "raw_input": raw_input,
            })

        try:
            if self.registry.is_async(skill_name):
                result = asyncio.run(
                    self.registry.call_async(skill_name, **args)
                )
            else:
                result = self.registry.call(skill_name, **args)

            if self.hooks:
                self.hooks.on_skill_end({
                    "agent_name": agent_name,
                    "skill_name": skill_name,
                    "arguments": args,
                    "result": result,
                    "status": "success",
                })

            return (True, str(result))
        except Exception as e:
            if self.hooks:
                self.hooks.on_skill_end({
                    "agent_name": agent_name,
                    "skill_name": skill_name,
                    "arguments": args,
                    "result": None,
                    "status": "error",
                    "error": str(e),
                })
            return (True, f"Skill error: {e}")
