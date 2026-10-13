from unittest.mock import Mock

from aelyn_career.application_replies import (
    ReplyAnalysis,
    ReplyOutcome,
    check_application_replies,
    match_application,
)
from aelyn_career.applications import ApplicationsStore, ApplicationStatus
from aelyn_email.models import Mail


def _mail(uid="1", sender="Laura Couepel", sender_email="laura.couepel@phosphea.com",
          subject="Entretien téléphonique phosphea", body="Quelles sont vos disponibilités ?"):
    return Mail(uid=uid, sender=sender, sender_email=sender_email, subject=subject, body=body)


def test_match_application_by_company_in_subject(tmp_path):
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")

    found = match_application(
        store, subject="Entretien téléphonique phosphea", sender="Laura Couepel",
        sender_email="laura.couepel@phosphea.com",
    )
    assert found is not None
    assert found.offer_id == "phosphea-1"


def test_match_application_falls_back_to_sender_domain(tmp_path):
    """Bug réel évité : un mail dont l'objet/l'expéditeur ne mentionne pas
    le nom de l'entreprise (ex. "Re: votre stage") doit quand même être
    retrouvé via le domaine de l'adresse."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")

    found = match_application(
        store, subject="Re: votre stage", sender="Laura",
        sender_email="laura.couepel@phosphea.com",
    )
    assert found is not None
    assert found.offer_id == "phosphea-1"


def test_match_application_returns_none_when_nothing_tracked(tmp_path):
    store = ApplicationsStore(tmp_path / "apps.db")
    found = match_application(
        store, subject="Newsletter hebdomadaire", sender="Le Monde",
        sender_email="contact@lemonde.fr",
    )
    assert found is None


def test_check_application_replies_updates_status_to_entretien(tmp_path):
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")

    llm = Mock()
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=True,
        issue=ReplyOutcome.ENTRETIEN,
        resume="La RH demande un créneau pour un entretien téléphonique.",
        details_entretien="Entretien téléphonique, contact laura.couepel@phosphea.com, 07 88 24 91 39.",
    )

    results = check_application_replies(store, llm, [_mail()])

    assert len(results) == 1
    assert results[0].status_changed is True
    assert results[0].application.status == ApplicationStatus.ENTRETIEN
    assert "Entretien téléphonique" in (results[0].application.notes or "")

    stored = store.get("phosphea-1")
    assert stored.status == ApplicationStatus.ENTRETIEN


def test_check_application_replies_ignores_unmatched_mail(tmp_path):
    """Un mail qui ne correspond à AUCUNE candidature suivie ne doit
    jamais déclencher d'appel LLM (coûteux) ni de résultat."""
    store = ApplicationsStore(tmp_path / "apps.db")
    llm = Mock()

    results = check_application_replies(
        store, llm,
        [_mail(sender_email="newsletter@random.com", subject="Offres de la semaine")],
    )

    assert results == []
    llm.structured.assert_not_called()


def test_check_application_replies_ignores_non_reply_classified_mail(tmp_path):
    """Un mail qui matche une candidature par coïncidence de mots mais
    que le LLM classe comme non pertinent ne doit pas modifier le suivi."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")

    llm = Mock()
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=False,
        issue=ReplyOutcome.NON_PERTINENT,
        resume="Newsletter générique, sans rapport avec une candidature précise.",
    )

    results = check_application_replies(store, llm, [_mail()])

    assert results == []
    stored = store.get("phosphea-1")
    assert stored.status == ApplicationStatus.POSTULE  # inchangé


def test_check_application_replies_does_not_downgrade_on_accuse_reception(tmp_path):
    """Un accusé de réception reçu APRÈS qu'un entretien a déjà été
    enregistré ne doit jamais faire reculer le statut suivi."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")
    store.update_status("phosphea-1", ApplicationStatus.ENTRETIEN)

    llm = Mock()
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=True,
        issue=ReplyOutcome.ACCUSE_RECEPTION,
        resume="Confirmation automatique de bonne réception.",
    )

    results = check_application_replies(store, llm, [_mail()])

    assert len(results) == 1
    assert results[0].status_changed is False
    assert results[0].application.status == ApplicationStatus.ENTRETIEN


def test_check_application_replies_records_journal_entry(tmp_path):
    from aelyn.core.journal import Journal

    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")
    journal = Journal(tmp_path / "journal.db")

    llm = Mock()
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=True,
        issue=ReplyOutcome.ENTRETIEN,
        resume="Demande de créneau pour un entretien.",
    )

    check_application_replies(store, llm, [_mail()], journal=journal)

    entries = journal.since(hours=1, agent="career")
    assert len(entries) == 1
    assert entries[0].action == "reponse_candidature"
