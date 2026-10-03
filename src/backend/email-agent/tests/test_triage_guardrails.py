from datetime import datetime, timezone
from unittest.mock import Mock, patch

from aelyn.core.journal import Action, ActionStatus
from aelyn_email.agent import EmailAgent
from aelyn_email.models import Category, Mail, ProposedAction, Triage


def make_mail() -> Mail:
    return Mail(
        uid="123",
        sender="La Poste",
        sender_email="offres@laposte.example",
        subject="Offre spéciale pour les seniors",
        body="Promotion valable jusqu'à la fin du mois.",
    )


def make_newsletter_analysis() -> Triage:
    return Triage(
        categorie=Category.NEWSLETTER,
        urgence=5,
        resume="Promotion commerciale sans réponse attendue.",
        action_proposee=ProposedAction.REPONDRE,
        justification="Le message demande une réponse immédiate.",
        brouillon_reponse="Bonjour, je suis intéressé.",
    )


def test_newsletter_is_never_urgent_or_answered():
    mail = make_mail()
    llm = Mock()
    llm.structured.return_value = make_newsletter_analysis()
    journal = Mock()
    journal.pending.return_value = []
    journal.record.return_value = 7
    agent = EmailAgent(llm=llm, journal=journal)

    with patch("aelyn_email.agent.client.list_unread", return_value=[mail]):
        results = agent.triage()

    _, analysis, action_id = results[0]
    assert action_id == 7
    assert analysis.urgence == 1
    assert analysis.action_proposee is ProposedAction.ARCHIVER
    assert analysis.brouillon_reponse is None
    assert journal.record.call_args.kwargs["action"] == ProposedAction.ARCHIVER.value


def test_cached_newsletter_proposal_is_corrected_in_place():
    mail = make_mail()
    action = Action(
        id=9,
        ts=datetime.now(timezone.utc),
        agent="email",
        action=ProposedAction.REPONDRE.value,
        target=mail.sender_email,
        summary=f"{mail.subject} : Promotion commerciale.",
        status=ActionStatus.PROPOSED,
        payload={
            "uid": mail.uid,
            "subject": mail.subject,
            "categorie": Category.NEWSLETTER.value,
            "urgence": 5,
            "resume": "Promotion commerciale.",
            "justification": "Répondre rapidement.",
            "brouillon": "Bonjour.",
        },
    )
    journal = Mock()
    journal.pending.return_value = [action]
    agent = EmailAgent(llm=Mock(), journal=journal)

    with patch("aelyn_email.agent.client.list_unread", return_value=[mail]):
        results = agent.triage()

    _, analysis, action_id = results[0]
    assert action_id == 9
    assert analysis.urgence == 1
    assert analysis.action_proposee is ProposedAction.ARCHIVER
    journal.revise_proposed.assert_called_once()
    assert (
        journal.revise_proposed.call_args.kwargs["action"]
        == ProposedAction.ARCHIVER.value
    )
    assert journal.revise_proposed.call_args.kwargs["payload"]["urgence"] == 1


def test_passive_action_outside_newsletter_spam_category_is_also_deurgentized():
    """Constaté en direct : une newsletter que le LLM catégorise "autre"
    (pas "newsletter") tout en proposant lui-même archiver/ignorer peut
    quand même garder urgence=5 - la catégorie ne déclenchait pas la
    correction, et celle-ci ne regardait jamais l'action réellement
    choisie en dehors de newsletter/spam."""
    mail = make_mail()
    llm = Mock()
    llm.structured.return_value = Triage(
        categorie=Category.AUTRE,
        urgence=5,
        resume="Newsletter marketing non catégorisée comme telle par le LLM.",
        action_proposee=ProposedAction.ARCHIVER,
        justification="Contenu promotionnel sans action requise.",
        brouillon_reponse=None,
    )
    journal = Mock()
    journal.pending.return_value = []
    journal.record.return_value = 11
    agent = EmailAgent(llm=llm, journal=journal)

    with patch("aelyn_email.agent.client.list_unread", return_value=[mail]):
        results = agent.triage()

    _, analysis, _ = results[0]
    assert analysis.urgence == 1
    assert analysis.action_proposee is ProposedAction.ARCHIVER
