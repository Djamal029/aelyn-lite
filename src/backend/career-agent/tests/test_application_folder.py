from aelyn.core.config import settings
from aelyn_career.application_folder import _folder_name, save_application_folder
from aelyn_career.models import CVContent

from test_application_writer import make_writer


def _offer(**overrides) -> dict:
    offer = {
        "id": "offer-1",
        "title": "Analyst Intern",
        "company": "Analysis Group",
        "description": "Recherche un stage en data science et épidémiologie.",
    }
    offer.update(overrides)
    return offer


def _cv() -> CVContent:
    return CVContent(
        profil="Profil test.",
        experiences=[],
        projets=[],
        competences={},
        formation=[],
        certifications=[],
        langues=[],
        centres_interet=[],
    )


def test_folder_name_strips_invalid_filesystem_characters():
    assert _folder_name("A/B: C", "Role <X>") == "AB C - Role X"


def test_folder_name_falls_back_to_title_when_company_is_empty():
    assert _folder_name("", "Stage Data Science") == "Stage Data Science"


def test_save_application_folder_writes_all_five_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "applications_export_dir", tmp_path)
    writer = make_writer()

    folder = save_application_folder(
        writer, _offer(), cv=_cv(), lettre="Madame, Monsieur,\n\nCorps.\n\nDjamal TOE"
    )

    assert folder.parent == tmp_path
    assert folder.name == "Analysis Group - Analyst Intern"
    files = {p.name for p in folder.iterdir()}
    assert files == {
        "description.md", "CV.docx", "CV.pdf",
        "Lettre_de_motivation.docx", "Lettre_de_motivation.pdf",
    }


def test_save_application_folder_description_contains_the_offer_text(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "applications_export_dir", tmp_path)
    writer = make_writer()

    folder = save_application_folder(
        writer, _offer(), cv=_cv(), lettre="Djamal TOE\n\nCorps."
    )

    description = (folder / "description.md").read_text(encoding="utf-8")
    assert "Analyst Intern" in description
    assert "Analysis Group" in description
    assert "data science et épidémiologie" in description


def test_save_application_folder_reuses_same_folder_on_a_second_call(
    monkeypatch, tmp_path
):
    """Deux appels pour la même offre doivent écraser le contenu du MÊME
    dossier, jamais créer un deuxième dossier numéroté : une candidature
    reflète toujours son dernier état, pas un historique de versions."""
    monkeypatch.setattr(settings, "applications_export_dir", tmp_path)
    writer = make_writer()

    save_application_folder(writer, _offer(), cv=_cv(), lettre="Version 1")
    save_application_folder(writer, _offer(), cv=_cv(), lettre="Version 2")

    assert len(list(tmp_path.iterdir())) == 1


def test_save_application_folder_generates_cv_and_lettre_when_not_given(
    monkeypatch, tmp_path
):
    """Sans `cv`/`lettre` fournis, la fonction doit générer un brouillon
    déterministe elle-même (jamais planter faute d'arguments optionnels)."""
    monkeypatch.setattr(settings, "applications_export_dir", tmp_path)
    writer = make_writer()

    folder = save_application_folder(writer, _offer())

    assert (folder / "CV.pdf").exists()
    assert (folder / "Lettre_de_motivation.pdf").exists()
