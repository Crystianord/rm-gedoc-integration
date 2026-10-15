"""
Gera config.py com ROLE_MAP e AREA_MAP preenchidos a partir dos
CSVs do RM (PFUNCAO, PSECAO) e dos JSONs de entidades do GEDOC.

Uso: py build_depara.py
"""
import csv
import json
import unicodedata
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def normalize(s: str) -> str:
    """Remove acentos, uppercase, strip — para comparação."""
    s = s.upper().strip()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ─── Carrega dados base ───────────────────────────────────────────────────────

with open("PFUNCAO_202606081018.csv", encoding="utf-8-sig") as f:
    pfuncao = {
        r["CODIGO"].strip().strip('"'): r["NOME"].strip()
        for r in csv.DictReader(f)
        if r.get("NOME", "").strip()
    }

with open("PSECAO_202606081022.csv", encoding="utf-8-sig") as f:
    psecao = {
        r["CODIGO"].strip().strip('"'): r["DESCRICAO"].strip()
        for r in csv.DictReader(f)
        if r.get("DESCRICAO", "").strip()
    }

with open("test.roles.json", encoding="utf-8") as f:
    _roles_raw = json.load(f)
    gedoc_roles_by_name = {r["name"]: r["_id"]["$oid"] for r in _roles_raw}
    gedoc_roles_all = [(r["name"], r["_id"]["$oid"]) for r in _roles_raw]

with open("test.areas.json", encoding="utf-8") as f:
    _areas_raw = json.load(f)
    gedoc_areas_by_name = {a["name"]: a["_id"]["$oid"] for a in _areas_raw}
    gedoc_areas_all = [(a["name"], a["_id"]["$oid"]) for a in _areas_raw]

with open("test.sites.json", encoding="utf-8") as f:
    gedoc_sites = {s["name"]: s["_id"]["$oid"] for s in json.load(f)}


def resolve_gedoc_role(gedoc_name: str):
    oid = gedoc_roles_by_name.get(gedoc_name)
    if oid:
        return oid
    norm = normalize(gedoc_name)
    for name, oid in gedoc_roles_by_name.items():
        if normalize(name) == norm:
            return oid
    return None


def resolve_gedoc_area(gedoc_name: str):
    oid = gedoc_areas_by_name.get(gedoc_name)
    if oid:
        return oid
    norm = normalize(gedoc_name)
    for name, oid in gedoc_areas_by_name.items():
        if normalize(name) == norm:
            return oid
    return None


# ─── De-para ROLES confirmados ────────────────────────────────────────────────
# (CODFUNCAO_RM, nome_GEDOC)
# Critério: exact match ou fuzzy com equivalência semântica confirmada
ROLE_DEPARA = [
    # --- EXACT ---
    ("3006",  "ALMOXARIFE DE SUPRIMENTOS"),
    ("4067",  "ASSISTENTE DE MANUTENCAO PREDIAL"),
    ("1120",  "AUXILIAR DE ALMOXARIFADO"),
    ("2133",  "AUXILIAR DE ELETRICISTA"),
    ("3131",  "AUXILIAR DE MANUTENCAO PREDIAL"),
    ("2140",  "AUXILIAR DE MECANICO"),
    ("3143",  "AUXILIAR DE SAUDE OCUPACIONAL"),
    ("1145",  "AUXILIAR DE SERVICOS GERAIS"),
    ("2151",  "BORRACHEIRO"),
    ("3170",  "CONTROLADOR(A) DE COMBUSTIVEL E ODOMETRO"),
    ("1363",  "COORDENADOR(A) DE ENGENHARIA PREDIAL"),
    ("2193",  "ELETRICISTA"),
    ("1197",  "ELETRICISTA MONTADOR"),
    ("I199",  "ENCARREGADO DE ALMOXARIFADO"),
    ("1207",  "ENCARREGADO DE GARAGEM"),
    ("I124",  "ENCARREGADO DE LIMPEZA"),
    ("1213",  "ENFERMEIRO(A) DO TRABALHO"),
    ("4151",  "ENGENHEIRO DE SEGURANCA DO TRABALHO"),
    ("2222",  "FRENTISTA"),
    ("4162",  "GERENTE"),
    ("2237",  "INSPETOR"),
    ("1253",  "JOVEM APRENDIZ (MECANICA)"),
    ("1254",  "JOVEM APRENDIZ (SAUDE OCUPACIONAL)"),
    ("4188",  "LANTERNEIRO"),
    ("3256",  "LANTERNEIRO DE REPARACAO"),
    ("1370",  "LANTERNEIRO NOTURNO"),
    ("2252",  "LAVADOR DE PECAS"),
    ("3263",  "LUBRIFICADOR"),
    ("1265",  "MANOBRISTA"),
    ("3267",  "MANTENEDOR PREDIAL"),
    ("2256",  "MECANICO"),
    ("1360",  "MECANICO ALINHADOR"),
    ("1369",  "MECANICO DE AR CONDICIONADO"),
    ("3269",  "MECANICO DE VALA"),
    ("2258",  "MECANICO MONTADOR"),
    ("2260",  "MECANICO SOCORRISTA"),
    ("1283",  "MONTADOR DE MOTOR"),
    ("1287",  "MOTORISTA"),
    ("I153",  "MOTORISTA CARRETEIRO"),
    ("1277",  "MÉDICO DO TRABALHO"),
    ("4218",  "PINTOR"),
    ("1305",  "PINTOR(A)"),
    ("1306",  "POLIDOR"),
    ("3307",  "PORTEIRO"),
    ("I274",  "SERVENTE DE LIMPEZA"),
    ("2310",  "TECNICO AMBIENTAL"),
    ("1356",  "TECNICO EM ELETRONICA EMBARCADA"),
    ("2312",  "TECNICO EM ENFERMAGEM DO TRABALHO"),
    ("3333",  "TECNICO EM SEGURANCA OCUPACIONAL"),
    ("2313",  "TECNICO EM SEGURANÇA DO TRABALHO"),
    ("2316",  "VISTORIADOR"),
    ("3337",  "VISTORIADOR(A) DE OFICINA"),
    # --- FUZZY VERIFICADO (mesma função, variação de gênero/abreviação) ---
    ("3157",  "BORRACHEIRO ALINHADOR"),      # RM: BORRACHEIRO ALINHADOR(A)
    ("1213",  "ENFERMEIRA DO TRABALHO"),     # RM: ENFERMEIRO(A) DO TRABALHO
    ("2312",  "TÉC DE ENFERMAGEM DO TRABALHO"),  # RM: TECNICO EM ENFERMAGEM DO TRABALHO
    ("I128",  "VIGILANTE"),                  # RM: VIGILANTE I
    ("4189",  "LAVADOR(A)"),                 # RM: LAVADOR
]

