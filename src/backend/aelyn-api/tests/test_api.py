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
