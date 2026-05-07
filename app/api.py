import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from openai import OpenAI

from app.agents.tool_aware_agent import ToolAwareAgent
from app.configs.config import (
    A2A_AGENT_VERSION,
    A2A_DOCUMENTATION_URL,
    A2A_EXTENDED_CARD_TOKEN,
    A2A_ICON_URL,
    A2A_PUBLIC_URL,
    CONTEXT_DECAY_PER_TOOL,
    CONTEXT_DECAY_PER_TURN,
    CONTEXT_DEDUP_ENABLED,
    CONTEXT_DYNAMIC_BUDGET_ENABLED,
    CONTEXT_MAX_INPUT_TOKENS,
    CONTEXT_MEMORY_MAX_TOKENS,
    CONTEXT_PIPELINE_ENABLED,
    CONTEXT_RECENT_WINDOW,
    CONTEXT_SCORE_OLDER_EXCHANGE,
    CONTEXT_SCORE_OLDER_TOOL_OUTPUT,
    CONTEXT_SCORE_RECENT_EXCHANGE,
    CONTEXT_SCORE_RECENT_TOOL_OUTPUT,
    CONTEXT_SCORE_SUMMARY,
    CONTEXT_SCORE_SYSTEM_PROMPT,
    CONTEXT_SCORE_TRANSIENT_MEMORY,
    CONTEXT_SUMMARY_MAX_LEVEL,
    CONTEXT_SUMMARY_TURNS_PER_GROUP,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_EMBEDDING_MODEL,
    LLM_MODEL_ID,
    LLM_TIMEOUT,
    MAX_STEPS,
    MEMORY_CONSOLIDATION_INTERVAL,
    MEMORY_CROSS_SESSION_THRESHOLD,
    MEMORY_DEDUP_THRESHOLD,
    MEMORY_IMPORTANCE_DECAY,
    MEMORY_SEARCH_MIN_SCORE,
    MEMORY_SEARCH_TOP_K,
    MEMORY_VECTOR_ENABLED,
    STATE_BACKEND,
    STATE_DB_PATH,
)
from app.a2a import build_a2a_router, build_agent_card, build_extended_agent_card
from app.a2a.adapter import A2AProtocolAdapter
from app.a2a.event_broker import A2AEventBroker, SQLiteA2AEventBroker
from app.a2a.schemas import Message as A2AMessage
from app.a2a.service import A2AService
from app.a2a.task_store import InMemoryA2ATaskStore, SQLiteA2ATaskStore
from app.core.sse import EventSourceResponse
from app.core.hooks import CompositeRunnerHooks
from app.core.middleware import CompositeRunnerMiddleware
from app.hooks.logging_hooks import LoggingHooks
from app.hooks.sse_hooks import SSEHooks
from app.middleware.tool_permission_middleware import ToolPermissionMiddleware
from app.security.input_guard import InputGuardMiddleware
from app.prompts.prompt import SYSTEM_PROMPT
from app.configs.logger import logger
from app.obj.schemas import ChatRequest, ChatResponse
from app.obj.types import AgentRunResult, ChatMessage
from app.core.runner import AgentRunner
from app.core.session_manager import (
    BaseSessionManager,
    InMemorySessionManager,
    SQLiteSessionManager,
)
from app.core.context_state import (
    BaseContextStore,
    ContextChannel,
    InMemoryContextStore,
    ProviderMode,
    SQLiteContextStore,
)
from app.core.context_builder import ContextBuilder, ContextEnvelope
from app.core.event_channel import EventChannel
from app.core.checkpoint import (
    Checkpoint,
    CheckpointManager,
    CheckpointOrchestrator,
    SQLiteCheckpointManager,
)
from app.core.cancellation import CancellationToken
from app.tools.register import build_default_registry
from app.tools.memory_tools import init_memory_store
from app.skills.register import build_default_skills
from app.core.skill_dispatcher import SkillDispatcher
from app.memory.document_store import DocumentMemoryStore
from app.memory.consolidator import MemoryConsolidator
from app.memory.embedding import EmbeddingService
from app.memory.extractor import KnowledgeExtractor
from app.memory.vector_store import VectorMemoryStore
from app.mcp.config import load_mcp_config
from app.mcp.tool_registry import MCPToolRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not LLM_API_KEY:
        raise RuntimeError(
            "LLM_API_KEY is not set. "
            "Please copy .env.example to .env and fill in your API key."
        )
    logger.info(
        "api event=startup model=%s max_steps=%s llm_timeout=%s "
        "state_backend=%s context_max_input_tokens=%s "
        "context_memory_max_tokens=%s",
        LLM_MODEL_ID,
        MAX_STEPS,
        LLM_TIMEOUT,
        _state_backend(),
        _context_max_input_tokens() or 0,
        _context_memory_max_tokens() or 0,
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
    ToolPermissionMiddleware(blocked_tools={"dangerous_tool"}),
])

