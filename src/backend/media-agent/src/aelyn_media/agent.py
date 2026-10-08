from __future__ import annotations

import asyncio
import re
import threading
import time
from urllib.parse import quote

from androidtvremote2 import AndroidTVRemote, InvalidAuth

from aelyn.core.config import settings


class MediaAgent:
    def __init__(self, remote: AndroidTVRemote) -> None:
        self.remote = remote

    def netflix(self) -> None:
        self.remote.send_launch_app_command("netflix://")
        print("Netflix lancé")

    def youtube(self) -> None:
        self.remote.send_launch_app_command("https://www.youtube.com/")
        print("YouTube lancé")

    def search_youtube(self, query: str) -> None:
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
        self.remote.send_launch_app_command(url)
        print(f"Recherche YouTube : {query}")

    def search_netflix(self, query: str) -> None:
        # KEYCODE_SEARCH est intercepté par l'assistant vocal Google de la
        # Freebox au niveau système (elle s'active mais ne fait rien),
        # jamais transmis à Netflix, remplacé par le deep link de
        # recherche propre à Netflix, qui ne touche à aucune touche globale.
        url = f"netflix://www.netflix.com/search?q={quote(query)}"
        self.remote.send_launch_app_command(url)
        print(f"Recherche Netflix : {query}")

    def tv_power(self) -> None:
        # KEYCODE_TV_POWER (pas KEYCODE_POWER, qui éteindrait/allumerait la
        # Freebox elle-même) : demande à la box de relayer un signal
        # HDMI-CEC vers le téléviseur branché ; n'a d'effet que si le CEC
        # est activé des deux côtés (box ET téléviseur, souvent nommé
        # "Anynet+"/"Bravia Sync"/"SimpLink" selon la marque).
        self.remote.send_key_command("TV_POWER")

    def home(self) -> None:
        self.remote.send_key_command("HOME")

    def back(self) -> None:
        self.remote.send_key_command("BACK")

    def up(self) -> None:
        self.remote.send_key_command("DPAD_UP")

    def down(self) -> None:
        self.remote.send_key_command("DPAD_DOWN")

    def left(self) -> None:
        self.remote.send_key_command("DPAD_LEFT")

    def right(self) -> None:
        self.remote.send_key_command("DPAD_RIGHT")

    def select(self) -> None:
        self.remote.send_key_command("DPAD_CENTER")

    def type_text(self, text: str) -> None:
        self.remote.send_text(text)
        print(f"Texte envoyé : {text}")

    def play_pause(self) -> None:
        # MEDIA_PLAY_PAUSE est le signal "correct", mais Netflix et YouTube
        # sur Freebox Pop ne l'honorent pas de manière fiable (constaté en
        # usage réel) : beaucoup d'apps Android TV ne câblent play/pause
        # qu'au clic OK/Entrée du lecteur (DPAD_CENTER), comme avec une
        # vraie télécommande. On envoie les deux : le signal dédié d'abord
        # (sans effet néfaste s'il est ignoré), puis OK en repli pour les
        # apps qui ne gèrent que ça.
        self.remote.send_key_command("MEDIA_PLAY_PAUSE")
        time.sleep(0.15)
        self.remote.send_key_command("DPAD_CENTER")

    def next(self) -> None:
        self.remote.send_key_command("MEDIA_NEXT")

    def previous(self) -> None:
        self.remote.send_key_command("MEDIA_PREVIOUS")

    def volume_up(self, amount: int = 1) -> None:
        # Le protocole Android TV Remote n'a pas de "monte à X" ni de
        # "monte de X d'un coup" : chaque pression est une seule touche
        # VOLUME_UP, comme une vraie télécommande : "augmente de 5" est
        # donc approximé par 5 pressions successives. Un léger délai
        # entre chaque évite de saturer le bus CEC (certaines TV ignorent
        # des pressions trop rapprochées).
        for _ in range(max(1, amount)):
            self.remote.send_key_command("VOLUME_UP")
            time.sleep(0.05)

    def volume_down(self, amount: int = 1) -> None:
        for _ in range(max(1, amount)):
            self.remote.send_key_command("VOLUME_DOWN")
            time.sleep(0.05)

    def mute(self) -> None:
        self.remote.send_key_command("VOLUME_MUTE")


