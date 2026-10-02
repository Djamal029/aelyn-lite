"""Tests pour `LLMClient.text_stream()` : la logique de filtrage du
raisonnement (`<think>...</think>`) pendant un flux, sans appel réseau
réel : `self._client.chat(..., stream=True)` est mocké pour renvoyer une
suite de fragments contrôlée, comme le ferait vraiment Ollama en mode
streaming (`{"message": {"content": "..."}}` par morceau).
"""

from unittest.mock import MagicMock, patch

from aelyn.core.llm import LLMClient


def _make_client(chunks: list[str]) -> LLMClient:
    """Un `LLMClient` dont `_client.chat(...)` renvoie `chunks` (un
    fragment de texte par appel à `next()`), sans jamais toucher un vrai
    serveur Ollama."""
    with patch("aelyn.core.llm.ollama") as mock_ollama:
        mock_ollama.Client.return_value = MagicMock()
        client = LLMClient(model="test-model")
    client._client.chat.return_value = iter({"message": {"content": c}} for c in chunks)
    return client


class TestTextStreamNoReasoning:
    """Modèle sans balise <think> (ex. mistral) : tout est diffusé tel quel."""

    def test_yields_all_content_once_buffer_threshold_passed(self):
        client = _make_client(["Bonjour, " * 10, "voici la suite.", " Et la fin."])
        result = "".join(client.text_stream(system="sys", user="user"))
        expected = "".join(["Bonjour, " * 10, "voici la suite.", " Et la fin."])
        assert result == expected

    def test_short_response_without_think_is_still_returned(self):
        # Réponse plus courte que le seuil de bascule (64 caractères) :
        # aucune balise n'arrivera jamais, mais le texte doit quand même
        # ressortir en entier une fois le flux terminé.
        client = _make_client(["Oui."])
        result = "".join(client.text_stream(system="sys", user="user"))
        assert result == "Oui."


class TestTextStreamWithReasoning:
    """Modèle qui pense à voix haute (ex. deepseek-r1) : le bloc <think>
    ne doit jamais apparaître dans le flux renvoyé à l'appelant."""

    def test_think_block_is_never_yielded(self):
        client = _make_client(
            ["<think>", "je réfléchis à la question", "</think>", "Voici la réponse."]
        )
        result = "".join(client.text_stream(system="sys", user="user"))
        assert result == "Voici la réponse."
        assert "think" not in result.lower()

    def test_think_close_tag_split_across_chunks(self):
        # La balise fermante peut arriver coupée entre deux fragments,
        # le buffer doit la recomposer avant de la chercher.
        client = _make_client(["<think>raisonnement...</th", "ink>Réponse finale."])
        result = "".join(client.text_stream(system="sys", user="user"))
        assert result == "Réponse finale."

    def test_content_after_close_tag_in_same_chunk_is_yielded_immediately(self):
        client = _make_client(["<think>court</think>Début de la réponse.", " Suite."])
        result = "".join(client.text_stream(system="sys", user="user"))
        assert result == "Début de la réponse. Suite."


class TestTextStreamEdgeCases:
    def test_empty_chunks_are_skipped(self):
        client = _make_client(["", "Bonjour", "", " le monde."])
        result = "".join(client.text_stream(system="sys", user="user"))
        assert result == "Bonjour le monde."

    def test_passes_num_ctx_option_through(self):
        client = _make_client(["reponse"])
        list(client.text_stream(system="sys", user="user", num_ctx=16384))
        _, kwargs = client._client.chat.call_args
        assert kwargs["options"]["num_ctx"] == 16384
        assert kwargs["stream"] is True
