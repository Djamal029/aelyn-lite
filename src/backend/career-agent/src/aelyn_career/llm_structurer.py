import dotenv

from aelyn.core.config import settings
from aelyn.core.journal import ActionStatus, Journal
from aelyn.core.llm import LLMClient
from aelyn_career.models import OffreStructuree
from aelyn_career.prompts import SYSTEM_STRUCTURE

dotenv.load_dotenv()

AGENT_NAME = "career"


class LLMOfferStructurer:
    def __init__(self, journal: Journal | None = None):
        # `settings.llm_model_career` lu ici (construction), pas une
        # constante de module figée à l'import : corrige au passage un
        # bug réel (l'ancien défaut, en l'absence de LLM_MODEL_CAREER
        # dans .env, était la chaîne littérale "LLM_MODEL_CAREER", pas un
        # vrai nom de modèle Ollama). `LLMOfferStructurer` est recréée à
        # CHAQUE recherche d'offres (cf. `pipeline.run_pipeline`, jamais
        # un singleton gardé entre deux recherches), donc un changement de
        # `settings.llm_model_career` via `PATCH /settings` s'applique dès
        # la prochaine recherche sans redémarrage, sans mécanisme de
        # rechargement dédié.
        self.llm_client = LLMClient(model=settings.llm_model_career)
        self.journal = journal or Journal(settings.journal_path)

    def structure_offers(self, offer_id: str, offer_text: str) -> dict:
        """Pour une offre (identifiée par `offer_id`, ex. `offre["id"]` de
        France Travail, stable et déjà unique, pas besoin de le hasher), prend
        le texte brut et le structure en JSON (compétences requises, niveau
        requis) via le LLM.

        Une offre déjà vue (même id) n'est jamais repassée au LLM : le
        résultat est relu depuis le journal.
        """
        deja_traitee = self.journal.find(
            agent=AGENT_NAME, action="structure_offer", target=offer_id
        )
        if deja_traitee is not None:
            return deja_traitee.payload

        structuree = self.llm_client.structured(
            schema=OffreStructuree,
            system=SYSTEM_STRUCTURE,
            user=offer_text,
        )
        payload = structuree.model_dump(mode="json")

        self.journal.record(
            agent=AGENT_NAME,
            action="structure_offer",
            target=offer_id,
            summary=f"Offre structurée (niveau {payload['niveau_requis']})",
            status=ActionStatus.EXECUTED,
            payload=payload,
        )
        return payload
