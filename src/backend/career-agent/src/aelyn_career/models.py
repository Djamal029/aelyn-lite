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


class JobApplication(BaseModel):
    url: str | None = None
    source: str | None = None
    email: str | None = None
    method: str | None = None
    deadline: str | None = None
    requires_cv: bool | None = None
    requires_cover_letter: bool | None = None


class JobCompany(BaseModel):
    name: str | None = None
    website: str | None = None
    size: str | None = None
    industry: str | None = None


class JobLocation(BaseModel):
    city: str | None = None
    region: str | None = None
    country: str | None = None
    remote: str | None = None
    raw: str | None = None


class JobSource(BaseModel):
    source: str
    url: str | None = None
    seen_at: str | None = None
    external_id: str | None = None


class CanonicalJobOffer(BaseModel):
    """Représentation canonique d'une offre, prête pour API/UI, sans
    jamais inventer de données absentes dans la source."""

    id: str
    source: str = "unknown"
    external_id: str | None = None
    url: str | None = None
    title: str | None = None
    company: JobCompany | None = None
    location: JobLocation | None = None
    contract_type: str = "UNKNOWN"
    telework: str | None = None
    seniority: str | None = None
    salary: dict | None = None
    posted_at: str | None = None
    expires_at: str | None = None
    deadline: str | None = None
    description: str | None = None
    domain: str = "general"
    is_ai_related: bool = False
    ai_score: float | None = None
    skills: list[str] = []
    tags: list[str] = []
    application: JobApplication | None = None
    confidence: float | None = None
    deduplicated: bool = False
    duplicate_count: int = 1
    sources_seen: list[JobSource] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class JobSearchResponse(BaseModel):
    total: int
    page: int = 1
    per_page: int = 10
    results: list[CanonicalJobOffer]
    filters: dict[str, list[str]] = Field(default_factory=dict)


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
