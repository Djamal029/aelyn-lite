"""Helpers génériques pour normaliser, classifier et dédupliquer des offres."""

from __future__ import annotations

import re
from collections.abc import Iterable

_SOURCE_PRIORITY = {
    "francetravail": 100,
    "jooble": 85,
    "adzuna": 80,
    "reed": 80,
    "careerjet": 75,
    "remoteok": 70,
    "remotive": 70,
    "arbeitnow": 70,
    "jsearch": 60,
    "fantasticjobs": 60,
    "theirstack": 60,
    "unknown": 10,
}

_DOMAIN_KEYWORDS = {
    "ai": [
        "intelligence artificielle", "artificial intelligence", "machine learning", "ml",
        "deep learning", "data science", "data scientist", "computer vision", "nlp",
        "llm", "prompt engineer", "retrieval augmented generation", "rag", "mlops",
        "ai engineer", "ml engineer", "genai", "generative ai", "vision by computer",
    ],
    "software": [
        "developer", "software", "backend", "frontend", "full stack", "platform",
        "java", "python", "typescript", "c#", "php", "go", "rust", "devops",
        "sre", "cloud", "kubernetes", "api",
    ],
    "data": [
        "data analyst", "data engineer", "data scientist", "bi", "power bi", "sql",
        "warehouse", "etl", "analytics", "dashboard", "spark", "dbt",
    ],
    "cyber": [
        "cyber", "sécurité", "security", "soc", "siem", "cloud security", "pentest",
        "incident response",
    ],
    "product": [
        "product manager", "product owner", "gestion de produit", "business analyst",
        "analyste produit",
    ],
    "marketing": [
        "marketing", "growth", "community manager", "performance marketing", "seo",
        "sem", "digital marketing",
    ],
    "sales": ["sales", "account manager", "business developer", "commercial", "vente"],
    "design": ["design", "ui", "ux", "product designer", "graphic design"],
    "hr": ["rh", "human resources", "recruiter", "hr business partner"],
    "finance": ["finance", "comptable", "contrôle de gestion", "risk", "audit"],
    "logistics": ["logistique", "supply chain", "operations", "warehouse management"],
    "health": ["santé", "medical", "care", "pharma", "biomedical"],
    "education": ["formation", "enseignement", "pedagogy", "academic"],
}

_AI_KEYWORDS = _DOMAIN_KEYWORDS["ai"]


