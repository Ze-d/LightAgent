from pydantic import BaseModel, Field
from typing import Literal


class HistoryMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    message: str = Field(..., description="当前用户输入")
    session_id: str | None = Field(
        default=None,
        description="可选的会话 ID；不传则创建新会话"
    )


class ChatResponse(BaseModel):
    session_id: str = Field(..., description="当前会话 ID")
    answer: str = Field(..., description="Agent 返回的最终答案")
    history_length: int = Field(..., description="当前会话历史消息数")