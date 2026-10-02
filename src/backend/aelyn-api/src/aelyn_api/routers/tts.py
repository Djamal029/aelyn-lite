"""Synthèse vocale (Kokoro / Edge TTS) exposée à l'API : même voix que
`aelyn chat --voix` (cf. `aelyn.core.voice`), pour que le frontend web
n'ait plus à se rabattre sur la voix robotique du navigateur
(`speechSynthesis`).

Contrairement au CLI (`speak()`, qui joue l'audio sur les haut-parleurs
de la machine qui exécute AELYN), cette route renvoie les octets audio
bruts : c'est le NAVIGATEUR qui joue le son, pas la machine qui héberge
l'API, nécessaire puisque ce ne sont généralement pas la même machine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from aelyn.core.voice import VoiceError, synthesize_audio

router = APIRouter(tags=["tts"])


class TTSIn(BaseModel):
    text: str


@router.post("/tts")
def synthesize(body: TTSIn) -> Response:
    """Renvoie l'audio synthétisé pour `body.text`.

    Content-Type variable selon le moteur qui a effectivement répondu :
    `audio/mpeg` (MP3) si Edge TTS a réussi (le cas courant, en ligne),
    `audio/wav` (WAV) si replié sur Kokoro (hors-ligne, ou Edge TTS en
    échec), le frontend doit gérer les deux, jamais un seul supposé.
    """
    if not body.text.strip():
        raise HTTPException(400, "Texte vide.")
    try:
        audio_bytes, content_type = synthesize_audio(body.text)
    except VoiceError as exc:
        raise HTTPException(502, f"Synthèse vocale indisponible : {exc}") from exc
    return Response(content=audio_bytes, media_type=content_type)
