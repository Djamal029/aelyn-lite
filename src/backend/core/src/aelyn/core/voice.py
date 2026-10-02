"""Entrées/sorties vocales d'AELYN : micro (SpeechRecognition) et voix (Kokoro).

Optionnel : nécessite l'extra `voice` (`uv sync --extra voice`) et, pour
le français, `espeak-ng` installé au niveau système (phonémisation via
`misaki`). Le reste d'AELYN fonctionne très bien sans ce module ; il
échoue avec un message clair plutôt qu'un `ModuleNotFoundError` brut si
on l'appelle sans ces dépendances.
"""

from __future__ import annotations

import logging
import re
import threading
import urllib.request
from functools import lru_cache
from pathlib import Path

from aelyn.core.config import settings

logger = logging.getLogger(__name__)

# Assets figés sur le tag model-files-v1.0 (vérifiés vivants) plutôt que
# "latest" : on ne veut pas qu'un futur renommage upstream casse ça.
_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_URL = f"{_RELEASE}/kokoro-v1.0.int8.onnx"
VOICES_URL = f"{_RELEASE}/voices-v1.0.bin"
VOICE_NAME = "ff_siwis"  # seule voix française de Kokoro
ESPEAK_LANG = "fr-fr"

# espeak-ng décrit les emojis au lieu de les ignorer ("😊" -> "visage
# souriant") : on les retire avant de synthétiser, jamais utile à l'oral.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️]+"
)
# "13e", "1er", "2ème" lus lettre par lettre ("13 e") plutôt qu'en toutes
# lettres, le françcais n'est qu'une langue de secours pour ce moteur
# (cf. ESPEAK_LANG), ses règles de lecture des nombres n'y sont pas
# toutes appliquées.
_ORDINAL_RE = re.compile(r"\b(\d+)(?:ère|ème|eme|er|re|nde|nd|e)\b", re.IGNORECASE)


def _expand_ordinal(match: re.Match[str]) -> str:
    try:
        from num2words import num2words

        return num2words(int(match.group(1)), lang="fr", to="ordinal")
    except Exception:  # num2words absent ou nombre non géré : on laisse tel quel
        return match.group(0)


