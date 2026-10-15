# Integração de Funcionários — RM para GEDOC

**Documento informativo para o cliente**
Versão 1.0 — Junho de 2026

---

## O que é essa integração?

A integração é um processo automático que mantém os funcionários cadastrados no seu sistema de RH (**RM**) sempre sincronizados com a plataforma de gestão de documentos (**GEDOC**). Toda vez que ela é executada, ela verifica o que mudou no RH e replica essas mudanças no GEDOC — sem que ninguém precise fazer isso manualmente.

**Resumindo:** é como um assistente invisível que, todos os dias, compara os dois sistemas e garante que eles estejam sempre com as mesmas informações.

---

## Por que ela existe?

Sem essa integração, cada nova contratação, demissão ou mudança de cargo precisaria ser feita duas vezes: uma no RH e outra no GEDOC. Além do retrabalho, existe o risco de esquecimento — um funcionário demitido continuar com acesso ativo, ou um novo colaborador não conseguir utilizar o sistema no primeiro dia.

A integração elimina esse problema: **o RH é atualizado normalmente, e o GEDOC acompanha automaticamente**.

---

## O que ela faz, na prática?

A cada execução, o sistema percorre a lista de funcionários do RH e toma as seguintes ações no GEDOC:

### Funcionário novo (admitido)
Quando um funcionário é cadastrado no RH, a integração o **cria automaticamente no GEDOC** com todos os dados relevantes: nome, CPF, cargo, setor, unidade e data de admissão.

### Funcionário demitido
Quando um funcionário tem a saída registrada no RH, a integração **bloqueia o acesso dele no GEDOC**. Ele não é apagado — fica registrado para fins de histórico — mas perde a capacidade de operar na plataforma.

### Funcionário recontratado
Se um colaborador que havia sido desligado retorna à empresa, a integração **reativa automaticamente o acesso dele no GEDOC** e atualiza os dados conforme o novo cadastro no RH.

### Dados alterados
Quando há uma mudança de cargo, setor ou qualquer outro dado relevante, a integração **atualiza o GEDOC** para refletir a nova situação.

### Nenhuma mudança
Quando um funcionário não teve alteração alguma desde a última execução, a integração **não faz nada** — ela não toca nos dados que já estão corretos.

---

## Como ela distingue os tipos de funcionário?

A integração reconhece dois perfis:

- **Funcionários próprios (internos):** colaboradores diretos da empresa, identificados pelo CNPJ cadastrado no RH. São tratados com um fluxo específico no GEDOC.
- **Funcionários terceirizados (externos):** colaboradores de empresas parceiras ou prestadoras. Seguem um fluxo diferente, adequado ao seu vínculo contratual.

Cada perfil é processado da forma correta, sem risco de confusão entre eles.

---

## Como ela garante que não vai quebrar nada?

### Verificação antes de agir
Antes de criar, atualizar ou bloquear qualquer funcionário, o sistema verifica se aquele funcionário já existe no GEDOC e qual é a situação atual dele. Ele nunca age "às cegas" — sempre compara o que tem com o que deveria ter.

### Detecção precisa de mudanças
O sistema não reescreve os dados do funcionário a cada execução. Ele compara campo por campo e só atualiza o que realmente mudou. Isso evita sobrescrever informações corretas e reduz ao mínimo as chamadas ao GEDOC.

### Tratamento de diferenças de formato
Os dois sistemas podem guardar a mesma informação de formas ligeiramente diferentes — um nome em letras maiúsculas em um lado e em letras minúsculas no outro, por exemplo, ou um telefone com e sem formatação. A integração normaliza essas diferenças antes de comparar, para não gerar atualizações desnecessárias por conta de algo irrelevante.

### Verificação de campos disponíveis por tipo de funcionário
Alguns dados de funcionários próprios não são retornados pelo GEDOC nas consultas — são dados que o sistema não expõe nessa categoria. A integração sabe disso e não compara esses campos para esse perfil, evitando falsos alertas de mudança.

### Registro de tudo
Cada ação realizada — criação, atualização, bloqueio, ou mesmo a decisão de não fazer nada — é registrada em um log detalhado. Se algo der errado, o erro é capturado, registrado e o processamento continua para os demais funcionários. Um problema com um registro não compromete o resto.

### Relatório ao final de cada execução
Ao terminar, a integração gera automaticamente um **relatório em Excel** com o resumo completo: quantos funcionários foram criados, atualizados, bloqueados, ignorados e se houve algum erro. Erros são destacados em vermelho para facilitar a identificação.

---

## Com que frequência ela roda?

A integração pode ser configurada de duas formas:

- **Modo diário (recomendado):** busca apenas as alterações das últimas 24 horas. Rápido e eficiente.
- **Modo completo:** processa todos os funcionários do RH do zero. Usado para garantir consistência total após manutenções ou na primeira execução.

---

## O que acontece se um dado não puder ser processado?

Se um funcionário vier do RH sem alguma informação essencial — como cargo ou setor não mapeados no GEDOC — ele é **ignorado naquela execução** e um aviso é registrado no relatório. Ele não é criado de forma incompleta. Na próxima execução, se o dado já estiver disponível, ele será processado normalmente.

---

## Resumo das garantias

| Situação | O que a integração faz |
|---|---|
| Funcionário novo no RH | Cria no GEDOC automaticamente |
| Funcionário demitido no RH | Bloqueia no GEDOC automaticamente |
| Funcionário recontratado no RH | Reativa no GEDOC automaticamente |
| Dados alterados no RH | Atualiza no GEDOC somente o que mudou |
| Nada mudou | Não faz nada — não toca nos dados |
| Dado incompleto ou não mapeado | Ignora o funcionário e registra aviso |
| Erro na comunicação com o GEDOC | Registra o erro, continua com os demais |
| Ao final de cada execução | Gera relatório Excel com resumo completo |
