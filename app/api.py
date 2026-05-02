import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.sse import EventSourceResponse
from openai import OpenAI

from app.agents.tool_aware_agent import ToolAwareAgent
from app.configs.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL_ID,
    LLM_TIMEOUT,
    MAX_STEPS,
)
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
from app.obj.types import AgentRunResult, ChatMessage
from app.core.runner import AgentRunner
from app.core.session_manager import BaseSessionManager, InMemorySessionManager
from app.core.event_channel import EventChannel
from app.core.checkpoint import Checkpoint, CheckpointManager
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
    logger.info(
        "api event=startup model=%s max_steps=%s llm_timeout=%s",
        LLM_MODEL_ID,
        MAX_STEPS,
        LLM_TIMEOUT,
    )

    mcp_configs = load_mcp_config()
    if mcp_configs:
        for config in mcp_configs:
            logger.info(
                "api event=mcp_register_start server=%s transport=%s",
                config.name,
                config.transport,
            )
            await mcp_registry.register_mcp_server(
                name=config.name,
                command=config.command,
                env=config.env,
                transport=config.transport,
                server_url=config.server_url,
                extra_env=config.extra_env,
            )
            logger.info(
                "api event=mcp_register_end server=%s transport=%s",
                config.name,
                config.transport,
            )

    yield


composite_hooks = CompositeRunnerHooks([LoggingHooks()])
composite_middleware = CompositeRunnerMiddleware([
    InputGuardMiddleware(),
    HistoryTrimMiddleware(max_messages=20),
    ToolPermissionMiddleware(blocked_tools={"dangerous_tool"}),
])

app = FastAPI(title="Minimal Agent API", lifespan=lifespan)
client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT)
runner = AgentRunner(
    client=client,
    max_steps=MAX_STEPS,
    hooks=composite_hooks,
    middleware=composite_middleware,
)
session_manager: BaseSessionManager = InMemorySessionManager()
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
    """Remove transient memory context before persisting or rebuilding history."""
    return [
        message for message in history
        if not (
            message.get("role") == "system"
            and message.get("content", "").startswith(MEMORY_CONTEXT_PREFIX)
        )
    ]


