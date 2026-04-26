"""Default skill registration."""
from app.core.skill_registry import SkillRegistry
from app.skills.simplify_skill import simplify
from app.skills.loop_skill import loop


def build_default_skills() -> SkillRegistry:
    registry = SkillRegistry()

    registry.register({
        "name": "simplify",
        "description": "Refactor code for readability, quality, and efficiency",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The code to simplify"},
                "target": {
                    "type": "string",
                    "description": "Target goal: readability, performance, or safety",
                    "enum": ["readability", "performance", "safety"],
                },
            },
            "required": ["code"],
        },
        "handler": simplify,
    })

    registry.register({
        "name": "loop",
        "description": "Run a command on a recurring interval",
        "parameters": {
            "type": "object",
            "properties": {
                "interval": {"type": "string", "description": "Time interval (e.g., 5m, 10s, 1h)"},
                "command": {"type": "string", "description": "The command to run"},
                "max_rounds": {"type": "integer", "description": "Maximum number of iterations"},
            },
            "required": ["interval", "command"],
        },
        "handler": loop,
    })

    return registry
