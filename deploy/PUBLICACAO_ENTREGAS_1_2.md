# Preparação de publicação — Entregas 1 e 2

## Situação

Pacote local do diretório de trabalho: não equivale a versão commitada, publicada
ou homologada na infraestrutura. Nenhum push/deploy é executado pelo empacotador.
Inclui Entrega 1, landing e Entrega 2 porque ainda não foram commitadas separadamente.
Central, credenciais e seus contratos não são modificados.

## Bloqueios antes da produção

- Confirmar serviço Render, branch, commit atual, comando Docker e auto-deploy reais.
- Confirmar banco exclusivo do Propostas, revisão Alembic e proprietário do backup.
- Backup completo recuperável do banco e arquivos; testar restauração em cópia.
- Diagnóstico de unicidade autorizado antes de d20261118b; não limpar dados sozinho.
- Revisar TLS/conectividade do banco, logs externos e topologia de rate limiting.
- Homologar migrations em MySQL/PostgreSQL compatível com o destino.
- Conferir configurações existentes sem imprimir/copiar segredos para chat ou pacote.

Não fazer push em main sem conferir auto-deploy: código novo antes do schema novo
pode interromper a aplicação. A preparação local não constitui autorização para
migrations de produção. Reconfirmar janela e destino antes da execução.

## Sequência de atualização proposta (não executada)

1. Identificar commit anterior e guardar artefato recuperável. Suspender alterações
   e cadastros durante a janela; planejar banco sem escritas para normalização.
2. Preservar SECRET_KEY e credenciais existentes. Não substituir pelas locais.
3. Manter PUBLIC_REGISTRATION_ENABLED=false e PUBLIC_REGISTRATION_PREVIEW=false
   durante preparação. Isso não substitui manutenção: models novos exigem schema novo.
4. Preparar ambiente de migration com o NOVO código e dependências, sem servi-lo
   ao público, conectado somente ao banco confirmado e com backup validado.
5. Conferir revisão. Não rodar init/stamp/scripts iniciais em banco existente.
6. Se estiver em c20261112, aplicar A, revisar dados e autorizar B. Se estiver
   em d20261118b, aplicar somente e20261118a. Revisão inesperada: interromper.
7. Validar db current/db check e preservação de dados antes de iniciar código novo.
8. Publicar commit revisado em operação separada. Hook existente não aplica novas
   migrations automaticamente; apenas reconhece revisões compatíveis.
9. Conferir health, login, landing e assets por GET, sem cadastros/e-mails reais.
10. Habilitar cadastro somente após aceite operacional e configuração completa.

Comandos de referência (NÃO executar sem confirmar ambiente/autorização):

```text
python -m flask --app wsgi db current
python -m flask --app wsgi db upgrade d20261118a
# Somente se B ainda não aplicada e diagnóstico aprovado:
# fornecer REGISTRATION_UNIQUENESS_APPROVED=true temporariamente ao processo
python -m flask --app wsgi db upgrade d20261118b
python -m flask --app wsgi db upgrade e20261118a
python -m flask --app wsgi db check
```

Não copiar .env local para o Render. Não executar db upgrade head às cegas.
DDL MySQL pode não reverter integralmente: em falha parcial, preservar logs seguros,
inspecionar estrutura e não repetir automaticamente. Downgrade destrutivo é proibido.

## Environment a conferir no serviço (sem valores de segredos)

Preservar banco, SECRET_KEY, Brevo e configuração Central existentes.

- PUBLIC_BASE_URL: origem HTTPS pública correta do Propostas.
- PUBLIC_REGISTRATION_PREVIEW=false em produção.
- PUBLIC_REGISTRATION_ENABLED=false na preparação; true só no aceite final.
- PUBLIC_REGISTRATION_DATA_REVIEWED=true apenas após diagnóstico real aprovado.
- TERMS_URL=https://livesun.com.br/termos
- PRIVACY_URL=https://livesun.com.br/lgpd
- TERMS_VERSION/PRIVACY_VERSION: identificadores de referência aprovados.
- EMAIL_CONFIRMATION_TTL_MINUTES=60; CONFIRMATION_RESEND_COOLDOWN_SECONDS=120.
- PUBLIC_REGISTRATION_RATE_LIMIT=5 per hour.
- REGISTRATION_IDENTITY_RATE_LIMIT=3 per hour.
- CONFIRMATION_RESEND_RATE_LIMIT=5 per hour.
- CENTRAL_REGISTRATION_RETRY_SECONDS=120.
- RATELIMIT_STORAGE_URI: memory:// só em processo/instância único; backend
  compartilhado necessário antes de escalar. Não configurar Redis sem serviço/driver.
- CENTRAL_API_TOKEN: credencial read existente de PROPOSTAS, não token de escrita.
- CENTRAL_WEBHOOK_SECRET: mesmo segredo já cadastrado no produto.
- CENTRAL_ENABLED: preservar decisão atual. Desligado não libera autocadastros.
  Só habilitar após conferir TODOS os vínculos; não ativar automaticamente.

O render.yaml local não comprova Environment/auto-deploy reais. Não reaplicar
Blueprint sem revisar: ele contém defaults históricos, inclusive CENTRAL_ENABLED=false.
Não foram adicionadas credenciais ou variáveis locais privadas ao manifesto.

## Rollback

Se precisar recuar código, manter dados e tabelas aditivas; não executar downgrade.
O hook do código antigo pode recusar revisão nova: rollback precisa de artefato
de compatibilidade testado ou intervenção planejada, não apenas selecionar commit
antigo às cegas. Restaurar backup é ação potencialmente destrutiva e exige janela,
avaliação de dados novos e autorização separada. Não restaurar automaticamente.

## Pacote local

Executar scripts/preparar_publicacao.py --destino PASTA_FORA_DO_REPOSITORIO.
Produz ZIP, manifesto.json e SHA256.txt. Seleção por allowlist e Git (inclui arquivos
novos não ignorados), exclui .env privados, chaves, backups, uploads, logs, bancos,
PDF original e script de credencial demonstrativa conhecida. .env.example sem
credenciais reais é intencionalmente incluído. Não contém histórico .git.
Scanner detecta padrões comuns, não garante ausência absoluta de segredos:
revisão humana do pacote/diff continua obrigatória antes de publicar.

O pacote não inclui ambiente virtual. Dependências pypdf/Playwright usadas apenas
para inspeção local não foram adicionadas ao runtime. Build Docker local não foi
executado porque Docker não está disponível nesta estação.