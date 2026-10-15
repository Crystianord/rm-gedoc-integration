# Integração RM → GEDOC — Documentação Completa

## O que esse projeto faz?

Esse sistema sincroniza automaticamente os funcionários cadastrados no **RM** (sistema de RH da empresa) com o **GEDOC** (plataforma de gestão de documentos). Toda vez que é executado, ele verifica quem entrou, saiu ou teve algum dado alterado no RM e replica essas mudanças no GEDOC.

**Em linguagem simples:** é uma ponte. O RM é a fonte da verdade (onde o RH cadastra tudo). O GEDOC precisa ter os mesmos funcionários para funcionar. Esse código é o responsável por manter os dois sincronizados.

---

## Glossário — Termos Técnicos Explicados

| Termo | O que significa na prática |
|---|---|
| **RM** | Sistema de RH da TOTVS. É de lá que vêm os dados dos funcionários. |
| **GEDOC** | Plataforma de gestão de documentos (sistemasgap.com.br). É para lá que os dados vão. |
| **CPF** | Cadastro de Pessoa Física — usado como identificador único do funcionário nos dois sistemas. |
| **CNPJ** | Cadastro Nacional de Pessoa Jurídica — identifica qual empresa o funcionário pertence. |
| **API REST** | Interface de comunicação entre sistemas pela internet. É como o código "conversa" com o GEDOC e com o RM — enviando e recebendo dados no formato JSON. |
| **JSON** | Formato de dados estruturados. Parece um dicionário: `{"nome": "João", "cpf": "12345678901"}`. |
| **ObjectId** | Identificador único do MongoDB (banco de dados do GEDOC). É um código hexadecimal de 24 caracteres, ex: `68efe0da480e0940fc5f58ed`. Cada funcionário, role, área e site tem um. |
| **Payload** | O "pacote de dados" enviado para a API. É o JSON montado com as informações do funcionário. |
| **Bearer Token** | Um código de acesso temporário (como uma senha de sessão) usado para autenticar chamadas à API do GEDOC. Expira em ~15 dias e precisa ser renovado no `.env`. |
| **API Key** | Chave de acesso permanente (não expira), usada para funcionários externos no GEDOC. |
| **Tenant** | Identificador do cliente dentro da plataforma GEDOC. É como um "código da empresa" que vai em todo request. |
| **De-para** | Tabela de mapeamento: "código X no RM = código Y no GEDOC". Como traduzir o CODFUNCAO do RM para o ObjectId do GEDOC. |
| **Delta** | Modo de sync que busca apenas funcionários alterados nos últimos N dias (padrão: 1 dia). Mais rápido. |
| **Full load** | Modo de sync que busca e processa TODOS os funcionários do RM. Mais lento, mas garante consistência total. |
| **Cache** | Cópia dos dados do GEDOC carregada na memória RAM no início de cada execução. Evita fazer uma chamada API individual para cada funcionário durante o sync. |
| **Role** | Função/cargo do funcionário no GEDOC. Ex: "MOTORISTA", "MECANICO". Tem um ObjectId único. |
| **Area** | Seção/departamento do funcionário no GEDOC. Ex: "MECANICA", "ALMOXARIFADO". Tem um ObjectId único. |
| **Site** | Unidade/filial física onde o funcionário trabalha. No GEDOC, cada filial tem um ObjectId. |
| **Company** | A empresa empregadora registrada no GEDOC. Funcionários externos têm uma company; internos não. |
| **Blocked** | Campo booleano no GEDOC que indica se o funcionário está bloqueado (demitido/inativo). `true` = bloqueado. |
| **Singleton** | Padrão de código onde existe apenas uma instância de um objeto em toda a execução. Ex: o `cache` e o `depara` são singletons — carregados uma vez e compartilhados por todos os módulos. |
| **HTTP Status** | Código de resposta de uma API. `200 OK` = sucesso. `404` = não encontrado. `409` = conflito (já existe). `422` = dados inválidos. |
| **Endpoint** | URL específica de uma API para uma operação. Ex: `POST /employees` para criar, `PUT /employees/{id}` para atualizar. |