# ─── De-para AREAS confirmados ────────────────────────────────────────────────
# (CODSECAO_RM, nome_GEDOC)
AREA_DEPARA = [
    ("01.01.4.08.04.002", "ABASTECIMENTO"),
    ("01.01.4.07.01.005", "ALMOXARIFADO"),
    ("01.01.2.02.00.001", "ASSESSORIA ESPECIAL"),
    ("01.01.4.08.01.003", "ELETRICA"),
    ("01.01.4.07.02.001", "GESTAO AMBIENTAL"),
    ("01.01.4.08",        "GESTAO DA PERFORMANCE VEICULAR"),
    ("01.01.4.07.02.004", "GESTAO DE SEGURANCA OCUPACIONAL"),
    ("01.01.4.07",        "GESTÃO DE FACILITIES"),
    ("01.01.4.08.03.002", "LANTERNAGEM"),
    ("01.01.4.07.03.001", "MANUTENCAO E CONSERVACAO PREDIAL"),
    ("01.01.4.08.01.002", "MECANICA"),
    ("01.01.4.08.03.003", "PINTURA"),
    ("01.01.4.08.02",     "RODAGEM"),
    ("01.01.4.08.04.003", "VISTORIA"),
    # Parciais comentadas — descomentar após confirmar com o negócio:
    # ("01.01.4.07.01.002", "LIMPEZA PREDIAL"),    # RM: SEGURANCA E LIMPEZA PREDIAL
    # ("01.01.4.07.02.003", "SAÚDE OCUPACIONAL"),  # RM: GESTAO DE SAUDE OCUPACIONAL
]


# ─── Montar dicts finais (sem duplicatas) ─────────────────────────────────────

role_map = {}
for rm_code, gedoc_name in ROLE_DEPARA:
    if rm_code in role_map:
        continue  # primeiro ganha
    oid = resolve_gedoc_role(gedoc_name)
    if oid:
        role_map[rm_code] = oid

area_map = {}
for rm_code, gedoc_name in AREA_DEPARA:
    if rm_code in area_map:
        continue
    oid = resolve_gedoc_area(gedoc_name)
    if oid:
        area_map[rm_code] = oid

# ─── Relatório de cobertura ───────────────────────────────────────────────────

mapped_gedoc_roles = set()
for rm_code, gedoc_name in ROLE_DEPARA:
    if rm_code in role_map:
        mapped_gedoc_roles.add(normalize(gedoc_name))

mapped_gedoc_areas = set()
for rm_code, gedoc_name in AREA_DEPARA:
    if rm_code in area_map:
        mapped_gedoc_areas.add(normalize(gedoc_name))

unmatched_roles = [
    (name, oid) for name, oid in gedoc_roles_all
    if normalize(name) not in mapped_gedoc_roles
]
unmatched_areas = [
    (name, oid) for name, oid in gedoc_areas_all
    if normalize(name) not in mapped_gedoc_areas
]

print(f"ROLE_MAP: {len(role_map)} entradas (de 97 roles GEDOC)")
print(f"AREA_MAP: {len(area_map)} entradas (de 55 areas GEDOC)")
print()
print(f"Roles GEDOC sem match RM ({len(unmatched_roles)}):")
for name, _ in unmatched_roles:
    print(f"  - {name}")
print()
print(f"Areas GEDOC sem match RM ({len(unmatched_areas)}):")
for name, _ in unmatched_areas:
    print(f"  - {name}")

