from unittest.mock import Mock

from aelyn.core.journal import Journal
from aelyn_career.llm_structurer import LLMOfferStructurer
from aelyn_career.models import NiveauRequis, OffreStructuree


def test_structure_offers_passes_a_wide_context_window(tmp_path, monkeypatch):
    """Bug réel observé en direct : sans `num_ctx` explicite, Ollama
    limite la fenêtre de contexte à 4096 tokens (prompt + sortie
    confondus) - une offre à description verbeuse (beaucoup de
    compétences techniques listées) tronquait la sortie JSON en plein
    milieu d'une chaîne sur les 3 tentatives, faisant échouer toute la
    recherche d'offres. `structure_offers` doit toujours demander une
    fenêtre large pour laisser la place à un long intitulé/une longue
    description ET une liste de compétences complète en sortie."""
    monkeypatch.setattr(
        "aelyn_career.llm_structurer.LLMClient", lambda model: Mock(
            structured=Mock(return_value=OffreStructuree(
                competences_requises=["Python"], niveau_requis=NiveauRequis.JUNIOR,
            ))
        ),
    )
    journal = Journal(tmp_path / "journal.db")
    structurer = LLMOfferStructurer(journal=journal)

    structurer.structure_offers("offer-1", "Une offre très détaillée...")

    kwargs = structurer.llm_client.structured.call_args.kwargs
    assert kwargs["num_ctx"] is not None
    assert kwargs["num_ctx"] >= 8192
