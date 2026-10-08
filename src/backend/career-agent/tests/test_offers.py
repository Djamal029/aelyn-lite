"""Tests pour FTOffers (career-agent/src/aelyn_career/france_travail/offers.py).

Aucun appel réseau réel : requests.post/requests.get sont mockés, donc ces
tests passent même sans identifiants France Travail dans .env.
"""

from unittest.mock import Mock, patch

import pytest

from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.offer_cache import OfferCache
from aelyn_career.search import JobSearchService
from aelyn_career.source_adapters import CareerjetAdapter, RemoteOKAdapter


def make_response(status_code: int, json_data: dict):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    return response


class TestConnect:
    @patch("aelyn_career.france_travail.offers.requests.post")
    def test_connect_success_sets_access_token(self, mock_post):
        mock_post.return_value = make_response(200, {"access_token": "abc123"})

        ft = FTOffers()
        ft.connect()

        assert ft.access_token == "abc123"

    @patch("aelyn_career.france_travail.offers.requests.post")
    def test_connect_sends_client_credentials(self, mock_post):
        mock_post.return_value = make_response(200, {"access_token": "abc123"})

        ft = FTOffers()
        ft.connect()

        _, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "client_credentials"
        assert kwargs["data"]["client_id"] == ft.client_id()
        assert kwargs["data"]["client_secret"] == ft.client_secret()

    @patch("aelyn_career.france_travail.offers.requests.post")
    def test_connect_failure_raises(self, mock_post):
        mock_post.return_value = make_response(401, {})

        ft = FTOffers()
        with pytest.raises(Exception):
            ft.connect()

    @patch("aelyn_career.france_travail.offers.requests.post")
    def test_connect_refreshes_existing_token(self, mock_post):
        """Un appel à `connect()` doit toujours adopter le jeton FRAIS reçu,
        jamais garder l'ancien : un `FTOffers` de longue durée (singleton
        côté API) ne se reconnecte qu'une fois à la création sans ce
        comportement, et tout jeton expiré depuis cassait la recherche
        jusqu'au redémarrage du serveur (bug réel observé en direct)."""
        mock_post.return_value = make_response(200, {"access_token": "nouveau"})

        ft = FTOffers(access_token="deja_present")
        ft.connect()

        assert ft.access_token == "nouveau"


