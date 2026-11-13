# Integração comercial com LiveSun Central

## Vínculo pela interface do Central (recomendado)

1. Publicar os arquivos da integração no **Propostas** após backup do banco. A configuração `deploy/gunicorn.render.conf.py` aplica a migration `c20261112` antes de iniciar os workers, somente se a revisão atual for `b8215bc35a91`; revisão inesperada ou estrutura parcial interrompe a inicialização para revisão, sem apagar dados. Não requer mudar o Comercial.
2. Inicialmente manter `CENTRAL_ENABLED=false`, configurar `CENTRAL_WEBHOOK_SECRET` com o mesmo segredo HMAC do produto PROPOSTAS no Central. Preparação não liga o guard comercial nem altera RBAC.
3. No Central, configurar `url_producao=https://propostas.livesun.com.br`, worker ativo e o segredo HMAC correspondente. Menu **Empresas do Propostas** consulta as empresas via HTTPS/HMAC, sem conexão direta ao banco do Propostas.
4. Ação **Cadastrar cliente e vincular** carrega os dados atuais do produto. Na tela seguinte o operador confirma cliente novo ou existente (mesmo CPF/CNPJ), plano e status inicial. Dados incompletos devem ser corrigidos no Propostas antes de importar; empresa inativa ou já vinculada não pode ser reassociada.
5. O Central cria cliente/assinatura na transação de aprovação, sem habilitar Asaas/cobrança automaticamente. O worker entrega o vínculo, e a tela mostra **Habilitado e vinculado** apenas após confirmação do Propostas. Timeout mantém pendência para retry, sem duplicar cliente/assinatura. Documento precisa continuar igual no momento da confirmação.
6. Conferir todos os vínculos antes de configurar `CENTRAL_ENABLED=true`, `CENTRAL_BASE_URL=https://livesun-central.onrender.com` e token somente leitura de PROPOSTAS em `CENTRAL_API_TOKEN`. Ativar antes dessa preparação bloqueará empresas sem autorização. CENTRAL_ENABLED=false não atende webhooks comerciais, apenas os endpoints assinados de descoberta/vínculo.

Endpoints exclusivos de preparação, protegidos por HMAC com janela de 300 segundos mesmo com guard desligado:

- GET `/central/empresas?apos=0`: página de até 50 empresas, `proximo` indica cursor. Assinar **path + query string exata**, sem origem.
- GET `/central/empresas/{empresa_id}`: dados atualizados para preparar cadastro, assinar path.
- POST `/central/cadastros/vincular`: corpo bruto assinado, IDs da empresa/cliente/assinatura/solicitação, evento determinístico `cad_...`, documento e entitlements válidos. Mesmo vínculo é idempotente; vínculo divergente retorna 409 e não é substituído. Criação é auditada no Propostas.

As empresas locais preexistentes não são alteradas automaticamente. Deploy/migration/Environment de produção precisam ser aplicados separadamente; preparação local não significa que o produto publicado já oferece estes endpoints. Nenhum segredo deve ser versionado.

### Publicação desta versão

- No Render, mantenha o comando padrão do Dockerfile ou use `gunicorn --config deploy/gunicorn.render.conf.py wsgi:app`. Um comando sobrescrito sem esse arquivo de configuração não executa o hook de migração.
- O hook do master Gunicorn obtém lock de migração no MySQL/PostgreSQL, cria apenas as duas tabelas de integração e valida colunas/PK/FK/unicidade. Um snapshot **somente do schema**, sem registros, é salvo em `migration-snapshots`, ao lado do diretório de uploads. Isso não substitui backup completo de dados no provedor. Migrations MySQL não são transacionais: falha parcial exige revisão, sem stamp ou drop automático.
- Log de sucesso: `central_schema_ready` com `revision=c20261112`. Execuções seguintes validam e não recriam tabelas.
- Configure `CENTRAL_ENABLED=false`, `CENTRAL_BASE_URL=https://livesun-central.onrender.com` e `CENTRAL_WEBHOOK_SECRET` no Environment do Propostas. O segredo deve coincidir com o que está criptografado no produto PROPOSTAS do Central. O arquivo privado `.env.central.render`, se preparado na estação, é ignorado pelo Git/Docker e pode ser importado no painel; nunca enviá-lo por chat.
- Sem segredo, a aplicação continua atendendo normalmente com guard desligado, mas os endpoints de integração retornam 503. Sem assinatura válida, retornam 401; 404 significa que a rota ainda não está publicada. Nenhum vínculo é criado só por publicar.

## Teste dos dois serviços na mesma máquina

