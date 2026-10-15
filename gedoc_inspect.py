"""
Inspeciona os primeiros registros da API de employees do GEDOC.
Mostra os campos disponíveis e os valores de status/terminated.

Uso: py gedoc_inspect.py
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("GEDOC_URL_EMPLOYEES", "https://gec-api.sistemasgap.com.br/employees")
API_KEY  = os.getenv("GEDOC_API_KEY", "")
TOKEN    = os.getenv("GEDOC_TOKEN", "")
ACCESS   = os.getenv("GEDOC_ACCESS", "")
TENANT   = os.getenv("GEDOC_TENANT", "").strip()

headers_apikey = {
    "x-api-key": API_KEY,
    "tenant": TENANT,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

headers_bearer = {
    "authorization": f"bearer {TOKEN}",
    "access": ACCESS,
    "tenant": TENANT,
    "content-type": "application/json",
    "accept": "application/json",
    "origin": "https://gec.sistemasgap.com.br",
}

print("=" * 60)
print("Testando GET /employees com x-api-key...")
r = requests.get(BASE_URL, headers=headers_apikey, params={"page": 1, "limit": 5}, timeout=30)
print(f"Status: {r.status_code}")

if r.ok:
    data = r.json()
    if isinstance(data, dict):
        print(f"Total: {data.get('total', '?')} | Campos raiz: {list(data.keys())}")
        rows = data.get("rows", [])
    else:
        rows = data
        print(f"Retornou lista com {len(rows)} itens")

    print(f"\nPrimeiros {len(rows)} registros:\n")
    for emp in rows:
        nome = emp.get("name") or emp.get("nome") or emp.get("fullName") or "?"
        eid  = emp.get("_id", "?")
        # Mostra todos os campos que podem indicar status
        status_fields = {
            k: v for k, v in emp.items()
            if any(kw in k.lower() for kw in ["status", "termin", "block", "active", "ativo", "inativ", "deslig"])
        }
        print(f"  Nome: {nome}")
        print(f"  ID  : {eid}")
        print(f"  Campos de status: {status_fields}")
        print(f"  Todos os campos : {list(emp.keys())}")
        print()
else:
    print(f"Erro: {r.text[:300]}")

print("=" * 60)
print("Testando GET /employees com bearer token...")
r2 = requests.get(BASE_URL, headers=headers_bearer, params={"page": 1, "limit": 5}, timeout=30)
print(f"Status: {r2.status_code}")
if not r2.ok:
    print(f"Erro: {r2.text[:200]}")
