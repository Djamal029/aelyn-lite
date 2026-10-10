"""Adapters de sources publiques pour le moteur de recherche d'offres.

Les adapters sont volontairement simples et tolérants : si la clé API n'est
pas configurée ou si la source est indisponible, ils retournent une liste vide
sans faire planter la recherche. Cela garde le système utilisable sur CPU et
avec des environnements partiellement configurés.
"""

from __future__ import annotations

import os
import re
from typing import Any

import requests


def _looks_like_mojibake(text: str | None) -> bool:
    """Détecte un texte UTF-8 mal décodé (observé en pratique sur des
    offres RemoteOK en arabe : `location` renvoyée corrompue par l'API
    elle-même, pas par notre traitement). Heuristique : une densité
    anormalement haute de caractères U+00C2-U+00DF, la plage des
    premiers octets UTF-8 à deux octets mal réinterprétés un par un.
    Un texte légitime (même accentué, ex. "Düsseldorf") n'approche
    jamais ce seuil."""
    if not text:
        return False
    suspicious = sum(1 for ch in text if 0xC2 <= ord(ch) <= 0xDF)
    return suspicious / len(text) > 0.15


def clean_text(text: str | None) -> str | None:
    """Supprime un champ texte corrompu plutôt que de l'afficher tel
    quel : la tentative de réparation (ré-encoder en latin-1 puis
    redécoder en UTF-8) échoue elle-même sur ce cas réel (perte
    d'information côté source), donc mieux vaut l'absence d'info qu'un
    charabia affiché à l'utilisateur."""
    return None if _looks_like_mojibake(text) else text


class BaseSourceAdapter:
    name: str = "base"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        return []


class JoobleAdapter(BaseSourceAdapter):
    name = "jooble"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        api_key = os.getenv("JOOBLE_API_KEY")
        if not api_key or not keywords:
            return []
        url = f"https://jooble.org/api/{api_key}"
        payload = {"keywords": keywords, "location": "", "page": "1"}
        try:
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json() or {}
        except Exception:
            return []
        jobs = data.get("jobs", [])[:limit]
        return [{
            "id": f"jooble:{job.get('id') or idx}",
            "source": "jooble",
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "contract_type": job.get("contract") or "UNKNOWN",
            "description": job.get("snippet"),
            "url": job.get("link"),
            "dateCreation": job.get("updated"),
            "application": {"url": job.get("link"), "method": "site"},
        } for idx, job in enumerate(jobs)]


class AdzunaAdapter(BaseSourceAdapter):
    name = "adzuna"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        app_id = os.getenv("ADZUNA_APP_ID")
        app_key = os.getenv("ADZUNA_APP_KEY")
        if not app_id or not app_key or not keywords:
            return []
        url = f"https://api.adzuna.com/v1/api/jobs/fr/search/1"
        params = {"app_id": app_id, "app_key": app_key, "what": keywords, "results_per_page": limit}
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json() or {}
        except Exception:
            return []
        jobs = data.get("results", [])[:limit]
        return [{
            "id": f"adzuna:{job.get('id') or idx}",
            "source": "adzuna",
            "title": job.get("title"),
            "company": (job.get("company") or {}).get("display_name"),
            "location": (job.get("location") or {}).get("display_name"),
            "contract_type": job.get("contract_type") or "UNKNOWN",
            "description": job.get("description"),
            "url": job.get("redirect_url"),
            "dateCreation": job.get("created"),
            "dateLimite": job.get("valid_to"),
            "application": {"url": job.get("redirect_url"), "method": "site"},
        } for idx, job in enumerate(jobs)]


class ReedAdapter(BaseSourceAdapter):
    name = "reed"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        api_key = os.getenv("REED_API_KEY")
        if not api_key or not keywords:
            return []
        url = "https://www.reed.co.uk/api/1.0/search"
        params = {"keywords": keywords, "resultsToTake": limit}
        try:
            response = requests.get(url, params=params, auth=(api_key, ""), timeout=15)
            response.raise_for_status()
            data = response.json() or {}
        except Exception:
            return []
        jobs = data.get("results", [])[:limit]
        return [{
            "id": f"reed:{job.get('jobId') or idx}",
            "source": "reed",
            "title": job.get("jobTitle"),
            "company": job.get("employerName"),
            "location": job.get("locationName"),
            "contract_type": job.get("contractType") or "UNKNOWN",
            "description": job.get("jobDescription"),
            "url": job.get("jobUrl"),
            "dateCreation": job.get("date"),
            "dateLimite": job.get("expirationDate"),
            "application": {"url": job.get("jobUrl"), "method": "site"},
        } for idx, job in enumerate(jobs)]


