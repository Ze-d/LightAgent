from app.a2a.schemas import (
    A2A_PROTOCOL_VERSION,
    A2A_REST_INTERFACE_URL,
    TEXT_PLAIN,
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
)
from app.core.skill_registry import SkillRegistry
from app.core.tool_registry import ToolRegistry


DEFAULT_AGENT_DESCRIPTION = (
    "MyAgent is a tool-aware conversational agent with session memory, "
    "checkpoint recovery, and streaming execution events."
)


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _skill_id(name: str) -> str:
    return name.replace("_", "-").replace(" ", "-").lower()


def build_agent_skills(
    skill_registry: SkillRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
) -> list[AgentSkill]:
    skills: list[AgentSkill] = [
        AgentSkill(
            id="general-assistant",
            name="General assistant",
            description=(
                "Answer user questions and coordinate local tools when they are "
                "needed to complete the task."
            ),
            tags=["chat", "reasoning", "tools"],
            examples=["Summarize this project and suggest the next implementation step."],
            inputModes=[TEXT_PLAIN],
            outputModes=[TEXT_PLAIN],
        )
    ]

    if skill_registry is not None:
        for spec in skill_registry.get_skill_schemas():
            skills.append(
                AgentSkill(
                    id=f"slash-{_skill_id(spec['name'])}",
                    name=spec["name"],
                    description=spec["description"],
                    tags=["slash-skill"],
                    inputModes=[TEXT_PLAIN],
                    outputModes=[TEXT_PLAIN],
                )
            )

    if tool_registry is not None:
        tool_names = tool_registry.list_names()
        if tool_names:
            skills.append(
                AgentSkill(
                    id="registered-tools",
                    name="Registered tool use",
                    description=(
                        "Use registered local tools when appropriate. Available "
                        f"tools: {', '.join(tool_names)}."
                    ),
                    tags=["tools"],
                    inputModes=[TEXT_PLAIN],
                    outputModes=[TEXT_PLAIN],
                )
            )

    return skills


def build_agent_card(
    public_base_url: str,
    *,
    agent_name: str,
    version: str,
    description: str = DEFAULT_AGENT_DESCRIPTION,
    provider_name: str = "MyAgent",
    documentation_url: str | None = None,
    skill_registry: SkillRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AgentCard:
    interface_url = _join_url(public_base_url, A2A_REST_INTERFACE_URL)
    return AgentCard(
        name=agent_name,
        description=description,
        version=version,
        url=interface_url,
        provider=AgentProvider(
            organization=provider_name,
            url=public_base_url.rstrip("/") or None,
        ),
        protocolVersion=A2A_PROTOCOL_VERSION,
        supportedInterfaces=[
            AgentInterface(
                url=interface_url,
                protocolBinding="HTTP+JSON",
                protocolVersion=A2A_PROTOCOL_VERSION,
            )
        ],
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            extendedAgentCard=False,
        ),
        defaultInputModes=[TEXT_PLAIN],
        defaultOutputModes=[TEXT_PLAIN],
        skills=build_agent_skills(
            skill_registry=skill_registry,
            tool_registry=tool_registry,
        ),
        documentationUrl=documentation_url,
    )
