from pathlib import Path

from aelyn_career.applications import ApplicationsStore, ApplicationStatus, status_label


def test_record_creates_a_postule_entry(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")

    app = store.record(offer_id="1", title="Data Scientist", company="ACME")

    assert app.offer_id == "1"
    assert app.title == "Data Scientist"
    assert app.company == "ACME"
    assert app.status == ApplicationStatus.POSTULE
    assert app.applied_ts == app.updated_ts
    assert app.notes is None


def test_record_is_idempotent_and_never_resets_an_already_tracked_status(
    tmp_path: Path,
):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist", company="ACME")
    store.update_status("1", ApplicationStatus.ENTRETIEN)

    again = store.record(offer_id="1", title="Data Scientist", company="ACME")

    assert again.status == ApplicationStatus.ENTRETIEN


def test_update_status_changes_status_and_returns_none_for_unknown_offer(
    tmp_path: Path,
):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist", company="ACME")

    updated = store.update_status("1", ApplicationStatus.REFUSE)
    missing = store.update_status("unknown", ApplicationStatus.REFUSE)

    assert updated is not None
    assert updated.status == ApplicationStatus.REFUSE
    assert missing is None


def test_update_status_appends_notes_rather_than_overwriting(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist")

    store.update_status("1", ApplicationStatus.RELANCE, note="Relancé le 10/10.")
    updated = store.update_status(
        "1", ApplicationStatus.ENTRETIEN, note="Entretien fixé au 20/10."
    )

    assert updated is not None
    assert "Relancé le 10/10." in updated.notes
    assert "Entretien fixé au 20/10." in updated.notes


def test_find_by_text_matches_title_or_company(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist", company="EDF")
    store.record(offer_id="2", title="Data Engineer", company="ACME")

    by_company = store.find_by_text("edf")
    by_title = store.find_by_text("engineer")
    no_match = store.find_by_text("inconnu")

    assert by_company is not None and by_company.offer_id == "1"
    assert by_title is not None and by_title.offer_id == "2"
    assert no_match is None


def test_find_by_text_matches_a_company_name_with_punctuation(tmp_path: Path):
    # Bug réel observé en direct : le routage de l'agent envoie ici "le
    # texte déjà débarrassé des mots de commande" ("collective work",
    # extrait de "chez Collective.work"), jamais la phrase entière
    # (`find_by_text` lui-même ne filtre aucun mot-outil) ; une recherche
    # par sous-chaîne UNIQUE échouait toujours sur ce nom à cause du
    # point ("collective.work" != "collective work"), cf. `find_by_text`.
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist", company="Collective.work")

    found = store.find_by_text("collective work")

    assert found is not None
    assert found.offer_id == "1"


def test_list_filters_by_status_and_orders_by_most_recently_updated(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist")
    store.record(offer_id="2", title="Data Engineer")
    store.update_status("2", ApplicationStatus.ENTRETIEN)

    all_apps = store.list()
    only_entretien = store.list(ApplicationStatus.ENTRETIEN)

    assert [a.offer_id for a in all_apps] == ["2", "1"]
    assert [a.offer_id for a in only_entretien] == ["2"]


def test_status_label_covers_every_status():
    for status in ApplicationStatus:
        assert status_label(status)
