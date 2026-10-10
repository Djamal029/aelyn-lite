from pathlib import Path

from aelyn.core.config import settings
from aelyn.core.journal import Journal
from aelyn.core.seen_offers import SeenOffers

from aelyn_career.proactive_search import run_proactive_search_once
from test_application_writer import make_writer


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


def test_run_proactive_search_once_drafts_a_folder_when_auto_draft_is_enabled(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(settings, "proactive_search_auto_draft", True)
    monkeypatch.setattr(settings, "applications_export_dir", tmp_path / "candidatures")
    offres = [{"id": "1", "intitule": "Data Scientist", "entreprise": {"nom": "ACME"}}]
    monkeypatch.setattr(
        "aelyn_career.proactive_search.find_best_matches", lambda **kw: offres
    )
    seen = SeenOffers(tmp_path / "seen.db")
    journal = Journal(tmp_path / "journal.db")

    run_proactive_search_once(
        seen_offers=seen, journal=journal, writer=make_writer()
    )

    entries = journal.since(hours=24, agent="career")
    assert "dossier de candidature préparé" in entries[0].summary
    assert entries[0].payload["application_folder"] is not None
    folders = list((tmp_path / "candidatures").iterdir())
    assert len(folders) == 1
    assert {p.name for p in folders[0].iterdir()} == {
        "description.md", "CV.docx", "CV.pdf",
        "Lettre_de_motivation.docx", "Lettre_de_motivation.pdf",
    }


def test_run_proactive_search_once_never_drafts_a_folder_by_default(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(settings, "applications_export_dir", tmp_path / "candidatures")
    offres = [{"id": "1", "intitule": "Data Scientist", "entreprise": {"nom": "ACME"}}]
    monkeypatch.setattr(
        "aelyn_career.proactive_search.find_best_matches", lambda **kw: offres
    )
    seen = SeenOffers(tmp_path / "seen.db")
    journal = Journal(tmp_path / "journal.db")

    run_proactive_search_once(seen_offers=seen, journal=journal)

    entries = journal.since(hours=24, agent="career")
    assert entries[0].payload["application_folder"] is None
    assert not (tmp_path / "candidatures").exists()