app = FastAPI(title="Minimal Agent API", lifespan=lifespan)


def _state_backend() -> str:
    backend = STATE_BACKEND.strip().lower()
    if backend in {"memory", "inmemory", "in_memory"}:
        return "memory"
    if backend == "sqlite":
        return "sqlite"
    raise RuntimeError(
        "STATE_BACKEND must be 'memory' or 'sqlite', "
        f"got: {STATE_BACKEND!r}"
    )


def _build_session_manager() -> BaseSessionManager:
    if _state_backend() == "sqlite":
        return SQLiteSessionManager(STATE_DB_PATH)
    return InMemorySessionManager()


def _build_context_store() -> BaseContextStore:
    if _state_backend() == "sqlite":
        return SQLiteContextStore(STATE_DB_PATH)
    return InMemoryContextStore()


def _build_checkpoint_manager() -> CheckpointManager | SQLiteCheckpointManager:
    if _state_backend() == "sqlite":
        return SQLiteCheckpointManager(STATE_DB_PATH)
    return CheckpointManager()


def _build_a2a_task_store() -> InMemoryA2ATaskStore | SQLiteA2ATaskStore:
    if _state_backend() == "sqlite":
        return SQLiteA2ATaskStore(STATE_DB_PATH)
    return InMemoryA2ATaskStore()


def _build_a2a_event_broker() -> A2AEventBroker:
    if _state_backend() == "sqlite":
        return SQLiteA2AEventBroker(STATE_DB_PATH)
    return A2AEventBroker()


def _context_max_input_tokens() -> int | None:
    return CONTEXT_MAX_INPUT_TOKENS if CONTEXT_MAX_INPUT_TOKENS > 0 else None


def _context_memory_max_tokens() -> int | None:
    return CONTEXT_MEMORY_MAX_TOKENS if CONTEXT_MEMORY_MAX_TOKENS > 0 else None


client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT)
session_manager: BaseSessionManager = _build_session_manager()
context_store: BaseContextStore = _build_context_store()
checkpoint_manager = _build_checkpoint_manager()
checkpoint_orchestrator = CheckpointOrchestrator(checkpoint_manager)
runner = AgentRunner(
    client=client,
    max_steps=MAX_STEPS,
    hooks=composite_hooks,
    middleware=composite_middleware,
    checkpoint=checkpoint_orchestrator,
)
# Initialize embedding service and vector store when enabled.
_embedding_service: EmbeddingService | None = None
_vector_store: VectorMemoryStore | None = None
if MEMORY_VECTOR_ENABLED and LLM_API_KEY:
    _embedding_service = EmbeddingService(client=client, model=LLM_EMBEDDING_MODEL)
    _vector_store = VectorMemoryStore(STATE_DB_PATH)
    logger.info(
        "api event=vector_store_init embedding_model=%s db=%s",
        LLM_EMBEDDING_MODEL,
        STATE_DB_PATH,
    )

memory_store = DocumentMemoryStore(
    vector_store=_vector_store,
    embedding_service=_embedding_service,
)
init_memory_store(memory_store)

# Initialize consolidator and knowledge extractor.
_consolidator: MemoryConsolidator | None = None
_knowledge_extractor: KnowledgeExtractor | None = None
if _vector_store is not None:
    _consolidator = MemoryConsolidator(
        vector_store=_vector_store,
        dedup_threshold=MEMORY_DEDUP_THRESHOLD,
        importance_decay=MEMORY_IMPORTANCE_DECAY,
        cross_session_threshold=MEMORY_CROSS_SESSION_THRESHOLD,
        consolidation_interval=MEMORY_CONSOLIDATION_INTERVAL,
    )
    # Attach consolidator to memory store so tools can trigger manual consolidation
    memory_store._consolidator = _consolidator  # type: ignore[attr-defined]
    _knowledge_extractor = KnowledgeExtractor(client=client, model=LLM_MODEL_ID)
    logger.info("api event=consolidator_init interval=%d", MEMORY_CONSOLIDATION_INTERVAL)

    # Index existing project/user memory into vector store on startup.
    try:
        memory_store.index_project_memory()
        memory_store.index_user_memory()
    except Exception:
        logger.warning("api event=memory_index_startup_failed", exc_info=True)

    # Run initial consolidation pass.
    try:
        _consolidator.run()
    except Exception:
        logger.warning("api event=consolidator_startup_failed", exc_info=True)