def _canonicalize(value: object) -> str:
    if value is None:
        return ""
    value = str(value)
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_texts(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            parts.extend(str(v) for v in value)
        else:
            parts.append(str(value))
    return " ".join(parts)


def normalize_contract_type(raw_contract: object, alternance: object | None = None) -> str:
    value = _canonicalize(raw_contract)
    if not value:
        if alternance is True:
            return "ALTERNANCE"
        return "UNKNOWN"

    if value in {"cdi", "permanent", "contractuel"}:
        return "CDI"
    if value in {"cdd", "temporary", "temporaire"}:
        return "CDD"
    if value in {"intérim", "interim", "temporary", "temporaire"}:
        return "TEMPORARY"
    if value in {"stage", "internship", "internship program", "alternance", "apprentissage"}:
        return "STAGE" if "stage" in value or "internship" in value else "ALTERNANCE"
    if value in {"freelance", "mission", "consultant", "contract"}:
        return "FREELANCE"
    if alternance is True:
        return "ALTERNANCE"
    return value.upper()


def infer_domain(title: str, description: str = "") -> str:
    text = _canonicalize(f"{title} {description}")
    if not text:
        return "general"

    found = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if _canonicalize(keyword) in text:
                found.append(domain)
                break
    if "ai" in found:
        return "ai"
    if found:
        return found[0]
    return "general"


def is_ai_related(title: str, description: str = "") -> bool:
    text = _canonicalize(f"{title} {description}")
    return any(_canonicalize(keyword) in text for keyword in _AI_KEYWORDS)


def expand_domain_terms(text: str) -> set[str]:
    """Mots de CHAQUE domaine (`_DOMAIN_KEYWORDS`) dont au moins un mot-clé
    apparaît dans `text`, pour enrichir un score de recouvrement lexical.

    Comble un angle mort constaté en direct (sélection CV/lettre, cf.
    `ApplicationWriter._keyword_selection`) : une offre qui dit "intelligence
    artificielle" ou "agents IA" ne partage AUCUN mot avec une certification
    intitulée "Machine Learning specialisation", bien que les deux désignent
    le même domaine - la certification la plus pertinente disparaissait donc
    silencieusement pour ce type d'offre. N'affecte jamais `infer_domain`/
    `is_ai_related` ci-dessus (classification d'offre, volontairement
    stricte sur le texte réel), seulement la mise en correspondance profil/
    offre en aval."""
    canon = _canonicalize(text)
    expanded: set[str] = set()
    for keywords in _DOMAIN_KEYWORDS.values():
        if any(_canonicalize(keyword) in canon for keyword in keywords):
            for keyword in keywords:
                expanded.update(re.findall(r"[a-z0-9]+", _canonicalize(keyword)))
    return expanded


def extract_skills(title: str, description: str = "") -> list[str]:
    text = _extract_texts(title, description)
    seen: set[str] = set()
    skills: list[str] = []
    for skill in [
        "Python", "Java", "TypeScript", "JavaScript", "SQL", "React", "Vue", "Angular",
        "Docker", "Kubernetes", "AWS", "Azure", "GCP", "FastAPI", "Django", "Flask",
        "Spark", "Airflow", "Power BI", "Tableau", "Machine Learning", "Deep Learning",
        "AI", "NLP", "LLM", "MLOps", "Product Management", "CRM", "Salesforce",
        "Cybersecurity", "DevOps", "Terraform", "C#", "Go", "Rust",
    ]:
        if skill.lower() in text.lower() and skill not in seen:
            seen.add(skill)
            skills.append(skill)
    return skills


def _source_key(offer: dict) -> tuple[str, ...]:
    title = _extract_texts(
        offer.get("intitule"),
        offer.get("title"),
        offer.get("titre"),
    )
    company = _extract_texts(
        (offer.get("entreprise") or {}).get("nom") if isinstance(offer.get("entreprise"), dict) else offer.get("entreprise"),
        offer.get("company"),
    )
    location = _extract_texts(
        (offer.get("lieuTravail") or {}).get("libelle") if isinstance(offer.get("lieuTravail"), dict) else offer.get("lieuTravail"),
        offer.get("location"),
    )
    raw_contract = offer.get("typeContrat") or offer.get("contract_type") or offer.get("contrat")
    if not raw_contract or str(raw_contract).upper() == "UNKNOWN":
        raw_contract = None
    contract = normalize_contract_type(raw_contract, offer.get("alternance"))
    if not title and not company and not location and not raw_contract:
        return (str(offer.get("id") or id(offer)),)
    return (
        _canonicalize(title),
        _canonicalize(company),
        _canonicalize(location),
        _canonicalize(contract),
    )


def _merge_offer(primary: dict, incoming: dict) -> dict:
    merged = dict(primary)
    for key in (
        "source", "title", "company", "location", "description", "url",
        "application", "application_source", "salary", "dateCreation",
        "date_publication", "posted_at", "dateLimiteDePotentiel", "dateLimite",
        "dateFin", "expires_at", "deadline",
    ):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    merged.setdefault("sources_seen", [])
    new_source_entry = {"source": incoming.get("source", "unknown"), "url": incoming.get("url")}
    source_entries = merged["sources_seen"] + [new_source_entry]
    deduped_entries: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in source_entries:
        key = (str(entry.get("source", "unknown")), str(entry.get("url") or ""))
        if key not in seen:
            seen.add(key)
            deduped_entries.append(entry)
    merged["sources_seen"] = deduped_entries
    merged["duplicate_count"] = len(merged["sources_seen"])
    merged["deduplicated"] = True
    if _SOURCE_PRIORITY.get(str(incoming.get("source", "unknown")).lower(), 0) > _SOURCE_PRIORITY.get(str(merged.get("source", "unknown")).lower(), 0):
        merged["source"] = incoming.get("source", merged.get("source"))
    return merged


def enrich_offer(raw_offer: dict, source: str = "unknown") -> dict:
    offer = dict(raw_offer)
    title = _extract_texts(
        offer.get("intitule"),
        offer.get("title"),
        offer.get("titre"),
    )
    description = _extract_texts(
        offer.get("description"),
        offer.get("descriptionCourte"),
        offer.get("descriptionTexte"),
    )
    domain = infer_domain(title, description)
    offer["source"] = source.lower()
    offer["domain"] = domain
    offer["is_ai_related"] = is_ai_related(title, description)
    offer["ai_score"] = 1.0 if offer["is_ai_related"] else 0.0
    offer["contract_type"] = normalize_contract_type(
        offer.get("typeContrat") or offer.get("contract_type") or offer.get("contrat"),
        offer.get("alternance"),
    )
    offer["skills"] = extract_skills(title, description)
    offer["sources_seen"] = [{"source": source.lower(), "url": offer.get("url")}]
    offer["duplicate_count"] = 1
    offer["deduplicated"] = False
    return offer


def deduplicate_offers(offers: list[dict]) -> list[dict]:
    """Fusionne les offres apparentées, sans perdre leur provenance."""
    groups: dict[tuple[str, ...], dict] = {}
    for offer in offers:
        key = _source_key(offer)
        if not any(key):
            groups.setdefault((offer.get("id") or str(id(offer)),), offer)
            continue
        if key in groups:
            groups[key] = _merge_offer(groups[key], offer)
        else:
            groups[key] = offer

    ordered = list(groups.values())
    ordered.sort(key=lambda o: _SOURCE_PRIORITY.get(str(o.get("source", "unknown")).lower(), 0), reverse=True)
    return ordered
