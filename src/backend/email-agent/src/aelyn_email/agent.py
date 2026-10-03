"""Agent email d'AELYN.

Trois responsabilités, trois méthodes publiques :

    triage()            lit la boîte, propose une action par mail, ne fait rien
    execute(id)         exécute UNE proposition validée par l'utilisateur
    compte_rendu()      raconte ce qui a été fait, en lisant le journal

Le LLM n'exécute jamais d'action. Il classe et il rédige. La décision
d'agir appartient à l'utilisateur, l'exécution appartient au code.

`run_command()` (en bas de fichier) est le point d'entrée partagé par
la CLI directe (`aelyn triage`) et l'agent conversationnel : un seul
endroit qui sait comment traduire un nom de commande en appel de
méthode, imprimer le résultat lisible par un humain, et gérer les
erreurs, pour ne pas dupliquer cette logique dans chaque appelant.
"""

from __future__ import annotations

import logging
import sys

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from aelyn.core.config import settings
from aelyn.core.journal import Action, ActionStatus, Journal
from aelyn.core.llm import LLMClient, LLMError

from aelyn_email import client
from aelyn_email.client import MailboxError
from aelyn_email.models import Category, Mail, ProposedAction, Triage
from aelyn_email.prompts import SYSTEM_REPORT, SYSTEM_TRIAGE

logger = logging.getLogger(__name__)

AGENT_NAME = "email"


