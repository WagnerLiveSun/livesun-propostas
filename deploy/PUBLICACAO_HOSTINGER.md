# Publicação — LiveSun Propostas

## Antes de começar

Este pacote prepara a estrutura SQL e modelos de execução, mas NÃO publica o sistema
automaticamente. Não houve acesso à conta Hostinger nem validação no servidor remoto.
Confirme seu plano: a documentação da Hostinger informa que Flask/Python requer VPS;
não basta enviar arquivos Python para `public_html` em um plano Web/Cloud.

Referências oficiais: artigos da Hostinger “Which programming languages and frameworks
are supported at Hostinger” e “How to import a database with phpMyAdmin in Hostinger”.

## 1. Banco novo: importar no phpMyAdmin

1. Crie um banco exclusivo e um usuário exclusivo no painel da hospedagem. Anote os
   nomes COMPLETOS atribuídos, incluindo prefixos. Não use root nem a senha local.
2. Entre no phpMyAdmin e SELECIONE esse banco vazio.
3. Em Importar, escolha `01_instalacao_banco_vazio.sql`, na pasta
   `D:\App_LiveSun\LiveSun_Propostas\deploy\mysql` do computador local.
4. Execute `03_verificar_instalacao.sql`. Devem existir nove tabelas, contando
   `alembic_version`, cuja revisão deve ser `73bd0d15d1db`.

O script 01 já inclui condição de pagamento, índices, chaves estrangeiras e controle
de migrations. Não execute o 02 depois dele. Não precisa de CREATE DATABASE, USE,
CREATE USER, GRANT, SUPER, procedures ou acesso root. Use banco com InnoDB e utf8mb4.
Não importe por cima de tabelas existentes e não ignore erros durante a importação.
Os scripts não são idempotentes: uma segunda execução deve falhar, não mascarar um
esquema incompleto. DDL MySQL não oferece rollback completo; em erro, investigue antes
de repetir. Para uma instalação nova parcialmente importada, recrie SOMENTE o banco
novo vazio, nunca um banco que já possua dados de trabalho.

## 2. Banco com a estrutura inicial

Faça backup. Consulte `SELECT version_num FROM alembic_version;`.

- `9eb8e86ea7b2`: aplique SOMENTE `02_atualizar_estrutura_inicial.sql`.
- `73bd0d15d1db`: já está atualizado, não execute 01 nem 02.
- Sem tabela alembic_version ou revisão diferente: não importe nem marque a revisão
  manualmente; compare o esquema e prepare uma migração específica.

Alternativa aos arquivos SQL: com a aplicação instalada e configurada no servidor,
execute `python -m flask --app wsgi db upgrade`. Escolha SQL OU migration para instalar;
os arquivos SQL já registram o estado correto para futuras migrations.

## 3. Os dados locais não estão nesses scripts

Não são exportadas empresas, clientes, propostas, usuários, hashes, chaves Brevo ou
senhas. O usuário de demonstração `livesun` com senha `livesun` NÃO é criado.
Se quiser transferir dados locais, será necessário um backup separado e também copiar
os logos da pasta uploads. Não exponha esse backup nem arquivos de chaves pela web.

## 4. Configuração da aplicação no VPS

Modelo de diretório no Linux: `/opt/livesun-propostas`.
Esse caminho é uma convenção deste pacote, não um caminho obrigatório da Hostinger.

- Envie src, config, migrations, deploy, requirements.txt, run.py e wsgi.py.
- NÃO envie `.venv` do Windows, `.env` local, logs, bases SQLite, `.devin` ou backups.
- Instale Python 3.11/3.12, venv, Nginx e Chrome/Chromium atualizado, conforme a
  distribuição escolhida. O navegador é necessário para o PDF idêntico à impressão.
- Crie um usuário de serviço `livesun` sem root e permita escrita somente nos
  diretórios necessários. O navegador precisa funcionar com sandbox; não o desative.
- Crie o venv Linux e instale as dependências:

```sh
cd /opt/livesun-propostas
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp deploy/.env.production.example .env
chmod 600 .env
.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"
```

Preencha TODAS as variáveis vazias do .env. Use a chave gerada em SECRET_KEY,
PUBLIC_BASE_URL com o domínio HTTPS real, credenciais MySQL da nuvem, remetente
Brevo autorizado e PDF_BROWSER_PATH com o executável Linux real. Nunca utilize
`localhost` como host do banco remoto sem confirmar o endereço no painel.
Se banco e backend estiverem em máquinas diferentes, autorize somente o IP do backend
e utilize rede privada/túnel seguro/TLS conforme o provedor; não exponha MySQL à internet.

Depois da importação SQL, crie a primeira empresa/administrador:

```sh
.venv/bin/python -m flask --app wsgi criar-admin
.venv/bin/python -m flask --app wsgi db check
```

A senha é solicitada sem exibição; escolha uma senha forte e única. A interface tem
limite inicial de três usuários por empresa.

## 5. Serviço e HTTPS

Revise os modelos `livesun-propostas.service`, `gunicorn.conf.py` e
`nginx.conf.example`. Ajuste domínio e caminhos. Não sobrescreva a configuração de
outros sites. Copie o serviço para `/etc/systemd/system/` e instale o site no Nginx
conforme a distribuição. Ative o certificado HTTPS antes do primeiro login.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now livesun-propostas
sudo nginx -t
sudo systemctl reload nginx
sudo journalctl -u livesun-propostas -n 100 --no-pager
```

Gunicorn aceita conexões apenas em 127.0.0.1:8000; somente Nginx deve ser público.
TRUST_PROXY=true pressupõe exatamente esse proxy confiável. Nunca publique o .env,
Key_Brevo.txt ou uploads por alias/root do Nginx. Não use `python run.py` nem o .bat
Windows no servidor de produção. A configuração produção mantém DEBUG desativado,
CSRF habilitado e cookie de sessão Secure/HttpOnly/SameSite=Lax.

## 6. Checklist obrigatório antes de abrir ao público

- Senhas fortes e conta de demonstração ausente ou desativada.
- HTTPS, firewall, patches do sistema/navegador e configuração do proxy conferidos.
- Implementar limitação de tentativas de login/recuperação no proxy ou aplicação;
  essa proteção ainda não existe no pacote. Não considerar a instalação homologada
  para exposição pública sem essa revisão e um teste de segurança.
- Homologar PDF e paginação em Linux (as fontes podem diferir das do Windows).
- Testar envio Brevo para endereço controlado, recuperação de senha e logo público.
- Testar isolamento multiempresa, uploads e permissões de cada perfil.
- Backup periódico do MySQL e uploads, retenção e teste de restauração.
- Monitorar logs e espaço em disco; não compartilhar logs com segredos.

Os modelos systemd/Nginx/Gunicorn precisam ser validados no Linux real; foram
preparados no Windows e não executados na Hostinger.