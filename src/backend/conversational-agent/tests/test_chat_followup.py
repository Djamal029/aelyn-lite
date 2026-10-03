"""Tests du bug rapporté par un utilisateur réel sur le frontend web :
"cherche des offres" (6 offres trouvées) puis "affiche les offres"
relançait une recherche neuve au lieu de réafficher les résultats déjà
trouvés. Cause : `POST /chat/message` ne passait pas par le vrai routage
de `ConversationalAgent` (fast router, follow-ups, résolution de
référence), corrigé en faisant passer CLI et API par la même
`_dispatch_phrase()`, via `handle_message()` pour l'API.

Toutes les dépendances coûteuses (LLM, IMAP, France Travail, rédaction
de candidature, historique SQLite) sont mockées : ces tests vérifient le
ROUTAGE et la résolution de "la liste entière" vs "un item précis", pas
un vrai appel réseau/LLM.
"""

from unittest.mock import patch

import pytest

from aelyn_conversation.agent import ConversationalAgent
from aelyn_email.models import Mail


@pytest.fixture
def agent():
    with (
        patch("aelyn_conversation.agent.LLMClient"),
        patch("aelyn_conversation.agent.is_model_available", return_value=False),
        patch("aelyn_conversation.agent.EmailAgent"),
        patch("aelyn_conversation.agent.FTOffers"),
        patch("aelyn_conversation.agent.ApplicationWriter"),
        patch("aelyn_conversation.agent.ChatHistory"),
    ):
        return ConversationalAgent(voice=False)


class TestShowAllFollowUp:
    """« affiche les offres »/« montre tous les mails » : la LISTE
    entière déjà trouvée, jamais une recherche/lecture neuve."""

    def test_affiche_les_offres_returns_cached_offers(self, agent):
        offres = [{"id": "1", "intitule": "Data Scientist"}, {"id": "2", "intitule": "ML Engineer"}]
        agent._last_results = ["- Data Scientist | X", "- ML Engineer | Y"]
        agent._last_list_type = "offers"
        agent._last_list_payload = offres
        agent._last_said = "2 offres trouvées."

        result = agent.handle_message("affiche les offres")

        assert result.result_type == "offers"
        assert result.results == offres
        assert "Data Scientist" in result.text
        assert "ML Engineer" in result.text
        # Jamais juste la phrase-résumé d'origine : la LISTE, pas son écho.
        assert result.text != "2 offres trouvées."

    def test_montre_les_variant_also_works(self, agent):
        offres = [{"id": "1", "intitule": "Data Scientist"}]
        agent._last_results = ["- Data Scientist | X"]
        agent._last_list_type = "offers"
        agent._last_list_payload = offres

        result = agent.handle_message("montre-moi les offres")

        assert result.result_type == "offers"
        assert result.results == offres

    def test_affiche_tous_les_mails_returns_cached_mails(self, agent):
        mails = [{"uid": "1", "subject": "Bonjour"}]
        agent._last_results = ["[1] X : Bonjour"]
        agent._last_list_type = "mails"
        agent._last_list_payload = mails
        agent._last_said = "1 mail non lu."

        result = agent.handle_message("montre tous les mails")

        assert result.result_type == "mails"
        assert result.results == mails

    def test_single_item_readback_is_not_intercepted_as_show_all(self, agent):
        # "lis le premier" doit résoudre UN item précis (comportement
        # préexistant), pas basculer dans la branche "liste entière"
        # (_SHOW_ALL_RE ne doit matcher que "les"/"tous"/"toutes").
        agent._last_results = ["- Offre A", "- Offre B"]
        agent._last_list_type = "offers"
        agent._last_list_payload = [{"id": "a"}, {"id": "b"}]

        result = agent.handle_message("lis le premier")

        assert result.text == "- Offre A"
        # Un item précis n'est pas "la liste" : pas de result_type ici,
        # comportement inchangé par rapport à avant ce correctif.
        assert result.result_type is None

    def test_no_prior_list_falls_back_to_last_said(self, agent):
        agent._last_results = []
        agent._last_said = "Bonjour !"

        result = agent.handle_message("affiche ça")

        assert result.text == "Bonjour !"
        assert result.result_type is None

    def test_camera_phrase_is_not_swallowed_by_read_back(self, agent):
        """`READ_BACK_RE` inclut maintenant "montre\\w*" (pour "montre les
        offres") ; il ne doit PAS pour autant intercepter "montre la
        caméra de l'entrée" quand une liste est déjà en mémoire (le
        risque de régression introduit par cet ajout, cf. `_try_read_back`
        et son garde-fou explicite sur "caméra"/"webcam")."""
        agent._last_results = ["- Data Scientist | X"]
        agent._last_list_type = "offers"
        agent._last_list_payload = [{"id": "1"}]

        # `_try_read_back` doit rendre la main (False) sans rien dire ni
        # modifier l'état, pour laisser le routage caméra s'en charger.
        handled = agent._try_read_back("montre la caméra de l'entrée")

        assert handled is False

    def test_turn_result_resets_between_calls(self, agent):
        """Un tour SANS liste ne doit jamais hériter du result_type/results
        d'un tour précédent qui en avait un (`_turn_result_*` doit être
        remis à zéro à chaque appel de `handle_message`)."""
        offres = [{"id": "1", "intitule": "Data Scientist"}]
        agent._last_results = ["- Data Scientist | X"]
        agent._last_list_type = "offers"
        agent._last_list_payload = offres
        first = agent.handle_message("affiche les offres")
        assert first.result_type == "offers"

        # "reformule ça" ne matche pas READ_BACK_RE et ne produit aucune
        # liste : le résultat de ce tour doit être vierge, pas hérité.
        with patch.object(agent, "_try_reformulate", return_value=True):
            second = agent.handle_message("reformule ça")

        assert second.result_type is None
        assert second.results is None