---

## Dois Tipos de Funcionário

Essa é a regra de negócio mais importante do sistema. Todo funcionário é classificado como **interno** ou **externo** com base no CNPJ da sua seção no RM:

### Funcionário Interno (HP Mobilidade)
- CNPJ configurado em `INTERNAL_CNPJS` no `config.py`
- É funcionário da própria empresa (CLT direto)
- Vai para o endpoint `/employees/internal` no GEDOC
- Autenticado com **Bearer Token** (`internal_headers`)
- O GEDOC **não retorna** campos pessoais (gênero, telefone, e-mail, CPF, data de nascimento, data de admissão) quando você busca um interno pelo GET — esses campos ficam `None` no cache
- No payload de criação/atualização, usa o campo `hiringDate` (data de contratação)

### Funcionário Externo
- Qualquer CNPJ que não está em `INTERNAL_CNPJS`
- É funcionário de empresa terceirizada/prestadora
- Vai para o endpoint `/employees` no GEDOC
- Autenticado com **API Key** (`headers`)
- O GEDOC retorna todos os campos no GET
- No payload, usa o campo `admissionDate` (data de admissão)

---

## Regras de Negócio

### 1. Identificação do funcionário
- A chave primária é **CPF + data de admissão** (ex: `01234567890_2015-03-01`).
- Se não encontrar pela data, o sistema tenta só pelo CPF como fallback e gera um aviso no log.
- Se o CPF não existir no RM, o funcionário é ignorado.

### 2. Funcionário Demitido (CODSITUACAO = "D")
- Se existe no GEDOC → **bloqueia** no GEDOC (campo `blocked = true`).
- Se não existe no GEDOC → ignora (não vale criar alguém que já foi demitido).
- O bloqueio usa o endpoint dedicado `PUT /employees/{id}/block-options` com o payload:
  ```json
  {"blocked": true, "blockStartDate": null, "blockedReason": "others", "blockComment": "Desligado por integração RM"}
  ```
- Se o funcionário já está bloqueado, a API retorna `409` — tratado como sucesso (idempotente).

### 3. Funcionário Recontratado (Ativo no RM, Bloqueado no GEDOC)
- Antes de atualizar, o sistema **desbloqueia** o funcionário no GEDOC.
- Usa o mesmo endpoint `PUT /employees/{id}/block-options` com `blocked: false`.
- Depois do desbloqueio, prossegue normalmente com a atualização dos dados.

### 4. Funcionário Novo (Ativo no RM, Não existe no GEDOC)
- **Cria** no GEDOC com os dados do RM.
- Internos: `POST /employees/internal`
- Externos: `POST /employees`

### 5. Funcionário Existente sem Alteração
- Se nenhum campo mudou → **ignora**, não chama a API de atualização.
- Ação registrada como "Ignorado — Sem alterações".

### 6. Funcionário Existente com Alteração
- **Atualiza** no GEDOC com os novos dados.
- O log registra quais campos mudaram e qual era o valor antigo/novo.

### 7. Resolução de Role, Area e Site
- O código RM tem seu próprio código de função (CODFUNCAO) e seção (CODSECAO).
- Esses códigos precisam ser traduzidos para os ObjectIds do GEDOC.
- Se o código não está no `depara.json`, o sistema tenta encontrar pelo nome no GEDOC e cria se não existir.
- Se role, area ou site não forem resolvidos → **funcionário ignorado** (com aviso no log).

