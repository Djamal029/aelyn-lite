from unittest.mock import Mock, patch

from aelyn.core.config import settings
from aelyn_career.application_writer import ApplicationSelection, ApplicationWriter, _merge_indices
from aelyn_career.models import CVExperience
from aelyn_career.profil_manager import ProfilManager, validate_profil_structure


def test_merge_indices_keeps_floor_order_and_appends_new_entries_within_limit():
    assert _merge_indices([2, 0], [0, 4, 1], limit=3) == [2, 0, 4]


def test_merge_indices_never_exceeds_limit_even_with_many_extras():
    assert _merge_indices([0], [1, 2, 3, 4], limit=3) == [0, 1, 2]


def make_profile() -> dict:
    return {
        "profile": {
            "education": [
                {
                    "institution": "ENSAI",
                    "degree": "Diplôme d'ingénieur",
                    "field": "Science des données, Machine Learning, Intelligence Artificielle",
                    "location": "France, Rennes",
                    "period": "2024-2027",
                },
                {
                    "institution": "Université Nazi Boni",
                    "degree": "Licence",
                    "field": "Statistique et Informatique",
                    "location": "Burkina Faso",
                    "period": "2020-2023",
                },
            ],
            "skills": {
                "Data Science": ["Python", "SQL"],
                "Statistique": ["R"],
            },
            "projects": {
                "academic_projects": [
                    {"title": "Statistical trial analysis", "description": "Analysis of trial outcomes."}
                ],
                "bachelor_projects": [],
                "personal_projects": [],
            },
            "certifications": {
                "website": [{"title": "Data Science Certificate", "issuer": "Example Institute"}],
                "linkedin": [{"title": "Cloud Fundamentals", "issuer": "Example Academy"}],
            },
            "languages": [{"language": "French", "level": "Fluent"}],
            "interests": ["Reading"],
            "experience": [
                {
                    "role": "Stagiaire Data Scientist",
                    "company": "Servier France",
                    "period": "May 2026 - September 2026",
                    "location": "Saclay, France",
                    "description": (
                        "Développement d'une méthode statistique pour les essais cliniques."
                    ),
                    "highlights": ["Built a robust probability-of-success framework"],
                    "results": {"deployment": "Interactive application deployed"},
                },
                {
                    "role": "Stagiaire Data Science",
                    "company": "Les Vieilles Charrues",
                    "period": "June 2026 - August 2026",
                    "location": "Carhaix-Plouguer, France",
                    "description": "Analyse statistique des candidatures de bénévoles.",
                    "highlights": ["Studied approximately 7500 volunteer applications"],
                },
                {
                    "role": "Intern in Biostatistics",
                    "company": "Centre MURAZ",
                    "period": "August 2023 - December 2023",
                    "location": "Bobo-Dioulasso, Burkina Faso",
                    "description": "Statistical analyses for public health research.",
                    "highlights": ["Performed exploratory multivariate analyses"],
                },
                {
                    "role": "Intern in Biostatistics",
                    "company": "Centre MURAZ",
                    "period": "January 2024 - April 2024",
                    "location": "Bobo-Dioulasso, Burkina Faso",
                    "description": (
                        "Evaluation of malaria-reduction interventions with mixed models."
                    ),
                    "highlights": [
                        (
                            "Evaluated public health interventions to reduce malaria incidence"
                        ),
                        "Applied Poisson and negative-binomial mixed-effects models",
                    ],
                    "methodology": ["Poisson mixed-effects models"],
                    "results": {
                        "malaria_reduction": (
                            "approximately 42% reduction in malaria occurrence rates"
                        )
                    },
                },
            ],
        }
    }


def make_writer() -> ApplicationWriter:
    return ApplicationWriter(ProfilManager(make_profile()), llm=Mock())


def test_profile_chunks_include_experience_highlights_methods_and_results():
    chunks = ProfilManager(make_profile()).parse_profile()
    january_muraz = next(
        chunk for chunk in chunks
        if chunk["type"] == "experience"
        and chunk["metadata"]["period"] == "January 2024 - April 2024"
    )

    assert "Poisson mixed-effects models" in january_muraz["text"]
    assert "approximately 42% reduction" in january_muraz["text"]


