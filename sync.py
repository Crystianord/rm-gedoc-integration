import re
import logging
from rm_client import RMClient
from gedoc_client import GEDOCClient
from gedoc_cache import cache
from mapper import map_rm_to_gedoc, map_rm_to_gedoc_internal, is_internal_employee, is_terminated, is_on_leave, is_future_hire
from report import SyncReport

logger = logging.getLogger(__name__)


def _normalize_date(value) -> str | None:
    """Deixa só YYYY-MM-DD para comparação."""
    if not value:
        return None
    return str(value)[:10]


def _norm_str(v) -> str:
    """Normaliza string para comparação case-insensitive (RM envia ALLCAPS)."""
    return (v or "").strip().upper()


def _norm_digits(v) -> str:
    """Remove não-dígitos — normaliza telefone e chapa independente de formatação."""
    return re.sub(r'\D', '', str(v or ""))


def _ids(obj_list: list) -> set:
    """Extrai _id de uma lista — suporta objetos {_id, name} e strings diretas."""
    result = set()
    for item in obj_list:
        if isinstance(item, dict) and item.get("_id"):
            result.add(str(item["_id"]))
        elif isinstance(item, str):
            result.add(item)
    return result


def get_changes(current: dict, new_payload: dict, is_internal: bool = False) -> list[str]:
    """Retorna lista descritiva dos campos que mudaram (vazia = sem alteração).

    Para funcionários internos, o GET /employees/internal não retorna campos pessoais
    (gender, phone, email, birthDate, identity) — comparar esses campos sempre geraria
    false positives. Eles são excluídos da comparação quando is_internal=True.
    """
    diffs = []

    def chk(field, old, new):
        if old != new:
            diffs.append(f"{field}: '{old}' → '{new}'")

    # name: comparar sem diferença de case (RM = ALLCAPS, GEDOC pode ser Title Case)
    chk("name", _norm_str(current.get("name")), _norm_str(new_payload.get("name")))

    # Campos pessoais e datas: ignorar para internos (GEDOC não os retorna no GET /employees/internal)
    if not is_internal:
        chk("gender",   current.get("gender"),                 new_payload.get("gender"))
        chk("phone",    _norm_digits(current.get("phone")),    _norm_digits(new_payload.get("phone")))
        chk("email",    current.get("email") or "",            new_payload.get("email") or "")
        chk("identity", _norm_digits(current.get("identity")), _norm_digits(new_payload.get("identity")))

        chk("birthDate",
            _normalize_date(current.get("birthDate")),
            _normalize_date(new_payload.get("birthDate")))

        current_date = current.get("admissionDate") or current.get("hiringDate")
        new_date     = new_payload.get("admissionDate") or new_payload.get("hiringDate")
        date_label   = "hiringDate" if "hiringDate" in new_payload else "admissionDate"
        chk(date_label, _normalize_date(current_date), _normalize_date(new_date))

    old_sites = _ids(current.get("sites", []))
    new_sites = set(new_payload.get("sites", []))
    if old_sites != new_sites:
        diffs.append(f"sites: {old_sites} → {new_sites}")

    old_roles = _ids(current.get("roles", []))
    new_roles = set(new_payload.get("roles", []))
    if old_roles != new_roles:
        diffs.append(f"roles: {old_roles} → {new_roles}")

    old_areas = _ids(current.get("areas", []))
    new_areas = set(new_payload.get("areas", []))
    if old_areas != new_areas:
        diffs.append(f"areas: {old_areas} → {new_areas}")

    if "blocked" in new_payload and current.get("blocked", False) != new_payload["blocked"]:
        diffs.append(f"blocked: {current.get('blocked', False)} → {new_payload['blocked']}")

    return diffs