class EmailAgent:
    def __init__(self, llm: LLMClient | None = None, journal: Journal | None = None) -> None:
        self.llm = llm or LLMClient()
        self.journal = journal or Journal(settings.journal_path)

    # ------------------------------------------------------------- 1. triage

    def triage(self, limit: int | None = None) -> list[tuple[Mail, Triage, int]]:
        """Lit les non-lus et enregistre une proposition par mail.

        Rien n'est envoyé, archivé ni marqué comme lu à ce stade. Un mail
        non lu reste non lu tant qu'on ne l'a pas validé/rejeté ; donc il
        réapparaît à CHAQUE appel de `triage()`, et repasserait par le LLM
        à chaque fois sans le cache ci-dessous (lenteur proportionnelle au
        nombre de mails non lus accumulés, pas au nombre de NOUVEAUX mails).
        """
        mails = client.list_unread(limit)
        if not mails:
            logger.info("Aucun mail non lu.")
            return []

        # Propositions déjà faites (pas encore validées/rejetées) : on les
        # réutilise au lieu de rappeler le LLM pour un mail déjà vu.
        deja_triage = {
            action.payload["uid"]: action
            for action in self.journal.pending(agent=AGENT_NAME)
            if "uid" in action.payload
        }

        resultats: list[tuple[Mail, Triage, int]] = []

        # Un mail à la fois : un petit modèle perd en précision dès qu'on
        # lui empile plusieurs documents dans le même contexte.
        for mail in mails:
            if mail.uid in deja_triage:
                action = deja_triage[mail.uid]
                try:
                    analyse = Triage(
                        categorie=Category(action.payload["categorie"]),
                        urgence=action.payload["urgence"],
                        resume=action.payload["resume"],
                        action_proposee=ProposedAction(action.action),
                        justification=action.payload["justification"],
                        brouillon_reponse=action.payload["brouillon"],
                    )
                except ValidationError:
                    # Une proposition déjà enregistrée (avant le correctif de
                    # troncature ci-dessous) peut avoir une `justification`
                    # trop longue en base : `model_copy()` ne revalide pas à
                    # l'écriture, seule la RELECTURE ici le détecte. Sans ce
                    # garde-fou, UN SEUL mail avec une entrée corrompue
                    # plantait tout `triage()` (plus aucun mail analysé, pas
                    # seulement celui-ci), observé en direct. On retombe sur
                    # un nouvel appel LLM pour ce mail plutôt que de
                    # perdre tous les autres résultats déjà calculés.
                    logger.warning(
                        "Proposition #%s corrompue (justification trop longue), nouvelle analyse de %s",
                        action.id,
                        mail.uid,
                    )
                else:
                    resultats.append((mail, analyse, action.id))
                    continue

            try:
                analyse = self.llm.structured(
                    schema=Triage,
                    system=SYSTEM_TRIAGE,
                    user=mail.for_llm(),
                )
            except LLMError:
                logger.exception("Triage impossible pour le mail %s", mail.uid)
                continue

            if analyse.action_proposee is ProposedAction.REPONDRE and mail.is_no_reply:
                # Garde-fou déterministe : le LLM suit cette règle de façon
                # inconstante (cf. docstring de `Mail.is_no_reply`).
                suffix = " [repondre écarté par le code : adresse automatisée]"
                # `model_copy()` NE revalide PAS (contrairement à `Triage(...)`
                # à la relecture du cache ci-dessus) : une justification déjà
                # proche de la limite devient silencieusement trop longue une
                # fois le suffixe ajouté, et plante au premier rechargement
                # depuis le journal (observé en direct : plus aucun mail
                # analysé tant que cette entrée restait non lue). Troncature
                # au lieu de laisser `model_copy` écrire une valeur invalide.
                justification = analyse.justification[: 200 - len(suffix)] + suffix
                analyse = analyse.model_copy(
                    update={
                        "action_proposee": ProposedAction.ARCHIVER,
                        "brouillon_reponse": None,
                        "justification": justification,
                    }
                )

            action_id = self.journal.record(
                agent=AGENT_NAME,
                action=analyse.action_proposee.value,
                target=mail.sender_email,
                summary=f"{mail.subject} : {analyse.resume}",
                status=ActionStatus.PROPOSED,
                payload={
                    "uid": mail.uid,
                    "subject": mail.subject,
                    "categorie": analyse.categorie.value,
                    "urgence": analyse.urgence,
                    "resume": analyse.resume,
                    "justification": analyse.justification,
                    "brouillon": analyse.brouillon_reponse,
                },
            )
            resultats.append((mail, analyse, action_id))

        resultats.sort(key=lambda r: r[1].urgence, reverse=True)
        return resultats

    # ------------------------------------------------------------ 2. exécuter

    def execute(self, action_id: int) -> bool:
        """Exécute une proposition après validation humaine."""
        action = self.journal.get(action_id)
        if action is None:
            raise ValueError(f"Action {action_id} introuvable")
        if action.status is not ActionStatus.PROPOSED:
            raise ValueError(f"Action {action_id} déjà traitée ({action.status.value})")

        uid = action.payload["uid"]

        try:
            match ProposedAction(action.action):
                case ProposedAction.REPONDRE:
                    if not settings.allow_autonomous_send:
                        logger.info("Envoi désactivé (allow_autonomous_send=False)")
                        return False
                    client.send_reply(
                        to=action.target or "",
                        subject=action.payload["subject"],
                        body=action.payload["brouillon"] or "",
                    )
                    client.mark_seen(uid)

                case ProposedAction.ARCHIVER:
                    client.archive(uid)

                case ProposedAction.IGNORER:
                    client.mark_seen(uid)

                case ProposedAction.LIRE_PLUS_TARD | ProposedAction.SIGNALER:
                    pass  # laissé non lu, volontairement

        except Exception as exc:
            self.journal.update_status(action_id, ActionStatus.FAILED)
            logger.exception("Échec de l'action %s : %s", action_id, exc)
            return False

        self.journal.update_status(action_id, ActionStatus.EXECUTED)
        return True

    def reject(self, action_id: int) -> None:
        """Rejette une proposition après validation humaine.

        Mêmes vérifications que `execute()` : sans ça, rejeter un
        identifiant inexistant ou déjà traité "réussissait" en silence
        (l'UPDATE touchait 0 ligne) alors que rien ne s'était passé.
        """
        action = self.journal.get(action_id)
        if action is None:
            raise ValueError(f"Action {action_id} introuvable")
        if action.status is not ActionStatus.PROPOSED:
            raise ValueError(f"Action {action_id} déjà traitée ({action.status.value})")
        self.journal.update_status(action_id, ActionStatus.REJECTED)

    # --------------------------------------------------------- 3. compte rendu

    def compte_rendu(self, hours: int = 24) -> str:
        """« Qu'est-ce que tu as fait ? » : répondu depuis le journal, pas de mémoire."""
        actions: list[Action] = self.journal.since(hours=hours, agent=AGENT_NAME)
        if not actions:
            return f"Aucune action sur les {hours} dernières heures."

        lignes = "\n".join(a.to_line() for a in actions)
        return self.llm.text(
            system=SYSTEM_REPORT,
            user=f"Journal des {hours} dernières heures :\n\n{lignes}",
        )


def _preview(body: str, max_lines: int = 2, max_chars: int = 100) -> str:
    """Aperçu court du corps d'un mail : quelques lignes non vides, tronquées."""
    lignes = [line.strip() for line in body.splitlines() if line.strip()]
    apercu = " / ".join(lignes[:max_lines])
    if len(apercu) > max_chars:
        apercu = apercu[:max_chars].rstrip() + "…"
    return apercu or "(vide)"


