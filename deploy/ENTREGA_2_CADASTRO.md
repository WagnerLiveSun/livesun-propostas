# Entrega 2 — solicitação de cadastro ao Central

## Escopo

Após confirmar e-mail e definir senha, a mesma transação ativa empresa/administrador
LOCALMENTE, consome o grant, marca PRONTO_ANALISE e cria uma única solicitação.
Ativo local NÃO significa acesso comercial. Nenhum trial, assinatura, quota,
checkout, onboarding completo, e-mail de liberação, fila de e-mails ou worker foi criado.
O Central e os contratos HMAC/webhook não foram alterados.

## Migration (não aplicada a bancos de uso nesta entrega)

Arquivo: `migrations/versions/e20261118a_solicitacao_central.py`.
Revisão anterior: `d20261118b`. Adiciona `empresas.razao_social_pendente` e
`solicitacoes_central`. Não ativa, envia ou reprocessa cadastros anteriores.
Registros DADOS_COMPLETOS da Entrega 1 permanecem intocados para revisão futura.
Não reaplicar migrations de instalação nem executar stamp.

O código precisa desta migration ANTES de voltar a servir tráfego, mesmo se o
cadastro público estiver desabilitado: os models passam a consultar a nova coluna.
O hook Gunicorn só reconhece a nova revisão e não a aplica automaticamente.
Planejar uma janela de atualização, backup e conferência do destino.

