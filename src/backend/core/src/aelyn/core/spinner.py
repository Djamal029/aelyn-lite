"""Indicateur visuel animé pour le mode vocal (`aelyn chat --voix`).

Sans lui, le terminal reste figé pendant que Kokoro/Edge TTS parle ou que
le micro écoute activement : rien ne distingue visuellement "AELYN
travaille" d'un programme figé/planté. Un simple spinner texte, mis à
jour en place (`\\r`, comme Siri qui pulse pendant qu'il écoute/répond),
suffit à lever le doute sans machinerie graphique.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time

_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """Contexte : affiche `label` avec un caractère qui tourne pendant que
    le bloc `with` s'exécute, efface la ligne à la sortie. S'enroule
    autour de n'importe quel appel bloquant (synthèse vocale, écoute
    micro) SANS changer son comportement ni avaler ses exceptions :
    celles-ci remontent normalement, l'affichage est juste nettoyé avant.
    """

    def __init__(self, label: str, *, interval: float = 0.08) -> None:
        self._label = label
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        for frame in itertools.cycle(_FRAMES):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r{frame} {self._label}")
            sys.stdout.flush()
            time.sleep(self._interval)

    def __enter__(self) -> "Spinner":
        # Pas de spinner sur une sortie non interactive (pipe, fichier,
        # test automatisé) : les caractères `\r` y polluent la sortie sans
        # jamais s'afficher comme une animation.
        if sys.stdout.isatty():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            # Efface la ligne du spinner : sans ça, le prochain print()
            # s'accroche à la fin du dernier frame affiché.
            sys.stdout.write("\r" + " " * (len(self._label) + 4) + "\r")
            sys.stdout.flush()