def _print_mail_table(mails: list[Mail]) -> None:
    """Tableau expéditeur/objet/date/aperçu, lecture d'un coup d'œil en CLI directe.

    Pas utilisé quand l'appelant est l'agent conversationnel (`plain=True`) :
    les bordures Rich casseraient `_group_result_lines`, qui regroupe la
    sortie capturée en une entrée par mail pour "lis le premier"/"résume
    le mail de X".
    """
    table = Table(show_lines=True)
    table.add_column("Expéditeur", overflow="fold", max_width=28)
    table.add_column("Objet", overflow="fold", max_width=40)
    table.add_column("Date", no_wrap=True)
    table.add_column("Aperçu", overflow="fold", max_width=40)
    for mail in mails:
        date = mail.date.strftime("%d/%m %H:%M") if mail.date else "-"
        table.add_row(f"[{mail.uid}] {mail.sender}", mail.subject, date, _preview(mail.body))
    Console().print(table)


def run_command(
    command: str,
    *,
    limit: int | None = None,
    action_id: int | None = None,
    hours: int = 24,
    agent: EmailAgent | None = None,
    plain: bool = False,
) -> tuple[int, list[Mail], list[dict] | None]:
    """Exécute une commande déjà résolue (verifier/triage/valider/rejeter/rapport).

    Point d'entrée partagé par `aelyn.cli` (sous-commandes directes) et
    `aelyn_conversation` (chat) : imprime un résultat lisible et rend un
    code de sortie, sans jamais faire fuiter `LLMError`/`MailboxError`
    à l'appelant. `agent`, s'il est fourni, est réutilisé tel quel (pas
    de nouveau `LLMClient` par appel), sinon il n'est construit que si
    la commande en a réellement besoin (`verifier` n'en a pas besoin).

    Retourne aussi les `Mail` traités par `verifier`/`triage` (liste vide
    sinon), pour qu'un appelant puisse ensuite résumer/répondre à l'un
    d'eux précisément, sans refaire une requête IMAP.

    Le 3e élément porte, UNIQUEMENT pour `triage` (`None` sinon), l'analyse
    par mail (`action_proposee`/`urgence`/`resume`/`action_id`) : `triage()`
    la calculait déjà mais ne la renvoyait jamais au-delà de cette fonction
    (seuls les `Mail` nus sortaient), donc aucun appelant - CLI ou agent
    conversationnel - ne pouvait afficher l'action proposée ailleurs que
    dans le texte imprimé ici.

    `plain=True` (utilisé par `aelyn_conversation`) garde le format simple
    une-ligne-par-mail au lieu du tableau Rich, pour ne pas casser le
    regroupement de la sortie capturée (cf. `_print_mail_table`).
    """
    try:
        if command == "verifier":
            mails = client.list_unread(limit)
            if not mails:
                print("Aucun mail non lu.")
                return 0, [], None
            if plain:
                for mail in mails:
                    print(f"[{mail.uid}] {mail.sender} <{mail.sender_email}> : {mail.subject}")
            else:
                _print_mail_table(mails)
            return 0, mails, None

        if agent is None:
            agent = EmailAgent()

        if command == "triage":
            print("Un instant, je m'en charge…")
            resultats = agent.triage(limit)
            if not resultats:
                print("Aucun mail non lu.")
                return 0, [], None
            for mail, analyse, action_id_ in resultats:
                print(
                    f"#{action_id_} [urgence {analyse.urgence}] "
                    f"{analyse.action_proposee.value} : {mail.subject}"
                )
                print(f"    {analyse.resume}")
            triage_info = [
                {
                    "uid": mail.uid,
                    "action_proposee": analyse.action_proposee.value,
                    "urgence": analyse.urgence,
                    "resume": analyse.resume,
                    "action_id": action_id_,
                }
                for mail, analyse, action_id_ in resultats
            ]
            return 0, [mail for mail, _, _ in resultats], triage_info

        if command == "valider":
            ok = agent.execute(action_id)
            print("Exécuté." if ok else "Non exécuté (voir logs).")
            return (0 if ok else 1), [], None

        if command == "rejeter":
            agent.reject(action_id)
            print(f"Proposition #{action_id} rejetée.")
            return 0, [], None

        if command == "rapport":
            print("Un instant, je m'en charge…")
            print(agent.compte_rendu(hours))
            return 0, [], None

        return 1, [], None
    except (LLMError, MailboxError, ValueError) as exc:
        # ValueError : numéro d'action inexistant/déjà traité (execute/reject).
        # Une entrée utilisateur (ou une reconnaissance vocale) invalide ne
        # doit jamais planter toute la session, juste être signalée.
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1, [], None