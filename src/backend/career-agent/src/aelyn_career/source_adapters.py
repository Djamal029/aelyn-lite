"""Adapters de sources publiques pour le moteur de recherche d'offres.

Les adapters sont volontairement simples et tolérants : si la clé API n'est
pas configurée ou si la source est indisponible, ils retournent une liste vide
sans faire planter la recherche. Cela garde le système utilisable sur CPU et
avec des environnements partiellement configurés.
"""

from __future__ import annotations

import os
from typing import Any

import requests


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
            "title": job.get("position"),
            "company": job.get("company"),
            "location": job.get("location") or "Remote",
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


def available_source_adapters() -> list[BaseSourceAdapter]:
    adapters: list[BaseSourceAdapter] = [
        JoobleAdapter(),
        AdzunaAdapter(),
        ReedAdapter(),
        CareerjetAdapter(),
        RemoteOKAdapter(),
        RemoteSourceAdapter(),
        ArbeitnowAdapter(),
    ]
    return adapters