### 8. Campos comparados na detecção de mudanças
| Campo | Externo | Interno | Normalização aplicada |
|---|---|---|---|
| name | ✅ | ✅ | Remove espaços + maiúsculas |
| gender | ✅ | ❌ | — |
| phone | ✅ | ❌ | Apenas dígitos |
| email | ✅ | ❌ | — |
| identity (chapa) | ✅ | ❌ | Apenas dígitos |
| birthDate | ✅ | ❌ | Apenas `YYYY-MM-DD` |
| admissionDate / hiringDate | ✅ | ❌ | Apenas `YYYY-MM-DD` |
| sites | ✅ | ✅ | Compara conjuntos de ObjectIds |
| roles | ✅ | ✅ | Compara conjuntos de ObjectIds |
| areas | ✅ | ✅ | Compara conjuntos de ObjectIds |

> **Por que internos têm menos campos comparados?** O endpoint GET `/employees/internal` do GEDOC não retorna campos pessoais — eles ficam como `None` no cache. Se comparássemos, sempre apareceria como "mudança" mesmo sem nada ter mudado.

---

## Arquitetura — Hierarquia dos Arquivos

```
run.py                      ← Ponto de entrada. Você executa esse.
│
└── sync.py                 ← Motor principal. Orquestra tudo.
    ├── rm_client.py        ← Busca funcionários no RM
    ├── gedoc_cache.py      ← Carrega dados do GEDOC na memória
    ├── mapper.py           ← Transforma dados do RM → formato GEDOC
    │   ├── depara.py       ← Lê/salva o de-para de roles e areas
    │   └── gedoc_params.py ← Cria roles/areas no GEDOC se não existirem
    ├── gedoc_client.py     ← Envia dados para o GEDOC (criar/atualizar/bloquear)
    └── report.py           ← Gera o relatório Excel ao final

config.py                   ← Configurações estáticas (mapas, CNPJs, etc.)
```

### Scripts utilitários (execução manual, não fazem parte do sync diário):
```
build_depara.py             ← Gera config.py a partir de CSVs do RM + JSONs do GEDOC
gedoc_create_entities.py    ← Cria roles e areas em lote no GEDOC via API
```

---

## Descrição de Cada Arquivo

### `run.py` — Ponto de Entrada
O arquivo que você executa. Configura o log (console + arquivo `integration.log`), aceita o argumento `--full` para carga completa, chama o sync e salva o relatório Excel.

```bash
python run.py           # Sync delta (últimas 24h)
python run.py --full    # Sync completo (todos os funcionários)
```

---

### `sync.py` — Motor Principal
O coração do sistema. Contém toda a lógica de decisão:

1. Carrega o cache do GEDOC na memória
2. Busca funcionários no RM (delta ou full)
3. Para cada funcionário:
   - Classifica como interno ou externo
   - Verifica se foi demitido → bloqueia
   - Verifica se estava bloqueado → desbloqueia
   - Monta o payload com os dados do RM
   - Busca no cache do GEDOC
   - Compara campos → cria, atualiza ou ignora

**Funções auxiliares de normalização:**
- `_normalize_date(value)` → Corta qualquer data para `YYYY-MM-DD` antes de comparar
- `_norm_str(v)` → Remove espaços e converte para maiúsculas (resolve diferença de case entre RM e GEDOC)
- `_norm_digits(v)` → Remove tudo que não é número (resolve diferença de formatação de telefone/chapa)
- `_ids(obj_list)` → Extrai os `_id` de uma lista de objetos do GEDOC para comparar como conjunto
- `get_changes(current, new_payload, is_internal)` → Compara o funcionário do cache com o payload novo e retorna lista de campos diferentes

---

### `rm_client.py` — Cliente do RM
Faz as chamadas HTTP para a API do RM (TOTVS). Autenticação por usuário e senha (Basic Auth).

- `get_all_employees()` → Busca todos os funcionários (full load)
- `get_delta_employees()` → Busca funcionários alterados desde `hoje - DELTA_DAYS` (padrão: 1 dia)

---

### `gedoc_cache.py` — Cache do GEDOC
Carrega todos os dados necessários do GEDOC **uma única vez** no início do sync e mantém em memória. Evita milhares de chamadas individuais à API durante o processamento.

