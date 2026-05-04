from app.a2a.schemas import (
    A2A_JSONRPC_INTERFACE_URL,
    A2A_PROTOCOL_VERSION,
    A2A_REST_INTERFACE_URL,
    TEXT_PLAIN,
    AgentCapabilities,
    AgentCard,
    AgentExtension,
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
BEARER_SECURITY_SCHEME_NAME = "bearerAuth"
A2A_EXTENDED_CARD_EXTENSION_URI = "https://a2a-protocol.org/extensions/extended-card"


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _skill_id(name: str) -> str:
    return name.replace("_", "-").replace(" ", "-").lower()


def build_agent_skills(
    skill_registry: SkillRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    *,
    include_tool_details: bool = False,
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
            if include_tool_details:
                for tool in tool_registry.get_openai_tools():
                    skills.append(
                        AgentSkill(
                            id=f"tool-{_skill_id(tool['name'])}",
                            name=tool["name"],
                            description=tool["description"],
                            tags=["tool"],
                            inputModes=[TEXT_PLAIN],
                            outputModes=[TEXT_PLAIN],
                        )
                    )
            else:
                skills.append(
                    AgentSkill(
                        id="registered-tools",
                        name="Registered tool use",
                        description=(
                            "Use registered local tools when appropriate. "
                            f"Available tools: {', '.join(tool_names)}."
                        ),
                        tags=["tools"],
                        inputModes=[TEXT_PLAIN],
                        outputModes=[TEXT_PLAIN],
                    )
                )

    return skills


def build_bearer_security() -> tuple[dict[str, dict], list[dict[str, list[str]]]]:
    return (
        {
            BEARER_SECURITY_SCHEME_NAME: {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "opaque",
            }
        },
        [{BEARER_SECURITY_SCHEME_NAME: []}],
    )


def build_agent_card(
    public_base_url: str,
    *,
    agent_name: str,
    version: str,
    description: str = DEFAULT_AGENT_DESCRIPTION,
    provider_name: str = "MyAgent",
    documentation_url: str | None = None,
    icon_url: str | None = None,
    extended_card_enabled: bool = False,
    security_schemes: dict[str, dict] | None = None,
    security_requirements: list[dict[str, list[str]]] | None = None,
    include_tool_details: bool = False,
    skill_registry: SkillRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AgentCard:
    jsonrpc_url = _join_url(public_base_url, A2A_JSONRPC_INTERFACE_URL)
    rest_url = _join_url(public_base_url, A2A_REST_INTERFACE_URL)
    resolved_security_schemes = dict(security_schemes or {})
    resolved_security_requirements = list(security_requirements or [])
    return AgentCard(
        name=agent_name,
        description=description,
        version=version,
        provider=AgentProvider(
            organization=provider_name,
            url=public_base_url.rstrip("/") or None,
        ),
        supportedInterfaces=[
            AgentInterface(
                url=jsonrpc_url,
                protocolBinding="JSONRPC",
                protocolVersion=A2A_PROTOCOL_VERSION,
            ),
            AgentInterface(
                url=rest_url,
                protocolBinding="HTTP+JSON",
                protocolVersion=A2A_PROTOCOL_VERSION,
            )
        ],
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            extendedAgentCard=extended_card_enabled,
            extensions=(
                [
                    AgentExtension(
                        uri=A2A_EXTENDED_CARD_EXTENSION_URI,
                        description="Authenticated extended Agent Card is available.",
                        required=False,
                    )
                ]
                if extended_card_enabled
                else []
            ),
        ),
        securitySchemes=resolved_security_schemes,
        securityRequirements=resolved_security_requirements,
        defaultInputModes=[TEXT_PLAIN],
        defaultOutputModes=[TEXT_PLAIN],
        skills=build_agent_skills(
            skill_registry=skill_registry,
            tool_registry=tool_registry,
            include_tool_details=include_tool_details,
        ),
        documentationUrl=documentation_url,
        iconUrl=icon_url,
    )


def build_extended_agent_card(
    public_base_url: str,
    *,
    agent_name: str,
    version: str,
    description: str = DEFAULT_AGENT_DESCRIPTION,
    provider_name: str = "MyAgent",
    documentation_url: str | None = None,
    icon_url: str | None = None,
    skill_registry: SkillRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AgentCard:
    security_schemes, security_requirements = build_bearer_security()
    return build_agent_card(
        public_base_url=public_base_url,
        agent_name=agent_name,
        version=version,
        description=description,
        provider_name=provider_name,
        documentation_url=documentation_url,
        icon_url=icon_url,
        extended_card_enabled=True,
        security_schemes=security_schemes,
        security_requirements=security_requirements,
        include_tool_details=True,
        skill_registry=skill_registry,
        tool_registry=tool_registry,
    )