def _prepare_for_speech(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _ORDINAL_RE.sub(_expand_ordinal, text)
    return text.strip()


class VoiceError(RuntimeError):
    pass


class VoiceTimeout(VoiceError):
    """Aucune parole détectée avant la limite de temps (silence)."""


class VoiceNotUnderstood(VoiceError):
    """De la parole a été détectée mais n'a pas pu être reconnue."""


def _kokoro_dir() -> Path:
    path = settings.data_dir / "kokoro"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_model_files() -> tuple[Path, Path]:
    model_path = _kokoro_dir() / "kokoro-v1.0.int8.onnx"
    voices_path = _kokoro_dir() / "voices-v1.0.bin"

    if not model_path.exists():
        print("Téléchargement du modèle vocal Kokoro (~90 Mo, une seule fois)…")
        urllib.request.urlretrieve(MODEL_URL, model_path)
    if not voices_path.exists():
        print("Téléchargement des voix Kokoro (~26 Mo, une seule fois)…")
        urllib.request.urlretrieve(VOICES_URL, voices_path)

    return model_path, voices_path


def _resolve_microphone_index(sr) -> int | None:
    """Index du micro dont le nom contient `settings.microphone_name`, ou `None` (défaut système)."""
    wanted = settings.microphone_name
    if not wanted:
        return None

    names = sr.Microphone.list_microphone_names()
    for index, name in enumerate(names):
        if wanted.lower() in name.lower():
            return index

    raise VoiceError(
        f"Aucun micro ne correspond à « {wanted} » (MICROPHONE_NAME dans .env). "
        f"Micros disponibles : {', '.join(names)}"
    )


# Amorce le décodage de Whisper vers le vocabulaire mélangé qui lui pose
# problème par défaut (métiers/technos en anglais dans une phrase française,
# noms propres), cf. bug rapporté : "Data Scientist", "Cauchy" mal reconnus.
_WHISPER_INITIAL_PROMPT = (
    "Conversation en français, avec parfois des termes techniques anglais : "
    "Data Scientist, Machine Learning, Deep Learning, stage, alternance, CDI, CDD."
)


def _register_cuda_dll_dirs() -> None:
    """ctranslate2 (moteur de faster-whisper) charge cublas64_12.dll /
    cudnn64_9.dll par `LoadLibrary` dynamique, mais ces .dll ne sont ni
    sur le PATH système ni fournies par ctranslate2 lui-même : elles
    viennent des paquets pip `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`
    (extra `voice`), installés mais invisibles à Windows tant que leur
    dossier n'est pas enregistré explicitement (`os.add_dll_directory`,
    Windows uniquement)."""
    import os
    import sys

    if sys.platform != "win32":
        return
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ModuleNotFoundError:
        return
    # Sur Windows ces paquets rangent les .dll sous bin/, pas lib/ (qui
    # n'existe même pas ici), contrairement au snippet habituel écrit
    # pour Linux (nvidia.cublas.lib). Paquets namespace (pas d'__init__.py)
    # donc `__file__` vaut None : on passe par `__path__` à la place.
    for package in (nvidia.cublas, nvidia.cudnn):
        bin_dir = os.path.join(package.__path__[0], "bin")
        if not os.path.isdir(bin_dir):
            continue
        os.add_dll_directory(bin_dir)
        # `os.add_dll_directory` seul ne suffit pas : ctranslate2 charge
        # cuBLAS/cuDNN via un `LoadLibrary` qui ignore les répertoires
        # ajoutés par cette API et ne respecte que le PATH classique
        # (vérifié empiriquement : la seule des deux qui a fait passer
        # l'erreur "Library cublas64_12.dll is not found").
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


@lru_cache(maxsize=1)
def _get_whisper_model():
    _register_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    compute_type = "float16" if settings.whisper_device == "cuda" else "int8"
    return WhisperModel(
        settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=compute_type,
    )


def _transcribe_whisper(audio) -> str:
    """Transcription locale (GPU si dispo) : bien plus robuste que
    `recognize_google` sur le français mélangé à de l'anglais technique
    et les noms propres. Lève une exception (modèle absent, GPU
    indisponible, pas encore téléchargé faute de connexion...) plutôt que
    de la gérer ici ; `transcribe()` bascule alors sur `recognize_google`."""
    import io

    model = _get_whisper_model()
    segments, _ = model.transcribe(
        io.BytesIO(audio.get_wav_data()),
        language="fr",
        initial_prompt=_WHISPER_INITIAL_PROMPT,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    # Sans ce log, impossible de diagnostiquer un "ça ne marche pas" : la
    # seule trace visible sinon est le "Processing audio..." de
    # faster_whisper lui-même, qui ne dit jamais CE QUI a été reconnu.
    logger.info("Whisper a reconnu : %r", text)
    if not text:
        raise VoiceNotUnderstood("Parole non reconnue (Whisper).")
    return text


def transcribe(
    *,
    timeout: float | None = 8.0,
    phrase_time_limit: float = 12.0,
    quiet: bool = False,
    calibrate: bool = True,
) -> str:
    """Enregistre une phrase depuis le micro et retourne le texte reconnu (français).

    `timeout` borne l'attente du DÉBUT de la parole (silence prolongé) ;
    `phrase_time_limit` borne la durée de la phrase une fois commencée.
    `quiet` supprime l'indicateur imprimé, utile en boucle de veille
    (attente du mot d'activation), où l'afficher à chaque tentative
    deviendrait vite du bruit visuel.
    `calibrate` recalibre le seuil de bruit ambiant (0,5s de plus) ;
    à désactiver dans une boucle de veille serrée, où cette latence se
    sent à chaque cycle sans apporter grand-chose sur un mot court.
    """
    try:
        import speech_recognition as sr
    except ModuleNotFoundError as exc:
        raise VoiceError(
            "Reconnaissance vocale indisponible : installez l'extra `voice` "
            "(`uv sync --extra voice`)."
        ) from exc

    device_index = _resolve_microphone_index(sr)
    recognizer = sr.Recognizer()
    # Seuil plancher après calibration : dans une pièce très calme,
    # `adjust_for_ambient_noise` peut fixer un seuil si bas qu'un bruit
    # anodin (souris, chaise, souffle) est ensuite pris pour le début
    # d'une phrase, échoue à la reconnaissance, et déclenche "je n'ai pas
    # compris" en boucle. `dynamic_energy_threshold=False` évite en plus
    # que ce seuil ne dérive pendant l'écoute elle-même.
    recognizer.dynamic_energy_threshold = False
    with sr.Microphone(device_index=device_index) as source:
        if calibrate:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            recognizer.energy_threshold = max(recognizer.energy_threshold, 300)
        if not quiet:
            print("🎙️  Je t'écoute...")
        try:
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit
            )
        except sr.WaitTimeoutError as exc:
            raise VoiceTimeout("Aucune parole détectée.") from exc

    try:
        return _transcribe_whisper(audio)
    except Exception as exc:
        # Modèle absent, GPU indisponible, pas encore téléchargé faute de
        # connexion... : on retombe sur l'API Google, jamais de plantage
        # pour autant que la connexion à celle-ci fonctionne. Le détail de
        # `exc` est loggé (pas juste "indisponible") : sans lui, un vrai
        # bug (ex. cuDNN manquant) est indiscernable d'un simple silence.
        logger.info(
            "Whisper indisponible ou muet (%s : %s), repli sur Google.",
            type(exc).__name__,
            exc,
        )

    try:
        return recognizer.recognize_google(audio, language="fr-FR")
    except sr.UnknownValueError as exc:
        raise VoiceNotUnderstood("Parole non reconnue.") from exc
    except sr.RequestError as exc:
        raise VoiceError(f"Service de reconnaissance vocale indisponible : {exc}") from exc


@lru_cache(maxsize=1)
def _get_kokoro():
    try:
        from kokoro_onnx import Kokoro
    except ModuleNotFoundError as exc:
        raise VoiceError(
            "Synthèse vocale indisponible : "
            "installez l'extra `voice` (`uv sync --extra voice`)."
        ) from exc
    model_path, voices_path = _ensure_model_files()
    return Kokoro(str(model_path), str(voices_path))


@lru_cache(maxsize=1)
def _get_g2p():
    try:
        from misaki import espeak
        from misaki.espeak import EspeakG2P
    except ModuleNotFoundError as exc:
        raise VoiceError(
            "Phonémisation française indisponible : installez l'extra `voice` "
            "(`uv sync --extra voice`)."
        ) from exc
    try:
        # `EspeakFallback` enregistre le binaire espeak-ng utilisé en
        # interne par `EspeakG2P` ; la variable n'est pas réutilisée
        # explicitement, mais l'appel est nécessaire (cf. exemple officiel
        # kokoro-onnx/examples/french.py).
        espeak.EspeakFallback(british=False)
        return EspeakG2P(language=ESPEAK_LANG)
    except Exception as exc:  # espeak-ng absent ou mal installé
        raise VoiceError(
            "espeak-ng est introuvable. Installez-le "
            "(`winget install eSpeak-NG.eSpeak-NG` sous Windows) puis relancez."
        ) from exc


EDGE_VOICE_NAME = "fr-FR-VivienneMultilingualNeural"  # voix multilingue : gère nativement les changements de langue (FR/EN) dans un même texte
# 5s fixes suffisent pour une phrase courte mais coupaient à tort une
# longue description (offre d'emploi...) avant la fin du flux, faisant
# croire à une absence de connexion alors que la génération continuait
# juste. On calque le budget sur la longueur du texte : ~15 caractères/s
# de marge (bien plus lent que le débit réel d'Edge TTS), borné entre 5s
# et 60s pour ne jamais bloquer trop longtemps si la connexion manque
# vraiment.
_EDGE_TIMEOUT_MIN = 5.0
_EDGE_TIMEOUT_MAX = 60.0
_EDGE_CHARS_PER_SECOND = 15


def _edge_timeout_for(text: str) -> float:
    return min(_EDGE_TIMEOUT_MAX, max(_EDGE_TIMEOUT_MIN, len(text) / _EDGE_CHARS_PER_SECOND))


def _synthesize_edge_tts(text: str) -> bytes:
    """Récupère l'audio MP3 d'Edge TTS pour `text`, SANS le jouer.

    Séparé de `_speak_edge_tts()` pour être réutilisé par `synthesize_audio()`
    (cf. plus bas, exposé par `POST /tts` côté aelyn-api) : l'API renvoie
    ces octets au navigateur au lieu de les jouer sur les haut-parleurs de
    la machine qui l'exécute. Lève une exception (réseau, timeout,
    dépendance absente) dans les deux cas ; chaque appelant décide de son
    propre repli (`speak()` sur Kokoro ; `synthesize_audio()` pareil).
    """
    import asyncio

    import edge_tts

    async def _fetch() -> bytes:
        communicate = edge_tts.Communicate(text, EDGE_VOICE_NAME)
        chunks: list[bytes] = []

        async def _collect() -> None:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])

        await asyncio.wait_for(_collect(), timeout=_edge_timeout_for(text))
        return b"".join(chunks)

    mp3_bytes = asyncio.run(_fetch())
    if not mp3_bytes:
        raise VoiceError("Edge TTS n'a renvoyé aucun audio.")
    return mp3_bytes