**O que é carregado:**
- Todos os funcionários externos (`/employees`) — indexados por `cpf_data`
- Todos os funcionários internos (`/employees/internal`) — também indexados por `cpf_data`
- Todos os roles disponíveis — indexados por `nome.upper()`
- Todas as areas disponíveis — indexadas por `nome.upper()`

**Chave de busca dos funcionários:**
```
{cpf_sem_pontuação}_{YYYY-MM-DD}
ex: "01234567890_2015-03-01"
```
Se a data não bater, o sistema cai no fallback de busca só por CPF (`find_employee_by_cpf`).

---

### `mapper.py` — Transformador de Dados
Converte o formato do RM para o formato que o GEDOC espera. É aqui que os campos do RM (em maiúsculas, ex: `NOME`, `CPF`, `DTADMISSAO`) viram um JSON com os nomes que a API do GEDOC aceita.

**Funções principais:**
- `is_internal_employee(emp)` → Checa o CNPJ da seção para classificar o tipo
- `is_terminated(emp)` → Checa se `CODSITUACAO == "D"`
- `map_rm_to_gedoc(emp)` → Monta payload para funcionário externo (inclui `company`, `admissionDate`)
- `map_rm_to_gedoc_internal(emp)` → Monta payload para funcionário interno (sem `company`, usa `hiringDate`)
- `_resolve_role(codfuncao, nomefuncao)` → Traduz código de função RM → ObjectId GEDOC
- `_resolve_area(codsecao, descrsecao)` → Traduz código de seção RM → ObjectId GEDOC

**Mapeamentos fixos em `config.py`:**
- `M` → `"male"`, `F` → `"female"` (campo gênero)
- CNPJ → ObjectId da company (externas)
- FILIAL → ObjectId do site
- CODFUNCAO → ObjectId do role (55 funções mapeadas)
- CODSECAO → ObjectId da area (14 seções mapeadas)

---

### `gedoc_client.py` — Cliente do GEDOC
Responsável por todas as operações de escrita no GEDOC. Cada método faz uma chamada HTTP e retorna `True` (sucesso) ou `False` (falha), salvando o erro em `self.last_error` para o relatório.

**Dois conjuntos de headers:**
- `self.headers` → Para funcionários externos (`x-api-key` + `tenant`)
- `self.internal_headers` → Para funcionários internos (`authorization: bearer TOKEN` + `access` + `tenant`)

**Métodos disponíveis:**

| Método | Endpoint | Uso |
|---|---|---|
| `create_employee` | `POST /employees` | Cria funcionário externo |
| `update_employee` | `PUT /employees/{id}` | Atualiza funcionário externo |
| `block_employee` | `PUT /employees/{id}/block-options` | Bloqueia externo (demissão) |
| `unblock_employee` | `PUT /employees/{id}/block-options` | Desbloqueia externo (recontratação) |
| `create_internal_employee` | `POST /employees/internal` | Cria funcionário interno |
| `update_internal_employee` | `PUT /employees/internal/{id}` | Atualiza funcionário interno |
| `block_internal_employee` | `PUT /employees/{id}/block-options` | Bloqueia interno (demissão) |
| `unblock_internal_employee` | `PUT /employees/{id}/block-options` | Desbloqueia interno (recontratação) |

> **Importante:** O bloqueio de internos e externos usa o mesmo endpoint `/block-options`, mas a URL base é sempre `/employees/{id}` (não `/employees/internal/{id}`). Isso foi descoberto inspecionando o Network tab do navegador.

---

### `depara.py` — De-para Persistente
Gerencia o arquivo `depara.json` que guarda a tradução de códigos do RM para ObjectIds do GEDOC. Cresce automaticamente: quando aparece um código RM novo, o sistema busca no GEDOC pelo nome, cria se necessário, e salva no `depara.json` para não precisar repetir na próxima execução.

