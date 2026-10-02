"""Script manuel : connecte vraiment la Freebox Pop et teste MediaAgent
en tapant des commandes, sans passer par aelyn_conversation.

Usage :
    cd media-agent
    uv run python scripts/text_chat.py
"""

import asyncio

from aelyn_media.agent import COMMANDS, MediaAgent, connect_to_player, run_command


async def main() -> int:
    remote = await connect_to_player()
    media = MediaAgent(remote)

    print("Commandes : " + ", ".join(COMMANDS) + ", quitter")
    print("Recherche : cherche <requête> sur youtube|netflix")
    print("Texte libre (une fois un champ de recherche sélectionné) : tape <texte>")
    while True:
        command = input("> ").strip()
        if command.lower() in {"quitter", "exit", "quit"}:
            return 0
        run_command(command, media)
        # `send_key_command`/`send_launch_app_command` mettent l'octet
        # chiffré (SSL) en attente d'envoi ; sans ce `await`, la boucle
        # replonge directement dans l'`input()` bloquant suivant sans
        # jamais rendre la main à la boucle asyncio, qui ne peut alors
        # jamais réellement écrire sur le socket : la commande semble
        # s'exécuter (aucune erreur) mais n'atteint jamais la TV.
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