def _speak_edge_tts(text: str) -> None:
    """Synthèse via Edge TTS (voix Vivienne, meilleure qualité, nécessite
    internet) ET lecture LOCALE immédiate (haut-parleurs de la machine).
    Lève une exception (réseau, timeout, dépendance absente) plutôt que
    de la gérer ici : `speak()` bascule alors sur Kokoro."""
    import io

    import sounddevice as sd
    import soundfile as sf

    mp3_bytes = _synthesize_edge_tts(text)
    data, sample_rate = sf.read(io.BytesIO(mp3_bytes))
    sd.play(data, sample_rate)
    sd.wait()


def _synthesize_kokoro(text: str):
    """Génère l'audio via Kokoro (locale, hors-ligne) et renvoie
    (échantillons, fréquence d'échantillonnage) SANS jouer le son.

    Séparé de `_speak_kokoro()` pour la même raison que
    `_synthesize_edge_tts()` ci-dessus : réutilisé par `synthesize_audio()`
    pour `POST /tts`. `_get_kokoro()`/`_get_g2p()` restent `lru_cache` :
    le modèle Kokoro n'est chargé qu'une fois par process (CLI comme API),
    jamais rechargé disque à chaque appel.
    """
    kokoro = _get_kokoro()
    g2p = _get_g2p()
    phonemes, _ = g2p(text)
    return kokoro.create(phonemes, VOICE_NAME, is_phonemes=True)