def test_cv_keeps_distinct_same_employer_experiences_and_omitted_recent_period():
    writer = make_writer()
    proposed = [
        CVExperience(
            role="Stagiaire Data Scientist",
            entreprise="Servier France",
            periode="May 2026 - September 2026",
            puces=["Built a robust probability-of-success framework"],
        ),
        CVExperience(
            role="Intern in Biostatistics",
            entreprise="Centre MURAZ",
            periode="August 2023 - December 2023",
            puces=["Performed exploratory multivariate analyses"],
        ),
    ]

    validated = writer._validate_experiences(proposed)
    muraz = [
        experience for experience in validated
        if experience.entreprise == "Centre MURAZ"
    ]

    assert [experience.periode for experience in muraz] == [
        "January 2024 - April 2024",
        "August 2023 - December 2023",
    ]
    assert any("approximately 42% reduction" in bullet for bullet in muraz[0].puces)
    assert len(validated) == 4


def test_cv_formation_comes_from_profile_not_llm():
    """`cv.formation` (simple `list[str]`) n'avait aucune validation,
    contrairement aux expériences/projets : le LLM pouvait reformuler ou
    omettre un diplôme malgré le prompt. `_real_formation` doit retrouver
    les deux entrées réelles, dans l'ordre du profil, peu importe ce que
    le LLM aurait produit."""
    writer = make_writer()
    formation = writer._real_formation()

    assert formation == [
        "Diplôme d'ingénieur en Science des données, Machine Learning, "
        "Intelligence Artificielle, ENSAI (2024-2027)",
        "Licence en Statistique et Informatique, Université Nazi Boni (2020-2023)",
    ]


def test_cv_replaces_llm_period_with_exact_profile_period():
    writer = make_writer()
    proposed = [
        CVExperience(
            role="Intern in Biostatistics",
            entreprise="Centre MURAZ",
            periode="Janvier 2024 - Avril 2024",
            puces=["Applied Poisson and negative-binomial mixed-effects models"],
        )
    ]

    validated = writer._validate_experiences(proposed)
    january_muraz = next(
        experience for experience in validated
        if experience.periode == "January 2024 - April 2024"
    )

    assert january_muraz.entreprise == "Centre MURAZ"
    assert any("Poisson" in bullet for bullet in january_muraz.puces)


def test_cv_does_not_keep_non_numeric_bullet_from_another_experience():
    writer = make_writer()
    proposed = [
        CVExperience(
            role="Stagiaire Data Scientist",
            entreprise="Servier France",
            periode="May 2026 - September 2026",
            puces=["Analyzed volunteer applications for a music festival"],
        )
    ]

    validated = writer._validate_experiences(proposed)
    servier = next(
        experience for experience in validated
        if experience.entreprise == "Servier France"
    )

    assert "Analyzed volunteer applications for a music festival" not in servier.puces
    assert all("volunteer" not in bullet.lower() for bullet in servier.puces)


def test_draft_cv_rebuilds_from_profile_when_llm_returns_invalid_evidence_ids(monkeypatch):
    monkeypatch.setattr(settings, "application_selection_mode", "llm")
    writer = make_writer()
    writer.llm.structured.return_value = ApplicationSelection(
        experience_indices=[999],
        project_indices=[999],
        skill_indices=[999],
        certification_indices=[999],
    )

    cv = writer.draft_cv("Data Scientist\nDescription de l'offre")

    assert "100" not in cv.profil
    assert "Data Scientist" in cv.profil
    servier = next(exp for exp in cv.experiences if exp.entreprise == "Servier France")
    festival = next(exp for exp in cv.experiences if exp.entreprise == "Les Vieilles Charrues")
    assert all("volunteer" not in bullet.lower() for bullet in servier.puces)
    assert any("volunteer" in bullet.lower() for bullet in festival.puces)
    assert [(project.titre, project.description) for project in cv.projets] == [
        ("Statistical trial analysis", "Analysis of trial outcomes.")
    ]
    assert cv.competences == {"Data Science": ["Python", "SQL"], "Statistique": ["R"]}
    assert cv.formation == writer._real_formation()
    # Déterministe même en mode "llm" (cf. `_select_application_items`) :
    # les deux certifications du profil ont un score mots-clés non nul
    # pour "Data Scientist", l'id invalide du LLM (999) n'entre pas en jeu.
    assert cv.certifications == ["Data Science Certificate", "Cloud Fundamentals"]
    assert cv.langues == ["French : Fluent"]
    assert cv.centres_interet == ["Reading"]
    writer.llm.structured.assert_called_once()
    assert writer.llm.structured.call_args.kwargs["schema"] is ApplicationSelection


