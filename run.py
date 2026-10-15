import sys
import os
from pathlib import Path

# ── Frozen mode (PyInstaller exe) ─────────────────────────────────────────────
# sys.executable = caminho do .exe
# sys._MEIPASS   = pasta _internal (onde o Python e módulos ficam)
if getattr(sys, 'frozen', False):
    _APP_DIR = Path(sys.executable).parent
    # Diz ao Playwright onde estão os browsers (copiados pelo build.bat)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(_APP_DIR / 'ms-playwright'))
else:
    _APP_DIR = Path(__file__).parent

# ── Credenciais: .env tem prioridade; se não existir usa local_config.py ──────
if not (_APP_DIR / '.env').exists():
    try:
        import local_config  # noqa
    except ImportError:
        pass

import logging
import argparse
from refresh_token import capturar_token_via_playwright, atualizar_env
from sync import run_sync
from notify_hyperflow import notificar

_log_file = str(_APP_DIR / 'integration.log')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_file, encoding="utf-8"),
    ],
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Integração RM → GEDOC")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Executa carga completa (todos os funcionários). Sem flag = apenas alterações.",
    )
    args = parser.parse_args()

    logging.info("Renovando token do GEDOC...")
    token, access = capturar_token_via_playwright(headless=True)
    if token:
        atualizar_env(token, access)
        logging.info("Token renovado.")
    else:
        logging.warning("Não foi possível renovar o token — usando o token atual.")

    logging.info(f"Iniciando sync {'COMPLETO' if args.full else 'DELTA'}...")
    report = run_sync(full_load=args.full)

    path = report.save(str(_APP_DIR))
    logging.info(f"Relatório Excel salvo em: {path}")

    notificar(report)
