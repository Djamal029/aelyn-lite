"""Point d'entrée CLI unique d'AELYN.

Un sous-programme par agent. Ce module ne connaît que des sous-commandes
et délègue toute la logique aux agents eux-mêmes :

- `verifier`/`triage`/`valider`/`rejeter`/`rapport` -> `aelyn_email.agent.run_command`
- `chat`                                            -> `aelyn_conversation.agent.ConversationalAgent`

Les futurs `aelyn_career`, `aelyn_computer`, etc. s'ajouteront de la
même façon : ce fichier reste un simple routeur de sous-commandes.
"""

from __future__ import annotations

import argparse
import logging
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aelyn", description="Assistant personnel local AELYN")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs détaillés")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verifier = sub.add_parser(
        "verifier", help="Teste la connexion IMAP et liste les non-lus, sans LLM"
    )
    p_verifier.add_argument("--limit", type=int, default=None)

    p_triage = sub.add_parser("triage", help="Analyse les mails non lus et propose une action chacun")
    p_triage.add_argument("--limit", type=int, default=None)

    p_valider = sub.add_parser("valider", help="Exécute une proposition validée")
    p_valider.add_argument("id", type=int)

    p_rejeter = sub.add_parser("rejeter", help="Rejette une proposition")
    p_rejeter.add_argument("id", type=int)

    p_rapport = sub.add_parser("rapport", help="Résume les actions récentes")
    p_rapport.add_argument("--hours", type=int, default=24)

    p_chat = sub.add_parser("chat", help="Mode conversationnel : tape des phrases libres")
    p_chat.add_argument(
        "--voix", action="store_true", help="Micro en entrée, voix (Kokoro) en sortie"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    # La console Windows encode en cp1252 par défaut : un sujet de mail
    # avec un accent ou un emoji fait planter un simple print() sinon.
    # `stdin` doit être reconfiguré au même titre : une entrée non
    # interactive (pipe, redirection depuis un fichier) est lue via cette
    # même page de code par défaut sur Windows, ce qui corrompt tout
    # accent AVANT même que le texte n'atteigne `input()` (observé :
    # "rédige" devenait "rÃ©dige", un mojibake UTF-8 mal relu en cp1252) ;
    # la saisie clavier interactive réelle n'est pas concernée (elle passe
    # par l'API console Windows, pas par cette page de code).
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "chat":
        from aelyn_conversation.agent import ConversationalAgent

        try:
            return ConversationalAgent(voice=args.voix).run()
        except KeyboardInterrupt:
            # Filet de sécurité : `run()` n'attrape Ctrl+C qu'autour de
            # l'écoute micro. Le presser PENDANT qu'AELYN parle (Kokoro
            # en cours de synthèse) ou pendant un appel LLM/IMAP plante
            # sinon avec une trace brute au lieu de quitter proprement.
            print()
            return 0

    from aelyn_email.agent import run_command

    code, _mails, _triage = run_command(
        args.command,
        limit=getattr(args, "limit", None),
        action_id=getattr(args, "id", None),
        hours=getattr(args, "hours", 24),
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
