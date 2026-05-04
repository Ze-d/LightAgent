from typing import Any, Callable, Literal, NotRequired, TypedDict


Role = Literal["system", "user", "assistant"]


class ChatMessage(TypedDict):
    """One OpenAI-compatible chat history message."""

    role: Role
    content: str


class FunctionCallOutput(TypedDict):
    """Tool result item sent back to the model after a function_call."""

    type: Literal["function_call_output"]
    call_id: str
    output: str


SideEffectPolicy = Literal["read_only", "idempotent", "non_idempotent"]


class ToolSpec(TypedDict, total=False):
    """Registered tool metadata and executable handler."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    side_effect_policy: SideEffectPolicy


class ToolCallEvent(TypedDict, total=False):
    """Lifecycle event emitted after a tool starts, succeeds, or fails."""

    agent_name: str
    step: int
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: str
    status: Literal["start", "success", "error"]
    error: str


class AgentRunResult(TypedDict):
    """Structured result returned by AgentRunner.run."""

    answer: str
    success: bool
    steps: int
    tool_events: list[ToolCallEvent]
    error: str | None
    response_id: NotRequired[str | None]


class RunStartEvent(TypedDict):
    """Hook payload emitted when a runner turn starts."""

    agent_name: str
    model: str
    history_length: int


class RunEndEvent(TypedDict):
    """Hook payload emitted when a runner turn reaches a terminal state."""

    agent_name: str
    success: bool
    steps: int
    error: str | None


class LLMStartEvent(TypedDict):
    """Hook payload emitted immediately before an LLM call."""

    agent_name: str
    step: int
    model: str
    input_length: int


class LLMEndEvent(TypedDict):
    """Hook payload emitted immediately after an LLM response."""

    agent_name: str
    step: int
    output_items_count: int


class LLMContext(TypedDict):
    """Mutable middleware context for the next LLM call."""

    agent_name: str
    model: str
    step: int
    current_input: list[dict] | str


class ToolContext(TypedDict):
    """Middleware context for a pending tool call."""

    agent_name: str
    step: int
    tool_name: str
    arguments: dict[str, Any]


# Skill types
class SkillSpec(TypedDict):
    """Registered skill metadata and executable handler."""

    name: str
    description: str
    parameters: dict[str, Any] | None
    handler: Callable[..., Any]


class SkillInvokeEvent(TypedDict):
    """Hook payload emitted when a skill command is invoked."""

    agent_name: str
    skill_name: str
    raw_input: str


class SkillCallEvent(TypedDict, total=False):
    """Lifecycle event emitted after a skill starts, succeeds, or fails."""

    agent_name: str
    skill_name: str
    arguments: dict[str, Any]
    result: Any
    status: Literal["start", "success", "error"]
    error: str
