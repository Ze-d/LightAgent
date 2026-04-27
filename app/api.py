import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.sse import EventSourceResponse
from openai import OpenAI

from app.agents.tool_aware_agent import ToolAwareAgent
from app.configs.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID, MAX_STEPS,LLM_TIMEOUT
from app.core.hooks import CompositeRunnerHooks
from app.core.middleware import CompositeRunnerMiddleware
from app.hooks.logging_hooks import LoggingHooks
from app.hooks.sse_hooks import SSEHooks
from app.middleware.history_trim_middleware import HistoryTrimMiddleware
from app.middleware.tool_permission_middleware import ToolPermissionMiddleware
from app.security.input_guard import InputGuardMiddleware
from app.prompts.prompt import SYSTEM_PROMPT
from app.configs.logger import logger
from app.obj.schemas import ChatRequest, ChatResponse
from app.obj.types import ChatMessage
from app.core.runner import AgentRunner
from app.core.session_manager import BaseSessionManager, InMemorySessionManager
from app.core.event_channel import EventChannel
from app.core.checkpoint import CheckpointManager
from app.tools.register import build_default_registry
from app.skills.register import build_default_skills
from app.core.skill_dispatcher import SkillDispatcher
from app.memory.document_store import DocumentMemoryStore
from app.mcp.config import load_mcp_config
from app.mcp.tool_registry import MCPToolRegistry


MEMORY_CONTEXT_PREFIX = "[Memory]\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not LLM_API_KEY:
        raise RuntimeError(
            "LLM_API_KEY is not set. "
            "Please copy .env.example to .env and fill in your API key."
        )
    logger.info(f"Starting with model={LLM_MODEL_ID}, max_steps={MAX_STEPS}")

    mcp_configs = load_mcp_config()
    if mcp_configs:
        for config in mcp_configs:
            await mcp_registry.register_mcp_server(
                name=config.name,
                command=config.command,
                env=config.env,
                transport=config.transport,
                server_url=config.server_url,
                extra_env=config.extra_env,
            )

    yield


composite_hooks = CompositeRunnerHooks([LoggingHooks()])
composite_middleware = CompositeRunnerMiddleware([
    InputGuardMiddleware(),
    HistoryTrimMiddleware(max_messages=20),
    ToolPermissionMiddleware(blocked_tools={"dangerous_tool"}),
])

app = FastAPI(title="Minimal Agent API", lifespan=lifespan)
client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT )
runner = AgentRunner(client=client, max_steps=MAX_STEPS, hooks=composite_hooks, middleware=composite_middleware)
session_manager : BaseSessionManager = InMemorySessionManager()
checkpoint_manager = CheckpointManager()
memory_store = DocumentMemoryStore()
tool_registry = build_default_registry()
skill_registry = build_default_skills()
skill_dispatcher = SkillDispatcher(skill_registry=skill_registry, hooks=composite_hooks)
runner.skill_dispatcher = skill_dispatcher
mcp_registry = MCPToolRegistry(tool_registry)






@app.get("/")
async def root():
    return {"message": "Minimal Agent API is running"}


def _strip_memory_messages(history: list[ChatMessage]) -> list[ChatMessage]:
    return [
        message for message in history
        if not (
            message.get("role") == "system"
            and message.get("content", "").startswith(MEMORY_CONTEXT_PREFIX)
        )
    ]


def _build_runner_history(history: list[ChatMessage], session_id: str) -> list[ChatMessage]:
    clean_history = _strip_memory_messages(history)
    memory_context = memory_store.build_context(session_id=session_id)
    if not memory_context:
        return list(clean_history)

    memory_message: ChatMessage = {
        "role": "system",
        "content": f"{MEMORY_CONTEXT_PREFIX}{memory_context}",
    }
    if clean_history and clean_history[0].get("role") == "system":
        return [clean_history[0], memory_message, *clean_history[1:]]
    return [memory_message, *clean_history]


def _record_session_memory(session_id: str, user_message: str, assistant_message: str) -> None:
    try:
        memory_store.append_session_exchange(
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except Exception as e:
        logger.warning(f"Failed to write session memory: session_id={session_id}, error={e}")


@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def chat(req: ChatRequest) -> ChatResponse:
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
        history = _strip_memory_messages(history)

    # 2. 创建ToolAwareAgent并丢弃上一轮未完成的checkpoint
    agent = ToolAwareAgent(
        name="chat-agent",
        model=LLM_MODEL_ID,
        system_prompt=SYSTEM_PROMPT,
    )
    checkpoint = checkpoint_manager.load(session_id)
    if checkpoint:
        logger.warning(
            f"Discarding stale checkpoint before new user turn: "
            f"session_id={session_id}, step={checkpoint.step}"
        )
        checkpoint_manager.clear(session_id)

    # 3. 追加用户消息
    history.append({
        "role": "user",
        "content": req.message,
    })
    session_manager.save(session_id, history)
    runner_history = _build_runner_history(history, session_id)

    # 4. 调用 Agent
    try:
        run_result = runner.run(
            agent=agent,
            history=runner_history,
            tool_registry=tool_registry,
            session_id=session_id,
            checkpoint_manager=checkpoint_manager,
        )
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
    _record_session_memory(session_id, req.message, answer)

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        history_length=len(history),
    )


@app.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(req: ChatRequest):
    channel = EventChannel()
    # Create SSEHooks with the event loop for cross-thread event publishing
    loop = asyncio.get_event_loop()
    sse_hooks = SSEHooks(channel=channel, loop=loop)
    run_hooks = CompositeRunnerHooks([LoggingHooks(), sse_hooks])

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
        history = _strip_memory_messages(loaded_history)

    # 2. 创建ToolAwareAgent并丢弃上一轮未完成的checkpoint
    agent = ToolAwareAgent(
        name="chat-agent",
        model=LLM_MODEL_ID,
        system_prompt=SYSTEM_PROMPT,
    )
    checkpoint = checkpoint_manager.load(session_id)
    if checkpoint:
        logger.warning(
            f"Discarding stale checkpoint before new user turn: "
            f"session_id={session_id}, step={checkpoint.step}"
        )
        checkpoint_manager.clear(session_id)

    # 3. 追加用户消息
    history.append({
        "role": "user",
        "content": req.message,
    })
    session_manager.save(session_id, history)
    runner_history = _build_runner_history(history, session_id)

    # 4. 在后台跑 runner，过程中事件会持续进入 channel
    async def run_agent():
        try:
            # Use run_in_executor to run sync runner.run() in thread pool
            # This prevents blocking the event loop, allowing SSE events to stream
            run_result = await loop.run_in_executor(
                None,  # use default thread pool
                lambda: runner.run(
                    agent=agent,
                    history=runner_history,
                    tool_registry=tool_registry,
                    hooks=run_hooks,
                    session_id=session_id,
                    checkpoint_manager=checkpoint_manager,
                )
            )
            answer = run_result["answer"]
            history.append({
                "role": "assistant",
                "content": answer,
            })
            session_manager.save(session_id, history)
            _record_session_memory(session_id, req.message, answer)

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


@app.get("/checkpoint/{session_id}")
def get_checkpoint(session_id: str):
    checkpoint = checkpoint_manager.load(session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint found for session: {session_id}"
        )
    return {
        "session_id": session_id,
        "step": checkpoint.step,
        "history_length": len(checkpoint.history),
        "timestamp": checkpoint.timestamp.isoformat(),
    }


@app.delete("/checkpoint/{session_id}")
def delete_checkpoint(session_id: str):
    checkpoint_manager.clear(session_id)
    return {"message": f"Checkpoint cleared for session: {session_id}"}
