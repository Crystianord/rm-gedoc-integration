import os
import time
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

URL_EMPLOYEES          = os.getenv("GEDOC_URL_EMPLOYEES", "https://gec-api.sistemasgap.com.br/employees")
URL_EMPLOYEES_INTERNAL = URL_EMPLOYEES + "/internal"
API_KEY = os.getenv("GEDOC_API_KEY", "")
TENANT  = os.getenv("GEDOC_TENANT", "").strip()


def _request(method, *args, retries: int = 1, retry_delay: float = 3.0, **kwargs):
    """Faz a request e retenta em caso de HTTP 500 (erro transitório de transação no MongoDB do GEDOC)."""
    r = method(*args, **kwargs)
    for _ in range(retries):
        if r.status_code != 500:
            break
        logger.warning(f"HTTP 500 recebido — aguardando {retry_delay}s e retentando...")
        time.sleep(retry_delay)
        r = method(*args, **kwargs)
    return r


class GEDOCClient:
    def __init__(self):
        self.last_error: str = ""
        self.headers = {
            "x-api-key": API_KEY,
            "tenant": TENANT,
            "Content-Type": "application/json",
        }

    @property
    def internal_headers(self) -> dict:
        return {
            "authorization": f"bearer {os.getenv('GEDOC_TOKEN', '')}",
            "access": os.getenv("GEDOC_ACCESS", ""),
            "tenant": TENANT,
            "content-type": "application/json",
            "accept": "application/json",
            "origin": "https://gec.sistemasgap.com.br",
        }

    def find_by_cpf(self, cpf: str) -> dict | None:
        cpf_digits = cpf.replace(".", "").replace("-", "").strip()
        cpf_formatted = (
            f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"
            if len(cpf_digits) == 11 else cpf_digits
        )
        for query in (cpf_digits, cpf_formatted):
            try:
                r = requests.get(
                    URL_EMPLOYEES,
                    headers=self.headers,
                    params={"q": query, "limit": 10},
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
                rows = data.get("rows", data) if isinstance(data, dict) else data
                for item in rows:
                    if item.get("cpf", "").replace(".", "").replace("-", "") == cpf_digits:
                        return item
            except requests.exceptions.RequestException as e:
                logger.error(f"Erro ao buscar CPF {query} no GEDOC: {e}")
        return None

    def create_employee(self, payload: dict) -> bool:
        cpf = payload.get('cpf')
        self.last_error = ""
        try:
            r = _request(requests.post, URL_EMPLOYEES, headers=self.headers, json=payload, timeout=30)
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao criar no GEDOC: {r.status_code} — {r.text}")
                logger.debug(f"[{cpf}] Payload enviado: {payload}")
                return False
            logger.info(f"[{cpf}] Funcionário criado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao criar no GEDOC: {e}")
            return False

    def update_employee(self, employee_id: str, payload: dict, cpf: str) -> bool:
        self.last_error = ""
        _block_fields = {"blocked", "blockedReason", "blockStartDate", "blockComment"}
        clean = {k: v for k, v in payload.items() if k not in _block_fields}
        try:
            r = _request(requests.put, f"{URL_EMPLOYEES}/{employee_id}", headers=self.headers, json=clean, timeout=30)
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao atualizar no GEDOC: {r.status_code} — {r.text}")
                logger.debug(f"[{cpf}] Payload enviado: {clean}")
                return False
            logger.info(f"[{cpf}] Funcionário atualizado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao atualizar no GEDOC: {e}")
            return False

    def _terminate(self, employee_id: str, cpf: str, headers: dict) -> bool:
        from datetime import datetime, timezone
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/terminate-options",
                headers=headers,
                json={
                    "terminated": True,
                    "terminationDate": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                    "terminatedReason": "6780dfa5558daff23c7294d7",
                    "terminatedComment": "Desligado por integração RM",
                    "blockCpf": False,
                    "blockCpfComment": "",
                },
                timeout=30,
            )
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao desligar no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário desligado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao desligar no GEDOC: {e}")
            return False

    def _cancel_termination(self, employee_id: str, cpf: str, headers: dict) -> bool:
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/cancel-termination",
                headers=headers,
                timeout=30,
            )
            if r.status_code == 409:
                logger.info(f"[{cpf}] Funcionário já ativo no GEDOC — ignorado.")
                return True
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao cancelar desligamento no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Desligamento cancelado no GEDOC (recontratação).")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao cancelar desligamento no GEDOC: {e}")
            return False

    def terminate_employee(self, employee_id: str, cpf: str) -> bool:
        """Desliga funcionário — usa bearer token (único auth aceito pelo /terminate-options)."""
        return self._terminate(employee_id, cpf, self.internal_headers)

    def terminate_internal_employee(self, employee_id: str, cpf: str) -> bool:
        """Desliga funcionário interno — usa bearer token."""
        return self._terminate(employee_id, cpf, self.internal_headers)

    def cancel_termination(self, employee_id: str, cpf: str) -> bool:
        """Cancela desligamento — usa bearer token."""
        return self._cancel_termination(employee_id, cpf, self.internal_headers)

    def cancel_termination_internal(self, employee_id: str, cpf: str) -> bool:
        """Cancela desligamento de funcionário interno — usa bearer token."""
        return self._cancel_termination(employee_id, cpf, self.internal_headers)

    def block_employee(self, employee_id: str, cpf: str) -> bool:
        """Bloqueia funcionário externo via /block-options (alternativa ao terminate para externos)."""
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/block-options",
                headers=self.internal_headers,
                json={"blocked": True, "blockStartDate": None, "blockedReason": "others",
                      "blockComment": "Desligado por integração RM"},
                timeout=30,
            )
            if r.status_code == 409:
                logger.info(f"[{cpf}] Funcionário externo já bloqueado no GEDOC — ignorado.")
                return True
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao bloquear externo no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário externo bloqueado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao bloquear externo no GEDOC: {e}")
            return False

    def block_leave_employee(self, employee_id: str, cpf: str) -> bool:
        """Bloqueia funcionário externo por afastamento (CODSITUACAO='P' no RM) via /block-options."""
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/block-options",
                headers=self.internal_headers,
                json={"blocked": True, "blockStartDate": None, "blockedReason": "removal",
                      "blockComment": "Afastado por integração RM x GEDOC"},
                timeout=30,
            )
            if r.status_code == 409:
                logger.info(f"[{cpf}] Funcionário externo já bloqueado no GEDOC — ignorado.")
                return True
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao bloquear (afastamento) externo no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário externo bloqueado (afastamento) no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao bloquear (afastamento) externo no GEDOC: {e}")
            return False

    def unblock_employee(self, employee_id: str, cpf: str) -> bool:
        """Desbloqueia funcionário externo via /block-options."""
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/block-options",
                headers=self.internal_headers,
                json={"blocked": False, "blockStartDate": None, "blockedReason": "",
                      "blockComment": "Reativado por integração RM"},
                timeout=30,
            )
            if r.status_code == 409:
                logger.info(f"[{cpf}] Funcionário externo já desbloqueado no GEDOC — ignorado.")
                return True
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao desbloquear externo no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário externo desbloqueado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao desbloquear externo no GEDOC: {e}")
            return False

    # --- Funcionários internos (HP MOBILIDADE) ---

    def create_internal_employee(self, payload: dict) -> bool:
        cpf = payload.get("cpf")
        self.last_error = ""
        try:
            r = _request(requests.post, URL_EMPLOYEES_INTERNAL, headers=self.internal_headers, json=payload, timeout=30)
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao criar interno no GEDOC: {r.status_code} — {r.text}")
                logger.debug(f"[{cpf}] Payload enviado: {payload}")
                return False
            logger.info(f"[{cpf}] Funcionário interno criado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao criar interno no GEDOC: {e}")
            return False

    def update_internal_employee(self, employee_id: str, payload: dict, cpf: str) -> bool:
        self.last_error = ""
        _block_fields = {"blocked", "blockedReason", "blockStartDate", "blockComment"}
        clean = {k: v for k, v in payload.items() if k not in _block_fields}
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES_INTERNAL}/{employee_id}",
                headers=self.internal_headers,
                json=clean,
                timeout=30,
            )
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao atualizar interno no GEDOC: {r.status_code} — {r.text}")
                logger.debug(f"[{cpf}] Payload enviado: {clean}")
                return False
            logger.info(f"[{cpf}] Funcionário interno atualizado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao atualizar interno no GEDOC: {e}")
            return False

    def unblock_internal_employee(self, employee_id: str, cpf: str) -> bool:
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/block-options",
                headers=self.internal_headers,
                json={"blocked": False, "blockStartDate": None, "blockedReason": "",
                      "blockComment": "Reativado por integração RM"},
                timeout=30,
            )
            if r.status_code == 409:
                logger.info(f"[{cpf}] Funcionário interno já desbloqueado no GEDOC — ignorado.")
                return True
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao desbloquear interno no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário interno desbloqueado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao desbloquear interno no GEDOC: {e}")
            return False

    def block_leave_internal_employee(self, employee_id: str, cpf: str) -> bool:
        """Bloqueia funcionário interno por afastamento (CODSITUACAO='P' no RM) via /block-options."""
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/block-options",
                headers=self.internal_headers,
                json={"blocked": True, "blockStartDate": None, "blockedReason": "removal",
                      "blockComment": "Afastado por integração RM x GEDOC"},
                timeout=30,
            )
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao bloquear (afastamento) interno no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário interno bloqueado (afastamento) no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao bloquear (afastamento) interno no GEDOC: {e}")
            return False

    def block_internal_employee(self, employee_id: str, cpf: str) -> bool:
        self.last_error = ""
        try:
            r = _request(requests.put,
                f"{URL_EMPLOYEES}/{employee_id}/block-options",
                headers=self.internal_headers,
                json={"blocked": True, "blockStartDate": None, "blockedReason": "others",
                      "blockComment": "Desligado por integração RM"},
                timeout=30,
            )
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                logger.error(f"[{cpf}] Erro ao bloquear interno no GEDOC: {r.status_code} — {r.text}")
                return False
            logger.info(f"[{cpf}] Funcionário interno bloqueado no GEDOC.")
            return True
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"[{cpf}] Erro ao bloquear interno no GEDOC: {e}")
            return False