context_builder = ContextBuilder(
    memory_store=memory_store,
    max_input_tokens=_context_max_input_tokens(),
    memory_max_tokens=_context_memory_max_tokens(),
    pipeline_enabled=CONTEXT_PIPELINE_ENABLED,
    dedup_enabled=CONTEXT_DEDUP_ENABLED,
    importance_scores={
        "system_prompt": CONTEXT_SCORE_SYSTEM_PROMPT,
        "recent_exchange": CONTEXT_SCORE_RECENT_EXCHANGE,
        "recent_tool_output": CONTEXT_SCORE_RECENT_TOOL_OUTPUT,
        "summary": CONTEXT_SCORE_SUMMARY,
        "older_exchange": CONTEXT_SCORE_OLDER_EXCHANGE,
        "older_tool_output": CONTEXT_SCORE_OLDER_TOOL_OUTPUT,
        "transient_memory": CONTEXT_SCORE_TRANSIENT_MEMORY,
    },
    importance_recent_window=CONTEXT_RECENT_WINDOW,
    importance_decay_per_turn=CONTEXT_DECAY_PER_TURN,
    importance_decay_per_tool=CONTEXT_DECAY_PER_TOOL,
    summary_max_level=CONTEXT_SUMMARY_MAX_LEVEL,
    summary_turns_per_group=CONTEXT_SUMMARY_TURNS_PER_GROUP,
    dynamic_budget_enabled=CONTEXT_DYNAMIC_BUDGET_ENABLED,
    llm_client=client,
)
tool_registry = build_default_registry()
skill_registry = build_default_skills()
skill_dispatcher = SkillDispatcher(skill_registry=skill_registry, hooks=composite_hooks)
runner.skill_dispatcher = skill_dispatcher
mcp_registry = MCPToolRegistry(tool_registry)
a2a_adapter = A2AProtocolAdapter()
a2a_task_store = _build_a2a_task_store()
a2a_event_broker = _build_a2a_event_broker()


def _resolve_a2a_public_url(request_base_url: str) -> str:
    return A2A_PUBLIC_URL or request_base_url


def _build_a2a_agent_card(request_base_url: str):
    return build_agent_card(
        public_base_url=_resolve_a2a_public_url(request_base_url),
        agent_name="chat-agent",
        version=A2A_AGENT_VERSION,
        documentation_url=A2A_DOCUMENTATION_URL,
        icon_url=A2A_ICON_URL,
        extended_card_enabled=bool(A2A_EXTENDED_CARD_TOKEN),
        skill_registry=skill_registry,
        tool_registry=tool_registry,
    )


def _build_a2a_extended_agent_card(request_base_url: str):
    return build_extended_agent_card(
        public_base_url=_resolve_a2a_public_url(request_base_url),
        agent_name="chat-agent",
        version=A2A_AGENT_VERSION,
        documentation_url=A2A_DOCUMENTATION_URL,
        icon_url=A2A_ICON_URL,
        skill_registry=skill_registry,
        tool_registry=tool_registry,
    )


@app.get("/")
async def root():
    return {"message": "Minimal Agent API is running"}


def _default_provider() -> str:
    if "api.openai.com" in LLM_BASE_URL:
        return "openai"
    return "openai_compatible"


def _default_provider_mode() -> ProviderMode:
    if _default_provider() == "openai":
        return "openai_previous_response"
    return "manual"


def _strip_memory_messages(history: list[ChatMessage]) -> list[ChatMessage]:
    """Remove transient memory context before persisting or rebuilding history."""
    return context_builder.strip_transient_context(history)


def _build_context_envelope(
    history: list[ChatMessage],
    session_id: str,
) -> ContextEnvelope:
    """Build the normalized LLM context envelope for one runner turn."""
    context_state = context_store.require(session_id)
    return context_builder.build(
        context_state=context_state,
        history=history,
    )


# Track session turn counts for knowledge extraction triggers.
_session_turn_counts: dict[str, int] = {}