class CareerjetAdapter(BaseSourceAdapter):
    name = "careerjet"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        api_key = os.getenv("CAREERJET_API_KEY")
        if not api_key or not keywords:
            return []
        params = {
            "keywords": keywords,
            "location": "",
            "locale_code": "fr_FR",
            "user_agent": "AELYN job search",
            "pagesize": min(limit, 50),
        }
        user_ip = os.getenv("CAREERJET_USER_IP")
        if user_ip:
            params["user_ip"] = user_ip
        referer = os.getenv("CAREERJET_REFERER")
        headers = {"Referer": referer} if referer else {}
        try:
            response = requests.get(
                "https://search.api.careerjet.net/v4/query",
                params=params,
                headers=headers,
                auth=(api_key, ""),
                timeout=15,
            )
            response.raise_for_status()
            data = response.json() or {}
        except Exception:
            return []
        jobs = data.get("jobs", [])[:limit]
        return [{
            "id": f"careerjet:{job.get('url') or idx}",
            "source": "careerjet",
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("locations"),
            "contract_type": job.get("contract_type") or "UNKNOWN",
            "description": job.get("description"),
            "url": job.get("url"),
            "dateCreation": job.get("date"),
            "dateLimite": job.get("expiration_date"),
            "application": {"url": job.get("url"), "method": "site"},
        } for idx, job in enumerate(jobs)]


