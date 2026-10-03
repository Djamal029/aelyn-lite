import json
import logging
import os
from pathlib import Path

import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# Certifications et bénévolat sont chacun dédoublés en deux sources
# (website/linkedin) dans profil.json ; même liste de sources pour les deux.
SOURCES = ["website", "linkedin"]

profil_path = os.getenv("PROFIL_PATH")
_EXAMPLE_PROFIL_PATH = Path(__file__).parent / "profil.example.json"


def load_profil_json(path: str | None = None) -> dict:
    """Relit `profil.json` depuis le disque, à l'appel (pas une valeur
    mise en cache). Utilisée pour le chargement initial (`profil_json`
    ci-dessous) ET pour recharger un profil modifié via `PUT
    /career/profile` (aelyn-api) sans redémarrer le process, cf.
    `ApplicationWriter.reload_profile`."""
    with open(path or profil_path, "r", encoding="utf-8") as f:
        return json.load(f)


try:
    profil_json = load_profil_json()
except (FileNotFoundError, TypeError):
    # `profil.json` est volontairement non versionné (données perso) :
    # une installation neuve (ex. version lite tout juste clonée, avant
    # même d'avoir lancé install.sh/.ps1 ou rempli son profil) ne l'a pas
    # encore. Planter ici ferait planter l'IMPORT de ce module, donc TOUT
    # aelyn-api dès le démarrage (observé en direct : la suite de tests
    # entière de la version lite refusait de se collecter pour cette
    # seule raison) - pire moment possible pour l'apprendre. Repli sur
    # l'exemple bidon plutôt que de bloquer tout le process : CV/lettre
    # de motivation produiront un résultat hors sujet avec ce profil
    # fictif, mais rien d'autre (mail, média, conversation) n'est
    # bloqué pour autant.
    logger.warning(
        "profil.json introuvable (%s) : repli sur profil.example.json. "
        "Lance install.sh/.ps1, ou édite profil.json toi-même, pour un vrai profil.",
        profil_path,
    )
    profil_json = load_profil_json(str(_EXAMPLE_PROFIL_PATH))


