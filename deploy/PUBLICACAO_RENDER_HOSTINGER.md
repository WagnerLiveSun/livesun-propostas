# Git → Render (Flask) + Hostinger (MySQL)

Este é o roteiro desta arquitetura. O roteiro VPS anterior é uma alternativa, não é
necessário executar Nginx/systemd/VPS quando o backend está no Render.

## 1. Antes de enviar ao Git

Nunca publique `.env`, `Key_Brevo.txt`, backups, dados de clientes ou uploads. Eles
estão no .gitignore e .dockerignore. Se uma chave já foi commitada, removê-la do
arquivo atual não elimina o histórico: revogue e substitua a chave exposta.
Revise `git status` e `git diff --cached` antes de publicar. Ainda não existe um
repositório Git inicializado nesta pasta; o destino e a branch serão escolhidos por você.

## 2. MySQL na Hostinger

Crie o banco/usuário e importe SOMENTE o script 01 para banco vazio, seguido pelo 03,
em `D:\App_LiveSun\LiveSun_Propostas\deploy\mysql`.
O script 02 é somente para um banco na revisão inicial; não execute após o 01.

No hPanel, acesse MySQL remoto e autorize os IPs DE SAÍDA do serviço Render, não o
IP do domínio público. No Render consulte o serviço → Connect → Outbound.
O serviço pode sair por qualquer endereço das faixas apresentadas. Confirme com
a Hostinger como autorizar as faixas, pois o painel pode aceitar apenas IPs individuais.
Se necessário, utilize IPs de saída dedicados. Não mantenha Any Host (%) habilitado.
Use o hostname MySQL remoto mostrado no painel, porta 3306 e os nomes completos
do banco/usuário, incluindo seus prefixos.

A conexão cruza provedores: confirme o suporte a TLS/CA e exigências de segurança
com a Hostinger antes de abrir ao público. A configuração atual não força/verifica
TLS MySQL. Não trate uma conexão TCP funcionando como comprovação de criptografia.
Se não houver transporte seguro suportado, altere a arquitetura ou prepare túnel
seguro/configuração TLS verificada antes de usar dados reais.

## 3. Criar serviço no Render

Envie o código ao repositório de sua escolha. Crie um Blueprint a partir dele para
ler `render.yaml`, ou um Web Service com runtime Docker, usando o Dockerfile da raiz.
O Blueprint seleciona plano pago Starter e disco de 1 GB; confirme o custo no painel.
Ele NÃO cria outro banco: utiliza o MySQL externo da Hostinger.

O Dockerfile instala Python e Chromium para gerar o mesmo PDF do layout impresso.
Não substitua por runtime Python simples sem instalar também o navegador.
Não é necessário configurar Build/Start Command: usa o CMD do Dockerfile.

Preencha os segredos solicitados no Render:

| Variável | Valor |
|---|---|
| MYSQL_HOST | hostname remoto da Hostinger |
| MYSQL_DATABASE | nome completo do banco |
| MYSQL_USER | usuário completo do banco |
| MYSQL_PASSWORD | senha exclusiva do banco |
| PUBLIC_BASE_URL | endereço HTTPS público deste serviço |
| BREVO_API_KEY | chave exclusiva do Propostas |

SECRET_KEY é gerada pelo Blueprint. Mantenha-a estável entre deploys; alterá-la
invalida sessões e links assinados. Não utilize senha root nem segredos locais.
O servidor escuta em 0.0.0.0:$PORT. Não use o .bat ou `python run.py` no Render.

## 4. Logos e uploads

O filesystem normal do Render é temporário; o Blueprint monta um disco persistente
em /app/storage e guarda os logos em /app/storage/uploads. Confirme a permissão de
escrita para o UID 10001 do container no primeiro deploy. Faça backups separados dos
uploads. Usar plano sem disco requer implementar armazenamento externo antes de
aceitar uploads; caso contrário, logos são perdidos ao reiniciar/republicar.

## 5. Primeira execução

O health check /healthz valida a conexão MySQL. Se retornar 503, verifique hostname,
senha, porta, regras de IPs remotos e logs do deploy.
No Shell do serviço, execute:

```sh
python -m flask --app wsgi db check
python -m flask --app wsgi criar-admin
```

Importar o script 01 já registra as migrations; não execute init/migrate novamente.
Novas versões usam `python -m flask --app wsgi db upgrade`, com backup e aplicação
em manutenção. Não são executadas migrations automaticamente durante o start.
Crie o administrador com senha forte; a conta livesun/livesun não é exportada.

## 6. Homologação necessária

Não houve build Docker local (Docker indisponível) nem deploy na conta Render.
Valide na plataforma: inicialização não-root, permissões do disco, sandbox Chromium,
fontes/paginação, Brevo, recuperação e isolamento entre empresas. O PDF usa sandbox;
não desative a proteção apenas para contornar erro de inicialização: investigue a
compatibilidade do ambiente ou use um serviço de renderização isolado adequado.

Antes do acesso público: HTTPS/domínio, TLS do banco, senhas fortes, backups, política
de retenção, revisão de segurança e limitação de tentativas de login/recuperação
(essa limitação ainda precisa ser implementada). Instalação configurada não equivale
a homologação de segurança.

Referências oficiais consultadas: Render Docs — Docker, Web Services, Persistent
Disks, Outbound IP Addresses e Blueprint YAML Reference; Hostinger Help — How to set
up remote MySQL access in Hostinger.