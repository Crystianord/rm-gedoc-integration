"""
Gera HTML do resultado do sync e envia para o HyperFlow.

Configuração via .env (opcional — já tem defaults):
    HYPERFLOW_ENDPOINT   = URL do fluxo no HyperFlow
    HYPERFLOW_CLIENT_ID  = client_id de autenticação
    HYPERFLOW_EMPRESA    = nome da empresa (padrão: HP MOBILIDADE)
"""
import os
import csv
import base64
import logging
import requests
from datetime import datetime
from io import StringIO
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

HYPERFLOW_ENDPOINT  = os.getenv(
    "HYPERFLOW_ENDPOINT",
    "https://runtime.hyperflowapis.global/api/aLmXT1-Pt/RM/returnProcessRMxGEDOC",
)
HYPERFLOW_CLIENT_ID = os.getenv("HYPERFLOW_CLIENT_ID", "92bc2fb3-daaa-4292-abf2-15aa4c8989dd")
HYPERFLOW_EMPRESA   = os.getenv("HYPERFLOW_EMPRESA", "HP MOBILIDADE")


def _records_to_csv_base64(records: list[dict]) -> str:
    """Serializa os registros do sync em CSV UTF-8 BOM e retorna base64."""
    if not records:
        return ""
    buf = StringIO()
    campos = ["CPF", "Nome", "Tipo", "Situação", "Ação", "Detalhe", "Hora"]
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writerow(campos)
    for r in records:
        writer.writerow([
            r.get("cpf", ""),
            r.get("nome", ""),
            r.get("tipo", ""),
            r.get("situacao", ""),
            r.get("acao", ""),
            r.get("detalhe", ""),
            r.get("hora", ""),
        ])
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return base64.b64encode(csv_bytes).decode("ascii")


def gerar_html_sync(report) -> str:
    records  = report._records
    started  = report._started_at
    dt_str   = started.strftime("%d/%m/%Y %H:%M:%S")
    ano      = started.year

    erros = [r for r in records if r["acao"] == "Erro"]
    sucesso = len(erros) == 0

    icon       = "✔" if sucesso else "❌"
    color      = "#28a745" if sucesso else "#b22222"
    background = "#f4f8f4" if sucesso else "#fff5f5"
    title      = "Sync Concluído" if sucesso else "Falha no Sync"
    subtitle   = (
        "A sincronização RM → GEDOC foi concluída sem erros."
        if sucesso else
        f"Ocorreram {len(erros)} erro(s) durante o sync RM → GEDOC."
    )

    contagem: dict[str, int] = {}
    for r in records:
        contagem[r["acao"]] = contagem.get(r["acao"], 0) + 1

    def _li(label, value):
        return (
            f"<li><strong>{label}:</strong> {value}</li>"
        )

    info_items = "".join([
        _li("Empresa", HYPERFLOW_EMPRESA),
        _li("Data da Operação", dt_str),
        _li("Total Processados", len(records)),
        _li("Criados",   contagem.get("Criado", 0)),
        _li("Atualizados", contagem.get("Atualizado", 0)),
        _li("Reativados", contagem.get("Reativado", 0) + contagem.get("Reativado + Atualizado", 0)),
        _li("Desligados", contagem.get("Desligado", 0)),
        _li("Ignorados",  contagem.get("Ignorado", 0)),
        _li("Erros",      contagem.get("Erro", 0)),
    ])

    # CSV base64 embutido
    bloco_download = ""
    csv_b64 = _records_to_csv_base64(records)
    if csv_b64:
        data_uri  = f"data:text/csv;charset=utf-8;base64,{csv_b64}"
        btn_color = color
        bloco_download = f"""
      <div style="margin-top:25px;border-top:1px solid #eee;padding-top:20px;">
        <a href="{data_uri}" target="_blank" download="sync_rm_gedoc_{started.strftime('%Y%m%d_%H%M%S')}.csv"
           style="background-color:{btn_color};color:white;padding:12px 24px;text-decoration:none;
                  border-radius:6px;font-weight:bold;display:inline-block;margin-bottom:20px;">
          📥 Baixar Relatório CSV
        </a>
        <div style="text-align:left;background-color:#f8f9fa;padding:15px;border-radius:8px;border:1px solid #ddd;">
          <p style="margin-top:0;font-weight:bold;font-size:14px;color:#b22222;">
            ⚠️ Se o botão acima não funcionar:
          </p>
          <p style="font-size:13px;color:#555;margin-bottom:10px;">
            Clique dentro da caixa abaixo, pressione <strong>Ctrl+A</strong> para selecionar tudo,
            copie e cole na barra de endereços do navegador (Chrome, Edge) e pressione Enter.
          </p>
          <textarea readonly style="width:100%;height:80px;font-size:11px;color:#666;padding:8px;
                    border:1px solid #ccc;border-radius:4px;resize:vertical;box-sizing:border-box;
                    font-family:monospace;">{data_uri}</textarea>
        </div>
      </div>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>{icon} {title}</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: {background}; margin: 0; padding: 0; }}
    .container {{ max-width: 600px; margin: 50px auto; background: #ffffff; border-radius: 16px;
                  padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; }}
    .icon {{ font-size: 48px; color: {color}; margin-bottom: 10px; }}
    h1 {{ color: {color}; font-size: 24px; margin-bottom: 15px; }}
    p {{ color: #333333; font-size: 16px; margin: 8px 0; }}
    .info-box {{ text-align: left; background-color: #f8f9fa; border-radius: 8px; padding: 20px;
                 margin-top: 20px; color: #374151; display: inline-block; width: 100%;
                 box-sizing: border-box; }}
    ul {{ list-style-type: none; padding: 0; margin: 0; }}
    li {{ font-size: 15px; margin-bottom: 10px; border-bottom: 1px solid #eeeeee; padding-bottom: 8px; }}
    li:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
    .footer {{ margin-top: 25px; font-size: 13px; color: #888888; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{subtitle}</p>

    <div class="info-box">
      <ul>
        {info_items}
      </ul>
    </div>

    {bloco_download}

    <div class="footer">
      <p>&copy; {ano} Automação de Integração RM x GEDOC</p>
    </div>
  </div>
</body>
</html>"""
    return html


def enviar_hyperflow(html: str) -> bool:
    if not HYPERFLOW_ENDPOINT:
        logger.info("[HYPERFLOW] Endpoint não configurado — notificação ignorada.")
        return False

    payload = {
        "empresa": HYPERFLOW_EMPRESA,
        "html": html,
    }
    headers = {
        "client_id": HYPERFLOW_CLIENT_ID,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(HYPERFLOW_ENDPOINT, json=payload, headers=headers, timeout=60)
        ok = 200 <= resp.status_code < 300
        logger.info(f"[HYPERFLOW] HTTP {resp.status_code} — {resp.text[:200]}")
        return ok
    except Exception as e:
        logger.error(f"[HYPERFLOW] Erro ao enviar notificação: {e}")
        return False


def notificar(report) -> bool:
    """Gera HTML com CSV embutido e envia ao HyperFlow. Chame após run_sync()."""
    html = gerar_html_sync(report)
    return enviar_hyperflow(html)
