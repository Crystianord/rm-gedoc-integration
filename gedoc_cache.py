"""
Cache em memória dos dados do GEDOC.
Carregado uma única vez no início do sync via preload().
Evita chamadas individuais à API para cada funcionário/role/área.
"""
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

URL_EMPLOYEES          = os.getenv("GEDOC_URL_EMPLOYEES", "https://gec-api.sistemasgap.com.br/employees")
URL_EMPLOYEES_INTERNAL = URL_EMPLOYEES + "/internal"
URL_ROLES              = os.getenv("GEDOC_URL_ROLES",     "https://gec-api.sistemasgap.com.br/roles")
URL_AREAS              = os.getenv("GEDOC_URL_AREAS",     "https://gec-api.sistemasgap.com.br/areas")
API_KEY = os.getenv("GEDOC_API_KEY", "")
TENANT  = os.getenv("GEDOC_TENANT", "").strip()


def _employee_headers() -> dict:
    return {
        "x-api-key": API_KEY,
        "tenant": TENANT,
        "Content-Type": "application/json",
    }


def _param_headers() -> dict:
    return {
        "authorization": f"bearer {os.getenv('GEDOC_TOKEN', '')}",
        "access": os.getenv("GEDOC_ACCESS", ""),
        "tenant": TENANT,
        "content-type": "application/json",
        "accept": "application/json",
        "origin": "https://gec.sistemasgap.com.br",
    }


def _fetch_all(url: str, headers: dict, extra_params: dict = None) -> list:
    """Pagina até buscar todos os registros.

    Detecta automaticamente se a API usa page=0 ou page=1 como primeira página:
    faz a primeira requisição com page=1; se a resposta tiver menos registros do
    que o esperado numa primeira página cheia, tenta também page=0.
    """
    results_map: dict[str, dict] = {}  # _id → row, elimina duplicatas
    limit = 100

    def _fetch_page(page: int) -> list:
        params = {"page": page, "limit": limit, **(extra_params or {})}
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("rows", [])

    # Tenta page=0 primeiro para detectar APIs 0-indexed
    try:
        page0_rows = _fetch_page(0)
        if page0_rows:
            page1_rows = _fetch_page(1)
            # Se page=0 e page=1 retornam os mesmos _ids → API é 1-indexed (page=0 = page=1)
            ids0 = {r.get("_id") for r in page0_rows}
            ids1 = {r.get("_id") for r in page1_rows}
            if ids0 == ids1:
                # API 1-indexed: ignora page=0, começa do 1
                logger.debug("API usa paginação 1-indexed (page=0 == page=1).")
                start_page = 1
            else:
                # API 0-indexed: page=0 tem dados novos → inclui e continua do 1
                logger.debug("API usa paginação 0-indexed (page=0 tem dados únicos).")
                for r in page0_rows:
                    if r.get("_id"):
                        results_map[r["_id"]] = r
                start_page = 1
        else:
            # page=0 retornou vazio → API começa no 1
            start_page = 1
    except Exception:
        start_page = 1

    page = start_page
    while True:
        rows = _fetch_page(page)
        for r in rows:
            if r.get("_id"):
                results_map[r["_id"]] = r
        if len(rows) < limit:
            break
        page += 1

    return list(results_map.values())


class GEDOCCache:
    def __init__(self):
        # cpf+data -> employee dict completo
        self.employees: dict[str, dict] = {}
        # cpf (só dígitos) -> employee dict  (fallback quando a data não bate)
        self.employees_by_cpf: dict[str, dict] = {}
        # name.upper() -> ObjectId
        self.roles: dict[str, str] = {}
        # name.upper() -> ObjectId
        self.areas: dict[str, str] = {}

    def preload(self):
        logger.info("Pré-carregando dados do GEDOC...")
        self._load_employees()
        self._load_internal_employees()
        self._load_roles()
        self._load_areas()
        logger.info(
            f"Cache carregado — "
            f"{len(self.employees)} funcionários | "
            f"{len(self.roles)} roles | "
            f"{len(self.areas)} áreas"
        )

    def _load_employees(self):
        try:
            rows = _fetch_all(URL_EMPLOYEES, _employee_headers())
            for r in rows:
                if r.get("cpf"):
                    r["_hiring_type"] = "external"
                    self.employees[self._make_key(r["cpf"], r.get("admissionDate"))] = r
                    self.employees_by_cpf[self._normalize_cpf(r["cpf"])] = r
        except Exception as e:
            logger.error(f"Erro ao carregar employees do GEDOC: {e}")

    def _load_internal_employees(self):
        # Inclui todos os status para capturar funcionários com docs inválidos,
        # bloqueados ou desligados que ainda precisam ser processados pelo sync.
        STATUS_ALL = (
            "activeValidDocs|activeInvalidOptionalDocs|allowedByProgrammaticAccess|"
            "activeInvalidDocs|blockedEmployee|terminationCompleted|terminatedWithInvalids"
        )
        try:
            rows = _fetch_all(
                URL_EMPLOYEES_INTERNAL,
                _param_headers(),
                {"sort": "name", "status": STATUS_ALL},
            )
            for r in rows:
                if r.get("cpf"):
                    r["_hiring_type"] = "internal"
                    date = r.get("hiringDate") or r.get("admissionDate")
                    self.employees[self._make_key(r["cpf"], date)] = r
                    self.employees_by_cpf[self._normalize_cpf(r["cpf"])] = r
        except Exception as e:
            logger.error(f"Erro ao carregar employees internos do GEDOC: {e}")

    def _load_roles(self):
        try:
            rows = _fetch_all(URL_ROLES, _param_headers(), {"sort": "name", "hiringType": "internal"})
            self.roles = {r["name"].strip().upper(): r["_id"] for r in rows if r.get("name")}
        except Exception as e:
            logger.error(f"Erro ao carregar roles do GEDOC: {e}")

    def _load_areas(self):
        try:
            rows = _fetch_all(URL_AREAS, _param_headers(), {"sort": "name", "hiringType": "internal"})
            self.areas = {a["name"].strip().upper(): a["_id"] for a in rows if a.get("name")}
        except Exception as e:
            logger.error(f"Erro ao carregar areas do GEDOC: {e}")

    def find_employee(self, cpf: str, admission_date=None) -> dict | None:
        return self.employees.get(self._make_key(cpf, admission_date))

    def find_employee_by_cpf(self, cpf: str) -> dict | None:
        """Busca só por CPF, sem considerar a data — usado como fallback."""
        return self.employees_by_cpf.get(self._normalize_cpf(cpf))

    def find_role(self, name: str) -> str | None:
        return self.roles.get(name.strip().upper())

    def find_area(self, name: str) -> str | None:
        return self.areas.get(name.strip().upper())

    def add_role(self, name: str, oid: str):
        self.roles[name.strip().upper()] = oid

    def add_area(self, name: str, oid: str):
        self.areas[name.strip().upper()] = oid

    def add_employee(self, cpf: str, admission_date, employee: dict):
        self.employees[self._make_key(cpf, admission_date)] = employee
        self.employees_by_cpf[self._normalize_cpf(cpf)] = employee

    @staticmethod
    def _normalize_cpf(cpf: str) -> str:
        return cpf.replace(".", "").replace("-", "").strip()

    @staticmethod
    def _make_key(cpf: str, admission_date=None) -> str:
        cpf_clean = cpf.replace(".", "").replace("-", "").strip()
        date_part = str(admission_date or "")[:10]  # YYYY-MM-DD
        return f"{cpf_clean}_{date_part}"


cache = GEDOCCache()
