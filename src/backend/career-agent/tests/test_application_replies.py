from unittest.mock import Mock

from aelyn_career.application_replies import (
    ApplicationConfirmation,
    InterviewDateProposal,
    ReplyAnalysis,
    ReplyOutcome,
    _looks_like_application_confirmation,
    _slugify,
    check_application_replies,
    detect_application_confirmation,
    extract_interview_date,
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


def test_check_application_replies_skips_already_processed_mail_on_second_call(tmp_path):
    """Le bug que corrige le dédoublonnage : un deuxième appel (ex.
    bouton "actualiser") avec le MÊME mail ne doit ni rappeler le LLM,
    ni ajouter une deuxième fois la même note."""
    from aelyn.core.journal import Journal

    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")
    journal = Journal(tmp_path / "journal.db")

    llm = Mock()
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=True,
        issue=ReplyOutcome.ENTRETIEN,
        resume="Demande de créneau.",
    )

    mail = _mail()
    first = check_application_replies(store, llm, [mail], journal=journal)
    second = check_application_replies(store, llm, [mail], journal=journal)

    assert len(first) == 1
    assert second == []
    llm.structured.assert_called_once()

    stored = store.get("phosphea-1")
    assert stored.notes.count("Demande de créneau") == 1


def test_check_application_replies_skips_already_processed_non_relevant_mail(tmp_path):
    """Un mail classé non pertinent une première fois ne doit pas
    redéclencher d'appel LLM au prochain passage non plus."""
    from aelyn.core.journal import Journal

    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")
    journal = Journal(tmp_path / "journal.db")

    llm = Mock()
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=False,
        issue=ReplyOutcome.NON_PERTINENT,
        resume="Sans rapport.",
    )

    mail = _mail()
    check_application_replies(store, llm, [mail], journal=journal)
    check_application_replies(store, llm, [mail], journal=journal)

    llm.structured.assert_called_once()


def test_check_application_replies_retries_mail_after_llm_failure(tmp_path):
    """Un échec LLM (transitoire) ne doit jamais marquer un mail comme
    définitivement vu : il doit rester candidat au prochain appel."""
    from aelyn.core.llm import LLMError
    from aelyn.core.journal import Journal

    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="phosphea-1", title="Stagiaire Biostatistiques H/F", company="Phosphea")
    journal = Journal(tmp_path / "journal.db")

    llm = Mock()
    llm.structured.side_effect = LLMError("indisponible")

    mail = _mail()
    check_application_replies(store, llm, [mail], journal=journal)

    llm.structured.side_effect = None
    llm.structured.return_value = ReplyAnalysis(
        est_reponse_candidature=True,
        issue=ReplyOutcome.ENTRETIEN,
        resume="Demande de créneau.",
    )
    results = check_application_replies(store, llm, [mail], journal=journal)

    assert len(results) == 1
    assert llm.structured.call_count == 2


def test_match_application_matches_via_company_word_in_body_even_when_sender_is_self(tmp_path):
    """Bug réel corrigé : un mail AUTO-TRANSFÉRÉ (l'utilisateur se
    renvoie l'invitation à entretien reçue du recruteur) a pour
    expéditeur sa propre adresse, pas celle du recruteur - le domaine
    est donc inexploitable. Seul un mot distinctif du nom de
    l'entreprise retrouvé dans le CORPS du mail transféré permet de le
    rattacher à la bonne candidature."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="inserm-epiageing-2027", title="Stage EpiAgeing", company="Inserm")

    found = match_application(
        store,
        subject="Fw: entretien stage EpiAgeing 2027 accélérométrie",
        sender="Djamal TOE",
        sender_email="djamaltoe012@gmail.com",
        body="Bonjour, transfert du mail reçu de l'équipe Inserm pour l'entretien.",
    )

    assert found is not None
    assert found.offer_id == "inserm-epiageing-2027"


def test_match_application_ignores_a_generic_word_shared_by_an_unrelated_company_name(tmp_path):
    """Un mot d'entreprise générique (filtré par `_GENERIC_WORDS`) ne
    doit jamais déclencher un rapprochement par coïncidence."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="stage-corp", title="Stagiaire", company="Stage")

    found = match_application(
        store, subject="Votre stage chez une autre entreprise", sender="RH",
        sender_email="rh@autre-entreprise.fr",
    )

    assert found is None


def test_slugify_produces_a_safe_lowercase_offer_id():
    assert _slugify("Phosphea", "Stagiaire Biostatistiques H/F") == "phosphea-stagiaire-biostatistiques-h-f"
    assert _slugify("", "") == "offre"


