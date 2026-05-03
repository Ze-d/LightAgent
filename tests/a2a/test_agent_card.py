from app.a2a.agent_card import build_agent_card, build_extended_agent_card
from app.a2a.schemas import A2A_PROTOCOL_VERSION
from app.core.skill_registry import SkillRegistry
from app.core.tool_registry import ToolRegistry


def test_build_agent_card_uses_aliases_and_public_url():
    card = build_agent_card(
        public_base_url="http://example.test/",
        agent_name="chat-agent",
        version="1.2.3",
    )

    payload = card.model_dump(by_alias=True, exclude_none=True)

    assert payload["name"] == "chat-agent"
    assert payload["version"] == "1.2.3"
    assert payload["url"] == "http://example.test/a2a/v1"
    assert payload["protocolVersion"] == A2A_PROTOCOL_VERSION
    assert payload["supportedInterfaces"] == [
        {
            "url": "http://example.test/a2a/v1",
            "protocolBinding": "HTTP+JSON",
            "protocolVersion": A2A_PROTOCOL_VERSION,
        }
    ]
    assert payload["capabilities"]["streaming"] is True
    assert payload["capabilities"]["extendedAgentCard"] is False
    assert payload["securitySchemes"] == {}
    assert payload["securityRequirements"] == []
    assert payload["defaultInputModes"] == ["text/plain"]
    assert payload["defaultOutputModes"] == ["text/plain"]


def test_build_agent_card_exposes_local_skill_and_tool_capabilities():
    skill_registry = SkillRegistry()
    skill_registry.register({
        "name": "summarize",
        "description": "Summarize supplied text",
        "parameters": None,
        "handler": lambda: "ok",
    })
    tool_registry = ToolRegistry()
    tool_registry.register({
        "name": "lookup",
        "description": "Lookup data",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: "ok",
    })

    card = build_agent_card(
        public_base_url="http://localhost:8000",
        agent_name="chat-agent",
        version="0.1.0",
        skill_registry=skill_registry,
        tool_registry=tool_registry,
    )

    skill_ids = {skill.id for skill in card.skills}
    skill_descriptions = {skill.id: skill.description for skill in card.skills}

    assert "general-assistant" in skill_ids
    assert "slash-summarize" in skill_ids
    assert "registered-tools" in skill_ids
    assert "lookup" in skill_descriptions["registered-tools"]


def test_build_agent_card_marks_extended_card_capability():
    card = build_agent_card(
        public_base_url="http://localhost:8000",
        agent_name="chat-agent",
        version="0.1.0",
        documentation_url="http://localhost:8000/docs/a2a",
        icon_url="http://localhost:8000/static/icon.png",
        extended_card_enabled=True,
    )
    payload = card.model_dump(by_alias=True, exclude_none=True)

    assert payload["capabilities"]["extendedAgentCard"] is True
    assert payload["capabilities"]["extensions"][0]["uri"]
    assert payload["documentationUrl"] == "http://localhost:8000/docs/a2a"
    assert payload["iconUrl"] == "http://localhost:8000/static/icon.png"


def test_build_extended_agent_card_exposes_tool_level_skills_and_bearer_auth():
    tool_registry = ToolRegistry()
    tool_registry.register({
        "name": "lookup",
        "description": "Lookup data",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: "ok",
    })

    card = build_extended_agent_card(
        public_base_url="http://localhost:8000",
        agent_name="chat-agent",
        version="0.1.0",
        tool_registry=tool_registry,
    )
    payload = card.model_dump(by_alias=True, exclude_none=True)
    skill_ids = {skill["id"] for skill in payload["skills"]}

    assert payload["capabilities"]["extendedAgentCard"] is True
    assert payload["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert payload["securityRequirements"] == [{"bearerAuth": []}]
    assert "tool-lookup" in skill_ids
