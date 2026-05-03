"""A2A protocol boundary for MyAgent.

This package owns A2A-facing schemas, discovery metadata, and HTTP routes.
The core runner stays protocol-agnostic.
"""

from app.a2a.agent_card import build_agent_card, build_extended_agent_card
from app.a2a.client import A2AClient
from app.a2a.routes import build_a2a_router
from app.a2a.tool_bridge import (
    create_remote_a2a_agent_tool_spec,
    register_remote_a2a_agent_tool,
)

__all__ = [
    "A2AClient",
    "build_agent_card",
    "build_extended_agent_card",
    "build_a2a_router",
    "create_remote_a2a_agent_tool_spec",
    "register_remote_a2a_agent_tool",
]
