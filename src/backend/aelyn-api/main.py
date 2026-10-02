"""Raccourci pour lancer l'API avec `uvicorn main:app --reload` depuis ce
dossier (`aelyn-api/`), comme demandé ; la vraie app vit dans
`src/aelyn_api/main.py` (layout `src/` uv, cohérent avec le reste du
workspace : core/, email-agent/, career-agent/, media-agent/, etc. sont
tous organisés ainsi). Nécessite que le package soit installé dans le
venv du workspace (`uv sync` depuis `src/backend`), ce qui est déjà le
cas pour tous les autres agents.
"""

from aelyn_api.main import app  # noqa: F401