def test_looks_like_application_confirmation_requires_a_keyword():
    confirming = _mail(subject="Votre candidature a bien été reçue chez ACME")
    unrelated = _mail(subject="Newsletter hebdomadaire", body="Rien à voir.")

    assert _looks_like_application_confirmation(confirming) is True
    assert _looks_like_application_confirmation(unrelated) is False


def test_detect_application_confirmation_returns_none_on_llm_failure():
    from aelyn.core.llm import LLMError

    llm = Mock()
    llm.structured.side_effect = LLMError("indisponible")

    assert detect_application_confirmation(llm, _mail()) is None


def test_check_application_replies_detects_and_tracks_a_new_application(tmp_path):
    """Une candidature envoyée HORS d'AELYN (portail/plateforme), donc
    jamais trackée au préalable, doit être détectée et ajoutée au suivi
    à partir d'un simple accusé de réception."""
    from aelyn.core.journal import Journal

    store = ApplicationsStore(tmp_path / "apps.db")
    journal = Journal(tmp_path / "journal.db")

    llm = Mock()
    llm.structured.return_value = ApplicationConfirmation(
        est_confirmation_candidature=True,
        entreprise="ACME",
        intitule_poste="Stagiaire Data Scientist",
    )

    mail = _mail(
        sender="ACME RH", sender_email="rh@acme.com",
        subject="Votre candidature a bien été reçue",
        body="Nous confirmons la réception de votre candidature.",
    )
    results = check_application_replies(store, llm, [mail], journal=journal)

    assert len(results) == 1
    assert results[0].application.company == "ACME"
    assert results[0].application.status == ApplicationStatus.POSTULE

    tracked = store.list()
    assert len(tracked) == 1
    assert tracked[0].company == "ACME"


