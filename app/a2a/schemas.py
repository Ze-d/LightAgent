from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


A2A_PROTOCOL_VERSION = "1.0"
A2A_REST_INTERFACE_URL = "/a2a/v1"
TEXT_PLAIN = "text/plain"


class A2ABaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        use_enum_values=True,
    )


class AgentInterface(A2ABaseModel):
    url: str
    protocol_binding: Literal["HTTP+JSON"] = Field(alias="protocolBinding")
    protocol_version: str = Field(alias="protocolVersion")


class AgentCapabilities(A2ABaseModel):
    streaming: bool = False
    push_notifications: bool = Field(default=False, alias="pushNotifications")
    extended_agent_card: bool = Field(default=False, alias="extendedAgentCard")


class AgentProvider(A2ABaseModel):
    organization: str
    url: str | None = None


class AgentSkill(A2ABaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=list, alias="inputModes")
    output_modes: list[str] = Field(default_factory=list, alias="outputModes")


class AgentCard(A2ABaseModel):
    name: str
    description: str
    version: str
    url: str
    provider: AgentProvider | None = None
    protocol_version: str = Field(alias="protocolVersion")
    supported_interfaces: list[AgentInterface] = Field(alias="supportedInterfaces")
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    default_input_modes: list[str] = Field(alias="defaultInputModes")
    default_output_modes: list[str] = Field(alias="defaultOutputModes")
    skills: list[AgentSkill] = Field(default_factory=list)
    documentation_url: str | None = Field(default=None, alias="documentationUrl")


class A2ARole(str, Enum):
    user = "ROLE_USER"
    agent = "ROLE_AGENT"


class TaskState(str, Enum):
    submitted = "TASK_STATE_SUBMITTED"
    working = "TASK_STATE_WORKING"
    input_required = "TASK_STATE_INPUT_REQUIRED"
    completed = "TASK_STATE_COMPLETED"
    failed = "TASK_STATE_FAILED"
    canceled = "TASK_STATE_CANCELED"
    rejected = "TASK_STATE_REJECTED"
    auth_required = "TASK_STATE_AUTH_REQUIRED"


class Part(A2ABaseModel):
    text: str | None = None
    data: Any | None = None
    raw: str | None = None
    url: str | None = None
    media_type: str | None = Field(default=None, alias="mediaType")
    filename: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_one_payload(self) -> "Part":
        payloads = [self.text, self.data, self.raw, self.url]
        if sum(item is not None for item in payloads) != 1:
            raise ValueError("A2A part must contain exactly one payload")
        return self


class Message(A2ABaseModel):
    role: A2ARole
    parts: list[Part]
    message_id: str | None = Field(default=None, alias="messageId")
    task_id: str | None = Field(default=None, alias="taskId")
    context_id: str | None = Field(default=None, alias="contextId")
    metadata: dict[str, Any] = Field(default_factory=dict)
    extensions: list[str] = Field(default_factory=list)
    reference_task_ids: list[str] = Field(
        default_factory=list,
        alias="referenceTaskIds",
    )


class Artifact(A2ABaseModel):
    artifact_id: str = Field(alias="artifactId")
    parts: list[Part]
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatus(A2ABaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: str | None = None


class Task(A2ABaseModel):
    id: str
    context_id: str = Field(alias="contextId")
    status: TaskStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    history: list[Message] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatusUpdateEvent(A2ABaseModel):
    task_id: str = Field(alias="taskId")
    context_id: str = Field(alias="contextId")
    status: TaskStatus
    final: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskArtifactUpdateEvent(A2ABaseModel):
    task_id: str = Field(alias="taskId")
    context_id: str = Field(alias="contextId")
    artifact: Artifact
    append: bool = False
    last_chunk: bool = Field(default=True, alias="lastChunk")
    metadata: dict[str, Any] = Field(default_factory=dict)


StreamEvent = TaskStatusUpdateEvent | TaskArtifactUpdateEvent


class SendMessageConfiguration(A2ABaseModel):
    accepted_output_modes: list[str] = Field(
        default_factory=list,
        alias="acceptedOutputModes",
    )
    task_push_notification_config: dict[str, Any] | None = Field(
        default=None,
        alias="taskPushNotificationConfig",
    )
    history_length: int | None = Field(default=None, alias="historyLength")
    return_immediately: bool = Field(default=False, alias="returnImmediately")


class SendMessageRequest(A2ABaseModel):
    tenant: str | None = None
    message: Message
    configuration: SendMessageConfiguration = Field(
        default_factory=SendMessageConfiguration,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class SendMessageResponse(A2ABaseModel):
    task: Task | None = None
    message: Message | None = None

    @model_validator(mode="after")
    def require_one_response(self) -> "SendMessageResponse":
        if (self.task is None) == (self.message is None):
            raise ValueError("SendMessageResponse must contain task or message")
        return self


class StreamResponse(A2ABaseModel):
    task: Task | None = None
    message: Message | None = None
    status_update: TaskStatusUpdateEvent | None = Field(
        default=None,
        alias="statusUpdate",
    )
    artifact_update: TaskArtifactUpdateEvent | None = Field(
        default=None,
        alias="artifactUpdate",
    )

    @model_validator(mode="after")
    def require_one_stream_payload(self) -> "StreamResponse":
        payloads = [
            self.task,
            self.message,
            self.status_update,
            self.artifact_update,
        ]
        if sum(item is not None for item in payloads) != 1:
            raise ValueError("StreamResponse must contain exactly one payload")
        return self


class ListTasksResponse(A2ABaseModel):
    tasks: list[Task]
    total_size: int = Field(alias="totalSize")
    page_size: int = Field(alias="pageSize")
    next_page_token: str = Field(default="", alias="nextPageToken")