COMMANDS: dict[str, str] = {
    "netflix": "netflix",
    "youtube": "youtube",
    "allume_tv": "tv_power",
    "home": "home",
    "back": "back",
    "haut": "up",
    "bas": "down",
    "gauche": "left",
    "droite": "right",
    "selectionner": "select",
    "select": "select",
    "pause": "play_pause",
    "suivant": "next",
    "precedent": "previous",
    "volume_plus": "volume_up",
    "volume_moins": "volume_down",
    "muet": "mute",
}


_SEARCH_RE = re.compile(r"^cherche\s+(.+?)\s+sur\s+(youtube|netflix)$", re.IGNORECASE)
_TYPE_RE = re.compile(r"^tape\s+(.+)$", re.IGNORECASE)


def dispatch_action(
    action: str,
    media: MediaAgent,
    query: str | None = None,
    amount: int | None = None,
) -> int:
    """Point d'entrée canonique : `run_command` (REPL texte) et
    `MediaController.dispatch` (agent conversationnel) passent tous deux
    par ici, pour ne jamais dupliquer la logique de dispatch."""
    if action in ("search_youtube", "search_netflix"):
        if not query:
            print(f"Recherche sans requête : {action}")
            return 1
        if action == "search_youtube":
            media.search_youtube(query)
        else:
            media.search_netflix(query)
        return 0

    method = getattr(media, action, None)
    if method is None:
        print(f"Action inconnue : {action}")
        return 1
    if action in ("volume_up", "volume_down") and amount:
        method(amount)
    else:
        method()
    return 0


def run_command(command: str, media: MediaAgent) -> int:
    """`command` garde sa casse d'origine (nécessaire pour `tape <texte>` :
    un titre tapé ne doit pas être mis en minuscules), seule la recherche
    dans `COMMANDS` normalise en minuscules."""
    match = _SEARCH_RE.match(command)
    if match:
        query, service = match.groups()
        return dispatch_action(f"search_{service.lower()}", media, query)

    type_match = _TYPE_RE.match(command)
    if type_match:
        media.type_text(type_match.group(1))
        return 0

    method_name = COMMANDS.get(command.lower())
    if method_name is None:
        print(f"Commande inconnue : {command}")
        return 1
    return dispatch_action(method_name, media)


async def connect_to_player() -> AndroidTVRemote:
    if not settings.tv_ip:
        raise RuntimeError("IP_TV manquant dans .env")

    remote = AndroidTVRemote(
        client_name="AELYN",
        certfile=str(settings.tv_cert_path),
        keyfile=str(settings.tv_key_path),
        host=settings.tv_ip,
    )

    await remote.async_generate_cert_if_missing()

    try:
        await remote.async_connect()
    except InvalidAuth:
        print("Appairage avec la Freebox Pop...")
        await remote.async_start_pairing()
        print("Regarde l'écran de la TV.")
        code = input("Code affiché sur la TV : ").strip().upper().replace("O", "0")
        await remote.async_finish_pairing(code)
        print("AELYN est maintenant appairé.")
        await remote.async_connect()
    print("Freebox Pop connectée.")

    return remote


class MediaController:
    """Pont synchrone vers `MediaAgent` pour un appelant sans event loop
    (`aelyn_conversation`, entièrement synchrone).

    `androidtvremote2` bufferise ses écritures (TLS) et compte sur
    l'event loop qui possède la connexion pour les vider ; sans event
    loop qui tourne en continu, une commande peut s'exécuter sans
    erreur mais ne jamais atteindre la TV (bug rencontré avec
    `scripts/text_chat.py` avant l'ajout d'un `asyncio.sleep`). Ici,
    l'event loop tourne en continu dans un thread dédié pendant toute
    la durée de vie du controller, donc les écritures sont toujours
    vidées normalement, sans hack applelant par appelant.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._media: MediaAgent | None = None

    def _get_media(self) -> MediaAgent:
        if self._media is None:
            remote = asyncio.run_coroutine_threadsafe(connect_to_player(), self._loop).result()
            self._media = MediaAgent(remote)
        return self._media

    def dispatch(
        self, action: str, query: str | None = None, amount: int | None = None
    ) -> int:
        media = self._get_media()

        async def _run() -> int:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, dispatch_action, action, media, query, amount
            )

        return asyncio.run_coroutine_threadsafe(_run(), self._loop).result()