class TestChatContextAfterLists:
    def test_summarize_orange_mail_after_checking_unread_mail(self, agent):
        orange = Mail(
            uid="328",
            sender="Orange",
            sender_email="jobs@orange.example",
            subject="Une nouvelle offre pour vous",
            body="Orange propose plusieurs offres de stage et postes techniques.",
        )

        with patch(
            "aelyn_conversation.agent.run_command",
            return_value=(0, [orange], None),
        ):
            result = agent.handle_message("vérifie mes mails")

        assert result.result_type == "mails"
        with patch.object(
            agent.llm, "text_stream", return_value=iter(["Six offres."])
        ) as summarize:
            summary = agent.handle_message("résume-moi le mail de Orange")

        assert "Six offres." in summary.text
        assert "Orange" in summarize.call_args.kwargs["user"]
        assert "Une nouvelle offre pour vous" in summarize.call_args.kwargs["user"]

    def test_describe_first_offer_from_latest_search(self, agent):
        from aelyn_conversation.models import Intent

        offers = [
            {
                "id": "risk-1",
                "intitule": "Analyste Risques de Crédit Entreprises",
                "description": "Analyse des risques de crédit des entreprises.",
                "entreprise": {"nom": "Banque Exemple"},
            },
            {
                "id": "risk-2",
                "intitule": "Consultant Gestion des Risques IT",
                "description": "Conseil en risques informatiques.",
                "entreprise": {"nom": "Conseil Exemple"},
            },
        ]

        with (
            patch.object(
                agent.intent_llm,
                "structured",
                return_value=Intent(
                    commande="chercher_offres",
                    mots_cles="data scientist",
                    limit=10,
                    reformulation="Je cherche 15 offres en gestion des risques bancaires.",
                ),
            ),
            patch(
                "aelyn_conversation.agent.career_run_command",
                return_value=(0, offers),
            ) as search,
        ):
            first = agent.handle_message("cherche 15 offres en gestion des risques bancaires")
            detail = agent.handle_message("décris-moi la première offre")

        assert search.call_args.kwargs["limit"] == 15
        assert search.call_args.kwargs["mots_cles"] == "gestion des risques bancaires"
        assert first.results == offers
        assert "Analyste Risques de Crédit Entreprises" in detail.text
        assert "Analyse des risques de crédit des entreprises." in detail.text
        assert "Data Scientist" not in detail.text

    def test_failed_offer_search_does_not_return_previous_turn(self, agent):
        from aelyn.core.llm import LLMError
        from aelyn_conversation.models import Intent

        agent._last_said = "Ancienne réponse sans rapport."
        with (
            patch.object(
                agent.intent_llm,
                "structured",
                return_value=Intent(
                    commande="chercher_offres",
                    mots_cles="data scientist",
                    limit=10,
                    reformulation="Je cherche des offres de data scientist.",
                ),
            ),
            patch(
                "aelyn_conversation.agent.career_run_command",
                side_effect=LLMError("model runner has unexpectedly stopped"),
            ),
        ):
            result = agent.handle_message("cherche des offres de data scientist")

        assert result.results == []
        assert "a échoué" in result.text
        assert "Ancienne réponse" not in result.text

    def test_failed_mail_summary_does_not_return_previous_turn(self, agent):
        from aelyn.core.llm import LLMError

        orange = Mail(
            uid="328",
            sender="Orange",
            sender_email="jobs@orange.example",
            subject="Une nouvelle offre pour vous",
            body="Message test.",
        )
        agent._last_mails = [orange]
        agent._last_said = "Ancienne réponse sans rapport."
        with patch.object(
            agent.llm,
            "text_stream",
            side_effect=LLMError("model runner has unexpectedly stopped"),
        ):
            result = agent.handle_message("résume-moi le mail de Orange")

        assert "Je n'ai pas pu faire le résumé" in result.text
        assert "Ancienne réponse" not in result.text


