"""
Gerencia o de-para persistente RM → GEDOC (roles e areas).
Salvo em depara.json — cresce automaticamente quando novos códigos RM aparecem.
Na primeira execução, inicializa com os maps do config.py.
"""
import json
import logging
from pathlib import Path
from config import ROLE_MAP, AREA_MAP

logger = logging.getLogger(__name__)

DEPARA_FILE = "depara.json"


class Depara:
    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if Path(DEPARA_FILE).exists():
            with open(DEPARA_FILE, encoding="utf-8") as f:
                return json.load(f)
        # Primeira execução: semeia com os maps do config.py
        logger.info("depara.json não encontrado — inicializando com config.py")
        data = {"roles": dict(ROLE_MAP), "areas": dict(AREA_MAP)}
        self._write(data)
        return data

    def _write(self, data: dict):
        with open(DEPARA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_role(self, codfuncao: str) -> str | None:
        return self._data["roles"].get(codfuncao)

    def get_area(self, codsecao: str) -> str | None:
        return self._data["areas"].get(codsecao)

    def set_role(self, codfuncao: str, oid: str):
        self._data["roles"][codfuncao] = oid
        self._write(self._data)
        logger.info(f"De-para salvo: ROLE {codfuncao} → {oid}")

    def set_area(self, codsecao: str, oid: str):
        self._data["areas"][codsecao] = oid
        self._write(self._data)
        logger.info(f"De-para salvo: AREA {codsecao} → {oid}")


# Singleton — importado pelos outros módulos
depara = Depara()
