from unittest.mock import Mock

from aelyn_career.application_writer import ApplicationWriter
from aelyn_career.models import CVExperience
from aelyn_career.profil_manager import ProfilManager


def make_profile() -> dict:
    return {
        "profile": {
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
