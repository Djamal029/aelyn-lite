"""`GET /system/status` : données RÉELLES pour la page Système/Overview du
frontend, qui affichait jusqu'ici du texte statique (uptime "6 j 14 h"
inventé, CPU/RAM à des pourcentages fixes, un statut "career-agent :
scoring hors-ligne, non branché au chat" qui ne correspond plus à rien
depuis que career-agent EST branché au chat, cf. le reste de cette
session).

Chaque champ est soit une vraie mesure (`psutil`, `nvidia-smi`, une
tentative de connexion réelle à chaque service), soit explicitement
`null`/signalé indisponible avec la raison, JAMAIS un nombre plausible
inventé. En particulier la température CPU : contrairement à la
température GPU (exposée nativement par `nvidia-smi`), Windows n'expose
aucune API standard fiable pour ça sans droits noyau ou un outil tiers
(LibreHardwareMonitor et consorts, qui doit tourner en service séparé) :
`psutil.sensors_temperatures()` n'existe même pas sur ce système
d'exploitation (vérifié : `AttributeError`, pas juste un retour vide), et
la zone thermique ACPI standard (`MSAcpi_ThermalZoneTemperature`, WMI)
répond "Not supported" sur cette machine (testé en direct). Plutôt que de
fabriquer un chiffre, ce endpoint renvoie `null` avec une explication.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import psutil
from fastapi import APIRouter

from aelyn.core.config import settings
from aelyn.core.llm import is_model_available, ollama_status
from aelyn_email.client import MailboxError, imap_session

from aelyn_api.deps import get_media_controller, get_offers_agent

router = APIRouter(prefix="/system", tags=["system"])

_PROCESS = psutil.Process()


def _cpu_temp_celsius() -> dict:
    """Voir le docstring du module : honnête plutôt que fabriqué."""
    return {
        "value": None,
        "available": False,
        "reason": (
            "Aucune API de température CPU fiable sur Windows sans outil "
            "tiers (LibreHardwareMonitor non installé) : "
            "psutil.sensors_temperatures() n'existe pas sur cette "
            "plateforme et la zone thermique ACPI standard répond "
            "'Not supported' sur cette machine."
        ),
    }


def _gpu_status() -> dict:
    """Température/usage/VRAM GPU via `nvidia-smi` (déjà la méthode
    utilisée pour investiguer la contention VRAM plus tôt dans ce
    projet) : réel si une carte NVIDIA + ses pilotes sont présents,
    `available: False` honnête sinon (pas de GPU NVIDIA, ou pilote
    absent), jamais une valeur par défaut déguisée en mesure."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"available": False, "reason": "nvidia-smi introuvable (pas de GPU NVIDIA/pilote ?)"}
    try:
        out = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        name, temp, util, mem_used, mem_total = (p.strip() for p in out.stdout.strip().split(","))
        return {
            "available": True,
            "name": name,
            "temperature_celsius": float(temp),
            "utilization_percent": float(util),
            "memory_used_mb": float(mem_used),
            "memory_total_mb": float(mem_total),
        }
    except Exception as exc:
        return {"available": False, "reason": f"nvidia-smi a échoué : {exc}"}


def _imap_status() -> dict:
    """Connexion IMAP RÉELLE (login + SELECT INBOX), pas une supposition
    basée sur la seule présence d'EMAIL_USER/EMAIL_PASS dans .env : des
    identifiants présents mais expirés/invalides doivent apparaître
    comme en panne ici, pas comme "configuré donc sûrement bon"."""
    try:
        with imap_session():
            pass
        return {"connected": True, "server": settings.imap_server}
    except MailboxError as exc:
        return {"connected": False, "server": settings.imap_server, "error": str(exc)}
    except Exception as exc:
        return {"connected": False, "server": settings.imap_server, "error": str(exc)}


def _france_travail_status() -> dict:
    """Joignabilité RÉELLE de l'API France Travail : réutilise le jeton
    de la session en cours s'il existe déjà (`offers_agent.access_token`,
    évite un appel OAuth superflu à chaque poll du dashboard), sinon
    tente une authentification réelle pour vérifier identifiants +
    joignabilité, plutôt que supposer "configuré donc disponible"."""
    offers_agent = get_offers_agent()
    if offers_agent.access_token is not None:
        return {"reachable": True, "source": "jeton de session déjà valide"}
    try:
        offers_agent.connect()
        return {"reachable": True, "source": "authentification vérifiée à l'instant"}
    except Exception as exc:
        return {"reachable": False, "source": "authentification vérifiée à l'instant", "error": str(exc)}


def _media_status() -> dict:
    """Statut TV NON INVASIF : ne déclenche JAMAIS de tentative de
    connexion/appairage depuis un simple appel de statut (ça afficherait
    un code d'appairage sur le vrai téléviseur de l'utilisateur pour la
    seule raison qu'il a ouvert son dashboard). `configured` = IP
    renseignée dans .env ; `connected` = une commande a DÉJÀ réussi à se
    connecter pendant la durée de vie de ce process (`MediaController`
    singleton, connexion paresseuse à son premier `dispatch()` réel,
    cf. media-agent/src/aelyn_media/agent.py)."""
    configured = bool(settings.tv_ip)
    controller = get_media_controller()
    connected = configured and controller._media is not None
    return {"configured": configured, "connected": connected}


