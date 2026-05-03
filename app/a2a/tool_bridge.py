from typing import Any

from pydantic import BaseModel, Field

from app.a2a.client import A2AClient, extract_text_from_send_response
from app.core.tool_registry import ToolRegistry
from app.obj.types import SideEffectPolicy, ToolSpec
from app.tools.validator import create_tool_spec


class RemoteA2AAgentInput(BaseModel):
    message: str = Field(..., description="Message to send to the remote A2A agent")
    context_id: str | None = Field(
        default=None,
        description="Optional remote A2A contextId for multi-turn continuity",
    )


def create_remote_a2a_agent_tool_spec(
    *,
    name: str,
    description: str,
    base_url: str,
    bearer_token: str | None = None,
    timeout: float = 30.0,
    side_effect_policy: SideEffectPolicy = "idempotent",
    client: A2AClient | None = None,
) -> ToolSpec:
    """Create a local tool that delegates one turn to a remote A2A agent."""

    def call_remote_agent(message: str, context_id: str | None = None) -> str:
        active_client = client or A2AClient(
            base_url,
            bearer_token=bearer_token,
            timeout=timeout,
        )
        try:
            response = active_client.send_text(
                message,
                context_id=context_id,
            )
            answer = extract_text_from_send_response(response)
            return answer or "Remote A2A agent returned no text."
        finally:
            if client is None:
                active_client.close()

    return create_tool_spec(
        name=name,
        description=description,
        model_cls=RemoteA2AAgentInput,
        handler=call_remote_agent,
        side_effect_policy=side_effect_policy,
    )


def register_remote_a2a_agent_tool(
    registry: ToolRegistry,
    *,
    name: str,
    description: str,
    base_url: str,
    bearer_token: str | None = None,
    timeout: float = 30.0,
    side_effect_policy: SideEffectPolicy = "idempotent",
    client: A2AClient | None = None,
) -> None:
    registry.register(
        create_remote_a2a_agent_tool_spec(
            name=name,
            description=description,
            base_url=base_url,
            bearer_token=bearer_token,
            timeout=timeout,
            side_effect_policy=side_effect_policy,
            client=client,
        )
    )


def remote_agent_tool_description(agent_name: str, agent_description: str) -> str:
    return (
        f"Delegate to remote A2A agent '{agent_name}'. "
        f"Remote agent description: {agent_description}"
    )