def validate_profil_structure(data: object) -> list[str]:
    """Vérifie que `data` a la structure minimale que `ProfilManager.
    parse_profile()` lit SANS filet (accès direct `dico['cle']`, pas
    `.get()`) : un champ manquant parmi ceux-ci ferait planter TOUTE
    génération de CV/lettre de motivation avec un `KeyError`/`TypeError`
    opaque, bien après qu'un `PUT /career/profile` malformé ait été
    accepté. Retourne la liste des problèmes trouvés (vide = valide),
    jamais une exception : à l'appelant (`aelyn_api.routers.career`) de
    décider quoi en faire (ici, un 422 qui les liste toutes d'un coup).

    Volontairement PAS exhaustif sur tous les champs optionnels
    (`.get(..., défaut)` dans `parse_profile` les rend inoffensifs s'ils
    manquent) : seuls les champs à accès direct, ceux qui provoqueraient
    un crash réel, sont vérifiés ici."""
    problems: list[str] = []

    if not isinstance(data, dict):
        return ["le contenu doit être un objet JSON (dict), pas une liste/valeur brute"]

    profile = data.get("profile")
    if not isinstance(profile, dict):
        return ["la clé racine 'profile' est manquante ou n'est pas un objet"]

    experiences = profile.get("experience")
    if not isinstance(experiences, list):
        problems.append("'profile.experience' est manquant ou n'est pas une liste (requis, même vide)")
    else:
        for i, exp in enumerate(experiences):
            if not isinstance(exp, dict):
                problems.append(f"profile.experience[{i}] n'est pas un objet")
                continue
            for field in ("role", "company", "period", "description"):
                if field not in exp:
                    problems.append(f"profile.experience[{i}] : champ '{field}' manquant")

    education = profile.get("education", [])
    if not isinstance(education, list):
        problems.append("'profile.education' doit être une liste")
    else:
        for i, edu in enumerate(education):
            if not isinstance(edu, dict):
                problems.append(f"profile.education[{i}] n'est pas un objet")
                continue
            for field in ("degree", "field", "institution"):
                if field not in edu:
                    problems.append(f"profile.education[{i}] : champ '{field}' manquant")

    skills = profile.get("skills", {})
    if not isinstance(skills, dict):
        problems.append("'profile.skills' doit être un objet (catégorie -> liste de compétences)")

    projects = profile.get("projects", {})
    if not isinstance(projects, dict):
        problems.append("'profile.projects' doit être un objet")
    else:
        for section in ("academic_projects", "bachelor_projects", "personal_projects"):
            items = projects.get(section, [])
            if not isinstance(items, list):
                problems.append(f"'profile.projects.{section}' doit être une liste")
                continue
            for i, proj in enumerate(items):
                if not isinstance(proj, dict) or "title" not in proj:
                    problems.append(f"profile.projects.{section}[{i}] : champ 'title' manquant")

    certifications = profile.get("certifications", {})
    if not isinstance(certifications, dict):
        problems.append("'profile.certifications' doit être un objet")
    else:
        for source in SOURCES:
            items = certifications.get(source, [])
            if not isinstance(items, list):
                problems.append(f"'profile.certifications.{source}' doit être une liste")
                continue
            for i, cert in enumerate(items):
                if not isinstance(cert, dict):
                    problems.append(f"profile.certifications.{source}[{i}] n'est pas un objet")
                    continue
                for field in ("title", "issuer"):
                    if field not in cert:
                        problems.append(f"profile.certifications.{source}[{i}] : champ '{field}' manquant")

    volunteering = profile.get("volunteering", {})
    if not isinstance(volunteering, dict):
        problems.append("'profile.volunteering' doit être un objet")
    else:
        for source in SOURCES:
            items = volunteering.get(source, [])
            if not isinstance(items, list):
                problems.append(f"'profile.volunteering.{source}' doit être une liste")
                continue
            for i, benevolat in enumerate(items):
                if not isinstance(benevolat, dict):
                    problems.append(f"profile.volunteering.{source}[{i}] n'est pas un objet")
                    continue
                for field in ("title", "organization"):
                    if field not in benevolat:
                        problems.append(f"profile.volunteering.{source}[{i}] : champ '{field}' manquant")

    recommendations = profile.get("recommendations", [])
    if not isinstance(recommendations, list):
        problems.append("'profile.recommendations' doit être une liste")
    else:
        for i, reco in enumerate(recommendations):
            if not isinstance(reco, dict):
                problems.append(f"profile.recommendations[{i}] n'est pas un objet")
                continue
            for field in ("recommender", "role", "organization"):
                if field not in reco:
                    problems.append(f"profile.recommendations[{i}] : champ '{field}' manquant")

    languages = profile.get("languages")
    if languages is not None:
        if not isinstance(languages, list):
            problems.append("'profile.languages' doit être une liste")
        else:
            for i, lang in enumerate(languages):
                if not isinstance(lang, dict) or "language" not in lang or "level" not in lang:
                    problems.append(f"profile.languages[{i}] : champs 'language'/'level' requis")

    interests = profile.get("interests")
    if interests is not None and not isinstance(interests, list):
        problems.append("'profile.interests' doit être une liste")

    return problems


