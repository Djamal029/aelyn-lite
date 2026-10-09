from pathlib import Path

from aelyn.core.journal import Journal
from aelyn.core.seen_offers import SeenOffers

from aelyn_career.proactive_search import run_proactive_search_once


def test_run_proactive_search_once_journals_only_genuinely_new_offers(
    monkeypatch, tmp_path: Path
):
    offres = [
        {
            "id": "1",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "score": 0.8,
        },
        {
            "id": "2",
            "intitule": "Data Engineer",
            "entreprise": {"nom": "Globex"},
            "score": 0.7,
        },
    ]
    monkeypatch.setattr(
        "aelyn_career.proactive_search.find_best_matches", lambda **kw: offres
    )
    seen = SeenOffers(tmp_path / "seen.db")
    seen.filter_new(["1"])  # l'offre 1 a déjà été vue lors d'un cycle précédent
    journal = Journal(tmp_path / "journal.db")

    new_count = run_proactive_search_once(seen_offers=seen, journal=journal)

    assert new_count == 1
    entries = journal.since(hours=24, agent="career")
    assert len(entries) == 1
    assert entries[0].target == "2"
    assert "Data Engineer" in entries[0].summary
    assert "Globex" in entries[0].summary


def test_run_proactive_search_once_journals_nothing_on_a_second_identical_run(
    monkeypatch, tmp_path: Path
):
    offres = [{"id": "1", "intitule": "Data Scientist", "score": 0.8}]
    monkeypatch.setattr(
        "aelyn_career.proactive_search.find_best_matches", lambda **kw: offres
    )
    seen = SeenOffers(tmp_path / "seen.db")
    journal = Journal(tmp_path / "journal.db")

    first = run_proactive_search_once(seen_offers=seen, journal=journal)
    second = run_proactive_search_once(seen_offers=seen, journal=journal)

    assert first == 1
    assert second == 0
    assert len(journal.since(hours=24, agent="career")) == 1


def test_run_proactive_search_once_returns_zero_and_never_raises_on_search_failure(
    monkeypatch, tmp_path: Path
):
    def _boom(**kwargs):
        raise RuntimeError("France Travail injoignable")

    monkeypatch.setattr("aelyn_career.proactive_search.find_best_matches", _boom)
    seen = SeenOffers(tmp_path / "seen.db")
    journal = Journal(tmp_path / "journal.db")

    new_count = run_proactive_search_once(seen_offers=seen, journal=journal)

    assert new_count == 0
    assert journal.since(hours=24, agent="career") == []
