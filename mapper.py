import re
from datetime import datetime
from config import COMPANY_MAP, SITE_MAP, INTERNAL_CNPJS
from depara import depara
from gedoc_params import gedoc_params
import logging

logger = logging.getLogger(__name__)


def parse_date(value: str) -> str | None:
    """Converte data do RM (com timezone) para UTC no formato esperado pelo GEDOC."""
    if not value:
        return None
    try:
        from datetime import timezone
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        return None


def normalize_cpf(cpf: str) -> str:
    return re.sub(r"[.\-]", "", cpf.strip())


def map_gender(sexo: str) -> str | None:
    return {"M": "male", "F": "female"}.get(sexo)


def _resolve_role(codfuncao: str, nomefuncao: str) -> str | None:
    """
    1. Consulta depara.json pelo CODFUNCAO
    2. Se não existe: busca no GEDOC pelo nome; cria se necessário
    3. Salva o novo mapeamento no depara.json
    ATENÇÃO: a query RM deve retornar o campo NOMEFUNCAO (nome da função).
    """
    oid = depara.get_role(codfuncao)
    if oid:
        return oid
    if not nomefuncao:
        logger.warning(f"CODFUNCAO '{codfuncao}' sem mapeamento e sem nome na query RM — ignorando")
        return None
    oid = gedoc_params.find_or_create_role(nomefuncao)
    if oid:
        depara.set_role(codfuncao, oid)
    return oid


def _resolve_area(codsecao: str, descrsecao: str) -> str | None:
    """
    1. Consulta depara.json pelo CODSECAO
    2. Se não existe: busca no GEDOC pelo nome; cria se necessário
    3. Salva o novo mapeamento no depara.json
    ATENÇÃO: a query RM deve retornar o campo DESCRSECAO (descrição da seção).
    """
    oid = depara.get_area(codsecao)
    if oid:
        return oid
    if not descrsecao:
        logger.warning(f"CODSECAO '{codsecao}' sem mapeamento e sem nome na query RM — ignorando")
        return None
    oid = gedoc_params.find_or_create_area(descrsecao)
    if oid:
        depara.set_area(codsecao, oid)
    return oid


def is_internal_employee(employee: dict) -> bool:
    """Retorna True se o funcionário é da HP MOBILIDADE (funcionário próprio)."""
    cnpj = employee.get("CNPJSECAO", "").strip()
    return cnpj in INTERNAL_CNPJS


def map_rm_to_gedoc_internal(employee: dict) -> dict | None:
    """Monta payload para POST /employees/internal (sem company, usa hiringDate)."""
    cpf = normalize_cpf(employee.get("CPF", ""))
    nome = employee.get("NOME", "").strip()
    birth_date = parse_date(employee.get("DTNASCIMENTO"))
    hiring_date = parse_date(employee.get("DTADMISSAO"))

    codsecao   = employee.get("CODSECAO", "").strip()
    descrsecao = employee.get("DESCRSECAO", "").strip()
    area_id    = _resolve_area(codsecao, descrsecao)

    codfuncao  = str(employee.get("CODFUNCAO", "")).strip()
    nomefuncao = employee.get("NOMEFUNCAO", "").strip()
    role_id    = _resolve_role(codfuncao, nomefuncao)

    filial  = str(employee.get("FILIAL", "")).strip()
    site_id = SITE_MAP.get(filial)

    missing = []
    if not area_id:
        missing.append(f"area (CODSECAO: {codsecao})")
    if not role_id:
        missing.append(f"role (CODFUNCAO: {codfuncao})")
    if not site_id:
        missing.append(f"site (FILIAL: {filial})")

    if missing:
        logger.warning(f"[{cpf}] Não resolvido: {', '.join(missing)} — funcionário ignorado")
        return None

    return {
        "name": nome,
        "cpf": cpf,
        "foreigner": False,
        "birthDate": birth_date,
        "hiringDate": hiring_date,
        "gender": map_gender(employee.get("SEXO", "")),
        "phone": employee.get("TELRESIDENCIAL", "").strip() or "",
        "identity": employee.get("CHAPA", "").strip() or "",
        "email": employee.get("EMAILCORPORATIVO", "").strip() or "",
        "sites": [site_id],
        "roles": [role_id],
        "areas": [area_id],
        "blocked": False,
        "blockedReason": "",
        "blockStartDate": None,
        "blockComment": "",
    }