def test_check_application_replies_does_not_duplicate_an_already_tracked_company(tmp_path):
    """Un accusé de réception pour une entreprise déjà suivie (sous un
    autre `offer_id`, ex. trackée manuellement avant ce mail) ne doit
    jamais créer une deuxième ligne pour la même candidature. Le mail
    (notification d'une plateforme générique, sans le nom de
    l'entreprise dans l'objet/l'expéditeur) ne doit pas non plus matcher
    via `match_application` - sinon ce test ne couvrirait pas le
    déduplicage propre à `_try_detect_new_application`."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(offer_id="deja-suivie", title="Stagiaire Data Scientist", company="ACME Corporation")

    llm = Mock()
    llm.structured.return_value = ApplicationConfirmation(
        est_confirmation_candidature=True,
        entreprise="ACME Corporation",
        intitule_poste="Stagiaire Data Scientist",
    )

    mail = _mail(
        sender="JobPlatform", sender_email="noreply@jobplatform.com",
        subject="Confirmation de votre candidature",
        body="Votre candidature a été transmise avec succès à l'entreprise.",
    )
    results = check_application_replies(store, llm, [mail])

    assert results == []
    assert len(store.list()) == 1


def test_check_application_replies_ignores_a_confirmation_like_mail_the_llm_rejects(tmp_path):
    """Le préfiltre par mots-clés est volontairement large (faux
    positifs possibles) : c'est au LLM de trancher. Un mail qui contient
    "candidature" sans réellement en confirmer une ne doit rien créer."""
    store = ApplicationsStore(tmp_path / "apps.db")

    llm = Mock()
    llm.structured.return_value = ApplicationConfirmation(
        est_confirmation_candidature=False,
    )

    mail = _mail(
        sender="Newsletter", sender_email="newsletter@random.com",
        subject="Conseils pour réussir votre candidature",
        body="Nos astuces pour une candidature réussie.",
    )
    results = check_application_replies(store, llm, [mail])

    assert results == []
    assert store.list() == []


def test_check_application_replies_skips_already_processed_confirmation_mail(tmp_path):
    """Comme pour une réponse à une candidature suivie, un mail de
    confirmation déjà traité ne doit jamais redéclencher d'appel LLM ni
    recréer la candidature au prochain appel."""
    from aelyn.core.journal import Journal

    store = ApplicationsStore(tmp_path / "apps.db")
    journal = Journal(tmp_path / "journal.db")

    llm = Mock()
    llm.structured.return_value = ApplicationConfirmation(
        est_confirmation_candidature=True,
        entreprise="ACME",
        intitule_poste="Stagiaire Data Scientist",
    )

    mail = _mail(
        sender="ACME RH", sender_email="rh@acme.com",
        subject="Votre candidature a bien été reçue",
        body="Nous confirmons la réception de votre candidature.",
    )
    check_application_replies(store, llm, [mail], journal=journal)
    second = check_application_replies(store, llm, [mail], journal=journal)

    assert second == []
    llm.structured.assert_called_once()
    assert len(store.list()) == 1


def test_application_confirmation_normalizes_placeholder_entreprise_to_none():
    """Bug réel corrigé : un LLM a renvoyé `entreprise="null"` (le mot en
    texte, pas la valeur JSON null) pour un mail qui ne nomme jamais
    l'employeur réel - une chaîne non vide, donc jamais filtrée par un
    simple `if not confirmation.entreprise`, qui a fini par créer une
    candidature affichée "chez null"."""
    confirmation = ApplicationConfirmation(
        est_confirmation_candidature=True, entreprise="null", intitule_poste="Stage X",
    )
    assert confirmation.entreprise is None


def test_check_application_replies_dedupes_by_title_despite_accents_and_unknown_company(tmp_path):
    """Bug réel corrigé : une candidature déjà suivie sous un intitulé
    SANS accents ("Modelisation...") ne doit pas être redoublée par un
    accusé de réception (ex. portail d'école qui ne nomme jamais
    l'employeur réel) ré-extrayant le MÊME intitulé AVEC accents
    ("Modélisation...") - `find_by_text` exige un match exact mot-à-mot
    et échouait sur ce cas, créant une deuxième ligne avec une entreprise
    manquante."""
    store = ApplicationsStore(tmp_path / "apps.db")
    store.record(
        offer_id="phim-ceem-sharka",
        title="Modelisation epidemio-economique de decisions heterogenes virose Prunus",
        company="PHIM / CEE-M",
    )

    llm = Mock()
    llm.structured.return_value = ApplicationConfirmation(
        est_confirmation_candidature=True,
        entreprise=None,
        intitule_poste="Modélisation épidémio-économique de décisions hétérogènes virose Prunus",
    )

    mail = _mail(
        sender="ENSAI Network", sender_email="contact@ensai.org",
        subject='Merci d\'avoir candidaté pour "Modélisation épidémio-économique..."',
        body="Votre candidature a bien été prise en compte.",
    )
    results = check_application_replies(store, llm, [mail])

    assert results == []
    tracked = store.list()
    assert len(tracked) == 1
    assert tracked[0].offer_id == "phim-ceem-sharka"


def test_interview_date_proposal_normalizes_placeholder_entreprise_to_none():
    proposal = InterviewDateProposal(entreprise="null", date_entretien="20/10 à 14h")
    assert proposal.entreprise is None
    assert proposal.date_entretien == "20/10 à 14h"


def test_extract_interview_date_returns_none_on_llm_failure():
    from aelyn.core.llm import LLMError

    llm = Mock()
    llm.structured.side_effect = LLMError("indisponible")

    assert extract_interview_date(llm, "mon entretien chez Phosphea est le 20/10") is None


def test_extract_interview_date_returns_parsed_proposal():
    llm = Mock()
    llm.structured.return_value = InterviewDateProposal(
        entreprise="Phosphea", date_entretien="20/10 à 14h"
    )

    proposal = extract_interview_date(llm, "mon entretien chez Phosphea est le 20/10 à 14h")

    assert proposal is not None
    assert proposal.entreprise == "Phosphea"
    assert proposal.date_entretien == "20/10 à 14h"


def test_interview_date_proposal_discards_a_date_entretien_with_no_real_date():
    """Bug réel observé en direct : pour "on me demande ma disponibilité
    pour le second entretien" (AUCUNE date dans la phrase), le LLM a
    renvoyé `date_entretien="second entretien"` - un simple rappel du
    contexte, pas une date - qui a ÉCRASÉ une date déjà enregistrée. Garde-
    fou déterministe : sans chiffre/mois/jour de semaine/"demain" dans la
    valeur elle-même, `date_entretien` est ramené à `None`."""
    proposal = InterviewDateProposal(entreprise="Phosphea", date_entretien="second entretien")
    assert proposal.date_entretien is None


def test_interview_date_proposal_keeps_a_date_entretien_with_a_weekday_but_no_digit():
    proposal = InterviewDateProposal(entreprise="Phosphea", date_entretien="lundi prochain")
    assert proposal.date_entretien == "lundi prochain"