def _record_session_memory(session_id: str, user_message: str, assistant_message: str) -> None:
    """Best-effort memory write; chat responses should not fail on memory errors."""
    try:
        summary = memory_store.summarizer.summarize_exchange(
            user_message=user_message,
            assistant_message=assistant_message,
        )
        memory_store.append_session_summary(session_id, summary)
        # Also index into vector store for semantic retrieval
        if _vector_store is not None:
            memory_store.index_session_entry(session_id, summary)
        # Notify consolidator of write
        if _consolidator is not None:
            _consolidator.on_write()
    except Exception as exc:
        logger.warning(
            "api event=session_memory_write_failed session_id=%s error_type=%s",
            session_id,
            type(exc).__name__,
            exc_info=True,
        )


def _maybe_extract_knowledge(session_id: str, history: list[ChatMessage]) -> None:
    """Trigger knowledge extraction after enough conversation turns."""
    if _knowledge_extractor is None or _vector_store is None:
        return

    _session_turn_counts[session_id] = _session_turn_counts.get(session_id, 0) + 1
    turn_count = _session_turn_counts[session_id]

    if not _knowledge_extractor.should_extract(turn_count):
        return

    # Reset counter to avoid repeated extraction for the same session
    _session_turn_counts[session_id] = 0

    try:
        facts = _knowledge_extractor.extract(history)
        if facts and _consolidator is not None:
            stored = _consolidator.store_knowledge_facts(facts, session_id)
            logger.info(
                "api event=knowledge_extracted session_id=%s facts=%d stored=%d",
                session_id,
                len(facts),
                stored,
            )
    except Exception:
        logger.warning(
            "api event=knowledge_extract_failed session_id=%s",
            session_id,
            exc_info=True,
        )


def _create_session() -> tuple[str, list[ChatMessage]]:
    """Create a new in-memory chat session with the system prompt."""
    history: list[ChatMessage] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    session_id = session_manager.create(history)
    context_store.create(
        channel="chat",
        session_id=session_id,
        provider=_default_provider(),
        provider_mode=_default_provider_mode(),
    )
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
    _ensure_context_state(session_id, channel="chat")
    return _strip_memory_messages(history)


def _ensure_context_state(
    session_id: str,
    *,
    channel: ContextChannel,
    external_context_id: str | None = None,
) -> None:
    """Backfill context state for sessions created before ContextStore existed."""
    if context_store.get(session_id) is not None:
        return
    context_store.create(
        channel=channel,
        session_id=session_id,
        external_context_id=external_context_id,
        provider=_default_provider(),
        provider_mode=_default_provider_mode(),
    )


def _resolve_context_session_id(session_id: str) -> str:
    """Resolve public context identifiers to the internal session key."""
    if session_manager.exists(session_id) or context_store.get(session_id) is not None:
        return session_id

    a2a_context = context_store.get_by_external_context(
        channel="a2a",
        external_context_id=session_id,
    )
    if a2a_context is not None:
        return a2a_context.session_id
    return session_id


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
    checkpoint = checkpoint_orchestrator.load(session_id)
    if not checkpoint:
        return

    logger.warning(
        "api event=checkpoint_discarded session_id=%s step=%s",
        session_id,
        checkpoint.step,
    )
    checkpoint_orchestrator.clear(session_id)


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
    context_store.bump_history_version(session_id)


def _prepare_agent_turn(
    req: ChatRequest,
) -> tuple[str, list[ChatMessage], ContextEnvelope, ToolAwareAgent, bool]:
    """Build the shared state needed by both sync and streaming chat endpoints."""
    session_id, history, created = _resolve_session(req)
    agent = _build_chat_agent()
    _discard_stale_checkpoint(session_id)
    _append_user_turn(session_id, history, req.message)
    context_envelope = _build_context_envelope(history, session_id)
    return session_id, history, context_envelope, agent, created


def _run_agent(
    agent: ToolAwareAgent,
    context_envelope: ContextEnvelope,
    session_id: str,
    hooks: CompositeRunnerHooks | None = None,
    resume_checkpoint: Checkpoint | None = None,
    cancellation_token: CancellationToken | None = None,
) -> AgentRunResult:
    """Call AgentRunner with the app-level registry."""
    run_result = runner.run(
        provider_state=context_envelope.provider_state,
        agent=agent,
        history=context_envelope.messages,
        tool_registry=tool_registry,
        hooks=hooks,
        session_id=session_id,
        resume_checkpoint=resume_checkpoint,
        cancellation_token=cancellation_token,
    )
    _persist_provider_response_id(context_envelope, run_result)
    return run_result


