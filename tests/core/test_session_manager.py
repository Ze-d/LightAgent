from app.core.session_manager import InMemorySessionManager


def test_create_and_load_session():
    manager = InMemorySessionManager()

    session_id = manager.create([
        {"role": "system", "content": "You are a test agent."}
    ])

    history = manager.load(session_id)

    assert history is not None
    assert len(history) == 1
    assert history[0]["role"] == "system"


def test_append_message():
    manager = InMemorySessionManager()

    session_id = manager.create([
        {"role": "system", "content": "You are a test agent."}
    ])

    manager.append(session_id, {"role": "user", "content": "你好"})
    history = manager.load(session_id)

    assert history is not None
    assert len(history) == 2
    assert history[-1]["role"] == "user"


def test_exists_and_delete():
    manager = InMemorySessionManager()

    session_id = manager.create([
        {"role": "system", "content": "You are a test agent."}
    ])

    assert manager.exists(session_id) is True

    manager.delete(session_id)

    assert manager.exists(session_id) is False
    assert manager.load(session_id) is None
def test_load_returns_copy():
    manager = InMemorySessionManager()

    session_id = manager.create([
        {"role": "system", "content": "You are a test agent."}
    ])

    history = manager.load(session_id)
    assert history is not None

    history.append({"role": "user", "content": "外部修改"})

    history2 = manager.load(session_id)
    assert history2 is not None
    assert len(history2) == 1