def _build_runner_history(history: list[ChatMessage], session_id: str) -> list[ChatMessage]:
    """Inject read-only memory context into the prompt sent to AgentRunner."""
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
    """Best-effort memory write; chat responses should not fail on memory errors."""
    try:
        memory_store.append_session_exchange(
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except Exception as e:
        logger.warning(
            "api event=session_memory_write_failed session_id=%s error_type=%s",
            session_id,
            type(e).__name__,
        )


def _create_session() -> tuple[str, list[ChatMessage]]:
    """Create a new in-memory chat session with the system prompt."""
    history: list[ChatMessage] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    session_id = session_manager.create(history)
    logger.debug("api event=session_created session_id=%s", session_id)
    return session_id, history


def _load_session(session_id: str) -> list[ChatMessage]:
    """Load persisted chat history or raise the HTTP error used by /chat."""
    history = session_manager.load(session_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return _strip_memory_messages(history)


def _resolve_session(req: ChatRequest) -> tuple[str, list[ChatMessage], bool]:
    """Return session state plus whether this request created the session."""
    if req.session_id is None:
        session_id, history = _create_session()
        return session_id, history, True
    return req.session_id, _load_session(req.session_id), False


def _build_chat_agent() -> ToolAwareAgent:
    """Create a fresh agent instance for one user turn."""
    return ToolAwareAgent(
        name="chat-agent",
        model=LLM_MODEL_ID,
        system_prompt=SYSTEM_PROMPT,
    )


def _discard_stale_checkpoint(session_id: str) -> None:
    """Drop unfinished progress before accepting a new user turn.

    A checkpoint represents an interrupted previous run. Once the user submits a
    new message, resuming that stale tool state would mix two different turns.
    """
    checkpoint = checkpoint_manager.load(session_id)
    if not checkpoint:
        return

    logger.warning(
        "api event=checkpoint_discarded session_id=%s step=%s",
        session_id,
        checkpoint.step,
    )
    checkpoint_manager.clear(session_id)


def _append_user_turn(
    session_id: str,
    history: list[ChatMessage],
    message: str,
) -> None:
    """Persist the user message before running the agent."""
    history.append({
        "role": "user",
        "content": message,
    })
    session_manager.save(session_id, history)


def _prepare_agent_turn(
    req: ChatRequest,
) -> tuple[str, list[ChatMessage], list[ChatMessage], ToolAwareAgent, bool]:
    """Build the shared state needed by both sync and streaming chat endpoints."""
    session_id, history, created = _resolve_session(req)
    agent = _build_chat_agent()
    _discard_stale_checkpoint(session_id)
    _append_user_turn(session_id, history, req.message)
    runner_history = _build_runner_history(history, session_id)
    return session_id, history, runner_history, agent, created


def _run_agent(
    agent: ToolAwareAgent,
    runner_history: list[ChatMessage],
    session_id: str,
    hooks: CompositeRunnerHooks | None = None,
    resume_checkpoint: Checkpoint | None = None,
) -> AgentRunResult:
    """Call AgentRunner with the app-level registry and checkpoint manager."""
    return runner.run(
        agent=agent,
        history=runner_history,
        tool_registry=tool_registry,
        hooks=hooks,
        session_id=session_id,
        checkpoint_manager=checkpoint_manager,
        resume_checkpoint=resume_checkpoint,
    )


def _persist_assistant_turn(
    session_id: str,
    history: list[ChatMessage],
    user_message: str,
    answer: str,
) -> None:
    """Persist the assistant reply and append a compact memory record."""
    history.append({
        "role": "assistant",
        "content": answer,
    })
    session_manager.save(session_id, history)
    _record_session_memory(session_id, user_message, answer)


def _last_user_message(history: list[ChatMessage]) -> str:
    for message in reversed(history):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def chat(req: ChatRequest) -> ChatResponse:
    logger.info(
        "api event=chat_request session_id=%s has_session=%s message_chars=%s",
        req.session_id or "",
        req.session_id is not None,
        len(req.message),
    )
    session_id, history, runner_history, agent, _ = _prepare_agent_turn(req)

    try:
        run_result = _run_agent(
            agent=agent,
            runner_history=runner_history,
            session_id=session_id,
        )
        answer = run_result["answer"]
    except Exception as e:
        logger.exception(
            "api event=agent_run_failed session_id=%s error_type=%s",
            session_id,
            type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {e}"
        )

    _persist_assistant_turn(session_id, history, req.message, answer)
    logger.info(
        "api event=chat_response session_id=%s history_length=%s answer_chars=%s",
        session_id,
        len(history),
        len(answer),
    )

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        history_length=len(history),
    )


@app.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(req: ChatRequest):
    logger.info(
        "api event=chat_stream_request session_id=%s has_session=%s message_chars=%s",
        req.session_id or "",
        req.session_id is not None,
        len(req.message),
    )
    channel = EventChannel()
    # SSE hooks publish from a worker thread back onto this event loop.
    loop = asyncio.get_event_loop()
    sse_hooks = SSEHooks(channel=channel, loop=loop)
    run_hooks = CompositeRunnerHooks([LoggingHooks(), sse_hooks])

    try:
        session_id, history, runner_history, agent, created = _prepare_agent_turn(req)
    except HTTPException as e:
        await channel.publish({
            "event": "error",
            "data": {"message": str(e.detail)}
        })
        await channel.close()
        return

    if created:
        await channel.publish({
            "event": "session_created",
            "data": {"session_id": session_id}
        })

    async def run_agent():
        try:
            # Keep AgentRunner synchronous and move it off the event loop here,
            # otherwise queued SSE events cannot flush while the agent is busy.
            run_result = await loop.run_in_executor(
                None,  # use default thread pool
                lambda: _run_agent(
                    agent=agent,
                    runner_history=runner_history,
                    hooks=run_hooks,
                    session_id=session_id,
                )
            )
            answer = run_result["answer"]
            _persist_assistant_turn(session_id, history, req.message, answer)

            await channel.publish({
                "event": "final_answer",
                "data": {
                    "session_id": session_id,
                    "answer": answer,
                    "history_length": len(history),
                }
            })
            logger.info(
                "api event=chat_stream_response session_id=%s "
                "history_length=%s answer_chars=%s",
                session_id,
                len(history),
                len(answer),
            )
        except Exception as e:
            logger.exception(
                "api event=chat_stream_failed session_id=%s error_type=%s",
                session_id,
                type(e).__name__,
            )
            await channel.publish({
                "event": "error",
                "data": {"message": str(e)}
            })
        finally:
            await channel.close()

    asyncio.create_task(run_agent())

    async for event in channel.stream():
        yield event


@app.post("/checkpoint/{session_id}/resume", response_model=ChatResponse)
def resume_checkpoint(session_id: str) -> ChatResponse:
    checkpoint = checkpoint_manager.load(session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint found for session: {session_id}",
        )

    history = _load_session(session_id)
    runner_history = _build_runner_history(history, session_id)
    agent = _build_chat_agent()

    try:
        run_result = _run_agent(
            agent=agent,
            runner_history=runner_history,
            session_id=session_id,
            resume_checkpoint=checkpoint,
        )
    except Exception as e:
        logger.exception(
            "api event=checkpoint_resume_failed session_id=%s error_type=%s",
            session_id,
            type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Checkpoint resume failed: {e}",
        )

    answer = run_result["answer"]
    if run_result["success"]:
        _persist_assistant_turn(
            session_id=session_id,
            history=history,
            user_message=_last_user_message(history),
            answer=answer,
        )

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        history_length=len(history),
    )


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
        "run_id": checkpoint.run_id,
        "step": checkpoint.step,
        "phase": checkpoint.phase,
        "history_length": len(checkpoint.history),
        "function_outputs_count": len(checkpoint.function_outputs),
        "tool_calls": [
            {
                "call_id": record.call_id,
                "tool_name": record.tool_name,
                "status": record.status,
                "arguments_hash": record.arguments_hash,
                "side_effect_policy": record.side_effect_policy,
            }
            for record in checkpoint.tool_calls
        ],
        "resumable": checkpoint.phase not in {"completed", "failed"},
        "requires_manual_action": any(
            record.status in {"running", "unknown"}
            and record.side_effect_policy == "non_idempotent"
            for record in checkpoint.tool_calls
        ),
        "timestamp": checkpoint.timestamp.isoformat(),
    }


@app.delete("/checkpoint/{session_id}")
def delete_checkpoint(session_id: str):
    checkpoint_manager.clear(session_id)
    return {"message": f"Checkpoint cleared for session: {session_id}"}
