"""Précharge dans Ollama tous les modèles qu'AELYN utilise, pour éviter le
premier appel lent (chargement du modèle en VRAM) au moment où l'utilisateur
parle réellement à AELYN pour la première fois de la session.

Lancé au démarrage de Windows (tâche planifiée, cf. README à côté), pas par
AELYN lui-même : un simple script indépendant, qui n'a besoin de rien
d'autre que `ollama` et les variables d'environnement déjà utilisées par le
reste du projet.
"""

import os
import sys
import time

import dotenv

dotenv.load_dotenv()

try:
    import ollama
except ModuleNotFoundError:
    print("Le paquet 'ollama' n'est pas installé (uv sync requis).", file=sys.stderr)
    sys.exit(1)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# Mêmes variables que core/config.py et career-agent : on ne réimplémente
# pas leur résolution, on lit juste les mêmes noms directement.
MODELS = {
    "LLM_MODEL": os.getenv("LLM_MODEL", "qwen3:4b"),
    "LLM_MODEL_HEAVY": os.getenv("LLM_MODEL_HEAVY", "qwen3:8b"),
    "LLM_MODEL_CAREER": os.getenv("LLM_MODEL_CAREER", "deepseek-r1:8b"),
}
# Même durée que `_KEEP_ALIVE` dans `core/src/aelyn/core/llm.py`. Les
# garder synchronisées n'est pas critique (un préchargement expiré retombe
# juste sur le comportement normal), mais ça évite une incohérence inutile.
KEEP_ALIVE = "30m"


def main() -> int:
    client = ollama.Client(host=OLLAMA_HOST)

    try:
        client.list()
    except Exception as exc:
        print(f"Ollama injoignable sur {OLLAMA_HOST} : {exc}", file=sys.stderr)
        return 1

    seen: set[str] = set()
    for var_name, model in MODELS.items():
        if model in seen:
            continue
        seen.add(model)
        start = time.monotonic()
        try:
            # Un appel `chat` minimal force Ollama à charger le modèle en
            # mémoire sans dépendre d'un prompt système/outil applicatif.
            # C'est le chargement qu'on veut déclencher, pas une vraie
            # réponse.
            client.chat(
                model=model,
                messages=[{"role": "user", "content": "Bonjour"}],
                keep_alive=KEEP_ALIVE,
                options={"num_predict": 1},
            )
            elapsed = time.monotonic() - start
            print(f"{var_name} ({model}) préchargé en {elapsed:.1f}s.")
        except Exception as exc:
            print(
                f"{var_name} ({model}) : échec du préchargement ({exc})", file=sys.stderr
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
