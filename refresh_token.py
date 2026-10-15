"""
Renova automaticamente o GEDOC_TOKEN e GEDOC_ACCESS no .env.

Uso:
    python refresh_token.py

Integração com run.py — adicione no início:
    from refresh_token import renovar_token_se_necessario
    renovar_token_se_necessario()
"""
import sys
import json
import os
import re
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEDOC_EMAIL = os.getenv("GEDOC_EMAIL", "")
GEDOC_SENHA = os.getenv("GEDOC_SENHA", "")

# No modo exe, .env fica ao lado do .exe; em dev, ao lado do .py
_BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
ENV_FILE = _BASE / ".env"

# Chaves onde o token pode estar no localStorage ou response JSON
_TOKEN_KEYS  = ["token", "accessToken", "access_token", "jwt", "jwtToken"]
_ACCESS_KEYS = ["access", "accessCode", "accessId", "tenantAccess"]


def _buscar_em_dict(d: dict, chaves: list) -> str | None:
    """Procura recursivamente por qualquer uma das chaves no dict."""
    for k in chaves:
        if k in d:
            v = d[k]
            if isinstance(v, str) and len(v) > 20:
                return v
    # Busca recursiva em valores que são dicts
    for v in d.values():
        if isinstance(v, dict):
            result = _buscar_em_dict(v, chaves)
            if result:
                return result
    return None


def capturar_token_via_playwright(headless: bool = True) -> tuple[str, str]:
    """
    Faz login no GEDOC, intercepta a resposta de autenticação
    e retorna (token, access).
    """
    token_encontrado  = {}
    access_encontrado = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=0 if headless else 100,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
            timeout=60000,  # 60s para o browser subir; evita travar para sempre
        )
        context = browser.new_context()
        page    = context.new_page()

        # ── Intercepta todas as respostas da API do GEDOC ──────────────────
        def on_response(response):
            url = response.url
            if "gec-api.sistemasgap.com.br" not in url and "sistemasgap.com.br" not in url:
                return
            if response.status not in (200, 201):
                return
            try:
                body = response.json()
                if not isinstance(body, dict):
                    return

                t = _buscar_em_dict(body, _TOKEN_KEYS)
                a = _buscar_em_dict(body, _ACCESS_KEYS)

                if t and not token_encontrado:
                    token_encontrado["value"]  = t
                    token_encontrado["url"]    = url
                    logger.info(f"Token capturado de: {url}")

                if a and not access_encontrado:
                    access_encontrado["value"] = a
                    access_encontrado["url"]   = url

            except Exception:
                pass

        page.on("response", on_response)

        try:
            # ── Login ──────────────────────────────────────────────────────
            page.set_default_timeout(30000)  # 30s para qualquer ação da página
            logger.info("Abrindo página de login do GEDOC...")
            page.goto("https://gec.sistemasgap.com.br/login", timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)

            email_input = page.get_by_role("textbox", name="E-mail")
            email_input.wait_for(state="visible", timeout=30000)
            email_input.click()
            email_input.fill(GEDOC_EMAIL)
            page.get_by_role("button", name="Verificar e-mail").click()

            senha_input = page.get_by_role("textbox", name="Senha")
            senha_input.wait_for(state="visible", timeout=15000)
            senha_input.click()
            senha_input.press_sequentially(GEDOC_SENHA, delay=50)

            page.wait_for_timeout(1500)
            entrar_btn = page.get_by_role("button", name="Entrar")
            entrar_btn.click()

            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except PlaywrightTimeout:
                pass
            page.wait_for_timeout(2000)

            # ── Tenta capturar do localStorage como fallback ───────────────
            if not token_encontrado:
                logger.info("Token não interceptado na rede — tentando localStorage...")
                try:
                    ls_raw = page.evaluate("() => JSON.stringify(localStorage)")
                    ls = json.loads(ls_raw)
                    logger.debug(f"Chaves no localStorage: {list(ls.keys())}")

                    t = _buscar_em_dict(ls, _TOKEN_KEYS)
                    a = _buscar_em_dict(ls, _ACCESS_KEYS)
                    if t:
                        token_encontrado["value"]  = t
                        token_encontrado["url"]    = "localStorage"
                    if a:
                        access_encontrado["value"] = a
                        access_encontrado["url"]   = "localStorage"
                except Exception as e:
                    logger.warning(f"Erro ao ler localStorage: {e}")

            # ── Dump completo para diagnóstico (só se não achou nada) ──────
            if not token_encontrado:
                logger.warning("Token NÃO encontrado. Fazendo dump do localStorage para diagnóstico...")
                try:
                    ls_raw = page.evaluate("() => JSON.stringify(localStorage)")
                    ls = json.loads(ls_raw)
                    dump_path = Path(__file__).parent / "_ls_dump.json"
                    dump_path.write_text(json.dumps(ls, indent=2, ensure_ascii=False))
                    logger.warning(f"Dump salvo em: {dump_path}")
                    logger.warning("Abra esse arquivo para identificar onde o token está armazenado.")
                except Exception as e:
                    logger.warning(f"Não foi possível fazer dump: {e}")

        finally:
            browser.close()

    token  = token_encontrado.get("value", "")
    access = access_encontrado.get("value", "")
    return token, access


