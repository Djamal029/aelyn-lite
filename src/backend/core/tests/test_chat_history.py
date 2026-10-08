from pathlib import Path

from aelyn.core.chat_history import ChatHistory


def test_recent_before_id_paginates_to_older_turns(tmp_path: Path):
    history = ChatHistory(tmp_path / "chat.db")
    ids = [history.append("user", f"message {i}") for i in range(5)]

    first_page = history.recent(limit=2)
    assert [m.content for m in first_page] == ["message 3", "message 4"]

    older_page = history.recent(limit=2, before_id=first_page[0].id)
    assert [m.content for m in older_page] == ["message 1", "message 2"]

    oldest_page = history.recent(limit=2, before_id=older_page[0].id)
    assert [m.content for m in oldest_page] == ["message 0"]
    assert oldest_page[0].id == ids[0]