def _speak_kokoro(text: str) -> None:
    """Synthèse via Kokoro ET lecture LOCALE immédiate (haut-parleurs de
    la machine) : locale, hors-ligne, toujours disponible."""
    try:
        import sounddevice as sd
    except ModuleNotFoundError as exc:
        raise VoiceError(
            "Lecture audio indisponible : "
            "installez l'extra `voice` (`uv sync --extra voice`)."
        ) from exc

    samples, sample_rate = _synthesize_kokoro(text)
    sd.play(samples, sample_rate)
    sd.wait()


def speak(text: str) -> None:
    """Synthétise `text` en français et le joue sur les haut-parleurs.

    Essaie d'abord Edge TTS (voix Vivienne, meilleure qualité) ; bascule
    automatiquement sur Kokoro (local, hors-ligne) dès que la connexion
    manque ou que la requête échoue : jamais d'attente longue ni de
    plantage faute de réseau.
    """
    text = _prepare_for_speech(text)
    if not text:
        return

    try:
        _speak_edge_tts(text)
        return
    except Exception as exc:
        # Le détail de `exc` est loggé (pas juste "indisponible") : sans
        # lui, un vrai timeout sur un texte long est indiscernable d'une
        # coupure réseau ou d'une dépendance manquante.
        logger.info(
            "Edge TTS indisponible (%s : %s), repli sur Kokoro (local).",
            type(exc).__name__,
            exc,
        )

    # `_speak_kokoro` joue déjà l'audio et attend sa fin en interne (`sd`
    # n'est même pas importé à ce niveau), un second `sd.wait()` ici
    # plantait avec un NameError à CHAQUE repli sur Kokoro (donc à chaque
    # perte de connexion), jamais vu tant qu'Edge TTS réussissait en démo.
    _speak_kokoro(text)


def synthesize_audio(text: str) -> tuple[bytes, str]:
    """Synthétise `text` et renvoie (octets audio, content-type) SANS
    rien jouer sur les haut-parleurs de la machine, pour `POST /tts`
    côté aelyn-api, qui laisse le NAVIGATEUR jouer l'audio plutôt que la
    machine qui exécute l'API (souvent pas la même machine que le
    frontend web). Même voix, même repli qu'à l'oral côté CLI (`speak()`) :
    Edge TTS d'abord (voix Vivienne, meilleure qualité, nécessite
    internet, renvoie du MP3), Kokoro en secours (locale, hors-ligne,
    toujours disponible une fois ses modèles téléchargés, renvoie du WAV).

    `_get_kokoro()`/`_get_g2p()` restent `lru_cache(maxsize=1)` : le
    modèle Kokoro n'est chargé qu'une seule fois par process API (pas à
    chaque requête), exactement comme pour le CLI.
    """
    text = _prepare_for_speech(text)
    if not text:
        raise VoiceError("Rien à synthétiser (texte vide une fois nettoyé).")

    try:
        return _synthesize_edge_tts(text), "audio/mpeg"
    except Exception as exc:
        logger.info(
            "Edge TTS indisponible pour /tts (%s : %s), repli sur Kokoro (local).",
            type(exc).__name__,
            exc,
        )

    import io

    import soundfile as sf

    samples, sample_rate = _synthesize_kokoro(text)
    buffer = io.BytesIO()
    sf.write(buffer, samples, sample_rate, format="WAV")
    return buffer.getvalue(), "audio/wav"


def speak_async(text: str) -> None:
    """Comme `speak()`, mais ne bloque pas l'appelant.

    Pour les accusés de réception ("je m'en occupe") qu'on veut dire
    PENDANT qu'une action lente démarre, pas avant. Les erreurs sont
    avalées (loggées) : un accusé de réception raté ne doit jamais
    faire échouer l'action réelle qui le suit.
    """

    def _run() -> None:
        try:
            speak(text)
        except VoiceError:
            logger.exception("Échec de la synthèse vocale asynchrone")

    threading.Thread(target=_run, daemon=True).start()