def run_sync(full_load: bool = False) -> SyncReport:
    rm    = RMClient()
    gedoc = GEDOCClient()
    rep   = SyncReport()

    cache.preload()

    employees = rm.get_all_employees() if full_load else rm.get_delta_employees()

    if not employees:
        logger.info("Nenhum funcionário retornado pelo RM.")
        return rep

    # Deduplica por CPF: o RM pode retornar múltiplos períodos do mesmo funcionário
    # (recontratações, ou histórico completo vindo de uma consulta sem RN=1).
    # Regra: se existir QUALQUER registro ativo (CODSITUACAO A/F) para o CPF, ele
    # sempre vence um registro demitido (D), independente da data de admissão —
    # do contrário, um registro D antigo com DTADMISSAO igual/maior que o ativo
    # fazia a pessoa ser desligada e reativada aleatoriamente a cada execução.
    # Entre registros do mesmo status, desempata pela maior DTADMISSAO.
    _seen: dict[str, dict] = {}
    for emp in employees:
        cpf = emp.get("CPF", "").strip()
        if not cpf:
            continue
        existing = _seen.get(cpf)
        if not existing:
            _seen[cpf] = emp
            continue

        emp_ativo = not is_terminated(emp)
        existing_ativo = not is_terminated(existing)

        if emp_ativo and not existing_ativo:
            _seen[cpf] = emp
        elif existing_ativo and not emp_ativo:
            continue
        elif str(emp.get("DTADMISSAO") or "") > str(existing.get("DTADMISSAO") or ""):
            _seen[cpf] = emp
    employees_sem_cpf = [e for e in employees if not e.get("CPF", "").strip()]
    employees = employees_sem_cpf + list(_seen.values())

    logger.info(f"{len(employees)} funcionário(s) para processar (após deduplicação por CPF).")

    stats = {"criados": 0, "atualizados": 0, "reativados": 0, "sem_alteracao": 0, "desligados": 0, "afastados": 0, "ignorados": 0, "erros": 0}

    for emp in employees:
        cpf  = emp.get("CPF", "").strip()
        nome = emp.get("NOME", "").strip()
        interno   = is_internal_employee(emp)
        tipo      = "Interno" if interno else "Externo"
        terminated  = is_terminated(emp)
        on_leave    = is_on_leave(emp)
        future_hire = is_future_hire(emp)
        situacao    = "Demitido" if terminated else ("Afastado" if on_leave else ("Admissão futura" if future_hire else "Ativo"))

        if not cpf:
            logger.warning(f"Funcionário sem CPF ignorado: {nome}")
            rep.record("", nome, tipo, situacao, "Ignorado", "Sem CPF")
            stats["ignorados"] += 1
            continue

        # ── Admissão futura (CODSITUACAO='Z') ───────────────────────────────────
        # Ainda não trabalha — não existe no GEDOC e não deve ser criado/tocado
        # até que a situação vire 'A'. Ignora sem sequer consultar o cache.
        if future_hire:
            rep.record(cpf, nome, tipo, situacao, "Ignorado", "Admissão futura — aguardando virar ativo")
            stats["ignorados"] += 1
            continue

        admission_date = emp.get("DTADMISSAO")
        gedoc_emp      = cache.find_employee(cpf, admission_date)

        # Para internos: GEDOC não retorna hiringDate no GET, então o cache indexa
        # sem data ({cpf}_). Tenta essa chave antes de cair no fallback por CPF.
        if not gedoc_emp and interno:
            gedoc_emp = cache.find_employee(cpf, None)

        # Fallback: busca só por CPF (externo com data divergente ou interno não achado acima)
        if not gedoc_emp:
            fallback = cache.find_employee_by_cpf(cpf)
            if fallback:
                gedoc_is_active = not (fallback.get("terminated") or fallback.get("blocked"))
                if terminated and gedoc_is_active:
                    # RM está demitindo um período antigo, mas o GEDOC encontrado por CPF
                    # está ativo — é outro contrato (re-admissão). Não tocar.
                    logger.warning(
                        f"[{cpf}] Fallback CPF encontrou registro ATIVO no GEDOC, mas RM indica "
                        f"demissão (data RM: {str(admission_date)[:10]}) — período anterior; "
                        f"registro atual do GEDOC não será desligado."
                    )
                    fallback = None  # trata como não encontrado
                else:
                    logger.warning(
                        f"[{cpf}] Encontrado no GEDOC por CPF mas data divergente "
                        f"(RM: {str(admission_date)[:10]} | "
                        f"GEDOC: {str(fallback.get('admissionDate') or fallback.get('hiringDate') or '')[:10]}) "
                        f"— usando registro existente."
                    )
            gedoc_emp = fallback

        # ── Demitido ──────────────────────────────────────────────────────────
        if terminated:
            # Só opera sobre funcionários internos encontrados no cache.
            # Não usa fallback via API para evitar falsos positivos em registros externos.
            if gedoc_emp and gedoc_emp.get("_hiring_type") == "external":
                logger.warning(f"[{cpf}] Demitido mas encontrado como externo no GEDOC — ignorado (só internos).")
                rep.record(cpf, nome, tipo, situacao, "Ignorado", "Demitido — registro externo no GEDOC, sem ação")
                stats["ignorados"] += 1
            elif gedoc_emp:
                ok = gedoc.terminate_internal_employee(gedoc_emp["_id"], cpf)
                if ok:
                    rep.record(cpf, nome, tipo, situacao, "Desligado")
                    stats["desligados"] += 1
                elif "terminated employee" in (gedoc.last_error or ""):
                    logger.info(f"[{cpf}] Já desligado no GEDOC — ignorado.")
                    rep.record(cpf, nome, tipo, situacao, "Ignorado", "Já desligado no GEDOC")
                    stats["ignorados"] += 1
                else:
                    rep.record(cpf, nome, tipo, situacao, "Erro", gedoc.last_error)
                    stats["erros"] += 1
            else:
                logger.info(f"[{cpf}] Demitido mas não existe no GEDOC — ignorado.")
                rep.record(cpf, nome, tipo, situacao, "Ignorado", "Demitido — não existe no GEDOC")
                stats["ignorados"] += 1
            continue

        # ── Afastado (CODSITUACAO em LEAVE_CODES — mapper.py) ───────────────────
        # Bloqueia no GEDOC com blockedReason='removal' — não desliga, é reversível
        # quando a pessoa voltar com situação ativa (ver desbloqueio abaixo).
        if on_leave:
            if gedoc_emp and gedoc_emp.get("_hiring_type") == "external":
                logger.warning(f"[{cpf}] Afastado mas encontrado como externo no GEDOC — ignorado (só internos).")
                rep.record(cpf, nome, tipo, situacao, "Ignorado", "Afastado — registro externo no GEDOC, sem ação")
                stats["ignorados"] += 1
            elif gedoc_emp:
                if gedoc_emp.get("blocked") or gedoc_emp.get("terminated"):
                    logger.info(f"[{cpf}] Já bloqueado/desligado no GEDOC — ignorado.")
                    rep.record(cpf, nome, tipo, situacao, "Ignorado", "Já bloqueado/desligado no GEDOC")
                    stats["ignorados"] += 1
                else:
                    ok = gedoc.block_leave_internal_employee(gedoc_emp["_id"], cpf)
                    if ok:
                        rep.record(cpf, nome, tipo, situacao, "Afastado")
                        stats["afastados"] += 1
                    else:
                        rep.record(cpf, nome, tipo, situacao, "Erro", gedoc.last_error)
                        stats["erros"] += 1
            else:
                logger.info(f"[{cpf}] Afastado mas não existe no GEDOC — ignorado.")
                rep.record(cpf, nome, tipo, situacao, "Ignorado", "Afastado — não existe no GEDOC")
                stats["ignorados"] += 1
            continue

        # ── Desbloqueio: ativo no RM mas desligado/bloqueado no GEDOC ───────────
        # (recontratação após demissão, ou retorno de afastamento). Usa o endpoint
        # correspondente ao estado atual: terminado -> cancel-termination,
        # apenas bloqueado (ex: afastamento anterior) -> block-options (unblock).
        reativado = False
        if gedoc_emp and gedoc_emp.get("terminated"):
            ok = gedoc.cancel_termination_internal(gedoc_emp["_id"], cpf)
            if not ok:
                rep.record(cpf, nome, tipo, situacao, "Erro", gedoc.last_error)
                stats["erros"] += 1
                continue
            gedoc_emp["terminated"] = False
            gedoc_emp["blocked"] = False  # atualiza cache local para não gerar diff falso
            reativado = True
            logger.info(f"[{cpf}] Reativado (cancel-termination) no GEDOC — prosseguindo com atualização.")
        elif gedoc_emp and gedoc_emp.get("blocked"):
            ok = gedoc.unblock_internal_employee(gedoc_emp["_id"], cpf)
            if not ok:
                rep.record(cpf, nome, tipo, situacao, "Erro", gedoc.last_error)
                stats["erros"] += 1
                continue
            gedoc_emp["blocked"] = False  # atualiza cache local para não gerar diff falso
            reativado = True
            logger.info(f"[{cpf}] Desbloqueado (fim de afastamento) no GEDOC — prosseguindo com atualização.")

        # ── Monta payload ─────────────────────────────────────────────────────
        payload = map_rm_to_gedoc_internal(emp) if interno else map_rm_to_gedoc(emp)
        if not payload:
            rep.record(cpf, nome, tipo, situacao, "Ignorado", "Role/área/site não resolvido (ver log)")
            stats["ignorados"] += 1
            continue

        # ── Criação ───────────────────────────────────────────────────────────
        if not gedoc_emp:
            ok = gedoc.create_internal_employee(payload) if interno else gedoc.create_employee(payload)
            if ok:
                rep.record(cpf, nome, tipo, situacao, "Criado")
                stats["criados"] += 1
            else:
                rep.record(cpf, nome, tipo, situacao, "Erro", gedoc.last_error)
                stats["erros"] += 1
            continue

        # ── Atualização ───────────────────────────────────────────────────────
        # Usa o hiringType registrado no GEDOC (não o RM) para escolher o endpoint.
        # Se RM e GEDOC divergirem, loga aviso — significa mudança de tipo que exige
        # intervenção manual (o GEDOC não permite converter de externo→interno via PUT).
        gedoc_interno = gedoc_emp.get("_hiring_type") == "internal"
        if gedoc_interno != interno:
            logger.warning(
                f"[{cpf}] Divergência de tipo: RM diz '{'interno' if interno else 'externo'}' "
                f"mas GEDOC tem '{'interno' if gedoc_interno else 'externo'}'. "
                f"Usando tipo do GEDOC para o update."
            )

        changes = get_changes(gedoc_emp, payload, is_internal=gedoc_interno)
        if not changes:
            if reativado:
                logger.info(f"[{cpf}] Reativado sem outras alterações.")
                rep.record(cpf, nome, tipo, situacao, "Reativado")
                stats["reativados"] += 1
            else:
                logger.debug(f"[{cpf}] Sem alterações — ignorado.")
                rep.record(cpf, nome, tipo, situacao, "Ignorado", "Sem alterações")
                stats["sem_alteracao"] += 1
            continue

        change_detail = " | ".join(changes)
        logger.info(f"[{cpf}] Alterações detectadas: {change_detail}")

        ok = (
            gedoc.update_internal_employee(gedoc_emp["_id"], payload, cpf)
            if gedoc_interno else
            gedoc.update_employee(gedoc_emp["_id"], payload, cpf)
        )

        # 403 "Cannot update a terminated employee": o campo terminated não foi detectado
        # antes do update (GEDOC retorna o status de forma diferente para alguns registros).
        # Tenta cancelar a terminação e refaz o update uma vez.
        if not ok and "terminated" in (gedoc.last_error or "").lower():
            logger.warning(f"[{cpf}] Terminado no GEDOC mas ativo no RM — cancelando terminação e retentando update.")
            if gedoc.cancel_termination_internal(gedoc_emp["_id"], cpf):
                ok = (
                    gedoc.update_internal_employee(gedoc_emp["_id"], payload, cpf)
                    if gedoc_interno else
                    gedoc.update_employee(gedoc_emp["_id"], payload, cpf)
                )
                if ok:
                    reativado = True
                elif "terminated" in (gedoc.last_error or "").lower():
                    # Estado inconsistente no GEDOC: API diz "ativo" no cancel mas
                    # "terminado" no update. Requer intervenção manual no painel GEDOC.
                    logger.warning(
                        f"[{cpf}] Estado inconsistente no GEDOC (ativo para cancel, terminado para update). "
                        f"Intervenção manual necessária no painel GEDOC."
                    )
                    rep.record(cpf, nome, tipo, situacao, "Ignorado", "Estado inconsistente no GEDOC — verificar manualmente")
                    stats["ignorados"] += 1
                    continue

        if ok:
            acao = "Reativado + Atualizado" if reativado else "Atualizado"
            rep.record(cpf, nome, tipo, situacao, acao, change_detail)
            stats["reativados" if reativado else "atualizados"] += 1
        else:
            rep.record(cpf, nome, tipo, situacao, "Erro", gedoc.last_error)
            stats["erros"] += 1

    logger.info(
        f"Sync concluído — "
        f"Criados: {stats['criados']} | "
        f"Reativados: {stats['reativados']} | "
        f"Atualizados: {stats['atualizados']} | "
        f"Sem alteração: {stats['sem_alteracao']} | "
        f"Desligados: {stats['desligados']} | "
        f"Afastados: {stats['afastados']} | "
        f"Ignorados: {stats['ignorados']} | "
        f"Erros: {stats['erros']}"
    )

    return rep
