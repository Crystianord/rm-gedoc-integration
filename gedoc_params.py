"""
Cliente GEDOC REST para Parametrizações (roles e areas).
Consulta o cache primeiro — só bate na API se não encontrar.
"""
import os
import logging
import requests
from dotenv import load_dotenv
from gedoc_cache import cache

load_dotenv()

logger = logging.getLogger(__name__)

URL_ROLES = os.getenv("GEDOC_URL_ROLES", "https://gec-api.sistemasgap.com.br/roles")
URL_AREAS = os.getenv("GEDOC_URL_AREAS", "https://gec-api.sistemasgap.com.br/areas")
TOKEN     = os.getenv("GEDOC_TOKEN", "")
ACCESS    = os.getenv("GEDOC_ACCESS", "")
TENANT    = os.getenv("GEDOC_TENANT", "").strip()


def _headers() -> dict:
    return {
        "authorization": f"bearer {TOKEN}",
        "access": ACCESS,
        "tenant": TENANT,
        "content-type": "application/json",
        "accept": "application/json",
        "origin": "https://gec.sistemasgap.com.br",
    }


class GEDOCParams:
    def find_or_create_role(self, name: str) -> str | None:
        try:
            oid = cache.find_role(name)
            if oid:
                return oid
            oid = self._create("/roles", name)
            cache.add_role(name, oid)
            logger.info(f"Role criado no GEDOC: '{name}' → {oid}")
            return oid
        except Exception as e:
            logger.error(f"Erro ao resolver role '{name}': {e}")
            return None

    def find_or_create_area(self, name: str) -> str | None:
        try:
            oid = cache.find_area(name)
            if oid:
                return oid
            oid = self._create("/areas", name)
            cache.add_area(name, oid)
            logger.info(f"Area criada no GEDOC: '{name}' → {oid}")
            return oid
        except Exception as e:
            logger.error(f"Erro ao resolver area '{name}': {e}")
            return None

    def _create(self, path: str, name: str) -> str:
        url = URL_ROLES if path == "/roles" else URL_AREAS
        r = requests.post(
            url,
            headers=_headers(),
            json={"name": name, "hiringType": ["internal"]},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["_id"]


gedoc_params = GEDOCParams()
