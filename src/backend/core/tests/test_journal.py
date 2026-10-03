from pathlib import Path

from aelyn.core.journal import ActionStatus, Journal


def test_revise_proposed_updates_only_pending_actions(tmp_path: Path):
    journal = Journal(tmp_path / "journal.db")
    action_id = journal.record(
        agent="email",
        action="repondre",
        summary="Promotion",
        status=ActionStatus.PROPOSED,
        payload={"urgence": 5},
    )

    revised = journal.revise_proposed(
        action_id,
        action="archiver",
        summary="Promotion sans urgence",
        payload={"urgence": 1},
    )

    assert revised is True
    action = journal.get(action_id)
    assert action is not None
    assert action.action == "archiver"
    assert action.summary == "Promotion sans urgence"
    assert action.payload == {"urgence": 1}

    journal.update_status(action_id, ActionStatus.EXECUTED)
    revised_after_execution = journal.revise_proposed(
        action_id,
        action="ignorer",
        summary="Ne doit pas changer",
        payload={},
    )

    assert revised_after_execution is False
    assert journal.get(action_id).action == "archiver"
