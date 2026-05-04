from app.core.checkpoint import (
    CheckpointManager,
    SQLiteCheckpointManager,
    Checkpoint,
    ToolExecutionRecord,
)


def test_save_and_load_checkpoint():
    manager = CheckpointManager()

    session_id = "test-session-1"
    history = [
        {"role": "system", "content": "You are a test agent."},
        {"role": "user", "content": "Hello"},
    ]
    agent_state = {"tool_event_history": []}

    manager.save(session_id, step=1, history=history, agent_state=agent_state)

    checkpoint = manager.load(session_id)
    assert checkpoint is not None
    assert checkpoint.step == 1
    assert len(checkpoint.history) == 2
    assert checkpoint.agent_state == agent_state


def test_load_returns_none_for_unknown_session():
    manager = CheckpointManager()

    checkpoint = manager.load("unknown-session")
    assert checkpoint is None


def test_get_latest_step():
    manager = CheckpointManager()

    session_id = "test-session-2"
    history = [{"role": "system", "content": "test"}]

    assert manager.get_latest_step(session_id) == 0

    manager.save(session_id, step=1, history=history, agent_state={})
    assert manager.get_latest_step(session_id) == 1

    manager.save(session_id, step=2, history=history, agent_state={})
    assert manager.get_latest_step(session_id) == 2


def test_save_creates_multiple_checkpoints():
    manager = CheckpointManager()

    session_id = "test-session-3"
    history = [{"role": "system", "content": "test"}]

    manager.save(session_id, step=1, history=history, agent_state={})
    manager.save(session_id, step=2, history=history, agent_state={})
    manager.save(session_id, step=3, history=history, agent_state={})

    checkpoint = manager.load(session_id)
    assert checkpoint.step == 3


def test_clear_checkpoint():
    manager = CheckpointManager()

    session_id = "test-session-4"
    history = [{"role": "system", "content": "test"}]

    manager.save(session_id, step=1, history=history, agent_state={})
    assert manager.has_checkpoint(session_id) is True

    manager.clear(session_id)
    assert manager.has_checkpoint(session_id) is False
    assert manager.load(session_id) is None


def test_has_checkpoint():
    manager = CheckpointManager()

    session_id = "test-session-5"
    assert manager.has_checkpoint(session_id) is False

    manager.save(session_id, step=1, history=[], agent_state={})
    assert manager.has_checkpoint(session_id) is True


def test_history_is_copied():
    manager = CheckpointManager()

    session_id = "test-session-6"
    history = [{"role": "system", "content": "test"}]

    manager.save(session_id, step=1, history=history, agent_state={})

    checkpoint = manager.load(session_id)
    assert checkpoint is not None

    checkpoint.history.append({"role": "user", "content": "modified"})

    checkpoint2 = manager.load(session_id)
    assert len(checkpoint2.history) == 1


def test_agent_state_is_copied():
    manager = CheckpointManager()

    session_id = "test-session-7"
    agent_state = {"tool_event_history": [{"name": "test_tool"}]}

    manager.save(session_id, step=1, history=[], agent_state=agent_state)

    checkpoint = manager.load(session_id)
    checkpoint.agent_state["tool_event_history"].append({"name": "another"})

    checkpoint2 = manager.load(session_id)
    assert len(checkpoint2.agent_state["tool_event_history"]) == 1


def test_save_records_checkpoint_phase_and_tool_outputs():
    manager = CheckpointManager()
    session_id = "test-session-8"
    tool_record = ToolExecutionRecord(
        call_id="call_1",
        tool_name="calculator",
        arguments={"expression": "2 + 3"},
        arguments_hash="hash",
        status="succeeded",
        output="5",
    )
    output = {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "5",
    }

    manager.save(
        session_id,
        step=1,
        history=[output],
        agent_state={},
        phase="tool_output_ready",
        llm_input=[output],
        tool_calls=[tool_record],
        function_outputs=[output],
        run_id="run-1",
    )

    checkpoint = manager.load(session_id)
    assert checkpoint.phase == "tool_output_ready"
    assert checkpoint.run_id == "run-1"
    assert checkpoint.function_outputs == [output]
    assert checkpoint.completed_call_ids == ["call_1"]

    checkpoint.tool_calls[0].output = "modified"
    checkpoint2 = manager.load(session_id)
    assert checkpoint2.tool_calls[0].output == "5"


def test_sqlite_checkpoint_manager_persists_latest_checkpoint(sqlite_db_path):
    manager = SQLiteCheckpointManager(sqlite_db_path)
    session_id = "session-sqlite"
    tool_record = ToolExecutionRecord(
        call_id="call_1",
        tool_name="lookup",
        arguments={"q": "x"},
        arguments_hash="hash",
        status="succeeded",
        output="result",
    )
    output = {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "result",
    }

    manager.save(
        session_id,
        step=1,
        history=[{"role": "user", "content": "hi"}],
        agent_state={"tool_event_history": []},
        phase="tool_requested",
        tool_calls=[tool_record],
        run_id="run-1",
    )
    manager.save(
        session_id,
        step=2,
        history=[output],
        agent_state={"tool_event_history": [{"name": "lookup"}]},
        phase="tool_output_ready",
        function_outputs=[output],
        run_id="run-1",
    )

    reloaded = SQLiteCheckpointManager(sqlite_db_path)
    checkpoint = reloaded.load(session_id)

    assert checkpoint is not None
    assert checkpoint.step == 2
    assert checkpoint.phase == "tool_output_ready"
    assert checkpoint.run_id == "run-1"
    assert checkpoint.function_outputs == [output]
    assert reloaded.has_checkpoint(session_id) is True