class TestSearchOffersFor:
    """`search_offers_for` : une requête pour UN seul mot-clé."""

    @patch("aelyn_career.france_travail.offers.requests.post")
    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_401_triggers_reconnect_and_retry(self, mock_get, mock_post):
        """Jeton expiré (401) : une seule reconnexion automatique, puis la
        recherche retente avec le nouveau jeton et réussit, sans que
        l'appelant n'ait rien à faire (bug réel : un `FTOffers` de longue
        durée ne se reconnectait jamais après la première fois)."""
        mock_post.return_value = make_response(200, {"access_token": "frais"})
        mock_get.side_effect = [
            make_response(401, {}),
            make_response(200, {"resultats": [{"id": "1"}], "filtresPossibles": None}),
        ]

        ft = FTOffers(access_token="perime")
        offres, _ = ft.search_offers_for("data scientist")

        assert ft.access_token == "frais"
        assert offres == [{"id": "1"}]
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer frais"

    @patch("aelyn_career.france_travail.offers.requests.post")
    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_401_twice_still_raises(self, mock_get, mock_post):
        """Si le jeton rafraîchi échoue ENCORE (ex. identifiants invalides,
        pas juste expirés), on ne boucle pas indéfiniment : une seule
        tentative de reconnexion, puis on remonte l'erreur."""
        mock_post.return_value = make_response(200, {"access_token": "toujours_mauvais"})
        mock_get.side_effect = [make_response(401, {}), make_response(401, {})]

        ft = FTOffers(access_token="perime")
        with pytest.raises(Exception, match="401"):
            ft.search_offers_for("data scientist")

        assert mock_get.call_count == 2

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_returns_resultats_and_filters(self, mock_get):
        mock_get.return_value = make_response(
            200,
            {
                "resultats": [{"id": "1", "intitule": "Data Scientist"}],
                "filtresPossibles": [{"filtre": "typeContrat"}],
            },
        )

        ft = FTOffers(access_token="token")
        offres, filtres = ft.search_offers_for("Data Scientist")

        assert offres == [{"id": "1", "intitule": "Data Scientist"}]
        assert filtres == [{"filtre": "typeContrat"}]

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_sends_authorization_header(self, mock_get):
        mock_get.return_value = make_response(200, {"resultats": []})

        ft = FTOffers(access_token="token")
        ft.search_offers_for("Data Scientist")

        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer token"

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_sends_expected_params(self, mock_get):
        mock_get.return_value = make_response(200, {"resultats": []})

        ft = FTOffers(access_token="token")
        ft.departments = "35,75"
        ft.search_offers_for("Machine Learning")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["motsCles"] == "Machine Learning"
        assert kwargs["params"]["departement"] == "35,75"
        assert kwargs["params"]["sort"] == 1

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_explicit_limit_is_sent_as_range_header(self, mock_get):
        response = make_response(206, {"resultats": [{"id": "1"}]})
        response.headers = {"Content-Range": "offre 0-19/1"}
        mock_get.return_value = response

        ft = FTOffers(access_token="token")
        offres, _ = ft.search_offers_for("Data Scientist", limit=20)

        assert len(offres) == 1
        assert mock_get.call_args.kwargs["headers"]["Range"] == "0-19"

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_paginates_when_limit_exceeds_api_page_size(self, mock_get):
        first_page = [{"id": str(i)} for i in range(150)]
        second_page = [{"id": str(i)} for i in range(150, 180)]
        first = make_response(206, {"resultats": first_page})
        first.headers = {"Content-Range": "offre 0-149/180"}
        second = make_response(206, {"resultats": second_page})
        second.headers = {"Content-Range": "offre 150-179/180"}
        mock_get.side_effect = [first, second]

        ft = FTOffers(access_token="token")
        offres, _ = ft.search_offers_for("Data Scientist", limit=180)

        assert len(offres) == 180
        ranges = [
            call.kwargs["headers"]["Range"]
            for call in mock_get.call_args_list
        ]
        assert ranges == ["0-149", "150-179"]

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_cdi_sends_type_contrat(self, mock_get):
        mock_get.return_value = make_response(200, {"resultats": []})

        ft = FTOffers(access_token="token")
        ft.search_offers_for("Data Scientist", contract_type="cdi")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["typeContrat"] == "CDI"

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_cdd_sends_type_contrat(self, mock_get):
        mock_get.return_value = make_response(200, {"resultats": []})

        ft = FTOffers(access_token="token")
        ft.search_offers_for("Data Scientist", contract_type="CDD")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["typeContrat"] == "CDD"

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_alternance_filters_on_boolean_field(self, mock_get):
        # `natureContrat=E1,E2` ne filtre pas réellement côté API (vérifié en
        # direct) : on ne l'envoie plus, on filtre sur le champ `alternance`.
        mock_get.return_value = make_response(
            200,
            {
                "resultats": [
                    {"id": "1", "intitule": "Data Scientist", "alternance": False},
                    {"id": "2", "intitule": "Alternance Data Scientist", "alternance": True},
                ]
            },
        )

        ft = FTOffers(access_token="token")
        offres, _ = ft.search_offers_for("Data Scientist", contract_type="alternance")

        _, kwargs = mock_get.call_args
        assert "natureContrat" not in kwargs["params"]
        assert [o["id"] for o in offres] == ["2"]

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_stage_sends_no_server_side_contract_filter_and_filters_on_keyword(self, mock_get):
        # Pas de "typeContrat" envoyé à l'API pour "stage" (contrairement à
        # cdi/cdd) : un stage n'étant pas un contrat de travail légal,
        # France Travail ne le range PAS fiablement sous un typeContrat
        # donné (vérifié en direct : CDI, MIS, LIB selon l'employeur,
        # jamais exclusivement CDD) - un filtre serveur "CDD" exclurait
        # alors de vraies offres de stage avant même ce filtre texte.
        mock_get.return_value = make_response(
            200,
            {
                "resultats": [
                    {"id": "1", "intitule": "Data Scientist", "alternance": False, "description": "", "typeContrat": "CDI"},
                    {"id": "2", "intitule": "Stage Data Scientist", "alternance": False, "description": "", "typeContrat": "MIS"},
                    {"id": "3", "intitule": "Alternance Data Scientist", "alternance": True, "description": "", "typeContrat": "CDD"},
                    {"id": "4", "intitule": "Data Scientist", "alternance": False, "description": "Stage de 6 mois", "typeContrat": "CDD"},
                ]
            },
        )

        ft = FTOffers(access_token="token")
        offres, _ = ft.search_offers_for("Data Scientist", contract_type="stage")

        _, kwargs = mock_get.call_args
        assert "typeContrat" not in kwargs["params"]
        assert {o["id"] for o in offres} == {"2", "4"}

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_204_is_success_with_no_results(self, mock_get):
        mock_get.return_value = make_response(204, {})

        ft = FTOffers(access_token="token")
        offres, filtres = ft.search_offers_for("Data Scientist")

        assert offres == []
        assert filtres is None

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_206_partial_content_is_success(self, mock_get):
        mock_get.return_value = make_response(206, {"resultats": [{"id": "1"}]})

        ft = FTOffers(access_token="token")
        offres, _ = ft.search_offers_for("Data Scientist")

        assert offres == [{"id": "1"}]

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_failure_raises(self, mock_get):
        mock_get.return_value = make_response(500, {})

        ft = FTOffers(access_token="token")
        with pytest.raises(Exception):
            ft.search_offers_for("Data Scientist")

    @patch("aelyn_career.france_travail.offers.requests.get")
    def test_missing_resultats_returns_empty_list(self, mock_get):
        mock_get.return_value = make_response(200, {"filtresPossibles": []})

        ft = FTOffers(access_token="token")
        offres, _ = ft.search_offers_for("Data Scientist")

        assert offres == []


