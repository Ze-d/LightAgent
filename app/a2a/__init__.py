"""A2A protocol boundary for MyAgent.

This package owns A2A-facing schemas, discovery metadata, and HTTP routes.
The core runner stays protocol-agnostic.
"""

from app.a2a.agent_card import build_agent_card
from app.a2a.routes import build_a2a_router

__all__ = ["build_agent_card", "build_a2a_router"]
