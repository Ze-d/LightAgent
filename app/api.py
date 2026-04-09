from fastapi import FastAPI, HTTPException, status
from openai import OpenAI

from app.configs.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID, MAX_STEPS,LLM_TIMEOUT
from app.prompts.prompt import SYSTEM_PROMPT
from app.configs.logger import logger
from app.obj.schemas import ChatRequest, ChatResponse
from app.obj.types import ChatMessage
from app.core.runner import AgentRunner
from app.core.session_manager import SessionManager
from app.agents.chat_agent import ChatAgent
from app.tools.register import build_default_registry

app = FastAPI(title="Minimal Agent API")

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT )
runner = AgentRunner(client=client, max_steps=MAX_STEPS)
session_manager = SessionManager()
tool_registry = build_default_registry()

agent = ChatAgent(
    name="chat-agent",
    model=LLM_MODEL_ID,
    system_prompt=SYSTEM_PROMPT,
)

@app.get("/")
async def root():
    return {"message": "Minimal Agent API is running"}


@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(req: ChatRequest) -> ChatResponse:
    logger.info("Received /chat request")

    # 1. 处理会话初始化或读取
    if req.session_id is None:
        history: list[ChatMessage] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        session_id = session_manager.create(history)
        logger.info(f"Created new session: {session_id}")
    else:
        session_id = req.session_id
        history: list[ChatMessage] | None = session_manager.load(session_id)
        if history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}"
            )

    # 2. 追加用户消息
    history.append({
        "role": "user",
        "content": req.message,
    })

    # 3. 调用 Agent
    try:
        answer = runner.run(agent, history, tool_registry)
    except Exception as e:
        logger.exception("Agent run failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {e}"
        )

    # 4. 保存 assistant 消息
    history.append({
        "role": "assistant",
        "content": answer,
    })

    # 5. 回写会话
    session_manager.save(session_id, history)

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        history_length=len(history),
    )