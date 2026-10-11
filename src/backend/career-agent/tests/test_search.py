from unittest.mock import Mock

from aelyn_career.offer_cache import OfferCache
from aelyn_career.search import JobSearchService


def test_search_falls_back_to_other_sources_when_france_travail_connect_fails(monkeypatch, tmp_path):
    """Bug réel : sans FRANCE_TRAVAIL_CLIENT_ID/SECRET configurés (ou si le
    service est en panne), `connect()` lève une exception. Avant ce
    correctif, cette exception remontait sans filet et faisait planter
    TOUTE la recherche, y compris les sources sans clé API (RemoteOK,
    Remotive, Arbeitnow, Workday...) - exactement le cas d'une installation
    aelyn-lite fraîche n'ayant configuré aucun identifiant France Travail.
    `search()` doit se rabattre sur les autres sources plutôt que
    planter."""
    monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "true")

    offers_agent = Mock()
    offers_agent.access_token = None
    offers_agent.connect.side_effect = Exception("Authentification France Travail échouée (400)")
    offers_agent.keywords = "data scientist"

    fallback_offer = {
        "id": "remotive:1",
        "source": "remotive",
        "title": "Data Scientist",
        "company": "ACME",
        "location": "Remote",
        "contract_type": "UNKNOWN",
        "description": "Build analytics with Python.",
        "url": "https://remotive.example/1",
    }
    fake_adapter = Mock()
    fake_adapter.name = "remotive"
    fake_adapter.search.return_value = [fallback_offer]
    monkeypatch.setattr(
        "aelyn_career.search.available_source_adapters", lambda: [fake_adapter]
    )

    service = JobSearchService(offers_agent, cache=OfferCache(tmp_path / "offers.db"))

    results = service.search(keywords="data scientist", limit=5)

    offers_agent.connect.assert_called_once()
    # `search_offers` (l'appel API France Travail lui-même) ne doit jamais
    # être tenté puisque la connexion a échoué.
    offers_agent.search_offers.assert_not_called()
    assert [o["id"] for o in results] == ["remotive:1"]


def test_search_still_queries_france_travail_when_connect_succeeds(monkeypatch, tmp_path):
    """Non-régression : quand France Travail EST configurée/joignable, elle
    reste bien interrogée comme avant (le correctif ne doit pas la
    désactiver dans le cas nominal)."""
    offers_agent = Mock()
    offers_agent.access_token = None
    offers_agent.connect.side_effect = lambda: setattr(offers_agent, "access_token", "tok")
    offers_agent.keywords = "data scientist"
    offers_agent.search_offers.return_value = (
        [{"id": "ft:1", "intitule": "Data Scientist", "description": "..."}],
        1,
    )
    monkeypatch.setattr("aelyn_career.search.available_source_adapters", lambda: [])

    service = JobSearchService(offers_agent, cache=OfferCache(tmp_path / "offers.db"))
    results = service.search(keywords="data scientist", limit=5)

    offers_agent.connect.assert_called_once()
    offers_agent.search_offers.assert_called_once()
    assert len(results) == 1