class ProfilManager:
    def __init__(self, profil_json=profil_json):
        self.profil = profil_json['profile']

    def parse_profile(self) -> list[dict]:
        if not self.profil:
            return None

        chunks = []
        # Formation, un chunk par diplôme. Absente jusqu'ici : le LLM de
        # rédaction (CV/lettre) n'avait alors aucune vraie donnée de
        # formation et en inventait une plausible mais fausse (observé :
        # "Master Data Science ENSAI 2025" et "Licence Bordeaux" inventés
        # de toutes pièces à la place du vrai diplôme d'ingénieur ENSAI
        # 2024-2027 et de la licence Statistique-Info à Nazi Boni).
        for edu in self.profil.get("education", []):
            text = f"{edu['degree']} en {edu['field']}, {edu['institution']} ({edu.get('location', '?')}), {edu.get('period', '?')}."
            chunks.append({
                "type": "education",
                "title": f"{edu['degree']} - {edu['institution']}",
                "text": text,
                "metadata": edu,
            })

        # Experiences - One by One
        for exp in self.profil.get('experience'):
            text = f"{exp['role']} chez {exp['company']} sur la période de {exp['period']} à/en {exp['location']}.\n"
            text += exp['description'] + "\n"
            if exp.get("highlights"):
                text += "Faits marquants : " + " ; ".join(exp["highlights"]) + ".\n"
            if exp.get("methodology"):
                text += "Méthodes : " + ", ".join(exp["methodology"]) + ".\n"
            if exp.get("results"):
                results = "; ".join(
                    f"{key.replace('_', ' ')} : {value}"
                    for key, value in exp["results"].items()
                )
                text += "Résultats : " + results + ".\n"
            text += f"Technologies : {', '.join(exp['technologies'])}" if exp.get("technologies") else ""
            chunks.append({
                "type": "experience",
                "title": f"{exp['role']} - {exp['company']}",
                "text": text,
                "metadata": exp,
            })

        # Skills - One chunk by cateogory
        for category, skills_list in self.profil.get("skills", {}).items():
            text = f"Compétences en {category.replace('_', ' ')} : {', '.join(skills_list)}."
            chunks.append({
                "type": "skill_category",
                "title": category,
                "text": text,
                "metadata": {"category": category, "skills": skills_list},
            })

        # 3. Projets, un par projet, toutes catégories confondues (academic/bachelor/personal)
        for section in ["academic_projects", "bachelor_projects", "personal_projects"]:
            for proj in self.profil.get("projects", {}).get(section, []):
                text = f"{proj['title']}. {proj.get('description', '')}"
                if proj.get("technologies"):
                    text += " Technologies : " + ", ".join(proj["technologies"]) + "."
                if proj.get("methodology"):
                    text += " Méthodologie : " + ", ".join(proj["methodology"]) + "."
                chunks.append({
                    "type": "project",
                    "title": proj["title"],
                    "text": text,
                    "metadata": proj,
                })

        # 4. Certifications, toutes sources confondues (website/linkedin)
        for source in SOURCES:
            for cert in self.profil.get("certifications", {}).get(source, []):
                text = f"Certification : {cert['title']}, délivrée par {cert['issuer']} ({cert.get('issue_date', '?')})."
                if cert.get("skills"):
                    text += " Compétences : " + ", ".join(cert["skills"]) + "."
                chunks.append({
                    "type": "certification",
                    "title": cert["title"],
                    "text": text,
                    "metadata": cert,
                })

        # 5. Bénévolat, toutes sources confondues (website/linkedin)
        for source in SOURCES:
            for benevolat in self.profil.get("volunteering", {}).get(source, []):
                text = f"{benevolat['title']} chez {benevolat['organization']} ({benevolat.get('duration', '?')}).\n"
                text += benevolat.get("description", "")
                if benevolat.get("responsibilities"):
                    text += " Responsabilités : " + ", ".join(benevolat["responsibilities"]) + "."
                if benevolat.get("skills"):
                    text += " Compétences : " + ", ".join(benevolat["skills"]) + "."
                chunks.append({
                    "type": "volunteering",
                    "title": f"{benevolat['title']} - {benevolat['organization']}",
                    "text": text,
                    "metadata": benevolat,
                })

        # 6. Recommandations, une par recommandation
        for reco in self.profil.get("recommendations", []):
            text = f"Recommandation de {reco['recommender']} ({reco['role']}, {reco['organization']}), au sujet de : {reco.get('context', '?')}.\n"
            text += "Points clés : " + ", ".join(reco.get("key_points", [])) + "."
            chunks.append({
                "type": "recommendation",
                "title": f"Recommandation - {reco['recommender']}",
                "text": text,
                "metadata": reco,
            })

        # 7. Langues et centres d'intérêt, un chunk chacun (pas un par
        # entrée : ni l'un ni l'autre ne pèse assez pour être scoré
        # individuellement contre une offre, mais il faut que le LLM de
        # rédaction du CV les voie).
        if self.profil.get("languages"):
            langues = ", ".join(f"{l['language']} ({l['level']})" for l in self.profil["languages"])
            chunks.append({
                "type": "languages",
                "title": "Langues",
                "text": f"Langues : {langues}.",
                "metadata": {"languages": self.profil["languages"]},
            })

        if self.profil.get("interests"):
            chunks.append({
                "type": "interests",
                "title": "Centres d'intérêt",
                "text": "Centres d'intérêt : " + ", ".join(self.profil["interests"]) + ".",
                "metadata": {"interests": self.profil["interests"]},
            })

        return chunks


def chunk_label(chunk: dict) -> str:
    """Traduit un chunk (cf. `parse_profile`) en phrase courte et naturelle,
    pour dire à l'utilisateur QUOI dans son profil a fait matcher une offre,
    pas juste un score, un élément concret qu'il reconnaît."""
    meta = chunk["metadata"]

    if chunk["type"] == "education":
        return f"ta formation à {meta['institution']}"
    if chunk["type"] == "experience":
        return f"ton expérience chez {meta['company']}"
    if chunk["type"] == "project":
        return f"ton projet « {chunk['title']} »"
    if chunk["type"] == "skill_category":
        return f"tes compétences en {meta['category'].replace('_', ' ')}"
    if chunk["type"] == "certification":
        return f"ta certification « {chunk['title']} »"
    if chunk["type"] == "volunteering":
        return f"ton bénévolat chez {meta['organization']}"
    if chunk["type"] == "recommendation":
        return f"la recommandation de {meta['recommender']}"
    return chunk["title"]