class RemoteOKAdapter(BaseSourceAdapter):
    name = "remoteok"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        headers = {"User-Agent": "AELYN job search (https://remoteok.com)"}
        try:
            response = requests.get("https://remoteok.com/api", headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json() or []
        except Exception:
            return []
        jobs = [item for item in data if isinstance(item, dict) and item.get("id")]
        if keywords:
            terms = [term.casefold() for term in keywords.split() if term]
            jobs = [
                job for job in jobs
                if all(term in " ".join([
                    str(job.get("position") or ""),
                    str(job.get("description") or ""),
                    " ".join(job.get("tags") or []),
                ]).casefold() for term in terms)
            ]
        return [{
            "id": f"remoteok:{job.get('id')}",
            "source": "remoteok",
            "title": clean_text(job.get("position")),
            "company": clean_text(job.get("company")),
            "location": clean_text(job.get("location")) or "Remote",
            "contract_type": "UNKNOWN",
            "description": job.get("description"),
            "url": job.get("url"),
            "dateCreation": job.get("date"),
            "application": {"url": job.get("apply_url") or job.get("url"), "method": "site"},
        } for job in jobs[:limit]]


class RemoteSourceAdapter(BaseSourceAdapter):
    name = "remote"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        url = "https://remotive.com/api/remote-jobs"
        try:
            response = requests.get(url, params={"limit": limit, "search": keywords or ""}, timeout=15)
            response.raise_for_status()
            data = response.json() or {}
        except Exception:
            return []
        jobs = data.get("jobs", [])[:limit]
        return [{
            "id": f"remotive:{job.get('id') or idx}",
            "source": "remotive",
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("candidate_required_location") or "Remote",
            "contract_type": job.get("job_type") or "UNKNOWN",
            "description": job.get("description"),
            "url": job.get("url"),
            "dateCreation": job.get("publication_date"),
            "dateLimite": job.get("expiration_date"),
            "application": {"url": job.get("url"), "method": "site"},
        } for idx, job in enumerate(jobs)]


class ArbeitnowAdapter(BaseSourceAdapter):
    name = "arbeitnow"

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        url = "https://www.arbeitnow.com/api/job-board-api"
        try:
            response = requests.get(url, params={"page": 1}, timeout=15)
            response.raise_for_status()
            data = response.json() or {}
        except Exception:
            return []
        jobs = data.get("data", []) or []
        if keywords:
            needle = keywords.casefold()
            jobs = [job for job in jobs if needle in (job.get("title", "") + " " + job.get("description", "")).casefold()][:limit]
        else:
            jobs = jobs[:limit]
        return [{
            "id": f"arbeitnow:{job.get('slug') or idx}",
            "source": "arbeitnow",
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("location"),
            "contract_type": job.get("job_type") or "UNKNOWN",
            "description": job.get("description"),
            "url": job.get("url"),
            "dateCreation": job.get("created_at"),
            "application": {"url": job.get("url"), "method": "site"},
        } for idx, job in enumerate(jobs)]


def _strip_html(html: str | None) -> str | None:
    """`jobDescription` (WorkdayAdapter) arrive en HTML (`<p>`, `<li>`...) :
    retiré pour matcher le format texte brut attendu par le pipeline de
    scoring (BM25/embeddings) et par l'affichage, comme toutes les autres
    sources. Pas de dépendance HTML parser pour un besoin aussi simple
    (une poignée de balises connues). Chaque frontière de bloc (ouvrante
    OU fermante : p/li/ul/ol/div/br) devient un saut de ligne, puis les
    lignes vides issues de bordures adjacentes (ex. `</p><p>`) sont
    éliminées en filtrant après `strip()` plutôt qu'en essayant de
    deviner une regex de collapse correcte pour tous les cas."""
    if not html:
        return None
    text = re.sub(r"</?(p|li|ul|ol|div|br)[^>]*>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line) or None


def _parse_workday_sites(raw: str) -> list[tuple[str, str, str]]:
    """`"tenant:wdN:site,tenant2:wdN2:site2"` -> `[(tenant, wdN, site), ...]`,
    silencieusement ignore une entrée mal formée plutôt que de faire
    planter toute la recherche pour une faute de frappe dans `.env`."""
    sites: list[tuple[str, str, str]] = []
    for entry in raw.split(","):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) == 3 and all(parts):
            sites.append((parts[0], parts[1], parts[2]))
    return sites


class WorkdayAdapter(BaseSourceAdapter):
    """De nombreux grands groupes (pharma notamment : AstraZeneca, Ipsen)
    hébergent leur site carrières sur Workday, dont le frontend interroge
    une API JSON non documentée mais publique et sans authentification
    (confirmé en direct : `POST /wday/cxs/{tenant}/{site}/jobs`, puis
    `GET` sur le même chemin + `externalPath` pour le détail d'une offre,
    y compris `jobDescription`). Contrairement aux agrégateurs généralistes
    ci-dessus, Workday est PAR ENTREPRISE : la liste des tenants à
    interroger vient de `WORKDAY_CAREERS_SITES` (`.env`), vide par défaut
    (aucune entreprise supposée a priori)."""

    name = "workday"
    # Description complète récupérée par une requête GET EN PLUS par
    # offre (le résultat de recherche n'en contient pas) : bornée au
    # nombre réellement conservé par offre de recherche demandée
    # (`limit` du générique `BaseSourceAdapter.search`), jamais toutes
    # les offres d'un tenant.
    _MAX_DETAIL_FETCHES_PER_SITE = 10

    def search(self, keywords: str | None = None, contract_type: str | None = None, limit: int = 10) -> list[dict]:
        sites = _parse_workday_sites(os.getenv("WORKDAY_CAREERS_SITES", ""))
        if not sites or not keywords:
            return []
        results: list[dict] = []
        for tenant, wd_version, site in sites:
            results.extend(self._search_site(tenant, wd_version, site, keywords, limit))
        return results[:limit]

    def _search_site(
        self, tenant: str, wd_version: str, site: str, keywords: str, limit: int
    ) -> list[dict]:
        base = f"https://{tenant}.{wd_version}.myworkdayjobs.com"
        cxs = f"{base}/wday/cxs/{tenant}/{site}"
        try:
            payload = {
                "appliedFacets": {}, "limit": limit, "offset": 0,
                "searchText": keywords,
            }
            response = requests.post(f"{cxs}/jobs", json=payload, timeout=15)
            response.raise_for_status()
            postings = (response.json() or {}).get("jobPostings", [])[:limit]
        except Exception:
            return []

        offers = []
        for idx, posting in enumerate(postings):
            external_path = posting.get("externalPath") or ""
            url = f"{base}/{site}{external_path}" if external_path else None
            description = None
            if idx < self._MAX_DETAIL_FETCHES_PER_SITE and external_path:
                try:
                    detail = requests.get(f"{cxs}{external_path}", timeout=15)
                    detail.raise_for_status()
                    posting_info = (detail.json() or {}).get("jobPostingInfo", {})
                    description = _strip_html(posting_info.get("jobDescription"))
                except Exception:
                    description = None
            offers.append({
                "id": f"workday:{tenant}:{external_path or idx}",
                "source": "workday",
                "title": posting.get("title"),
                "company": tenant,
                "location": posting.get("locationsText"),
                "contract_type": posting.get("timeType") or "UNKNOWN",
                "description": description,
                "url": url,
                "dateCreation": posting.get("postedOn"),
                "application": {"url": url, "method": "site"},
            })
        return offers


def available_source_adapters() -> list[BaseSourceAdapter]:
    adapters: list[BaseSourceAdapter] = [
        JoobleAdapter(),
        AdzunaAdapter(),
        ReedAdapter(),
        CareerjetAdapter(),
        RemoteOKAdapter(),
        RemoteSourceAdapter(),
        ArbeitnowAdapter(),
        WorkdayAdapter(),
    ]
    return adapters
