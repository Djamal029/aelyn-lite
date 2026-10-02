"""Persistance des réglages dans `.env` (pas juste en mémoire).

`PATCH /settings` doit survivre à un redémarrage de l'API, contrairement
à l'ancien `PATCH /settings/allow-autonomous-send` (explicitement en
mémoire seulement, cf. son docstring avant ce module). `dotenv.set_key`
réécrit UNE SEULE ligne `CLE=valeur` dans le fichier (la crée en fin de
fichier si la clé n'existe pas encore), sans toucher aux commentaires ni
aux autres lignes : plus sûr qu'un remplacement du fichier entier, vu le
volume de commentaires de documentation que `.env` a accumulé (cf. le
balayage anti-tiret-cadratin de ce projet, qui en a justement reformulé
beaucoup).
"""

from __future__ import annotations

import dotenv


def get_env_path() -> str:
    """Chemin du `.env` RÉELLEMENT utilisé par `load_dotenv()` (même
    résolution que `aelyn.core.config`/tous les modules qui appellent
    `dotenv.load_dotenv()` sans argument : recherche en remontant depuis
    le répertoire de travail courant). Lève si aucun `.env` n'est trouvé
    plutôt que d'en écrire un nouveau au mauvais endroit en silence."""
    path = dotenv.find_dotenv(usecwd=True)
    if not path:
        raise FileNotFoundError(
            "Aucun fichier .env trouvé (recherché en remontant depuis le "
            "répertoire de travail du process API)."
        )
    return path


def set_env_value(key: str, value: str) -> None:
    """Écrit `KEY=value` dans le `.env` réel, en ne touchant QUE cette
    ligne (créée en fin de fichier si absente). N'affecte PAS le process
    déjà démarré (`os.environ`/`aelyn.core.config.settings` restent tels
    quels) : l'appelant doit aussi mettre à jour `settings.xxx` en mémoire
    pour un effet immédiat, cf. `aelyn_api.routers.settings`."""
    dotenv.set_key(get_env_path(), key, value)
