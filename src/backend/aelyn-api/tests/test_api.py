"""Tests des routes qui ne dépendent d'aucun service externe (IMAP,
France Travail, Ollama, TV) : health, caméras (métadonnées, pas
d'ouverture réelle), liste des actions média, et le flux complet de
passkey des réglages. Les routes qui appellent un vrai service restent
vérifiées manuellement (cf. rapport), même esprit que
`career-agent/tests/test_offers.py` : ce qui peut être testé sans réseau
l'est ; le reste ne l'est pas plutôt que d'être mocké au point de ne
plus rien garantir.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from aelyn.core.config import settings
from aelyn_api.main import app
from aelyn_api.security import _tokens

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestCameras:
    def test_list_cameras_reflects_configured_indices(self, monkeypatch):
        monkeypatch.setattr(settings, "camera_entree_index", 3)
        monkeypatch.setattr(settings, "camera_salon_index", 4)

        response = client.get("/security/cameras")

        assert response.status_code == 200
        cameras = {c["name"]: c for c in response.json()}
        assert cameras["entree"]["index"] == 3
        assert cameras["salon"]["index"] == 4
        assert cameras["entree"]["configured"] is True

    def test_unknown_camera_detail_is_404(self) -> None:
        response = client.get("/security/cameras/cuisine")
        assert response.status_code == 404


class TestSystemResources:
    def test_resource_snapshot_is_lightweight_and_measured(self, monkeypatch) -> None:
        import aelyn_api.routers.system as system

        class Memory:
            percent = 42.0
            used = 4_200_000_000
            total = 10_000_000_000

        class Disk:
            percent = 51.0
            used = 51_000_000_000
            total = 100_000_000_000

        class Network:
            bytes_sent = 1_000
            bytes_recv = 2_000

        def unexpected_service_call():
            raise AssertionError("La route ressources ne doit pas tester les services")

        monkeypatch.setattr(system.psutil, "cpu_percent", lambda interval: 17.0)
        monkeypatch.setattr(system.psutil, "virtual_memory", lambda: Memory())
        monkeypatch.setattr(system.psutil, "disk_usage", lambda path: Disk())
        monkeypatch.setattr(system.psutil, "net_io_counters", lambda: Network())
        monkeypatch.setattr(system, "_cpu_temp_celsius", lambda: {"available": False, "value": None})
        monkeypatch.setattr(system, "_gpu_status", lambda: {"available": False, "reason": "test"})
        monkeypatch.setattr(system, "_imap_status", unexpected_service_call)
        monkeypatch.setattr(system, "_france_travail_status", unexpected_service_call)
        monkeypatch.setattr(system, "ollama_status", unexpected_service_call)

        response = client.get("/system/resources")

        assert response.status_code == 200
        data = response.json()
        assert data["cpu_percent"] == 17.0
        assert data["ram"]["percent"] == 42.0
        assert data["disk"]["percent"] == 51.0
        assert data["gpu"]["available"] is False
        assert isinstance(data["uptime_seconds"], int)

    def test_resource_snapshot_lists_every_mounted_disk(self, monkeypatch) -> None:
        import aelyn_api.routers.system as system

        class Memory:
            percent = 42.0
            used = 4_200_000_000
            total = 10_000_000_000

        class Network:
            bytes_sent = 1_000
            bytes_recv = 2_000

        class Partition:
            def __init__(self, mountpoint: str) -> None:
                self.mountpoint = mountpoint

        class Usage:
            def __init__(self, percent: float) -> None:
                self.percent = percent
                self.used = int(percent * 1_000_000_000)
                self.total = 100_000_000_000

        usage_by_mount = {"C:\\": Usage(98.1), "D:\\": Usage(46.7)}

        def unexpected_service_call():
            raise AssertionError("La route ressources ne doit pas tester les services")

        monkeypatch.setattr(system.psutil, "cpu_percent", lambda interval: 17.0)
        monkeypatch.setattr(system.psutil, "virtual_memory", lambda: Memory())
        monkeypatch.setattr(system.psutil, "disk_usage", lambda path: usage_by_mount[path])
        monkeypatch.setattr(
            system.psutil, "disk_partitions", lambda all=False: [Partition("C:\\"), Partition("D:\\")]
        )
        monkeypatch.setattr(system.psutil, "net_io_counters", lambda: Network())
        monkeypatch.setattr(system, "_cpu_temp_celsius", lambda: {"available": False, "value": None})
        monkeypatch.setattr(system, "_gpu_status", lambda: {"available": False, "reason": "test"})
        monkeypatch.setattr(system, "_imap_status", unexpected_service_call)
        monkeypatch.setattr(system, "_france_travail_status", unexpected_service_call)
        monkeypatch.setattr(system, "ollama_status", unexpected_service_call)

        response = client.get("/system/resources")

        assert response.status_code == 200
        disks = response.json()["disks"]
        assert [d["mountpoint"] for d in disks] == ["C:\\", "D:\\"]
        assert disks[0]["percent"] == 98.1
        assert disks[1]["percent"] == 46.7


class TestMediaActions:
    def test_list_actions_includes_known_commands(self) -> None:
        response = client.get("/media/actions")
        assert response.status_code == 200
        actions = response.json()
        assert "netflix" in actions
        assert "volume_up" in actions
        assert "search_youtube" in actions

    def test_unknown_action_is_404(self) -> None:
        response = client.post("/media/does_not_exist")
        assert response.status_code == 404


class TestGeneralCareerSearch:
    def test_returns_source_dates_deadline_and_real_apply_url_without_raw_payload(self):
        from aelyn_api.deps import get_offers_agent

        offer = {
            "id": "ft-42",
            "source": "francetravail",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "lieuTravail": {"libelle": "Paris"},
            "typeContrat": "CDI",
            "dateCreation": "2026-09-01T00:00:00Z",
            "dateLimiteDePotentiel": "2026-09-30",
            "origineOffre": {
                "partenaires": [{"nom": "Site employeur", "url": "https://example.com/apply/42"}]
            },
            "description": "Réaliser des analyses statistiques.",
            "sources_seen": [{"source": "francetravail", "url": "https://example.com/apply/42"}],
        }
        agent = MagicMock()

        with patch("aelyn_api.routers.career.JobSearchService.search", return_value=[offer]):
            app.dependency_overrides[get_offers_agent] = lambda: agent
            try:
                response = client.get("/career/search", params={"query": "data scientist"})
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["source"] == "francetravail"
        assert result["posted_at"] == "2026-09-01T00:00:00Z"
        assert result["expires_at"] == "2026-09-30"
        assert result["deadline"] == "2026-09-30"
        assert result["url"] == "https://example.com/apply/42"
        assert result["application"]["url"] == result["url"]
        assert result["application"]["source"] == "Site employeur"
        assert result["company"]["name"] == "ACME"
        assert result["metadata"] == {}

    def test_scored_france_travail_route_returns_dates_and_application_link(self):
        from aelyn_api.deps import get_offers_agent

        offer = {
            "id": "ft-43",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "lieuTravail": {"libelle": "Paris"},
            "dateCreation": "2026-09-03",
            "dateLimiteDePotentiel": "2026-10-02",
            "origineOffre": {
                "partenaires": [{"nom": "ACME Careers", "url": "https://acme.example/jobs/43"}]
            },
        }
        agent = MagicMock()
        agent.access_token = "token"

        with patch("aelyn_api.routers.career.find_best_matches", return_value=[offer]):
            app.dependency_overrides[get_offers_agent] = lambda: agent
            try:
                response = client.get("/career")
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        result = response.json()[0]
        assert result["date_publication"] == "2026-09-03"
        assert result["date_limite"] == "2026-10-02"
        assert result["deadline"] == "2026-10-02"
        assert result["url"] == "https://acme.example/jobs/43"


class TestYouTubeSearch:
    def test_returns_503_when_no_api_key_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "youtube_api_key", None)

        response = client.get("/media/youtube/search", params={"q": "test"})

        assert response.status_code == 503

    @patch("aelyn_api.routers.media.requests.get")
    def test_maps_youtube_response_to_result_shape(self, mock_get, monkeypatch) -> None:
        monkeypatch.setattr(settings, "youtube_api_key", "fake-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "Une vidéo",
                        "channelTitle": "Une chaîne",
                        "thumbnails": {"medium": {"url": "https://example.com/thumb.jpg"}},
                    },
                }
            ]
        }
        mock_get.return_value = mock_response

        response = client.get("/media/youtube/search", params={"q": "test"})

        assert response.status_code == 200
        results = response.json()
        assert results == [
            {
                "video_id": "abc123",
                "title": "Une vidéo",
                "channel": "Une chaîne",
                "thumbnail": "https://example.com/thumb.jpg",
            }
        ]
        # La clé API doit partir en paramètre de requête, jamais en dur.
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["key"] == "fake-key"
        assert kwargs["params"]["q"] == "test"

    @patch("aelyn_api.routers.media.requests.get")
    def test_network_failure_returns_502(self, mock_get, monkeypatch) -> None:
        import requests

        monkeypatch.setattr(settings, "youtube_api_key", "fake-key")
        mock_get.side_effect = requests.ConnectionError("boom")

        response = client.get("/media/youtube/search", params={"q": "test"})

        assert response.status_code == 502


class TestNetflixPlay:
    """`POST /media/netflix/play` réutilise EXACTEMENT `search_netflix` (cf.
    docstring de media.py), ces tests vérifient ce câblage, pas une
    quelconque précision de lecture que la plateforme ne permet pas."""

    def test_reuses_search_netflix_dispatch(self) -> None:
        from aelyn_api.deps import get_media_controller

        controller = MagicMock()
        controller.dispatch.return_value = 0
        app.dependency_overrides[get_media_controller] = lambda: controller
        try:
            response = client.post("/media/netflix/play", json={"title": "Stranger Things"})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Stranger Things"
        assert "best-effort" in body["note"]
        controller.dispatch.assert_called_once_with("search_netflix", "Stranger Things", None)

    def test_tv_unreachable_returns_502(self) -> None:
        from aelyn_api.deps import get_media_controller

        controller = MagicMock()
        controller.dispatch.side_effect = RuntimeError("TV injoignable")
        app.dependency_overrides[get_media_controller] = lambda: controller
        try:
            response = client.post("/media/netflix/play", json={"title": "Stranger Things"})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 502


class TestSettingsPasskeyFlow:
    def test_auth_fails_when_no_passkey_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "settings_passkey", None)

        response = client.post("/settings/auth", json={"passkey": "anything"})

        assert response.status_code == 503

    def test_auth_fails_with_wrong_passkey(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "settings_passkey", "correct-horse")

        response = client.post("/settings/auth", json={"passkey": "wrong"})

        assert response.status_code == 401

    def test_patch_without_token_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "settings_passkey", "correct-horse")

        response = client.patch("/settings/allow-autonomous-send", json={"value": True})

        assert response.status_code == 401

    def test_full_auth_then_patch_flow(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "settings_passkey", "correct-horse")
        monkeypatch.setattr(settings, "allow_autonomous_send", False)

        auth = client.post("/settings/auth", json={"passkey": "correct-horse"})
        assert auth.status_code == 200
        token = auth.json()["token"]
        assert token in _tokens

        patched = client.patch(
            "/settings/allow-autonomous-send",
            json={"value": True},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert patched.status_code == 200
        assert patched.json() == {"allow_autonomous_send": True}

    def test_garbage_token_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "settings_passkey", "correct-horse")

        response = client.patch(
            "/settings/allow-autonomous-send",
            json={"value": True},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

        assert response.status_code == 401

    def test_generic_patch_persists_proactive_search_settings(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "settings_passkey", "correct-horse")
        monkeypatch.setattr(settings, "proactive_search_enabled", False)
        monkeypatch.setattr(settings, "proactive_search_interval_minutes", 180)
        monkeypatch.setattr(
            "aelyn_api.routers.settings.set_env_value", lambda key, value: None
        )

        auth = client.post("/settings/auth", json={"passkey": "correct-horse"})
        token = auth.json()["token"]

        response = client.patch(
            "/settings",
            json={
                "proactive_search_enabled": True,
                "proactive_search_interval_minutes": 60,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["proactive_search_enabled"] is True
        assert body["proactive_search_interval_minutes"] == 60
        assert settings.proactive_search_enabled is True
        assert settings.proactive_search_interval_minutes == 60

    def test_generic_patch_rejects_an_interval_outside_bounds(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "settings_passkey", "correct-horse")

        auth = client.post("/settings/auth", json={"passkey": "correct-horse"})
        token = auth.json()["token"]

        response = client.patch(
            "/settings",
            json={"proactive_search_interval_minutes": 5},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422


class TestActivity:
    """GET /activity : vide pour un journal/historique sans contenu
    (nouvel utilisateur), rempli sinon - jamais le mock statique affiché
    jusqu'ici côté frontend (mocks/activity.ts). L'endpoint fusionne
    maintenant Journal (propositions/actions) ET ChatHistory (échanges) :
    les deux dépendances doivent être mockées, sinon le vrai historique de
    chat de la machine de dev (des centaines d'échanges réels) fuite dans
    des tests censés ne vérifier que le comportement du Journal."""

    def test_empty_sources_return_empty_list(self) -> None:
        from aelyn_api.deps import get_chat_history, get_journal

        journal = MagicMock()
        journal.since.return_value = []
        history = MagicMock()
        history.recent.return_value = []
        app.dependency_overrides[get_journal] = lambda: journal
        app.dependency_overrides[get_chat_history] = lambda: history
        try:
            response = client.get("/activity")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == []

    def test_excludes_structure_offer_cache_noise(self) -> None:
        from datetime import datetime, timezone

        from aelyn.core.journal import Action, ActionStatus
        from aelyn_api.deps import get_chat_history, get_journal

        journal = MagicMock()
        journal.since.return_value = [
            Action(
                id=1,
                ts=datetime.now(timezone.utc),
                agent="career",
                action="structure_offer",
                target="offre-1",
                summary="Offre structurée (niveau junior)",
                status=ActionStatus.EXECUTED,
                payload={},
            ),
            Action(
                id=2,
                ts=datetime.now(timezone.utc),
                agent="email",
                action="archiver",
                target="spam@example.com",
                summary="Newsletter : promotion.",
                status=ActionStatus.PROPOSED,
                payload={},
            ),
        ]
        history = MagicMock()
        history.recent.return_value = []
        app.dependency_overrides[get_journal] = lambda: journal
        app.dependency_overrides[get_chat_history] = lambda: history
        try:
            response = client.get("/activity")
        finally:
            app.dependency_overrides.clear()

        body = response.json()
        assert len(body) == 1
        assert body[0]["source"] == "email"
        assert "Newsletter" in body[0]["message"]


class TestEmailActions:
    """POST /email/{id}/validate|reject : seul moyen, pour le frontend web,
    d'agir sur une proposition de triage déjà faite (le chat refuse
    délibérément valider/rejeter, cf. `confirm=False`)."""

    def test_validate_executes_and_returns_status(self) -> None:
        from aelyn_api.deps import get_email_agent

        agent = MagicMock()
        agent.execute.return_value = True
        app.dependency_overrides[get_email_agent] = lambda: agent
        try:
            response = client.post("/email/7/validate")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"status": "executed"}
        agent.execute.assert_called_once_with(7)

    def test_validate_not_executed_when_autonomous_send_disabled(self) -> None:
        from aelyn_api.deps import get_email_agent

        agent = MagicMock()
        agent.execute.return_value = False
        app.dependency_overrides[get_email_agent] = lambda: agent
        try:
            response = client.post("/email/7/validate")
        finally:
            app.dependency_overrides.clear()

        assert response.json() == {"status": "not_executed"}

    def test_validate_unknown_action_is_404(self) -> None:
        from aelyn_api.deps import get_email_agent

        agent = MagicMock()
        agent.execute.side_effect = ValueError("Action 999 introuvable")
        app.dependency_overrides[get_email_agent] = lambda: agent
        try:
            response = client.post("/email/999/validate")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_reject_rejects_and_returns_status(self) -> None:
        from aelyn_api.deps import get_email_agent

        agent = MagicMock()
        app.dependency_overrides[get_email_agent] = lambda: agent
        try:
            response = client.post("/email/7/reject")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"status": "rejected"}
        agent.reject.assert_called_once_with(7)


class TestChatOfferCaching:
    def test_offers_from_chat_message_become_generatable_by_id(self) -> None:
        """Bug réel : une offre affichée dans le tableau du chat web ne
        venait jamais de GET /career (qui seul alimentait le cache
        process utilisé par POST /career/{id}/cv) - cliquer "préparer le
        CV" pour une offre vue dans le chat répondait donc 404 "inconnue,
        appelle GET /career d'abord", alors que l'utilisateur ne voit
        jamais que le tableau du chat."""
        from aelyn_api.deps import get_application_writer, get_conversational_agent
        from aelyn_career.models import CVContent
        from aelyn_conversation.models import TurnResult

        offer = {
            "id": "chat-offer-1",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "description": "Analyse de données.",
        }
        agent = MagicMock()
        agent.handle_message.return_value = TurnResult(
            text="1 offre trouvée.", result_type="offers", results=[offer]
        )
        writer = MagicMock()
        writer.draft_cv.return_value = CVContent(
            profil="Profil", experiences=[], projets=[], competences={},
            formation=[], certifications=[], langues=[], centres_interet=[],
        )
        app.dependency_overrides[get_conversational_agent] = lambda: agent
        app.dependency_overrides[get_application_writer] = lambda: writer
        try:
            chat_response = client.post("/chat/message", json={"message": "cherche des offres"})
            assert chat_response.status_code == 200

            cv_response = client.post("/career/chat-offer-1/cv")
        finally:
            app.dependency_overrides.clear()

        assert cv_response.status_code == 200
        assert cv_response.json()["profil"] == "Profil"


class TestCoverLetterRoute:
    def test_generate_cover_letter_for_cached_offer(self) -> None:
        from aelyn_api.deps import get_application_writer, get_offers_agent

        offer = {
            "id": "lm-offer-1",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "description": "Analyse de données.",
        }
        agent = MagicMock()
        writer = MagicMock()
        writer.draft_cover_letter.return_value = "Madame, Monsieur,\n\nCandidature..."
        app.dependency_overrides[get_offers_agent] = lambda: agent
        app.dependency_overrides[get_application_writer] = lambda: writer
        try:
            with patch("aelyn_api.routers.career.find_best_matches", return_value=[offer]):
                client.get("/career")  # alimente le cache process (cache_offers)

            response = client.post("/career/lm-offer-1/lm")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"text": "Madame, Monsieur,\n\nCandidature..."}

    def test_generate_cover_letter_for_unknown_offer_is_404(self) -> None:
        from aelyn_api.deps import get_application_writer

        app.dependency_overrides[get_application_writer] = lambda: MagicMock()
        try:
            response = client.post("/career/unknown-offer/lm")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404


class TestApplyByMail:
    def test_apply_by_mail_sends_cv_and_cover_letter_as_pdf_attachments(self, monkeypatch) -> None:
        from aelyn_api.deps import get_application_writer, get_offers_agent
        from aelyn_career.models import CVContent

        offer = {
            "id": "mail-offer-1",
            "intitule": "Data Scientist",
            "entreprise": {"nom": "ACME"},
            "description": "Analyse de données.",
        }
        writer = MagicMock()
        cv = CVContent(
            profil="Profil", experiences=[], projets=[], competences={},
            formation=[], certifications=[], langues=[], centres_interet=[],
        )
        writer.draft_cv.return_value = cv
        writer.draft_cover_letter.return_value = "Madame, Monsieur,\n\nCandidature..."
        writer.contact_header.return_value = "Djamal TOE"
        # Le polish LLM reçoit ce que `draft_cv`/`draft_cover_letter` ont
        # renvoyé : sur un writer entièrement mocké, il faut aussi fixer ces
        # retours sinon `cv_to_pdf_bytes` reçoit un MagicMock au lieu d'un
        # vrai `CVContent`.
        writer.polish_cv_with_llm.return_value = cv
        writer.polish_cover_letter_with_llm.return_value = (
            writer.draft_cover_letter.return_value
        )

        sent = {}

        def fake_send(*, to, subject, body, attachments):
            sent["to"] = to
            sent["subject"] = subject
            sent["attachment_names"] = [a[0] for a in attachments]

        monkeypatch.setattr(
            "aelyn_career.apply_by_mail.send_mail_with_attachments", fake_send
        )
        app.dependency_overrides[get_offers_agent] = lambda: MagicMock()
        app.dependency_overrides[get_application_writer] = lambda: writer
        try:
            with patch("aelyn_api.routers.career.find_best_matches", return_value=[offer]):
                client.get("/career")  # alimente le cache process (cache_offers)

            response = client.post("/career/mail-offer-1/apply-by-mail")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        body = response.json()
        assert body["offer_title"] == "Data Scientist"
        assert "@" in sent["to"]
        assert sent["attachment_names"] == ["CV.pdf", "Lettre_de_motivation.pdf"]

    def test_apply_by_mail_for_unknown_offer_is_404(self) -> None:
        from aelyn_api.deps import get_application_writer

        app.dependency_overrides[get_application_writer] = lambda: MagicMock()
        try:
            response = client.post("/career/unknown-offer/apply-by-mail")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