def _persist_provider_response_id(
    context_envelope: ContextEnvelope,
    run_result: AgentRunResult,
) -> None:
    response_id = run_result.get("response_id")
    if (
        not run_result["success"]
        or not response_id
        or context_envelope.provider_state.provider != "openai"
        or context_envelope.provider_state.provider_mode != "openai_previous_response"
    ):
        return
    context_store.update_provider_state(
        context_envelope.session_id,
        last_response_id=response_id,
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
    context_store.bump_history_version(session_id)
    _record_session_memory(session_id, user_message, answer)
    _maybe_extract_knowledge(session_id, history)


def _last_user_message(history: list[ChatMessage]) -> str:
    for message in reversed(history):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _load_or_create_a2a_session(context_id: str) -> tuple[str, list[ChatMessage]]:
    context_state = context_store.get_or_create_for_external_context(
        channel="a2a",
        external_context_id=context_id,
        provider=_default_provider(),
        provider_mode=_default_provider_mode(),
    )
    session_id = context_state.session_id
    history = session_manager.load(session_id)
    if history is not None:
        return session_id, _strip_memory_messages(history)

    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    session_manager.save(session_id, history)
    logger.debug(
        "api event=a2a_session_created context_id=%s session_id=%s",
        context_id,
        session_id,
    )
    return session_id, list(history)


def _run_a2a_turn(
    message: A2AMessage,
    context_id: str,
    cancellation_token: CancellationToken | None = None,
) -> AgentRunResult:
    user_message = a2a_adapter.extract_text(message)
    session_id, history = _load_or_create_a2a_session(context_id)
    agent = _build_chat_agent()
    _discard_stale_checkpoint(session_id)
    _append_user_turn(session_id, history, user_message)
    context_envelope = _build_context_envelope(history, session_id)
    run_result = _run_agent(
        agent=agent,
        context_envelope=context_envelope,
        session_id=session_id,
        cancellation_token=cancellation_token,
    )
    _persist_assistant_turn(
        session_id=session_id,
        history=history,
        user_message=user_message,
        answer=run_result["answer"],
    )
    return run_result


a2a_service = A2AService(
    task_store=a2a_task_store,
    adapter=a2a_adapter,
    run_turn=_run_a2a_turn,
    event_broker=a2a_event_broker,
)
app.include_router(
    build_a2a_router(
        agent_card_provider=_build_a2a_agent_card,
        service=a2a_service,
        extended_agent_card_provider=_build_a2a_extended_agent_card,
        extended_agent_card_token=A2A_EXTENDED_CARD_TOKEN,
    )
)


@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def chat(req: ChatRequest) -> ChatResponse:
    logger.info(
        "api event=chat_request session_id=%s has_session=%s message_chars=%s",
        req.session_id or "",
        req.session_id is not None,
        len(req.message),
    )
    session_id, history, context_envelope, agent, _ = _prepare_agent_turn(req)

    try:
        run_result = _run_agent(
            agent=agent,
            context_envelope=context_envelope,
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
        session_id, history, context_envelope, agent, created = _prepare_agent_turn(req)
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
                    context_envelope=context_envelope,
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
    internal_session_id = _resolve_context_session_id(session_id)
    checkpoint = checkpoint_orchestrator.load(internal_session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint found for session: {session_id}",
        )

    history = _load_session(internal_session_id)
    context_envelope = _build_context_envelope(history, internal_session_id)
    agent = _build_chat_agent()

    try:
        run_result = _run_agent(
            agent=agent,
            context_envelope=context_envelope,
            session_id=internal_session_id,
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
            session_id=internal_session_id,
            history=history,
            user_message=_last_user_message(history),
            answer=answer,
        )

    return ChatResponse(
        session_id=internal_session_id,
        answer=answer,
        history_length=len(history),
    )


@app.get("/checkpoint/{session_id}")
def get_checkpoint(session_id: str):
    internal_session_id = _resolve_context_session_id(session_id)
    checkpoint = checkpoint_orchestrator.load(internal_session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint found for session: {session_id}"
        )
    return {
        "session_id": internal_session_id,
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
    internal_session_id = _resolve_context_session_id(session_id)
    checkpoint_orchestrator.clear(internal_session_id)
    return {"message": f"Checkpoint cleared for session: {internal_session_id}"}