def map_rm_to_gedoc(employee: dict) -> dict | None:
    cpf = normalize_cpf(employee.get("CPF", ""))
    nome = employee.get("NOME", "").strip()
    birth_date = parse_date(employee.get("DTNASCIMENTO"))
    admission_date = parse_date(employee.get("DTADMISSAO"))

    cnpj = employee.get("CNPJSECAO", "").strip()
    company_id = COMPANY_MAP.get(cnpj)

    codsecao   = employee.get("CODSECAO", "").strip()
    descrsecao = employee.get("DESCRSECAO", "").strip()  # nome da área — deve vir da query RM
    area_id    = _resolve_area(codsecao, descrsecao)

    codfuncao  = str(employee.get("CODFUNCAO", "")).strip()
    nomefuncao = employee.get("NOMEFUNCAO", "").strip()  # nome da função — deve vir da query RM
    role_id    = _resolve_role(codfuncao, nomefuncao)

    filial  = str(employee.get("FILIAL", "")).strip()
    site_id = SITE_MAP.get(filial)

    missing = []
    if not company_id:
        missing.append(f"company (CNPJ: {cnpj})")
    if not area_id:
        missing.append(f"area (CODSECAO: {codsecao})")
    if not role_id:
        missing.append(f"role (CODFUNCAO: {codfuncao})")
    if not site_id:
        missing.append(f"site (FILIAL: {filial})")

    if missing:
        logger.warning(f"[{cpf}] Não resolvido: {', '.join(missing)} — funcionário ignorado")
        return None

    email  = employee.get("EMAILCORPORATIVO", "").strip() or None
    phone  = employee.get("TELRESIDENCIAL", "").strip() or None
    gender = map_gender(employee.get("SEXO", ""))

    payload = {
        "name": nome,
        "cpf": cpf,
        "foreigner": False,
        "birthDate": birth_date,
        "admissionDate": admission_date,
        "gender": gender,
        "phone": phone,
        "identity": employee.get("CHAPA", "").strip() or None,
        "email": email,
        "sites": [site_id],
        "roles": [role_id],
        "areas": [area_id],
        "contracts": [],
        "company": company_id,
        "blocked": False,
        "blockedReason": "",
        "blockStartDate": None,
        "blockComment": "",
        "programmaticAccess": {
            "active": False,
            "allowedUntil": None,
            "reason": "",
            "usersResponsible": [],
        },
    }

    optional_nullable = {"birthDate", "admissionDate", "gender", "phone", "identity", "email"}
    return {k: v for k, v in payload.items() if k not in optional_nullable or v is not None}


# Códigos de afastamento no RM — bloqueio reversível no GEDOC (blockedReason='removal'),
# não desligamento. Pessoa volta a ativo com CODSITUACAO='A'.
LEAVE_CODES = {
    "E",  # Licença Maternidade
    "I",  # Aposentadoria por Incapacidade Permanente
    "L",  # Licença sem vencimento
    "M",  # Serviço Militar
    "O",  # Doença Ocupacional
    "P",  # Afastamento Previdência
    "R",  # Licença Remunerada
    "S",  # Mandato Sindical (ônus do Sindicato)
    "T",  # Afastamento Acidente de Trabalho
    "U",  # Outros
    "W",  # Licença Maternidade Compl. 180 dias
    "C",  # Contrato de Trabalho Suspenso
    "K",  # Cessão / Requisição
    "N",  # Mandato Sindical (ônus do Empregador)
    "G",  # Recesso Remunerado de Estágio
    "Y",  # Licença Paternidade
    "Q",  # Prisão / Cárcere
}


def is_terminated(employee: dict) -> bool:
    return employee.get("CODSITUACAO", "").upper() == "D"


def is_on_leave(employee: dict) -> bool:
    """Situação de afastamento no RM — bloqueia no GEDOC com motivo 'removal' em vez de desligar."""
    return employee.get("CODSITUACAO", "").upper() in LEAVE_CODES


def is_future_hire(employee: dict) -> bool:
    """CODSITUACAO='Z' — admissão prevista pro próximo mês, ainda não trabalha.
    Não existe no GEDOC ainda — não deve gerar nenhuma ação até virar 'A'."""
    return employee.get("CODSITUACAO", "").upper() == "Z"
