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


def test_delete_removes_a_tracked_application(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist", company="ACME")

    deleted = store.delete("1")

    assert deleted is True
    assert store.get("1") is None


def test_delete_is_idempotent_for_an_unknown_offer(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")

    assert store.delete("never-existed") is False


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


def test_set_description_and_questions(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")
    store.record(offer_id="1", title="Data Scientist", company="ACME")

    store.set_description("1", "Stage de 6 mois, modélisation statistique.")
    updated = store.set_questions("1", "1. Débouchés après le stage ?\n2. Équipe ?")

    assert updated.description == "Stage de 6 mois, modélisation statistique."
    assert "Débouchés" in updated.questions

    reloaded = store.get("1")
    assert reloaded.description == "Stage de 6 mois, modélisation statistique."
    assert reloaded.questions == updated.questions


def test_set_description_returns_none_for_unknown_offer(tmp_path: Path):
    store = ApplicationsStore(tmp_path / "applications.db")
    assert store.set_description("inconnu", "...") is None
    assert store.set_questions("inconnu", "...") is None


def test_migrates_a_pre_existing_database_without_losing_data(tmp_path: Path):
    """Bug réel évité : une base `applications.db` créée AVANT l'ajout
    des colonnes `description`/`questions` doit continuer à fonctionner
    (migration automatique à l'ouverture), sans perdre les lignes déjà
    suivies."""
    import sqlite3

    db_path = tmp_path / "applications.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE applications (
            offer_id VARCHAR PRIMARY KEY,
            title VARCHAR NOT NULL,
            company VARCHAR,
            status VARCHAR NOT NULL,
            applied_ts VARCHAR NOT NULL,
            updated_ts VARCHAR NOT NULL,
            notes TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO applications VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("old-1", "Stagiaire", "OldCo", "postule", "2026-01-01T00:00:00+00:00",
         "2026-01-01T00:00:00+00:00", None),
    )
    conn.commit()
    conn.close()

    store = ApplicationsStore(db_path)
    existing = store.get("old-1")

    assert existing is not None
    assert existing.title == "Stagiaire"
    assert existing.description is None
    assert existing.questions is None

    # Et les nouvelles colonnes sont bien utilisables après migration.
    updated = store.set_description("old-1", "Texte de l'offre récupéré après coup.")
    assert updated.description == "Texte de l'offre récupéré après coup."
