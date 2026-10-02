"""Tests du routage rapide (sans LLM) des phrases caméra.

`fast_intent` court-circuite l'appel Ollama pour les phrases sans
ambiguïté (cf. fast_router.py) ; les phrases caméra ("montre la caméra
de l'entrée"/"du salon", "montre toute la pièce") en font partie : le
mot "caméra"/"webcam" ne peut se confondre avec aucune autre commande.
Pas besoin d'un LLM réel pour vérifier ce routage déterministe.
"""

import pytest

from aelyn_conversation.fast_router import fast_intent


class TestCameraFastRouting:
    @pytest.mark.parametrize(
        "phrase",
        [
            "montre la caméra de l'entrée",
            "montre-moi la caméra de l'entrée",
            "affiche la webcam de l'entrée",
            "fais voir l'entrée avec la caméra",
        ],
    )
    def test_routes_to_entree(self, phrase):
        intent = fast_intent(phrase)

        assert intent is not None
        assert intent.commande == "camera"
        assert intent.camera_name == "entree"

    @pytest.mark.parametrize(
        "phrase",
        [
            "montre la caméra du salon",
            "montre-moi la caméra du salon",
            "affiche la webcam du salon",
        ],
    )
    def test_routes_to_salon(self, phrase):
        intent = fast_intent(phrase)

        assert intent is not None
        assert intent.commande == "camera"
        assert intent.camera_name == "salon"

    def test_toute_la_piece_routes_to_salon(self):
        # "toute la pièce" n'a qu'une seule caméra qui la couvre (le
        # salon) : pas d'ambiguïté à laisser au LLM ici.
        intent = fast_intent("montre toute la pièce")

        assert intent is not None
        assert intent.commande == "camera"
        assert intent.camera_name == "salon"

    def test_reformulation_is_short_and_present(self):
        intent = fast_intent("montre la caméra de l'entrée")

        assert intent.reformulation
        assert len(intent.reformulation.split()) <= 12

    def test_unrelated_media_phrase_is_not_routed_to_camera(self):
        intent = fast_intent("lance Netflix")

        assert intent is not None
        assert intent.commande == "media"

    def test_unrelated_phrase_falls_through_to_llm(self):
        # Aucun mot-clé caméra/média/mail : `fast_intent` doit rendre la
        # main (None) plutôt que de deviner, pour laisser le LLM classer.
        assert fast_intent("raconte-moi une blague") is None