def atualizar_env(token: str, access: str):
    """
    Atualiza GEDOC_TOKEN e GEDOC_ACCESS.
    - Sempre atualiza os.environ (em memória — suficiente pois o token renova a cada run)
    - Se .env existir ao lado do exe/script: persiste no .env
    - Se não existir e não for exe: persiste no local_config.py
    """
    if token:
        os.environ["GEDOC_TOKEN"] = token
    if access:
        os.environ["GEDOC_ACCESS"] = access

    if ENV_FILE.exists():
        _atualizar_arquivo(ENV_FILE, token, access, "GEDOC_TOKEN", "GEDOC_ACCESS")
        logger.info("Token atualizado no .env.")
    elif not getattr(sys, 'frozen', False):
        local_cfg = _BASE / "local_config.py"
        if local_cfg.exists():
            _atualizar_arquivo(local_cfg, token, access,
                               '"GEDOC_TOKEN"', '"GEDOC_ACCESS"', aspas=True)
            logger.info("Token atualizado no local_config.py.")
    else:
        logger.info("Token ativo em memória (exe mode — renova a cada execução).")


def _atualizar_arquivo(path: Path, token: str, access: str,
                       chave_token: str, chave_access: str, aspas: bool = False):
    conteudo = path.read_text(encoding="utf-8")

    if token:
        if aspas:
            # Formato local_config.py:  "GEDOC_TOKEN":  "valor",
            conteudo = re.sub(
                rf'({re.escape(chave_token)}:\s*")[^"]*(")',
                rf'\g<1>{token}\2',
                conteudo,
            )
        else:
            # Formato .env:  GEDOC_TOKEN=valor
            if re.search(rf"^{re.escape(chave_token)}=", conteudo, re.MULTILINE):
                conteudo = re.sub(rf"^{re.escape(chave_token)}=.*$", f"{chave_token}={token}",
                                  conteudo, flags=re.MULTILINE)
            else:
                conteudo += f"\n{chave_token}={token}"

    if access:
        if aspas:
            conteudo = re.sub(
                rf'({re.escape(chave_access)}:\s*")[^"]*(")',
                rf'\g<1>{access}\2',
                conteudo,
            )
        else:
            if re.search(rf"^{re.escape(chave_access)}=", conteudo, re.MULTILINE):
                conteudo = re.sub(rf"^{re.escape(chave_access)}=.*$", f"{chave_access}={access}",
                                  conteudo, flags=re.MULTILINE)
            else:
                conteudo += f"\n{chave_access}={access}"

    path.write_text(conteudo, encoding="utf-8")


def renovar_token_se_necessario() -> bool:
    """
    Chamado pelo run.py antes do sync.
    Faz um request de teste e renova o token só se receber 401.
    Retorna True se renovou, False se ainda estava válido.
    """
    import requests
    from dotenv import dotenv_values

    env = dotenv_values(ENV_FILE)
    token  = env.get("GEDOC_TOKEN", "")
    tenant = env.get("GEDOC_TENANT", "")
    access = env.get("GEDOC_ACCESS", "")

    headers = {
        "authorization": f"bearer {token}",
        "access": access,
        "tenant": tenant,
        "content-type": "application/json",
        "accept": "application/json",
        "origin": "https://gec.sistemasgap.com.br",
    }

    # Testa com um request simples (busca 1 funcionário interno)
    try:
        r = requests.get(
            "https://gec-api.sistemasgap.com.br/employees/internal",
            headers=headers,
            params={"page": 1, "limit": 1},
            timeout=10,
        )
        if r.status_code != 401:
            logger.info("Token ainda válido — nenhuma renovação necessária.")
            return False
    except Exception as e:
        logger.warning(f"Erro ao testar token: {e}")

    logger.warning("Token expirado (401) — renovando automaticamente...")
    token, access = capturar_token_via_playwright(headless=True)

    if not token:
        logger.error("Falha ao capturar novo token. Verifique _ls_dump.json para diagnóstico.")
        raise RuntimeError("Não foi possível renovar o GEDOC_TOKEN automaticamente.")

    atualizar_env(token, access)

    # Recarrega as variáveis de ambiente na sessão atual
    os.environ["GEDOC_TOKEN"]  = token
    os.environ["GEDOC_ACCESS"] = access
    logger.info("Token renovado com sucesso!")
    return True


# ── Execução direta: força renovação ──────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Garante que GEDOC_SENHA está no .env
    env = {}
    if ENV_FILE.exists():
        from dotenv import dotenv_values
        env = dotenv_values(ENV_FILE)

    senha = env.get("GEDOC_SENHA") or os.getenv("GEDOC_SENHA", "")
    if not senha:
        senha = input("Senha do GEDOC (será salva no .env): ").strip()
        # Salva a senha no .env para próximas execuções
        conteudo = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
        if "GEDOC_SENHA=" not in conteudo:
            conteudo += f"\nGEDOC_SENHA={senha}"
            ENV_FILE.write_text(conteudo, encoding="utf-8")
    os.environ["GEDOC_SENHA"] = senha

    logger.info("Forçando renovação do token...")
    token, access = capturar_token_via_playwright(headless=False)

    if token:
        atualizar_env(token, access)
        logger.info(f"Token: {token[:40]}...")
        logger.info("Pronto! .env atualizado.")
    else:
        logger.error("Não foi possível capturar o token.")
        logger.error("Verifique o arquivo _ls_dump.json para entender onde o token está guardado.")