**Estrutura do `depara.json`:**
```json
{
  "roles": {
    "1287": "6900ebb125f65ec8981818c4",
    "2256": "6973d839d876289e0e8c5bd6"
  },
  "areas": {
    "01.01.4.08.01.002": "69d3e2056872f64859061fad"
  }
}
```

---

### `gedoc_params.py` — Criação de Parâmetros no GEDOC
Complementa o `depara.py`. Quando um código RM não está no de-para e o nome do role/area é conhecido, esse módulo:
1. Busca no cache (já carregado em memória)
2. Se não achar no cache, chama a API do GEDOC para buscar
3. Se não existir no GEDOC, **cria** o role/area via `POST /roles` ou `POST /areas`
4. Salva o novo ObjectId no cache e no `depara.json`

---

### `config.py` — Configurações Estáticas
Todos os mapeamentos fixos do sistema. **Gerado automaticamente pelo `build_depara.py`**, mas pode ser editado manualmente.

**O que contém:**
- URLs do RM e GEDOC (lidas do `.env`)
- `COMPANY_MAP`: CNPJ → ObjectId da company no GEDOC
- `ROLE_MAP`: CODFUNCAO do RM → ObjectId do role no GEDOC (55 funções)
- `AREA_MAP`: CODSECAO do RM → ObjectId da area no GEDOC (14 seções)
- `SITE_MAP`: Código de filial do RM → ObjectId do site no GEDOC
- `INTERNAL_CNPJS`: Conjunto de CNPJs que identificam funcionários próprios (internos)
- `DELTA_DAYS`: Quantos dias atrás buscar no delta (padrão: 1, configurável via `.env`)

---

### `report.py` — Relatório Excel
Gera um arquivo `.xlsx` ao final de cada sync com três abas:

- **Resumo**: Total de criados, atualizados, bloqueados, ignorados e erros. Destaca em vermelho se houver erros.
- **⚠ Erros** *(só aparece se houver erros)*: Tabela com todos os funcionários que falharam, com o motivo.
- **Processados**: Tabela com todos os funcionários processados e a ação tomada.

**Cores usadas:**
- Verde → Criado
- Azul → Atualizado
- Laranja → Bloqueado
- Cinza → Ignorado
- Vermelho → Erro

---

### `build_depara.py` — Script de Setup (execução manual)
Utilitário de setup inicial, não faz parte do sync diário. Gera o `config.py` automaticamente cruzando:
- CSVs exportados do RM (`PFUNCAO_*.csv`, `PSECAO_*.csv`)
- JSONs exportados do GEDOC (`test.roles.json`, `test.areas.json`, `test.sites.json`)

Também gera `depara_review.csv` com roles/areas do GEDOC que não tiveram correspondência no RM para revisão manual.

```bash
python build_depara.py
```

---

### `gedoc_create_entities.py` — Script de Setup (execução manual)
Cria em lote no GEDOC todos os roles e areas listados nos CSVs `gedoc_areas_to_create.csv` e `gedoc_roles_to_create.csv`. Verifica se já existe antes de criar. Salva progresso em `gedoc_create_progress.json` para poder retomar se interrompido.

```bash
python gedoc_create_entities.py           # Cria tudo
python gedoc_create_entities.py --areas   # Só areas
python gedoc_create_entities.py --roles   # Só funções
python gedoc_create_entities.py --reset   # Apaga progresso e recomeça
```

---

## Fluxo Completo de uma Execução

