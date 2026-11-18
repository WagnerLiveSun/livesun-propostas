# Entrega 1 — cadastro público e confirmação

**Entrega 2:** o fluxo vigente após definição de senha está em
`deploy/ENTREGA_2_CADASTRO.md`. Ativa registros somente localmente, prepara solicitação
ao Central e mantém barreira de provisionamento. Requer migration `e20261118a`
aplicada manualmente antes de servir o código atualizado. Instruções históricas
abaixo sobre contas permanecerem inativas após a senha foram substituídas.

**Atualização — cadastro progressivo:** o primeiro formulário agora possui cinco
campos e aceite, sem senha. Após confirmar o e-mail, `/cadastro/completar` permite
definir senha e completar PJ com autorização temporária restrita. A conta continua
inativa. Consulte `deploy/LANDING_PROPOSTAS.md` para o fluxo vigente; os detalhes
históricos abaixo sobre campos iniciais/token devem ser lidos com esta atualização.

## Estado e limites

Cadastro desabilitado por padrão.
Para visualizar apenas a tela em desenvolvimento, configure
`PUBLIC_REGISTRATION_PREVIEW=true` e mantenha `PUBLIC_REGISTRATION_ENABLED=false`.
Somente GET `/cadastro` será permitido; POST, reenvio e confirmação ficam bloqueados.
Não requer documentos fictícios, não cria contas nem envia e-mails. A aplicação
recusa esse modo fora do ambiente development. Reinicie o servidor após editar `.env`.

Nenhuma assinatura, solicitação ao Central,
trial, quota, checkout, onboarding, fila ou worker foi adicionado.
Empresa e administrador permanecem INATIVOS após confirmação do e-mail.
`EMAIL_CONFIRMADO` não é autorização comercial. Contas existentes não são
marcadas como pendentes. Não há limpeza automática nem expurgo de contas pendentes.

## Diagnóstico obrigatório antes da ativação

Não foi consultado o banco configurado: loopback pode representar túnel remoto.
O script demonstrativo existente não comprova sua execução nem a ausência de
usuários ativos. Não habilitar o cadastro até diagnóstico e revisão humana.

1. Confirmar destino, responsável e autorização do banco (preferir cópia isolada).
2. Obter backup completo e verificar possibilidade de restauração.
3. Usar credencial somente leitura e variável temporária
   `REGISTRATION_DIAGNOSTIC_DATABASE_URL`. Nunca passar senha por argumento.
4. Na raiz `D:\App_LiveSun\LiveSun_Propostas`, executar somente com autorização:

```powershell
.\.venv\Scripts\python.exe scripts\diagnosticar_cadastro.py --banco-autorizado NOME_EXATO_AUTORIZADO
```

O script não carrega `.env`, não chama a factory nem consulta o Central. Retorna
somente contagens de ativos, ausências, duplicidades normalizadas, documentos
inválidos e possível conta demonstrativa. Usa transação read-only e rollback.
5. Apresentar resultados ao responsável. Estado `ativo` não prova uso real.
6. Classificar manualmente todos os registros de demonstração. Proposta preferida:
   arquivar uma cópia isolada com acesso restrito; anonimizar apenas dados aprovados,
   preservando relacionamentos. Limpeza/exclusão exige autorização separada.
7. Se houver credencial demonstrativa ativa, autorizar sua desativação ou troca.
8. Repetir diagnóstico. Nenhum e-mail/documento duplicado pode permanecer para B.
   Documentos ausentes legados podem permanecer NULL; nunca são inventados.

## Migrations — somente após autorização, nunca automaticamente nesta entrega

Revisões: `c20261112` → `d20261118a` → `d20261118b`.
A adiciona colunas e tabelas. B normaliza identidades e adiciona unicidade global.
Execute em janela sem escritas (parar web e comandos administrativos), após backup.
Em MySQL falha de DDL pode deixar estrutura parcial: inspecionar antes de repetir.
Não usar stamp nem apagar tabelas. Downgrade destrutivo desabilitado.

```powershell
# Ambiente de destino previamente conferido e autorizado, cadastro desabilitado.
.\.venv\Scripts\python.exe -m flask --app wsgi db upgrade d20261118a
# Somente após diagnóstico aprovado e sem usuários ativos afetados:
$env:REGISTRATION_UNIQUENESS_APPROVED='true'
try { .\.venv\Scripts\python.exe -m flask --app wsgi db upgrade d20261118b }
finally { Remove-Item Env:REGISTRATION_UNIQUENESS_APPROVED -ErrorAction SilentlyContinue }
```

B recusa ausência de autorização, e-mail vazio e duplicidades ANTES do backfill.
Não transforma registros conflitantes nem escolhe automaticamente qual preservar.
O hook antigo de startup continua migrando apenas até `c20261112`; reconhece as
duas revisões novas sem executá-las automaticamente. Com código novo é necessário
aplicar A manualmente antes de servir tráfego, mesmo com cadastro desabilitado,
pois os models contêm as colunas novas. Não publicar código sem esse planejamento.