def test_llm_mode_merges_with_keyword_floor_never_drops_relevant_evidence(monkeypatch):
    """Le mode "llm" ne REMPLACE plus la sélection par mots-clés, il la
    COMPLÈTE (cf. `_merge_indices`) : un CV réel ne doit jamais perdre une
    expérience/un projet/une compétence que le simple recouvrement lexical
    jugeait déjà pertinent, même si le LLM local propose autre chose."""
    monkeypatch.setattr(settings, "application_selection_mode", "llm")
    writer = make_writer()
    writer.llm.structured.return_value = ApplicationSelection(
        experience_indices=[1, 999],
        project_indices=[0],
        skill_indices=[0, 0, 999],
        certification_indices=[1],
    )

    selected = writer._select_application_items("Data Scientist\nPython analytics")

    # Plancher mots-clés (4 expériences, aucune pertinente lexicalement :
    # toutes gardées à égalité) fusionné avec l'ajout LLM (déjà inclus).
    assert selected.experience_indices == [0, 1, 2, 3]
    assert selected.project_indices == [0]
    # Plancher mots-clés : les deux compétences "Data Science" (Python, SQL)
    # partagent un mot avec l'offre, "Statistique" (R) non.
    assert selected.skill_indices == [0, 1, 2]
    # Toujours déterministe (mots-clés), même en mode "llm" : le LLM a beau
    # proposer [1] ("Cloud Fundamentals"), seule "Data Science Certificate"
    # (index 0) partage un mot avec l'offre - la sortie LLM est ignorée.
    assert selected.certification_indices == [0, 1]


def test_keywords_mode_does_not_call_the_llm(monkeypatch):
    monkeypatch.setattr(settings, "application_selection_mode", "keywords")
    writer = make_writer()

    selected = writer._select_application_items("Data Scientist\nPython analytics")

    assert selected.experience_indices
    assert selected.skill_indices
    writer.llm.structured.assert_not_called()


def test_certification_matches_offer_via_domain_synonym_not_literal_overlap():
    """Constaté en direct : une offre qui dit "intelligence artificielle"/
    "agents IA" ne partage AUCUN mot avec une certification intitulée
    "Machine Learning Specialization" - sans `expand_domain_terms`
    (job_sources.py), la certification la plus pertinente disparaissait
    silencieusement pour ce type d'offre, au profit des 3 premières
    certifications du profil sans rapport avec l'offre."""
    profile = make_profile()
    profile["profile"]["certifications"]["linkedin"].append(
        {"title": "Machine Learning Specialization", "issuer": "DeepLearning.AI"}
    )
    writer = ApplicationWriter(ProfilManager(profile), llm=Mock())

    cv = writer.draft_cv(
        "Stage Intelligence Artificielle\n"
        "Description de l'offre :\n"
        "Construction d'agents IA et de solutions generatives."
    )

    assert "Machine Learning Specialization" in cv.certifications


def test_ambiguous_same_employer_experience_does_not_guess_from_partial_labels():
    writer = make_writer()

    result = writer._real_experience_metadata(
        entreprise="Centre MURAZ",
        periode="2030-2031",
        role="Researcher",
    )

    assert result is None


def test_cover_letter_and_refinement_use_only_profile_and_offer_facts(monkeypatch):
    monkeypatch.setattr(settings, "application_selection_mode", "keywords")
    writer = make_writer()
    from aelyn_career.application_writer import offer_text

    offer = offer_text({
        "intitule": "Data Scientist",
        "entreprise": {"nom": "ACME"},
        "description": "Statistical analysis and Python.",
        "url": "https://example.com/apply",
        "dateLimite": "2026-12-01",
    })
    with patch.object(writer, "contact_header", return_value=""):
        letter = writer.draft_cover_letter(offer)
        refined = writer.refine_cover_letter(
            "J'ai un doctorat inventé et dirigé une équipe de 100 personnes.",
            offer,
        )

    for text in (letter, refined):
        assert "Data Scientist" in text
        assert "ACME" in text
        assert "inventé" not in text.lower()
        assert "100 personnes" not in text
        assert "Veuillez agréer" in text
    writer.llm.text.assert_not_called()


def test_profile_validation_rejects_missing_location_before_profile_is_saved():
    profile = make_profile()
    del profile["profile"]["experience"][0]["location"]

    errors = validate_profil_structure(profile)

    assert any("experience[0]" in error and "location" in error for error in errors)
