"""Script manuel : structure une vraie offre via le LLM (LLMOfferStructurer)
pour voir concrètement le résultat.

Usage :
    cd career-agent
    uv run python scripts/manual_structure_check.py
"""

from aelyn_career.llm_structurer import LLMOfferStructurer

OFFRE_EXEMPLE = """Stage Data Scientist en Computer Vision - 6 mois
Nous recherchons un stagiaire pour travailler sur des modeles de deep learning
(PyTorch, CLIP) appliques a l'analyse d'images medicales. Niveau Bac+5."""


def main() -> int:
    structurer = LLMOfferStructurer()

    print("Offre :")
    print(OFFRE_EXEMPLE)
    print()

    resultat = structurer.structure_offers("exemple-manuel-1", OFFRE_EXEMPLE)
    print("Résultat structuré :")
    print(resultat)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