class TestDraftPhrasingGap:
    """"prépare un mail pour X"/"réponds à ce mail" ne déclenchaient pas
    `_try_draft` (seuls "brouillon"/"rédige"/"draft" le faisaient), et
    `Intent.commande` n'a AUCUNE catégorie "brouillon de mail" : la
    phrase tombait dans `inconnu` (conversation libre) au lieu de
    rédiger un brouillon, alors que l'intention était évidente. Même
    classe de bug que le suivi "affiche les offres" (un mot de cadrage
    différent de l'habituel casse un chemin qui devrait être robuste à
    la formulation), appliquée à la regex de déclenchement plutôt qu'à
    la résolution de référence."""

    @staticmethod
    def _make_mail() -> Mail:
        return Mail(
            uid="1",
            sender="Conforama",
            sender_email="contact@conforama.fr",
            subject="Votre commande",
            body="Corps du mail.",
        )

    def test_prepare_un_mail_triggers_draft(self, agent):
        # Depuis l'ajout de la confirmation proactive (cf.
        # `TestPendingConfirmation`), `_try_draft` ne rédige plus au
        # premier tour : il pose "veux-tu que je..." et attend le tour
        # suivant. Ce test vérifie toujours que DRAFT_RE/`_find_mail`
        # reconnaissent bien cette formulation (le bug d'origine), la
        # rédaction effective est couverte séparément.
        agent._last_mails = [self._make_mail()]
        result = agent.handle_message("prépare un mail pour Conforama")

        assert "Conforama" in result.text
        assert agent._pending_action == {"kind": "draft_mail", "mail": agent._last_mails[0]}

    def test_reponds_a_ce_mail_triggers_draft(self, agent):
        agent._last_mails = [self._make_mail()]
        agent._mail_focus = agent._last_mails[0]
        result = agent.handle_message("réponds à ce mail")

        assert "Conforama" in result.text
        assert agent._pending_action is not None

    def test_ecris_un_mail_triggers_draft(self, agent):
        agent._last_mails = [self._make_mail()]
        result = agent.handle_message("écris un mail à Conforama")

        assert "Conforama" in result.text
        assert agent._pending_action is not None

    def test_unrelated_prepare_phrase_is_not_swallowed(self, agent):
        # "prépare-toi" sans "mail" ne doit jamais tenter un brouillon
        # (aucun contexte mail dans la phrase) : DRAFT_RE ne doit pas
        # matcher, laissant la phrase continuer vers le routage normal
        # (ici simulé en "inconnu", comme le ferait un vrai LLM).
        from aelyn_conversation.models import Intent

        with patch.object(
            agent, "_try_draft", wraps=agent._try_draft
        ) as mock_draft, patch.object(
            agent.intent_llm,
            "structured",
            return_value=Intent(commande="inconnu", reformulation=""),
        ), patch.object(agent, "_converse") as mock_converse:
            agent.handle_message("prépare-toi, on y va")

        # `_try_draft` a bien été appelé (dans la chaîne de dispatch) mais
        # a rendu la main (DRAFT_RE ne matche pas), laissant la phrase
        # atteindre `_converse` via la classification "inconnu".
        mock_draft.assert_called_once()
        mock_converse.assert_called_once()

    def test_prepare_cv_is_not_caught_by_draft_re(self, agent):
        # "prépare-moi un CV" doit rester intercepté par `_try_prepare_cv`
        # (ordre de dispatch), pas partir vers `_try_draft` sous prétexte
        # que "prépare" est maintenant un mot-clé accepté par `DRAFT_RE`.
        with patch.object(agent, "_try_prepare_cv", return_value=True) as mock_cv:
            agent.handle_message("prépare-moi un CV pour cette offre")

        mock_cv.assert_called_once()


