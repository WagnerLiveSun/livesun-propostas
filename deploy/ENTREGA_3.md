# Entrega 3 — trial, boas-vindas e leitura restrita

## Estado e ativação

Implementação local. NÃO aplicar/push/deploy antes de revisar dados demonstrativos,
backup e scripts. Nenhum banco de uso, local ou produção, foi atualizado nesta entrega.
Central: PostgreSQL. Propostas: MariaDB 11.8.9. Mesma política para TODAS as empresas.
Não há exceção legada em runtime. Um bypass restrito a `app.testing` preserva testes
unitários antigos de CRUD, nunca habilita operação sem Central em produção.

## Sequência de banco (DBeaver)

1. Backup completo de ambos os bancos e arquivos relevantes; conferir restauração.
2. Executar no Propostas `ENTREGA_3_DIAGNOSTICO.sql` e no Central
   `deploy/sql/postgresql/06_entrega_3_diagnostico.sql`.
3. Revisar resultados e aprovar tratamento dos demonstrativos ANTES de ativar.
4. Central, somente banco PostgreSQL na revisão 20261112_04:
   `deploy/sql/postgresql/06_entrega_3_notificacoes.sql` e depois
   `deploy/sql/postgresql/06_entrega_3_validacao.sql`.
5. Propostas, somente banco MariaDB na revisão e20261118a:
   `deploy/mariadb/ENTREGA_3_TRIAL.sql` e depois `ENTREGA_3_VALIDACAO.sql`.
6. Comparar contagens originais e revisão; conferir sem diferenças com models
   em ambiente configurado: `python -m flask --app wsgi db check`.

Executar arquivos completos, uma vez, parar no primeiro erro. PostgreSQL inclui
transação; MariaDB DDL não tem rollback integral. Sem procedimentos, nome de banco
fixo, stamp ou sistema de versão próprio. SQL atualiza somente Alembic existente.
Não executar SQL e migration da mesma revisão sobre o mesmo banco.
Alternativa após backup: `flask --app wsgi db upgrade` até a revisão específica
`20261118_01` no Central ou `f20261118a` no Propostas.

Models precisam das estruturas ANTES de servir o código novo. O hook existente
do Propostas só reconhece a revisão nova, não a aplica. Central possui preparação
de deploy própria; não presumir que aplicação automática substitui esta conferência.
Nenhum script limpa/arquiva/anonimiza nem ativa empresas ou assinaturas antigas.

## Proposta de tratamento dos dados demonstrativos

Diagnóstico real ainda não executado nesta entrega, para não acessar bancos de uso.
A proposta segura é: backup validado, inventário agregado, confirmação humana de
quais empresas são apenas demonstração e arquivamento da cópia em local restrito.
Preferir manter registros no ambiente isolado de demonstração; só anonimizar ou
remover no ambiente público mediante autorização específica e plano de referências.
Nunca escolher automaticamente uma empresa para apagar, nem zerar quotas existentes.
Todas as empresas que permanecerem ativas precisam de vínculo e autorização Central.
Propostas sem data_criacao exigem revisão antes de contabilizar trial; não inventar data.

## Variáveis

Propostas: `CENTRAL_CHECKOUT_URL` deve ser HTTPS sem credencial/fragmento. Sem URL
válida o botão fica oculto, sem destino fictício. Sem checkout, cobrança ou pagamento.
`CENTRAL_ENABLED=true` é necessário; desligado não libera nenhuma empresa.
Preservar CENTRAL_BASE_URL, token read e HMAC. Validar vínculos ANTES da ativação.

Central: `ACCESS_EMAIL_ENABLED=false` por padrão; habilitar apenas após homologar
remetente/serviço. `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME=LiveSun`.
Não copiar segredos do Propostas automaticamente nem colocá-los em Git.
Worker existente do Central processa mensagens; nenhum worker ou fila no Propostas.

## Fonte da verdade e datas

Entitlements e HMAC mantêm o contrato atual. Trial usa GET autenticado existente
`/api/v1/assinaturas/{id}`, validando assinatura, cliente, produto, versão e datas.
Cache é vinculado a empresa/assinatura/versão, por até 15 minutos e limitado ao
TTL da autorização. Datas ausentes/incompatíveis impedem escrita em TRIAL.
Sem data fictícia ou prazo calculado pelo Propostas. ATIVA segue os entitlements;
se consulta adicional falhar, início fica indisponível sem bloquear autorização válida.
Início de trial não é reiniciado no cliente: contrato atual só fornece início da
assinatura e trial_ate. Mudança de início para o mesmo ID exige revisão; extensão
do fim mantém consumo e reconcilia propostas ainda não contabilizadas do intervalo.
Concessão de novo trial no mesmo ID não zera contador automaticamente.

