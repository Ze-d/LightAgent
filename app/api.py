import asyncio

from fastapi import FastAPI, HTTPException, status
from fastapi.sse import EventSourceResponse
from openai import OpenAI

from app.agents.tool_aware_agent import ToolAwareAgent
from app.configs.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID, MAX_STEPS,LLM_TIMEOUT
from app.listener.log_listener import log_listener
from app.prompts.prompt import SYSTEM_PROMPT
from app.configs.logger import logger
from app.obj.schemas import ChatRequest, ChatResponse
from app.obj.types import ChatMessage
from app.core.runner import AgentRunner
from app.core.session_manager import BaseSessionManager, InMemorySessionManager
from app.listener.sse_listener import make_tool_event_listener
from app.core.event_channel import EventChannel
from app.tools.register import build_default_registry

app = FastAPI(title="Minimal Agent API")

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT )
runner = AgentRunner(client=client, max_steps=MAX_STEPS)
session_manager : BaseSessionManager = InMemorySessionManager()
tool_registry = build_default_registry()
def log_tool_event(event: ToolCallEvent) -> None:
    logger.info(f"[tool-event] {event}")

from app.configs.logger import logger





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
        logger.debug(f"Created new session: {session_id}")
    else:
        session_id = req.session_id
        history: list[ChatMessage] | None = session_manager.load(session_id)
        if history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}"
            )
    # 2. 创建 ToolAwareAgent，注入工具调用事件监听器
    agent = ToolAwareAgent(
    name="chat-agent",
    model=LLM_MODEL_ID,
    system_prompt=SYSTEM_PROMPT,
    tool_call_listener=log_listener(),
)
    # 2. 追加用户消息
    history.append({
        "role": "user",
        "content": req.message,
    })
    session_manager.save(session_id, history)  # 保存用户消息后的状态，以便工具调用时能拿到最新历史

    # 3. 调用 Agent
    try:
        run_result = runner.run(agent, history, tool_registry)
        answer = run_result["answer"]
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


@app.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(req: ChatRequest):
    channel = EventChannel()

    # 1. 初始化会话
    if req.session_id is None:
        history: list[ChatMessage] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        session_id = session_manager.create(history)
        await channel.publish({
            "event": "session_created",
            "data": {"session_id": session_id}
        })
    else:
        session_id = req.session_id
        loaded_history: list[ChatMessage] | None = session_manager.load(session_id)
        if loaded_history is None:
            await channel.publish({
                "event": "error",
                "data": {"message": f"Session not found: {session_id}"}
            })
            await channel.close()
            return
        history = loaded_history

    # 2. 追加用户消息
    history.append({
        "role": "user",
        "content": req.message,
    })

    # 3. 创建 ToolAwareAgent
    loop = asyncio.get_running_loop()
    agent = ToolAwareAgent(
        name="chat-agent",
        model=LLM_MODEL_ID,
        system_prompt=SYSTEM_PROMPT,
        tool_call_listener=make_tool_event_listener(channel, loop),
    )

    # 4. 在后台跑 runner，过程中事件会持续进入 channel
    async def run_agent():
        try:
            # Use run_in_executor to run sync runner.run() in thread pool
            # This prevents blocking the event loop, allowing SSE events to stream
            run_result = await loop.run_in_executor(
                None,  # use default thread pool
                lambda: runner.run(
                    agent=agent,
                    history=history,
                    tool_registry=tool_registry,
                )
            )
            answer = run_result["answer"]
            history.append({
                "role": "assistant",
                "content": answer,
            })
            session_manager.save(session_id, history)

            await channel.publish({
                "event": "final_answer",
                "data": {
                    "session_id": session_id,
                    "answer": answer,
                    "history_length": len(history),
                }
            })
        except Exception as e:
            await channel.publish({
                "event": "error",
                "data": {"message": str(e)}
            })
        finally:
            await channel.close()

    asyncio.create_task(run_agent())

    async for event in channel.stream():
        yield event