Em `D:\App_LiveSun\LiveSun_Propostas\.env`, use `CENTRAL_BASE_URL=http://127.0.0.1:5001` e `CENTRAL_ALLOW_LOCAL_HTTP=true`, com `FLASK_ENV=development`. No Central local, configure `WEBHOOK_ALLOW_LOCAL_HTTP=true`, permita `127.0.0.1` em `WEBHOOK_ALLOWED_HOSTS` e use `http://127.0.0.1:5000/webhooks/assinatura` no produto PROPOSTAS. Reinicie os dois serviços e o worker após editar o ambiente. Os opt-ins permitem somente HTTP loopback em desenvolvimento; produção exige HTTPS. JWT, HMAC, vínculo e status continuam obrigatórios. Nunca ative fail-open para contornar erro de comunicação. Sem webhook entregue, o estado muda quando expira o cache (900 segundos por padrão).

Não modifica perfis, menus ou permissões funcionais. Somente valida acesso comercial por empresa.

1. Backup do banco e código; aplicar `flask --app wsgi db upgrade` na raiz `D:\App_LiveSun\LiveSun_Propostas` com ambiente correto.
2. Criar cliente e assinatura no Central.
3. Para cada empresa local: `flask --app wsgi central-vincular EMPRESA_ID CLIENTE_ID_CENTRAL`. Não presuma IDs iguais. O vínculo é único e não pode ser alterado silenciosamente.
4. Emitir JWT `read` no Central e configurar variáveis do arquivo `deploy/.env.central.example` no ambiente do Propostas.
5. Usar o mesmo segredo HMAC do produto cadastrado no Central; mínimo 32 caracteres aleatórios.
6. Habilitar `CENTRAL_ENABLED=true` somente após migration/vínculos/configuração. Sem vínculo o acesso é negado; sem token ou HMAC a aplicação recusa inicializar com a integração habilitada.
7. Testar login, suspensão de sessão existente, bloqueio, reativação e queda do Central.

Variáveis: CENTRAL_BASE_URL (HTTPS), CENTRAL_API_TOKEN, CENTRAL_WEBHOOK_SECRET, CENTRAL_CACHE_TTL_SECONDS (1–900), CENTRAL_FAILSAFE_MINUTES (0–60), CENTRAL_ALLOW_FAIL_OPEN_NON_SENSITIVE (false por padrão).

Receptor: POST `/webhooks/assinatura`. Valida HMAC-SHA256 sobre `timestamp + '.' + corpo bruto`, assinatura `sha256=<hex>`, headers X-LiveSun-Event/Signature/Timestamp, janela 300 segundos e evento_id único. Snapshot completo `entitlements` é obrigatório. Atualiza cache e registro de evento atomicamente. Eventos obsoletos não substituem estado novo.

Reconciliação: GET `/central/estado/{cliente_id}` com HMAC calculado sobre `timestamp + '.' + path`. Só retorna estado local; não consulta o Central.

Cache usa tabelas novas no banco do Propostas e funciona entre processos/workers. Login consulta após autenticar a senha e antes de abrir sessão. Guard global verifica todas as requisições autenticadas exceto static/logout, health check e endpoints assinados. Sessão bloqueada não opera. Rotas já em execução não são interrompidas.

Sensíveis falham fechadas quando cache expira. Contingência com cache expirado só é permitida se explicitamente configurada **e** a chamada usar `sensitive=False`; nenhum endpoint operacional foi liberado assim. Nunca libera estado bloqueado. Não há cache global por usuário nem identificação de tenant por cabeçalho controlado pelo usuário.

O decorator `require_active_subscription` pode ser usado em novas rotas autenticadas; o guard global já cobre as rotas existentes. Limites são obtidos e expostos pelo cliente, mas enforcement de quotas de criação é responsabilidade futura do produto e não foi alterado nesta etapa.

Testes: `.venv\Scripts\python.exe -m unittest discover -s tests -p test_central.py`.

## Base recuperada do Git em 12/11/2026

Os arquivos rastreados foram restaurados de `origin/main`, commit `fcea0abca8757bb93590e5bb60a3f011219117c1` (30/10/2026), confirmado por fetch e HEAD remoto. A integração foi reaplicada sobre essa base: somente hooks na factory/login, novos módulos/migration e isolamento de configuração nos testes. Funcionalidades do Git de PDF, persistência de logo, health check, CSS versionado e envios foram preservadas. Alterações locais antigas que regrediam essas funcionalidades não foram reaplicadas.

Backup completo anterior em `D:\App_LiveSun\LiveSun_CentralControle\backups\Propostas-antes-atualizacao-20261112-183945`. Arquivos de ambiente, uploads e banco local foram preservados. Esse backup local não comprova backup atual do banco de produção.