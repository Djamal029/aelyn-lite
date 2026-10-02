"""Modèles du domaine "carrière"."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NiveauRequis(StrEnum):
    STAGE = "stage"
    JUNIOR = "junior"
    SENIOR = "senior"
    POSTDOC = "postdoc"


class OffreStructuree(BaseModel):
    """Ce que le LLM doit produire pour UNE offre (cf. `SYSTEM_STRUCTURE`)."""

    competences_requises: list[str]
    niveau_requis: NiveauRequis


class CVExperience(BaseModel):
    role: str
    entreprise: str
    periode: str
    puces: list[str] = Field(max_length=3)
    """2 à 3 réalisations concrètes, les plus pertinentes pour l'offre visée."""


class CVProjet(BaseModel):
    titre: str
    description: str
    """Une ligne : ce que fait le projet et les technologies clés."""


class CVContent(BaseModel):
    """Contenu d'un CV tenant sur une page, sélectionné et priorisé pour
    UNE offre précise (cf. `SYSTEM_CV`), jamais tout le profil, jamais
    plus que ce qui tient sur une page.

    Les `max_length` ci-dessous ne sont pas que documentaires : injectés
    dans le JSON Schema envoyé à Ollama (`maxItems`), ils contraignent
    le décodage ; une simple consigne texte dans le prompt ne suffisait
    pas toujours (observé : 3 projets générés malgré une consigne
    "1 à 2 maximum")."""

    profil: str
    """Paragraphe de 2 à 3 phrases (pas juste un titre) : qui est
    {user_name}, ses compétences clés, ce qu'il recherche, dans le style
    d'un vrai "Profil" de CV, tourné vers l'offre."""
    experiences: list[CVExperience] = Field(max_length=4)
    projets: list[CVProjet] = Field(max_length=3)
    competences: dict[str, list[str]]
    """Regroupées par catégorie, comme dans le profil source (ex. "Machine
    Learning", "Statistique & Méthodologie"), jamais une liste plate."""
    formation: list[str]
    certifications: list[str] = Field(max_length=3)
    langues: list[str] = []
    centres_interet: list[str] = []