def _tailscale_status() -> dict:
    """État RÉEL de Tailscale via sa propre CLI (`tailscale status --json`,
    interface stable documentée, pas un fichier de config interne fragile).
    Ajouté après coup : signalé par l'agent frontend que son mock gardait
    `tailscale: "connected"` codé en dur faute d'une vraie source ici. Vérifié
    sur cette machine : Tailscale EST installé mais PAS connecté
    (`BackendState: "NeedsLogin"`) au moment d'écrire ceci, donc ce mock
    aurait affiché un faux "connecté" si jamais branché tel quel.

    `available=False` (binaire absent) et `connected=False` (installé mais
    pas dans l'état "Running") sont deux cas DIFFÉRENTS, distingués
    explicitement plutôt que confondus dans un seul booléen."""
    tailscale_bin = shutil.which("tailscale")
    if not tailscale_bin:
        return {"available": False, "connected": False, "reason": "tailscale introuvable (non installé ?)"}
    try:
        out = subprocess.run(
            [tailscale_bin, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        data = json.loads(out.stdout)
        backend_state = data.get("BackendState", "?")
        ips = data.get("TailscaleIPs") or []
        return {
            "available": True,
            "connected": backend_state == "Running",
            "backend_state": backend_state,
            "tailscale_ips": ips,
        }
    except Exception as exc:
        return {"available": True, "connected": False, "reason": f"échec de l'appel : {exc}"}


def _voice_assets_status() -> dict:
    """Présence sur disque des modèles Whisper (reconnaissance)/Kokoro
    (synthèse), SANS les charger (charger faster-whisper/Kokoro pour de
    vrai utiliserait de la VRAM pour la seule durée d'un health check, ce
    qui pourrait évincer un modèle Ollama déjà chargé sur ce GPU 6 Go,
    cf. toute l'investigation contention VRAM de ce projet) : "présent"
    est vérifié réellement, "se charge sans erreur" ne l'est pas, par
    choix, pas par oubli."""
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    whisper_dir = hf_cache / f"models--Systran--faster-whisper-{settings.whisper_model_size}"
    kokoro_dir = settings.data_dir / "kokoro"
    kokoro_model = kokoro_dir / "kokoro-v1.0.int8.onnx"
    kokoro_voices = kokoro_dir / "voices-v1.0.bin"
    return {
        "whisper": {
            "model_size": settings.whisper_model_size,
            "present": whisper_dir.is_dir() and any(whisper_dir.iterdir()),
            "note": "présence sur disque vérifiée, pas un chargement réel (coût VRAM évité)",
        },
        "kokoro": {
            "present": kokoro_model.is_file() and kokoro_voices.is_file(),
            "note": "présence sur disque vérifiée, pas un chargement réel",
        },
    }


@router.get("/status")
def system_status() -> dict:
    resources = system_resources()
    ollama = ollama_status()

    return {
        "resources": resources,
        "services": {
            "ollama": {
                **ollama,
                "roles": {
                    "llm_model": {
                        "model": settings.llm_model,
                        "available_locally": settings.llm_model in ollama.get("models", []),
                    },
                    "llm_model_heavy": {
                        "model": settings.llm_model_heavy,
                        "available_locally": is_model_available(settings.llm_model_heavy),
                    },
                    "llm_model_career": {
                        "model": settings.llm_model_career,
                        "available_locally": is_model_available(settings.llm_model_career),
                    },
                },
            },
            "imap": _imap_status(),
            "france_travail": _france_travail_status(),
            "media_tv": _media_status(),
            "voice_assets": _voice_assets_status(),
            "tailscale": _tailscale_status(),
        },
    }


def _all_disks() -> list[dict]:
    """Un disque par partition montée réellement accessible, pas
    seulement celle où vit AELYN : observé en usage réel, une machine
    avec plusieurs disques (C:, D:, E:...) ne montrait jusqu'ici que
    celui du dossier de données, ce qui ne reflète pas l'espace
    disponible ailleurs. Un lecteur amovible sans média, ou une
    partition inaccessible, est silencieusement ignoré plutôt que de
    faire échouer toute la route (`disk_usage` lève sur un CD-ROM
    vide par exemple)."""
    disks = []
    seen_mountpoints = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen_mountpoints:
            continue
        seen_mountpoints.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        disks.append({
            "mountpoint": part.mountpoint,
            "percent": usage.percent,
            "used_gb": round(usage.used / 1_000_000_000, 1),
            "total_gb": round(usage.total / 1_000_000_000, 1),
        })
    return disks


@router.get("/resources")
def system_resources() -> dict:
    """Mesures système seules, sans appels IMAP/France Travail/Ollama.

    Cette route peut être actualisée régulièrement par la page Données :
    chaque nombre est mesuré à la requête, et aucun historique fictif
    n'est présenté comme une télémétrie persistante.
    """
    cpu_percent = psutil.cpu_percent(interval=0.2)
    vmem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(settings.data_dir.anchor or "/"))
    net = psutil.net_io_counters()
    return {
        "cpu_percent": cpu_percent,
        "cpu_temp_celsius": _cpu_temp_celsius(),
        "ram": {
            "percent": vmem.percent,
            "used_mb": round(vmem.used / 1_000_000, 1),
            "total_mb": round(vmem.total / 1_000_000, 1),
        },
        "disk": {
            "percent": disk.percent,
            "used_gb": round(disk.used / 1_000_000_000, 1),
            "total_gb": round(disk.total / 1_000_000_000, 1),
        },
        "disks": _all_disks(),
        "gpu": _gpu_status(),
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "note": "cumulé depuis le démarrage du système, pas un débit instantané",
        },
        "uptime_seconds": round(time.time() - _PROCESS.create_time()),
        "uptime_note": "durée de vie du processus API depuis son dernier démarrage",
    }
