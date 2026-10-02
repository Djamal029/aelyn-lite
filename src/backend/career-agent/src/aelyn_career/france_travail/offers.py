import os
import re

import dotenv
import requests

from aelyn.core.config import settings

# Sépare sur la virgule ou sur " et "/" & " : un LLM qui extrait des
# mots-clés depuis une phrase libre (ex. "des offres chez EDF et Roche")
# écrit souvent la conjonction telle quelle plutôt qu'une vraie virgule.
_KEYWORD_SEPARATOR_RE = re.compile(r",|\bet\b|&", re.IGNORECASE)

dotenv.load_dotenv()
CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
URL = os.getenv("FRANCE_TRAVAIL_URL", "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search")

# Codes officiels (endpoint /referentiel/typesContrats) : CDI et CDD sont de
# vraies valeurs acceptées par le paramètre `typeContrat`, vérifié en direct.
# Il n'existe en revanche aucun code dédié pour "Stage". Quant à
# `natureContrat=E1,E2` (apprentissage/professionnalisation), il est accepté
# sans erreur par l'API mais ne filtre pas réellement les résultats (vérifié
# en direct : la première offre renvoyée reste hors alternance) : on ne s'y
# fie pas, on filtre après coup sur le champ booléen fiable `alternance` de
# chaque offre.
CONTRACT_TYPE_PARAMS = {
    "cdi": {"typeContrat": "CDI"},
    "cdd": {"typeContrat": "CDD"},
    "alternance": {},
    "stage": {"typeContrat": "CDD"},
}


class FTOffers:
    def __init__(self, access_token=None):
        self.__client_id = CLIENT_ID
        self.__client_secret = CLIENT_SECRET
        self.access_token = access_token
        self.url = URL
        # `None` = pas de valeur forcée sur CETTE instance : `keywords`/
        # `departments` lisent alors `settings.xxx` À CHAQUE accès (cf.
        # ces propriétés) plutôt qu'une copie figée à la construction.
        # Assigner `ft.keywords = "..."` (utilisé par les tests, et
        # possible pour un appelant qui veut une recherche ponctuelle
        # différente du réglage global) fixe un override qui prend le
        # dessus jusqu'à ce qu'il soit remis à `None`.
        self._keywords_override: str | None = None
        self._departments_override: str | None = None

    @property
    def keywords(self) -> str:
        # Propriété (pas un attribut figé à la construction) : `FTOffers`
        # est un singleton de longue durée côté API (cf.
        # `aelyn_api.deps.get_offers_agent`/`ConversationalAgent.offers_agent`),
        # un `PATCH /settings` doit changer la recherche de la PROCHAINE
        # requête sans redémarrage, ce qu'une copie figée à `__init__`
        # n'aurait jamais permis.
        if self._keywords_override is not None:
            return self._keywords_override
        return settings.keywords

    @keywords.setter
    def keywords(self, value: str) -> None:
        self._keywords_override = value

    @property
    def departments(self) -> str:
        if self._departments_override is not None:
            return self._departments_override
        return settings.department

    @departments.setter
    def departments(self, value: str) -> None:
        self._departments_override = value

    def client_id(self):
        return self.__client_id

    def client_secret(self):
        return self.__client_secret

    def connect(self):
        response = requests.post(
            "https://entreprise.francetravail.fr/connexion/oauth2/access_token",
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id(),
                "client_secret": self.client_secret(),
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
        )
        status_code = response.status_code
        if status_code != 200:
            raise Exception(f"Authentification France Travail échouée ({status_code})")
        token_data = response.json()
        # Toujours remplacer par le jeton FRAIS qu'on vient d'obtenir :
        # l'ancienne version ne l'appliquait QUE si `access_token` était
        # encore `None`, donc un rappel de `connect()` réussissait son
        # authentification mais jetait le nouveau jeton et gardait
        # l'ancien. Sur `FTOffers`, singleton de longue durée côté API
        # (connecté UNE seule fois à la création), ce jeton expire après
        # un certain temps (comme tout jeton OAuth client_credentials) et
        # n'était alors plus jamais rafraîchi : toute recherche échouait
        # en 401 jusqu'au redémarrage du serveur (observé en direct après
        # plusieurs jours d'exécution continue).
        self.access_token = token_data["access_token"]

    def search_offers_for(self, mot_cle: str, contract_type: str | None = None):
        """Recherche pour UN seul mot-clé (l'API combine plusieurs `motsCles`
        séparés par virgule en ET, ce qui donne 0 résultat dès qu'on en met
        plusieurs de larges en même temps).

        `contract_type` : "cdi", "cdd", "alternance" ou "stage" (voir
        CONTRACT_TYPE_PARAMS). Résultats triés du plus récent au plus ancien.
        """
        params = {
            "motsCles": mot_cle,
            "departement": self.departments,
            "sort": 1,  # du plus récent au plus ancien
        }
        if contract_type:
            params.update(CONTRACT_TYPE_PARAMS.get(contract_type.lower(), {}))

        # Un jeton expiré renvoie 401 : on se reconnecte UNE fois et on
        # retente, plutôt que de dépendre entièrement de l'appelant pour
        # savoir quand rafraîchir (cf. `connect()` ci-dessus — sur un
        # `FTOffers` de longue durée, personne d'autre ne le fera).
        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            }
            response = requests.get(url=self.url, headers=headers, params=params)
            status_code = response.status_code
            if status_code == 401 and attempt == 0:
                self.connect()
                continue
            break

        if status_code == 204:
            # Recherche réussie, aucune offre ne correspond aux critères.
            return [], None
        if status_code not in (200, 206):
            # 206 = contenu partiel (pagination via l'en-tête Content-Range),
            # toujours un succès pour cette API.
            raise Exception(f"Recherche d'offres France Travail échouée ({status_code})")

        data = response.json()
        possible_filters = data.get("filtresPossibles")
        offres = data.get("resultats", [])

        if contract_type:
            contract_type = contract_type.lower()
            if contract_type == "alternance":
                offres = [offre for offre in offres if offre.get("alternance")]
            elif contract_type == "stage":
                # Pas de code API dédié au stage (cf. CONTRACT_TYPE_PARAMS) :
                # on ne garde que les CDD non-alternance dont l'intitulé ou
                # la description mentionne "stage".
                offres = [
                    offre
                    for offre in offres
                    if not offre.get("alternance")
                    and (
                        "stage" in offre.get("intitule", "").lower()
                        or "stage" in offre.get("description", "").lower()
                    )
                ]

        return offres, possible_filters

    def search_offers(self, contract_type: str | None = None, keywords: str | None = None):
        """Une recherche par mot-clé (de `keywords` si fourni, sinon
        `self.keywords`), résultats fusionnés, dédupliqués par identifiant
        d'offre, triés du plus récent au plus ancien (`dateCreation`).

        `keywords` permet une recherche ponctuelle (ex. "EDF", "Data
        Scientist") sans changer la configuration par défaut de l'agent.
        """
        source = keywords if keywords else self.keywords
        mots_cles = [mot.strip() for mot in _KEYWORD_SEPARATOR_RE.split(source) if mot.strip()]

        offres_par_id: dict[str, dict] = {}
        possible_filters = None
        for mot_cle in mots_cles:
            offres, filtres = self.search_offers_for(mot_cle, contract_type=contract_type)
            if filtres is not None:
                possible_filters = filtres
            for offre in offres:
                offres_par_id[offre["id"]] = offre

        resultats = list(offres_par_id.values())
        resultats.sort(key=lambda offre: offre.get("dateCreation", ""), reverse=True)
        return resultats, possible_filters