# ─── Grava review CSV ─────────────────────────────────────────────────────────

AREA_PARTIAL = {
    "LIMPEZA PREDIAL": ("01.01.4.07.01.002", "SEGURANCA E LIMPEZA PREDIAL", "REVISAR - match parcial"),
    "SAUDE OCUPACIONAL": ("01.01.4.07.02.003", "GESTAO DE SAUDE OCUPACIONAL", "REVISAR - match parcial"),
}

with open("depara_review.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "TIPO", "NOME_GEDOC", "GEDOC_OBJECT_ID",
        "CODIGO_RM_SUGERIDO", "NOME_RM_SUGERIDO", "OBSERVACAO",
    ])
    for name, oid in unmatched_roles:
        w.writerow(["ROLE", name, oid, "", "", "PREENCHER CODFUNCAO RM se existir"])

    for name, oid in unmatched_areas:
        key = normalize(name)
        partial = AREA_PARTIAL.get(name) or AREA_PARTIAL.get(name.upper())
        if partial:
            w.writerow(["AREA", name, oid, partial[0], partial[1], partial[2]])
        else:
            w.writerow(["AREA", name, oid, "", "",
                        "SEM CORRESPONDENCIA NO PSECAO — provavelmente area de terceiros"])

print()
print("depara_review.csv salvo.")

# ─── Grava config.py ─────────────────────────────────────────────────────────

import os
env_content = open(".env", encoding="utf-8").read() if os.path.exists(".env") else ""

config_lines = [
    'import os',
    'from dotenv import load_dotenv',
    '',
    'load_dotenv()',
    '',
    '# RM API (TOTVS consultaSQLServer)',
    'RM_QUERY_URL       = os.getenv("RM_QUERY_URL", "")',
    'RM_QUERY_URL_DELTA = os.getenv("RM_QUERY_URL_DELTA", "")',
    'RM_USERNAME        = os.getenv("RM_USERNAME", "")',
    'RM_PASSWORD        = os.getenv("RM_PASSWORD", "")',
    '',
    '# GEDOC API',
    'GEDOC_URL_SEARCH = os.getenv("GEDOC_URL_SEARCH", "")',
    'GEDOC_URL_CREATE = os.getenv("GEDOC_URL_CREATE", "")',
    'GEDOC_URL_UPDATE = os.getenv("GEDOC_URL_UPDATE", "")',
    'GEDOC_URL_BLOCK  = os.getenv("GEDOC_URL_BLOCK",  "")',
    'GEDOC_API_KEY    = os.getenv("GEDOC_API_KEY", "")',
    'GEDOC_TENANT     = os.getenv("GEDOC_TENANT", "")',
    '',
    '# Mapeamento de ObjectIds do GEDOC',
    'COMPANY_MAP = {',
    '    # CNPJ do RM -> ObjectId da company no GEDOC',
    '    "25.260.525/0001-97": "PREENCHER_OBJECTID",',
    '}',
    '',
]

# ROLE_MAP
config_lines.append('ROLE_MAP = {')
config_lines.append('    # CODFUNCAO do RM -> ObjectId do role no GEDOC')
config_lines.append(f'    # {len(role_map)} entradas geradas automaticamente por build_depara.py')
for rm_code in sorted(role_map):
    oid = role_map[rm_code]
    rm_name = pfuncao.get(rm_code, "?")
    gedoc_name_found = None
    for gname, goid in gedoc_roles_by_name.items():
        if goid == oid:
            gedoc_name_found = gname
            break
    config_lines.append(f'    "{rm_code}": "{oid}",  # {rm_name} -> {gedoc_name_found}')
config_lines.append('}')
config_lines.append('')

# AREA_MAP
config_lines.append('AREA_MAP = {')
config_lines.append('    # CODSECAO do RM -> ObjectId da area no GEDOC')
config_lines.append(f'    # {len(area_map)} entradas geradas automaticamente por build_depara.py')
for rm_code in sorted(area_map):
    oid = area_map[rm_code]
    rm_name = psecao.get(rm_code, "?")
    gedoc_name_found = None
    for aname, aoid in gedoc_areas_by_name.items():
        if aoid == oid:
            gedoc_name_found = aname
            break
    config_lines.append(f'    "{rm_code}": "{oid}",  # {rm_name} -> {gedoc_name_found}')
config_lines.append('}')
config_lines.append('')

# SITE_MAP
config_lines.append('SITE_MAP = {')
config_lines.append('    # FILIAL do RM -> ObjectId do site no GEDOC')
config_lines.append('    # Preencher manualmente: veja test.sites.json para os ObjectIds disponíveis')
for site_name, site_oid in gedoc_sites.items():
    config_lines.append(f'    # "{site_name}": "{site_oid}",  # descomentar e ajustar FILIAL do RM')
config_lines.append('    "PREENCHER_FILIAL": "PREENCHER_OBJECTID",')
config_lines.append('}')
config_lines.append('')

config_lines.append('DELTA_DAYS = int(os.getenv("DELTA_DAYS", "1"))')

with open("config.py", "w", encoding="utf-8") as f:
    f.write("\n".join(config_lines))

print("config.py salvo.")
