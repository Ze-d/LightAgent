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