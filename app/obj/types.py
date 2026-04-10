from typing import Any, Callable, Literal, TypedDict


Role = Literal["system", "user", "assistant"]


class ChatMessage(TypedDict):
    role: Role
    content: str


class FunctionCallOutput(TypedDict):
    type: Literal["function_call_output"]
    call_id: str
    output: str


class ToolSpec(TypedDict):
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]


class ToolCallEvent(TypedDict, total=False):
    agent_name: str
    step: int
    tool_name: str
    arguments: dict[str, Any]
    result: str
    status: Literal["start", "success", "error"]
    error: str


class AgentRunResult(TypedDict):
    answer: str
    success: bool
    steps: int
    tool_events: list[ToolCallEvent]
    error: str | None


class RunStartEvent(TypedDict):
    agent_name: str
    model: str
    history_length: int


class RunEndEvent(TypedDict):
    agent_name: str
    success: bool
    steps: int
    error: str | None


class LLMStartEvent(TypedDict):
    agent_name: str
    step: int
    model: str
    input_length: int


class LLMEndEvent(TypedDict):
    agent_name: str
    step: int
    output_items_count: int

class LLMContext(TypedDict):
    agent_name: str
    model: str
    step: int
    current_input: list[dict] | str


class ToolContext(TypedDict):
    agent_name: str
    step: int
    tool_name: str
    arguments: dict[str, Any]