class TestPendingConfirmation:
    """AELYN propose ("veux-tu que je...") au lieu d'exécuter directement
    pour les actions lentes/conséquentes (brouillon de mail, CV, lettre de
    motivation) : demande utilisateur réelle, pour ne plus jamais deviner
    silencieusement NI échouer sec sur une référence par ailleurs déjà
    résolue. Couvre les 3 issues possibles du tour suivant : confirmation,
    refus, et phrase sans rapport (l'action en attente ne doit JAMAIS
    s'exécuter "en retard" sur un tour qui n'y répond pas)."""

    @staticmethod
    def _make_mail() -> Mail:
        return Mail(
            uid="1",
            sender="Conforama",
            sender_email="contact@conforama.fr",
            subject="Votre commande",
            body="Corps du mail.",
        )

    @staticmethod
    def _make_offer() -> dict:
        return {"id": "42", "intitule": "Data Scientist", "entreprise": {"nom": "EDF"}}

    # ---- brouillon de mail --------------------------------------------

    def test_draft_asks_before_executing(self, agent):
        agent._last_mails = [self._make_mail()]
        with patch.object(agent.llm, "text_stream") as mock_stream:
            result = agent.handle_message("rédige un brouillon pour le mail de Conforama")

        mock_stream.assert_not_called()
        assert "Conforama" in result.text
        assert agent._pending_action == {"kind": "draft_mail", "mail": agent._last_mails[0]}

    def test_draft_confirmed_on_next_turn_executes(self, agent):
        agent._last_mails = [self._make_mail()]
        agent.handle_message("rédige un brouillon pour le mail de Conforama")

        with patch.object(agent.llm, "text_stream", return_value=iter(["Bonjour,", " voici."])):
            result = agent.handle_message("oui")

        assert result.text == "Bonjour, voici."
        assert agent._pending_action is None

    def test_draft_declined_on_next_turn_does_not_execute(self, agent):
        agent._last_mails = [self._make_mail()]
        agent.handle_message("rédige un brouillon pour le mail de Conforama")

        with patch.object(agent.llm, "text_stream") as mock_stream:
            agent.handle_message("non laisse tomber")

        mock_stream.assert_not_called()
        assert agent._pending_action is None

    def test_draft_unrelated_reply_drops_pending_without_executing_stale(self, agent):
        # L'utilisateur change de sujet sans répondre à "veux-tu que je
        # réponde..." : l'action ne doit jamais se déclencher plus tard
        # sur CE tour ni sur un tour ultérieur sans rapport. La phrase de
        # suivi n'étant reconnue par aucun fast-router/`_try_*`, elle
        # retombe sur le LLM d'intention (mocké ici comme "inconnu", même
        # principe que `test_unrelated_prepare_phrase_is_not_swallowed` :
        # un `Intent` MagicMock non configuré casserait le rendu Rich de
        # `intent.reformulation`).
        from aelyn_conversation.models import Intent

        agent._last_mails = [self._make_mail()]
        agent.handle_message("rédige un brouillon pour le mail de Conforama")

        with (
            patch.object(agent.llm, "text_stream") as mock_stream,
            patch.object(
                agent.intent_llm,
                "structured",
                return_value=Intent(commande="inconnu", reformulation=""),
            ),
            patch.object(agent, "_converse") as mock_converse,
        ):
            agent.handle_message("quel temps fait-il ?")

        mock_stream.assert_not_called()
        mock_converse.assert_called_once()
        assert agent._pending_action is None

    def test_forgiving_confirmation_words_are_recognized(self, agent):
        for word in ["vas-y", "d'accord", "ok", "carrément", "ouais"]:
            agent._last_mails = [self._make_mail()]
            agent.handle_message("rédige un brouillon pour le mail de Conforama")
            with patch.object(agent.llm, "text_stream", return_value=iter(["Réponse."])):
                result = agent.handle_message(word)
            assert result.text == "Réponse.", f"{word!r} aurait dû confirmer"
            assert agent._pending_action is None

    # ---- CV -------------------------------------------------------------

    def test_prepare_cv_asks_before_executing(self, agent):
        offre = self._make_offer()
        agent._last_offers = [offre]
        with patch.object(agent.application_writer, "draft_cv") as mock_draft_cv:
            result = agent.handle_message("prépare-moi un CV pour l'offre chez EDF")

        mock_draft_cv.assert_not_called()
        assert "Data Scientist" in result.text
        assert agent._pending_action == {"kind": "prepare_cv", "offre": offre}

    def test_prepare_cv_confirmed_executes(self, agent):
        from aelyn_career.models import CVContent

        offre = self._make_offer()
        agent._last_offers = [offre]
        agent.handle_message("prépare-moi un CV pour l'offre chez EDF")

        cv = CVContent(
            profil="Profil.",
            experiences=[],
            projets=[],
            competences={},
            formation=[],
            certifications=[],
        )
        with (
            patch.object(agent.application_writer, "draft_cv", return_value=cv) as mock_draft_cv,
            patch.object(agent.application_writer, "contact_header", return_value=""),
        ):
            agent.handle_message("oui")

        mock_draft_cv.assert_called_once()
        assert agent._pending_action is None

    # ---- lettre de motivation --------------------------------------------

    def test_prepare_lm_asks_before_executing(self, agent):
        offre = self._make_offer()
        agent._last_offers = [offre]
        with patch.object(agent.application_writer, "draft_cover_letter_stream") as mock_stream:
            result = agent.handle_message("prépare une lettre de motivation pour l'offre chez EDF")

        mock_stream.assert_not_called()
        assert "Data Scientist" in result.text
        assert agent._pending_action == {"kind": "prepare_lm", "offre": offre}

    def test_prepare_lm_confirmed_executes(self, agent):
        offre = self._make_offer()
        agent._last_offers = [offre]
        agent.handle_message("prépare une lettre de motivation pour l'offre chez EDF")

        with (
            patch.object(
                agent.application_writer,
                "draft_cover_letter_stream",
                return_value=iter(["Madame, Monsieur,"]),
            ) as mock_stream,
            patch.object(agent.application_writer, "contact_header", return_value=""),
        ):
            result = agent.handle_message("d'accord")

        mock_stream.assert_called_once()
        assert result.text == "Madame, Monsieur,"
        assert agent._last_lm == "Madame, Monsieur,"
        assert agent._pending_action is None

    def test_refine_lm_asks_before_executing(self, agent):
        agent._last_lm = "Ancienne lettre."
        agent._last_lm_offer = self._make_offer()
        with patch.object(agent.application_writer, "refine_cover_letter_stream") as mock_stream:
            result = agent.handle_message("affine cette lettre de motivation")

        mock_stream.assert_not_called()
        assert agent._pending_action == {"kind": "refine_lm"}
        assert "?" in result.text

    def test_refine_lm_confirmed_executes(self, agent):
        agent._last_lm = "Ancienne lettre."
        agent._last_lm_offer = self._make_offer()
        agent.handle_message("affine cette lettre de motivation")

        with (
            patch.object(
                agent.application_writer,
                "refine_cover_letter_stream",
                return_value=iter(["Lettre améliorée."]),
            ) as mock_stream,
            patch.object(agent.application_writer, "contact_header", return_value=""),
        ):
            result = agent.handle_message("vas-y")

        mock_stream.assert_called_once()
        assert result.text == "Lettre améliorée."
        assert agent._pending_action is None

    # ---- comportement partagé CLI/API ------------------------------------

    def test_no_pending_action_is_a_no_op(self, agent):
        """Sans rien en attente, une réponse de type "oui" isolée doit
        suivre son routage normal (ici la conversation libre), jamais
        planter sur un `_pending_action` absent."""
        from aelyn_conversation.models import Intent

        with (
            patch.object(
                agent.intent_llm,
                "structured",
                return_value=Intent(commande="inconnu", reformulation=""),
            ),
            patch.object(agent, "_converse") as mock_converse,
        ):
            agent.handle_message("oui")

        mock_converse.assert_called_once()