## Configurações / Render (não executadas)

Preservar todas as configurações e credenciais Central/Brevo existentes.
Configurar remetente Brevo verificado, `PUBLIC_BASE_URL` HTTPS canônica sem query,
`TERMS_URL`, `PRIVACY_URL`, `TERMS_VERSION` e `PRIVACY_VERSION` aprovadas.
Não foram criados textos jurídicos fictícios. Ajustar:

- `EMAIL_CONFIRMATION_TTL_MINUTES=60` (1–10080).
- `CONFIRMATION_RESEND_COOLDOWN_SECONDS=120` (1–86400).
- `PUBLIC_REGISTRATION_RATE_LIMIT=5 per hour` por IP.
- `REGISTRATION_IDENTITY_RATE_LIMIT=3 per hour` por identidade HMAC.
- `CONFIRMATION_RESEND_RATE_LIMIT=5 per hour` por IP.
- `RATELIMIT_STORAGE_URI=memory://` apenas no processo/instância único aprovado.
  Reiniciar perde contadores; várias instâncias não compartilham limites. Antes
  de escalar, instalar driver e configurar backend compartilhado. Redis não é obrigatório.
- `PUBLIC_REGISTRATION_DATA_REVIEWED=true` apenas após revisão dos dados.
- `PUBLIC_REGISTRATION_ENABLED=true` apenas após B e homologação completa.

O manifesto Render existente não foi alterado e não habilita cadastro sozinho.
Gunicorn Render tem access log desativado para não gravar tokens; conferir também
logs do proxy/plataforma. Não presumir que configuração da aplicação controla logs
externos. `deploy/gunicorn.conf.py` é alternativa com dois processos e não deve ser
usada com rate limit em memória ao habilitar cadastro.
HTTPS, origem canônica e política do proxy devem ser conferidos pelo operador.

## Fluxo e privacidade

- GET/POST `/cadastro`: PF ou PJ; formulário com CSRF, honeypot, payload até 16 KiB.
- GET/POST `/cadastro/confirmar/<token>`: GET não consome; POST consome atomicamente.
- GET/POST `/cadastro/reenviar-confirmacao`: resposta genérica e cooldown persistente.
- CPF/CNPJ numéricos são verificados por dígitos verificadores (não comprovam identidade).
- E-mail de administrador é único globalmente; contato da empresa não é login e
  pode repetir. Login público usa e-mail; identificador interno aleatório evita truncá-lo.
- Apenas hash do token é persistido. Token bruto existe em memória e no e-mail.
- Aceite guarda versões e data; auditoria guarda IDs e ações, não senha/token.
- Brevo síncrono: tentativa é persistida antes da rede; sem retry automático.
  `ACEITA_BREVO` não significa entregue. `NAO_CONFIRMADA` e `INDETERMINADA`
  não garantem ausência de entrega; usuário pode solicitar novo token limitado.
  Interrupção pode deixar tentativa INICIADA; verificar antes de qualquer ação manual.
- Respostas de duplicidade/reenvio são genéricas. Tempo de resposta pode variar
  pelo envio síncrono: não há garantia de indistinguibilidade temporal absoluta.

## Testes sem rede ou banco de produção

```powershell
Set-Location 'D:\App_LiveSun\LiveSun_Propostas'
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

Testes novos usam SQLite temporário, Brevo mockado e proibição de rede. Migrations
são executadas somente nesses bancos; compilação DDL cobre MySQL/PostgreSQL mas
não substitui homologação/concorrência em instâncias reais descartáveis.

## Teste manual seguro e critérios

Em ambiente isolado com Brevo substituído por mock, nunca com chave real:
1. Habilitar após estrutura e identidades revisadas; abrir `/cadastro`.
2. Testar PF e PJ válidos, documentos inválidos, senhas divergentes e aceite ausente.
3. Conferir empresa/administrador inativos e hash de token, sem token em logs/banco.
4. Abrir link capturado pelo mock; GET mantém token. Confirmar por botão uma vez.
5. Reutilizar/expirar link: resposta segura sem mudar estado.
6. Reenviar após cooldown: token anterior inválido, sem nova empresa/usuário.
7. Confirmar login negado inclusive após e-mail confirmado e Central desligado.
8. Testar falha Brevo: cadastro persiste pendente, tentativa registrada, sem erro técnico na tela.
9. Repetir identidades em outra empresa: banco rejeita, UI não expõe cadastro existente.
10. Conferir regressão da integração Central e isolamento dos tenants.

Não enviar e-mail real para teste sem autorização explícita. Ficam para próxima
entrega: provisionamento Central, habilitação, trial e demais funcionalidades.