## Quota e bloqueios

TRIAL: 10 propostas criadas por empresa/assinatura no período confirmado. Criação
e replicação reservam contador na transação da proposta. Lock empresa -> vínculo ->
contador, UPDATE condicional criadas<10, registro por proposta e rollback conjunto.
Requisições simultâneas não ultrapassam 10. Cadastro inválido não consome quota.
Propostas já criadas no período são contabilizadas inicialmente pela data_criacao,
nunca data_emissao editável. Uso já registrado não é removido/zerado por extensão.
Envio e reenvio não consomem quota; no limite ainda podem enviar propostas existentes.

Trial vencido ou SUSPENSA/BLOQUEADA/CANCELADA/EXPIRADA: login leva a lista;
somente GET lista/detalhe/PDF. Bloqueia criar, editar, replicar, status, enviar,
imprimir HTML, dashboard, clientes, produtos, usuários, empresa/configurações.
EXCLUIDA não permite acesso comercial. Sem Central ou cache expirado: fail-closed,
inclusive para leitura. Suspensão só ganha CTA de inadimplência quando a causa foi
obtida do Central; não presume causa por status. PDF existente continua disponível.
O link de logo usado pelo PDF é embutido localmente, sem liberar cadastros.

ATIVA recebida de webhook válido/consulta autorizada remove apenas quota trial.
Pagamento ou clique no link nunca ativa localmente. Central permanece responsável.

## Interface

Boas-vindas no dashboard autorizado: empresa, PROPOSTAS, status, prazo real, uso;
três ações e ocultação persistida por usuário/empresa. Sem tour/gamificação.
Banner de proximidade apenas visual com 3 dias ou menos, sem e-mail antecipado.
Estado restrito não mostra formulários de alteração nem menus de cadastro.
No perfil visualizador, as permissões existentes continuam no servidor.

## E-mail (Central)

Somente eventos novos ASSINATURA_CRIADA (TRIAL/ATIVA), ASSINATURA_ATIVADA,
ASSINATURA_REATIVADA, produto PROPOSTAS. Nenhum backfill retroativo.
Autocadastro aguarda VINCULADA; outros vínculos aguardam webhook entregue.
Revalida estado atual antes do envio; aviso ultrapassado/revogado é cancelado.
Notificação única por evento; hash do destinatário, sem credencial/conteúdo completo
persistidos. Nome, status e datas do Central são renderizados somente ao enviar.
Não envia senha/token. URL do produto exige origem HTTPS sem credenciais.
Modelo simples, primeiros passos e suporte. Sem marketing ou campanhas.

Tentativa persistida antes da rede; ACEITA_BREVO significa aceite, não entrega.
HTTP 429 pode tentar até três vezes; recusa definitiva registra FALHA. Timeout,
5xx/resposta ambígua ou processo interrompido ficam INCERTO e não repetem cegamente.
Falha não desfaz a liberação nem falha o callback. Falhas/incertos são consultáveis
na tabela de tentativas por operação administrativa, sem expor payload no log.

## Testes e manual

Propostas: `.\.venv\Scripts\python.exe -m pytest tests -q`.
Central: mesma chamada na raiz do Central, TEST_DATABASE_URL somente descartável.
Testes usam SQLite temporário/mocks, incluindo concorrência. DDL gerado a partir
das migrations para os bancos reais; homologação de execução real é reportada à parte.
Nunca apontar fixtures ao banco de uso: elas criam/removem tabelas.

Manual em homologação: vincular empresa, liberar TRIAL no Central; receber email
mockado só após vínculo; login -> banner; criar/replicar até 10; 11ª falha;
enviar/reenviar não conta; vencer trial -> lista/detalhe/PDF apenas; SUSPENSA etc
igual; EXCLUIDA/falha com cache vencido sem acesso; ATIVA devolve operações; ocultar
boas-vindas persiste; duas empresas não compartilham contadores ou preferências.

## Rollback

Não há DROP/downgrade destrutivo: apagar contadores permitiria renovar quota e
apagar notificações permitiria e-mails repetidos. Recuar código somente em janela
planejada, mantendo tabelas/histórico. Não alterar Alembic para fingir revisão antiga.
Revisão nova pode ser recusada por hook antigo; preparar artefato de rollback
explicitamente compatível e testado antes de qualquer deploy, sem mecanismo genérico.
Backup só se restaura com autorização e avaliação de registros novos.

Escopo excluído: checkout, cobrança/cartão, upgrade/downgrade, módulos comerciais,
fila de e-mails/worker no Propostas, alterações no contrato de API/webhook/HMAC.