Somente após autorização do ambiente correto, na raiz
`D:\App_LiveSun\LiveSun_Propostas`:

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi db current
.\.venv\Scripts\python.exe -m flask --app wsgi db upgrade e20261118a
.\.venv\Scripts\python.exe -m flask --app wsgi db check
```

Não execute esses comandos em produção sem autorização específica. MySQL DDL
não é totalmente transacional: em erro parcial, inspecionar antes de repetir.
Não há downgrade destrutivo nem limpeza automática.

## Configurações

Reutiliza CENTRAL_BASE_URL, CENTRAL_API_TOKEN (credencial read do PROPOSTAS),
CENTRAL_WEBHOOK_SECRET, CENTRAL_ENABLED e regras existentes de HTTP local/HTTPS.
Nenhuma credencial foi gerada/alterada. Nova opção:

```dotenv
CENTRAL_REGISTRATION_RETRY_SECONDS=120
```

Intervalo efetivo limitado entre 30 segundos e 24 horas. Reenvio ainda tem limite
de 3/hora por IP, autorização restrita e CSRF. Armazenamento de rate limit em
memória é adequado somente à topologia de processo/instância única; escalar exige
backend compartilhado configurado. Não foi adicionado Redis obrigatório.

## Contrato existente

POST `{CENTRAL_BASE_URL}/api/v1/cadastros`, Bearer de produto read, JSON com somente:
evento_id, empresa_id, razao_social, nome_fantasia, cnpj_cpf, email, telefone,
responsavel. Evento: `cad_` + SHA256(`PROPOSTAS:empresa:{id}`)[:32], exatamente o
padrão exigido pelo callback existente. Snapshot persistido preserva conteúdo no retry.
Senha/hash/grants/termos e credenciais não são enviados.

Razão social é `empresa.razao_social or empresa.nome` SOMENTE no payload.
PJ fica com razao_social_pendente=true localmente se não possui razão social;
o valor real não é inventado. Após liberação comercial, um aviso no painel leva
o administrador ao formulário Empresa já existente. Salvar razão social remove
a pendência. Não é um onboarding novo nem altera o contrato do Central.

Respostas 200/202 só marcam RECEBIDA_CENTRAL após validar produto, empresa, evento,
status e ID. IDs retornados pelo POST NÃO criam vínculo/cache. Só o callback assinado
existente faz isso. Aprovação/assinatura continuam sendo ações do operador Central.

## Falha e processamento síncrono

Cadastro e solicitação são confirmados antes da rede. Um UPDATE condicional
reivindica lease de 60s e persiste tentativa antes do POST (timeouts 3s/8s), sem
seguir redirects ou herdar proxies/netrc. Apenas o mesmo lease pode concluir.
Falha mantém PENDENTE com categoria fixa, sem resposta remota/exceção no log.
Se a resposta se perder, retry envia o MESMO evento e snapshot; Central deduplica.
Recebimento no Central não promete autorização do produto.

POST bem-sucedido seguido de falha de persistência deixa ENVIO_NAO_CONFIRMADO;
aguardar cooldown e lease antes de reenviar. Sem worker, uma interrupção ANTES
da primeira tentativa persistida pode deixar pendência sem falha e sem botão.
Não há reenvio automático nesses casos; suporte deve revisar. Não marcar como
recebido nem criar outro cadastro para contornar a pendência.

## UX e proteção de provisionamento

POST `/cadastro/completar` redireciona a GET `/cadastro/recebido`.
Texto aprovado:

> Cadastro recebido
>
> Seus dados foram recebidos e estão em análise pela equipe LiveSun.
>
> Após a análise, você receberá um e-mail com a liberação do acesso ao LiveSun Propostas.
>
> Se necessário, nossa equipe poderá entrar em contato pelo e-mail ou WhatsApp informado no cadastro.

Este pacote NÃO envia e-mail de liberação. A mensagem descreve a operação futura
da equipe; é necessário providenciar esse contato após análise, sem prazo prometido.

GET não consulta Central, não envia nem altera solicitação. Não usa ID livre na URL.
POST `/cadastro/tentar-novamente` exige cookie assinado/HTTPOnly de acompanhamento,
CSRF, cooldown, rate limiting, falha registrada, status pendente, ausência de vínculo
e ausência de tentativa concorrente. Botão fica oculto sem falha, após recebimento
ou com vínculo; durante cooldown fica desabilitado.

Autorização de acompanhamento dura 1h, vinculada a usuário/empresa/cadastro e à
versão HMAC da senha; troca de senha revoga. Não é login do aplicativo. Ao expirar,
usuário autentica com senha no login existente e recebe somente acompanhamento.
Dados de autorização não são renderizados ou registrados nos logs.
Desligar cadastro público não impede acompanhamento/reenvio de contas concluídas.

Barreira, antes do guard Central, vale só para empresas com CadastroPublico:
- sem vínculo: sem sessão de uso do aplicativo;
- CENTRAL_ENABLED=false: sem acesso, mesmo com vínculo;
- vínculo + integração ligada: verificação de entitlements existente;
- empresas legadas sem CadastroPublico: comportamento anterior preservado.
Sessões existentes/forçadas também são restringidas; escrita pendente é negada.
Callback, reconciliação, arquivos estáticos e health não são bloqueados pela barreira.

## Testes automáticos (sem produção/rede real)

```powershell
Set-Location 'D:\App_LiveSun\LiveSun_Propostas'
.\.venv\Scripts\python.exe -m pytest tests -q
```

Usam SQLite temporário, Central/Brevo mockados. Cobrem contrato, timeout/HTTP/JSON,
atomicidade, lease, idempotência, cooldown, CSRF, rate limit, GET sem rede,
isolamento, sessão restrita, callback/HMAC existente e dados legados.
DDL compila para MySQL/PostgreSQL; concorrência e DDL nesses bancos reais ainda
exigem homologação em bases exclusivas descartáveis.

## Teste manual autorizado em homologação

1. Aplicar migration somente após backup/conferência/autorização.
2. Usar Central de homologação com produto PROPOSTAS configurado e callback existente.
   Não apontar o teste ao Central de produção. Envio de e-mail real exige autorização;
   preferir Brevo mockado e capturar link apenas no ambiente de teste.
3. Cadastrar PF/PJ, confirmar e definir senha. Conferir PRONTO_ANALISE, ativos locais,
   uma solicitação e nenhuma assinatura local; PJ com razão social ausente/pendente.
4. Conferir redirecionamento e texto aprovado. Login antes do vínculo só acompanha.
5. Simular timeout: pendente com falha; GET não envia; botão respeita intervalo.
6. Reenviar: mesmo evento, sem duplicata. Após recebido, botão desaparece.
7. Operador aprova no Central e entrega callback assinado. Duplicata é idempotente.
8. CENTRAL_ENABLED=false continua sem acesso. Habilitado e autorizado: login segue
   entitlements existentes. PJ vê aviso para complementar razão social no painel.
9. Outra empresa não acessa acompanhamento; grant expirado/trocada senha é recusado.

Próxima entrega: homologação operacional, tratamento autorizado dos cadastros antigos,
processo de e-mail de liberação e complementação cadastral. Trial automático/quota/
checkout/onboarding/worker continuam fora do escopo.