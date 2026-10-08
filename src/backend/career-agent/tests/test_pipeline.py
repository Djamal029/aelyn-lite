from unittest.mock import Mock

import numpy as np

from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.pipeline import find_best_matches


def test_profile_scoring_pipeline_accepts_multi_source_offer(monkeypatch):
    offer = {
        "id": "remotive:42",
        "source": "remotive",
        "title": "Data Scientist",
        "company": "ACME",
        "location": "Remote",
        "contract_type": "UNKNOWN",
        "description": "Build analytics with Python.",
    }
    search_service = Mock()
    search_service.search.return_value = [offer]
    monkeypatch.setattr("aelyn_career.pipeline.JobSearchService", lambda ft: search_service)

    structurer = Mock()
    structurer.structure_offers.return_value = {
        "competences_requises": ["Python"],
        "niveau_requis": "junior",
    }
    embedder = Mock()
    embedder.final_score.return_value = np.array([0.81])
    embedder.query_relevance.return_value = 0.9
    profil_manager = Mock()
    profil_manager.parse_profile.return_value = [
        {"type": "skill_category", "title": "Data Science", "text": "Python", "metadata": {"category": "Data Science"}},
    ]

    result = find_best_matches(
        keywords="data scientist",
        top_n=1,
        max_offers=7,
        ft=FTOffers(access_token="token"),
        structurer=structurer,
        embedder=embedder,
        profil_manager=profil_manager,
    )

    assert len(result) == 1
    assert result[0]["id"] == "remotive:42"
    assert result[0]["source"] == "remotive"
    assert result[0]["title"] == "Data Scientist"
    search_service.search.assert_called_once_with(
        contract_type=None,
        keywords="data scientist",
        limit=7,
    )
    embedder.query_relevance.assert_called_once_with(
        "data scientist",
        "Data Scientist",
        ["Python"],
    )