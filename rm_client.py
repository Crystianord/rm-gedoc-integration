import requests
import logging
from datetime import datetime, timedelta
from config import RM_QUERY_URL, RM_QUERY_URL_DELTA, RM_USERNAME, RM_PASSWORD, DELTA_DAYS

logger = logging.getLogger(__name__)


class RMClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = (RM_USERNAME, RM_PASSWORD)
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, url: str, params: dict = None) -> list:
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else [data]
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao consultar RM: {e}")
            return []

    def get_all_employees(self) -> list:
        """Carga completa — usa RM_QUERY_URL diretamente."""
        logger.info("Buscando carga completa do RM...")
        return self._get(RM_QUERY_URL)

    def get_delta_employees(self) -> list:
        """Delta — usa RM_QUERY_URL_DELTA se configurada, senão RM_QUERY_URL com parâmetro de data."""
        since = (datetime.now() - timedelta(days=DELTA_DAYS)).strftime("%Y-%m-%d")
        logger.info(f"Buscando alterações desde {since} no RM...")
        url = RM_QUERY_URL_DELTA if RM_QUERY_URL_DELTA else RM_QUERY_URL
        return self._get(url, params={"dataInicio": since})
