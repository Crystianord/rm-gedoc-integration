"""
Cria em lote no GEDOC todas as areas e funções via REST API.
Verifica se já existe antes de criar. Salva ObjectIds em gedoc_entity_ids.json.

Uso:
  py gedoc_create_entities.py              # cria tudo
  py gedoc_create_entities.py --areas      # só areas
  py gedoc_create_entities.py --roles      # só funções
  py gedoc_create_entities.py --reset      # apaga progresso e recomeça

Se der 401: atualize GEDOC_TOKEN no .env (token JWT expira em ~15 dias).
"""

import csv
import json
import sys
import time
import os
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

BASE_URL = os.getenv("GEDOC_API_BASE", "https://gec-api.sistemasgap.com.br")
TOKEN    = os.getenv("GEDOC_TOKEN", "")
ACCESS   = os.getenv("GEDOC_ACCESS", "")
TENANT   = os.getenv("GEDOC_TENANT", "")

AREAS_CSV     = "gedoc_areas_to_create.csv"
ROLES_CSV     = "gedoc_roles_to_create.csv"
PROGRESS_FILE = "gedoc_create_progress.json"
IDS_FILE      = "gedoc_entity_ids.json"

DELAY = 0.3  # segundos entre requests


def headers():
    return {
        "authorization": f"bearer {TOKEN}",
        "access": ACCESS,
        "tenant": TENANT,
        "content-type": "application/json",
        "accept": "application/json",
        "origin": "https://gec.sistemasgap.com.br",
    }


# ─── Progresso ────────────────────────────────────────────────────────────────

def load_progress() -> dict:
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"areas_done": [], "roles_done": [], "areas_failed": [], "roles_failed": []}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def load_ids() -> dict:
    if Path(IDS_FILE).exists():
        with open(IDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"areas": {}, "roles": {}}


def save_ids(ids: dict):
    with open(IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)


# ─── API ──────────────────────────────────────────────────────────────────────

def find_area(name: str) -> str | None:
    r = requests.get(f"{BASE_URL}/areas", headers=headers(), params={
        "page": 1, "limit": 50, "sort": "name", "q": name, "hiringType": "internal",
    })
    r.raise_for_status()
    for row in r.json().get("rows", []):
        if row["name"].strip().upper() == name.strip().upper():
            return row["_id"]
    return None


def create_area(name: str) -> str:
    r = requests.post(f"{BASE_URL}/areas", headers=headers(), json={
        "name": name, "hiringType": ["internal"],
    })
    r.raise_for_status()
    return r.json()["_id"]


def find_role(name: str) -> str | None:
    r = requests.get(f"{BASE_URL}/roles", headers=headers(), params={
        "page": 1, "limit": 50, "sort": "name", "q": name, "hiringType": "internal",
    })
    r.raise_for_status()
    for row in r.json().get("rows", []):
        if row["name"].strip().upper() == name.strip().upper():
            return row["_id"]
    return None


def create_role(name: str) -> str:
    r = requests.post(f"{BASE_URL}/roles", headers=headers(), json={
        "name": name, "hiringType": ["internal"],
    })
    r.raise_for_status()
    return r.json()["_id"]


# ─── Processamento ────────────────────────────────────────────────────────────

def process_areas(areas, progress, ids):
    done    = set(progress["areas_done"])
    failed  = set(progress["areas_failed"])
    pending = [(code, name) for code, name in areas if name not in done and name not in failed]

    if not pending:
        print("Areas: nada pendente.")
        return

    print(f"\nAreas: {len(done)} já feitas | {len(pending)} pendentes | {len(failed)} com erro")

    for i, (code, name) in enumerate(pending, 1):
        label = f"[{i}/{len(pending)}] '{name}'"
        try:
            oid = find_area(name)
            if oid:
                status = "JÁ EXISTE"
            else:
                oid = create_area(name)
                status = "CRIADA   "
            ids["areas"][name] = oid
            save_ids(ids)
            progress["areas_done"].append(name)
            save_progress(progress)
            print(f"  {status}  {label} → {oid}")
        except Exception as e:
            progress["areas_failed"].append(name)
            save_progress(progress)
            print(f"  ERR       {label} — {e}")

        time.sleep(DELAY)


def process_roles(roles, progress, ids):
    done    = set(progress["roles_done"])
    failed  = set(progress["roles_failed"])
    pending = [(code, name) for code, name in roles if name not in done and name not in failed]

    if not pending:
        print("Funções: nada pendente.")
        return

    print(f"\nFunções: {len(done)} já feitas | {len(pending)} pendentes | {len(failed)} com erro")

    for i, (code, name) in enumerate(pending, 1):
        label = f"[{i}/{len(pending)}] '{name}'"
        try:
            oid = find_role(name)
            if oid:
                status = "JÁ EXISTE"
            else:
                oid = create_role(name)
                status = "CRIADA   "
            ids["roles"][name] = oid
            save_ids(ids)
            progress["roles_done"].append(name)
            save_progress(progress)
            print(f"  {status}  {label} → {oid}")
        except Exception as e:
            progress["roles_failed"].append(name)
            save_progress(progress)
            print(f"  ERR       {label} — {e}")

        time.sleep(DELAY)


# ─── Main ─────────────────────────────────────────────────────────────────────

def load_csv(path: str) -> list[tuple]:
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        return [(r[0], r[1]) for r in reader if len(r) >= 2]


def main():
    args = sys.argv[1:]

    if "--reset" in args:
        Path(PROGRESS_FILE).unlink(missing_ok=True)
        print("Progresso apagado.")
        return

    if not TOKEN:
        print("ERRO: GEDOC_TOKEN não definido no .env")
        sys.exit(1)

    run_areas = "--areas" in args or not args
    run_roles = "--roles" in args or not args

    areas = load_csv(AREAS_CSV) if run_areas else []
    roles = load_csv(ROLES_CSV) if run_roles else []

    progress = load_progress()
    ids      = load_ids()

    if run_areas:
        process_areas(areas, progress, ids)

    if run_roles:
        process_roles(roles, progress, ids)

    p = load_progress()
    print(f"\n{'='*50}")
    print(f"Areas  : {len(p['areas_done'])} feitas | {len(p['areas_failed'])} erros")
    print(f"Funções: {len(p['roles_done'])} feitas | {len(p['roles_failed'])} erros")
    print(f"ObjectIds salvos em: {IDS_FILE}")


if __name__ == "__main__":
    main()