```
python run.py
│
├── Configura log (console + integration.log)
├── Chama run_sync(full_load=False)
│   │
│   ├── cache.preload()
│   │   ├── GET /employees          → carrega externos na memória
│   │   ├── GET /employees/internal → carrega internos na memória
│   │   ├── GET /roles              → carrega roles na memória
│   │   └── GET /areas              → carrega areas na memória
│   │
│   ├── rm.get_delta_employees()    → busca alterações no RM (últimas 24h)
│   │
│   └── Para cada funcionário:
│       ├── É interno ou externo? (CNPJ da seção)
│       ├── Está demitido? (CODSITUACAO = "D")
│       │   └── SIM → block_employee / block_internal_employee → próximo
│       ├── Está no cache do GEDOC?
│       │   ├── NÃO → create_employee / create_internal_employee → próximo
│       │   └── SIM:
│       │       ├── Está bloqueado no GEDOC mas ativo no RM?
│       │       │   └── SIM → unblock_employee / unblock_internal_employee
│       │       ├── Monta payload com map_rm_to_gedoc[_internal]()
│       │       ├── get_changes() → algum campo mudou?
│       │       │   ├── NÃO → registra "Ignorado — Sem alterações" → próximo
│       │       │   └── SIM → update_employee / update_internal_employee
│       │       └── registra resultado no relatório
│
└── report.save() → salva sync_report_YYYYMMDD_HHMMSS.xlsx
```

---

## Configuração — Arquivo `.env`

O arquivo `.env` deve existir na raiz do projeto com as seguintes variáveis:

```env
# RM (TOTVS)
RM_QUERY_URL=https://rm.empresa.com.br/api/...
RM_QUERY_URL_DELTA=https://rm.empresa.com.br/api/...   # opcional
RM_USERNAME=usuario
RM_PASSWORD=senha

# GEDOC
GEDOC_URL_EMPLOYEES=https://gec-api.sistemasgap.com.br/employees
GEDOC_URL_ROLES=https://gec-api.sistemasgap.com.br/roles
GEDOC_URL_AREAS=https://gec-api.sistemasgap.com.br/areas
GEDOC_API_KEY=chave-de-api-para-funcionarios-externos
GEDOC_TENANT=codigo-do-tenant
GEDOC_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...   # Bearer Token (expira ~15 dias)
GEDOC_ACCESS=codigo-de-acesso

# Configurações
DELTA_DAYS=1   # quantos dias atrás buscar no modo delta
```

> **Atenção:** O `GEDOC_TOKEN` expira em aproximadamente 15 dias. Se aparecer erro `401 Unauthorized`, é necessário renovar o token no sistema GEDOC e atualizar o `.env`.

---

## Arquivos Gerados em Execução

| Arquivo | O que é |
|---|---|
| `integration.log` | Log de texto de todas as execuções (acumulativo) |
| `sync_report_YYYYMMDD_HHMMSS.xlsx` | Relatório Excel de cada execução |
| `depara.json` | De-para persistente de roles e areas (cresce automaticamente) |

---

## Como Adicionar uma Nova Filial (Site)

1. No GEDOC, encontre o ObjectId do novo site (via interface ou API)
2. No `config.py`, adicione em `SITE_MAP`:
   ```python
   SITE_MAP = {
       "1": "68efe0fbd6e073e37e51985f",  # GARAGEM CENTRAL
       "2": "ObjectId_da_nova_filial",   # NOVA FILIAL
   }
   ```
3. O número `"2"` é o código da `FILIAL` no RM (campo `CODFILIAL`)

## Como Adicionar uma Nova Empresa Terceirizada (Company)

1. No GEDOC, encontre o ObjectId da nova company
2. No `config.py`, adicione em `COMPANY_MAP`:
   ```python
   COMPANY_MAP = {
       "00.000.000/0001-00": "68efe0da480e0940fc5f58ed",
       "XX.XXX.XXX/0001-XX": "ObjectId_da_nova_company",
   }
   ```

## Como Adicionar uma Nova Empresa Como Interna

Em `config.py`, adicione o CNPJ em `INTERNAL_CNPJS`:
```python
INTERNAL_CNPJS = {
    "00.000.000/0001-00",
    "XX.XXX.XXX/0001-XX",   # nova empresa interna
}
```