class TestSearchOffers:
    """`search_offers` : une recherche par mot-clé, résultats fusionnés."""

    def test_calls_search_offers_for_once_per_keyword(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist,Machine Learning,IA"

        with patch.object(ft, "search_offers_for", return_value=([], None)) as mock_search:
            ft.search_offers()

        appels = [call.args[0] for call in mock_search.call_args_list]
        assert appels == ["Data Scientist", "Machine Learning", "IA"]

    def test_keywords_override_uses_given_keywords(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist"

        with patch.object(ft, "search_offers_for", return_value=([], None)) as mock_search:
            ft.search_offers(keywords="EDF,Roche")

        appels = [call.args[0] for call in mock_search.call_args_list]
        assert appels == ["EDF", "Roche"]

    def test_empty_string_keywords_falls_back_to_default(self):
        # Régression : un LLM peut renvoyer "" plutôt que None pour un champ
        # optionnel non rempli ; "" n'est pas None, donc un simple `is not
        # None` traiterait ça comme "aucun mot-clé" et ne chercherait rien.
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist"

        with patch.object(ft, "search_offers_for", return_value=([], None)) as mock_search:
            ft.search_offers(keywords="")

        appels = [call.args[0] for call in mock_search.call_args_list]
        assert appels == ["Data Scientist"]

    def test_merges_and_dedupes_by_id(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist,Machine Learning"

        offre_commune = {"id": "1", "intitule": "Data Scientist / ML"}
        offre_unique = {"id": "2", "intitule": "Machine Learning Engineer"}

        with patch.object(
            ft,
            "search_offers_for",
            side_effect=[
                ([offre_commune], [{"filtre": "typeContrat"}]),
                ([offre_commune, offre_unique], None),
            ],
        ):
            offres, filtres = ft.search_offers()

        assert {o["id"] for o in offres} == {"1", "2"}
        assert filtres == [{"filtre": "typeContrat"}]

    def test_ignores_extra_whitespace_in_keywords(self):
        ft = FTOffers(access_token="token")
        ft.keywords = " Data Scientist ,  , Machine Learning "

        with patch.object(ft, "search_offers_for", return_value=([], None)) as mock_search:
            ft.search_offers()

        appels = [call.args[0] for call in mock_search.call_args_list]
        assert appels == ["Data Scientist", "Machine Learning"]

    def test_forwards_contract_type_to_each_call(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist,Machine Learning"

        with patch.object(ft, "search_offers_for", return_value=([], None)) as mock_search:
            ft.search_offers(contract_type="cdi")

        for call in mock_search.call_args_list:
            assert call.kwargs["contract_type"] == "cdi"

    def test_sorts_results_by_most_recent_first(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist"

        ancienne = {"id": "1", "dateCreation": "2026-01-01T00:00:00.000Z"}
        recente = {"id": "2", "dateCreation": "2026-09-01T00:00:00.000Z"}

        with patch.object(ft, "search_offers_for", return_value=([ancienne, recente], None)):
            offres, _ = ft.search_offers()

        assert [o["id"] for o in offres] == ["2", "1"]

    def test_deduplicates_same_visible_job_even_if_ids_differ(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist"
        recent = {
            "id": "1",
            "intitule": "Analyste risques bancaires",
            "entreprise": {"nom": "Banque Exemple"},
            "lieuTravail": {"libelle": "Paris"},
            "typeContrat": "CDI",
            "dateCreation": "2026-09-02",
        }
        duplicate = {**recent, "id": "2", "dateCreation": "2026-09-01"}
        other_employer = {
            **recent,
            "id": "3",
            "entreprise": {"nom": "Autre Banque"},
        }

        with patch.object(
            ft,
            "search_offers_for",
            return_value=([recent, duplicate, other_employer], None),
        ):
            offres, _ = ft.search_offers()

        assert [offre["id"] for offre in offres] == ["1", "3"]

    def test_search_limit_is_applied_after_merging_keywords(self):
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist,Machine Learning"
        results = [
            {"id": "1", "intitule": "Offre 1"},
            {"id": "2", "intitule": "Offre 2"},
            {"id": "3", "intitule": "Offre 3"},
        ]

        with patch.object(ft, "search_offers_for", return_value=(results, None)):
            offres, _ = ft.search_offers(limit=2)

        assert [offre["id"] for offre in offres] == ["1", "2"]


class TestJobSearchService:
    def test_search_returns_deduplicated_enriched_offers(self, monkeypatch):
        # Explicite, pas juste l'absence par défaut : un poste de dev avec
        # AELYN_ENABLE_PUBLIC_JOB_APIS=true dans son .env réel (cf. autres
        # tests de cette classe, qui l'activent expressément) ferait sinon
        # de vrais appels réseau ici et casserait l'assertion de longueur.
        monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "false")
        ft = FTOffers(access_token="token")
        service = JobSearchService(ft)
        offre_1 = {"id": "1", "intitule": "Data Scientist", "typeContrat": "CDI", "description": "Python, ML, AI", "dateCreation": "2026-09-01"}
        offre_2 = {"id": "2", "intitule": "Data Scientist", "typeContrat": "CDI", "description": "Python, ML, AI", "dateCreation": "2026-09-02"}

        with patch.object(ft, "search_offers", return_value=([offre_1, offre_2], None)):
            offres = service.search(keywords="data scientist", limit=10)

        assert len(offres) == 1
        assert offres[0]["source"] == "francetravail"
        assert offres[0]["is_ai_related"] is True
        assert offres[0]["contract_type"] == "CDI"

    def test_search_aggregates_and_deduplicates_configured_sources(self, monkeypatch):
        monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "true")
        ft = FTOffers(access_token="token")
        service = JobSearchService(ft)
        france_travail_offer = {
            "id": "ft-1",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "lieuTravail": {"libelle": "Paris"},
            "typeContrat": "CDI",
            "dateCreation": "2026-09-02",
            "origineOffre": {
                "partenaires": [{"nom": "ACME Careers", "url": "https://acme.example/jobs/1"}]
            },
        }
        duplicate = {
            "id": "remote:1",
            "source": "remotive",
            "title": "Data Scientist",
            "company": "ACME",
            "location": "Paris",
            "contract_type": "CDI",
            "url": "https://acme.example/jobs/1",
        }
        adapter = Mock()
        adapter.name = "remotive"
        adapter.search.return_value = [duplicate]

        with patch.object(ft, "search_offers", return_value=([france_travail_offer], None)):
            with patch("aelyn_career.search.available_source_adapters", return_value=[adapter]):
                offers = service.search(keywords="data scientist", limit=10)

        assert len(offers) == 1
        assert offers[0]["duplicate_count"] == 2
        assert offers[0]["url"] == "https://acme.example/jobs/1"
        assert offers[0]["application_source"] == "ACME Careers"
        assert {entry["source"] for entry in offers[0]["sources_seen"]} == {
            "francetravail",
            "remotive",
        }
        adapter.search.assert_called_once()

    def test_supplemental_sources_use_first_configured_keyword_when_query_is_empty(self, monkeypatch):
        monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "true")
        ft = FTOffers(access_token="token")
        ft.keywords = "Data Scientist,Machine Learning"
        service = JobSearchService(ft)
        adapter = Mock()
        adapter.name = "remotive"
        adapter.search.return_value = []

        with patch.object(ft, "search_offers", return_value=([], None)):
            with patch("aelyn_career.search.available_source_adapters", return_value=[adapter]):
                service.search(keywords=None, limit=5)

        assert adapter.search.call_args.kwargs["keywords"] == "Data Scientist"

    def test_search_prioritizes_never_seen_offers_over_already_seen_ones(self, monkeypatch, tmp_path):
        """Relancer la même recherche de mots-clés plus tard ne doit pas
        remontrer sans arrêt les mêmes offres comme si elles étaient
        neuves (cf. OfferCache.mark_seen/seen_hashes)."""
        monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "false")
        ft = FTOffers(access_token="token")
        cache = OfferCache(tmp_path / "offers_cache.db")
        service = JobSearchService(ft, cache=cache)
        old_offer = {
            "id": "1", "intitule": "Old Offer", "entreprise": {"nom": "ACME"},
            "typeContrat": "CDI", "dateCreation": "2026-09-01",
        }
        new_offer = {
            "id": "2", "intitule": "New Offer", "entreprise": {"nom": "ACME"},
            "typeContrat": "CDI", "dateCreation": "2026-09-02",
        }

        with patch.object(ft, "search_offers", return_value=([old_offer], None)):
            first = service.search(keywords="data scientist", limit=10)
        assert first[0]["intitule"] == "Old Offer"
        assert first[0]["already_seen"] is False

        with patch.object(ft, "search_offers", return_value=([old_offer, new_offer], None)):
            second = service.search(keywords="data scientist", limit=1)

        assert second[0]["intitule"] == "New Offer"
        assert second[0]["already_seen"] is False

    def test_search_logs_each_call_with_new_and_total_counts(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "false")
        ft = FTOffers(access_token="token")
        cache = OfferCache(tmp_path / "offers_cache.db")
        service = JobSearchService(ft, cache=cache)
        offer = {
            "id": "1", "intitule": "Data Scientist", "entreprise": {"nom": "ACME"},
            "typeContrat": "CDI", "dateCreation": "2026-09-01",
        }

        with patch.object(ft, "search_offers", return_value=([offer], None)):
            service.search(keywords="data scientist", limit=10)

        logs = cache.recent_searches()
        assert len(logs) == 1
        assert logs[0].query == "data scientist"
        assert logs[0].result_count == 1
        assert logs[0].new_count == 1

    def test_search_stage_filters_out_unknown_contract_offers_without_stage_wording(self, monkeypatch, tmp_path):
        """Bug réel constaté en direct : Arbeitnow (et sources similaires)
        ne déclarent jamais de contract_type fiable ("UNKNOWN"), donc le
        filtre contract_type="stage" laissait passer n'importe quel poste,
        y compris des postes seniors confirmés, simplement parce que la
        source ne précise rien. Un poste "UNKNOWN" doit désormais mentionner
        "stage"/"intern" dans son titre ou sa description pour survivre."""
        monkeypatch.setenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "true")
        ft = FTOffers(access_token="token")
        cache = OfferCache(tmp_path / "offers_cache.db")
        service = JobSearchService(ft, cache=cache)
        senior_offer = {
            "id": "arbeitnow:1", "source": "arbeitnow",
            "title": "Senior Data Engineer", "company": "SFEIR", "location": "Rennes",
            "contract_type": "UNKNOWN", "description": "5+ years of experience required.",
        }
        intern_offer = {
            "id": "arbeitnow:2", "source": "arbeitnow",
            "title": "Data Engineer Intern", "company": "SFEIR", "location": "Rennes",
            "contract_type": "UNKNOWN", "description": "6-month internship for students.",
        }
        adapter = Mock()
        adapter.name = "arbeitnow"
        adapter.search.return_value = [senior_offer, intern_offer]

        with patch.object(ft, "search_offers", return_value=([], None)):
            with patch("aelyn_career.search.available_source_adapters", return_value=[adapter]):
                offers = service.search(keywords="data engineer rennes", contract_type="stage", limit=10)

        assert [o["id"] for o in offers] == ["arbeitnow:2"]


class TestAdditionalSourceAdapters:
    def test_careerjet_maps_apply_url_and_dates(self, monkeypatch):
        monkeypatch.setenv("CAREERJET_API_KEY", "test-key")
        response = Mock()
        response.json.return_value = {
            "jobs": [{
                "title": "Data Scientist",
                "company": "ACME",
                "locations": "Paris",
                "url": "https://example.com/job/1",
                "date": "2026-09-02",
                "expiration_date": "2026-10-01",
            }]
        }

        with patch("aelyn_career.source_adapters.requests.get", return_value=response) as mock_get:
            offers = CareerjetAdapter().search("data scientist")

        assert offers[0]["source"] == "careerjet"
        assert offers[0]["url"] == "https://example.com/job/1"
        assert offers[0]["dateLimite"] == "2026-10-01"
        assert mock_get.call_args.kwargs["auth"] == ("test-key", "")

    def test_remoteok_filters_and_maps_direct_apply_url(self):
        response = Mock()
        response.json.return_value = [
            {"id": 1, "position": "Data Scientist", "company": "ACME", "tags": ["python"], "url": "https://remoteok.com/1", "apply_url": "https://acme.example/apply"},
            {"id": 2, "position": "Product Designer", "company": "Other", "tags": ["design"], "url": "https://remoteok.com/2"},
        ]

        with patch("aelyn_career.source_adapters.requests.get", return_value=response):
            offers = RemoteOKAdapter().search("data python")

        assert len(offers) == 1
        assert offers[0]["source"] == "remoteok"
        assert offers[0]["application"]["url"] == "https://acme.example/apply"
