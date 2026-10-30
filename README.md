# LiveSun - Propostas

Sistema SaaS independente para gestão de propostas comerciais/orçamentos.

## Publicação na Hostinger

Para Git → Render com MySQL na Hostinger, utilize o roteiro
`D:\App_LiveSun\LiveSun_Propostas\deploy\PUBLICACAO_RENDER_HOSTINGER.md`.
O projeto inclui Dockerfile (Python + Chromium), render.yaml, disco persistente
para logos e health check `/healthz`. O Blueprint usa serviço pago; conferir custos.
Nessa arquitetura não é necessário hospedar Python na Hostinger.

Scripts MySQL: `D:\App_LiveSun\LiveSun_Propostas\deploy\mysql`.
Guia: `D:\App_LiveSun\LiveSun_Propostas\deploy\PUBLICACAO_HOSTINGER.md`.
O script 01 instala um banco vazio; o 02 atualiza somente a revisão inicial.
Não execute os dois em sequência nem importe sobre dados sem backup.

## Stack

- Python 3.11+
- Flask 3.0+
- SQLAlchemy 2.0+
- MySQL ou PostgreSQL
- Flask-Migrate
- Flask-Login
- Brevo API (e-mails)
- fpdf (geração de PDF)

## Instalação

1. Criar ambiente virtual:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows
```

2. Instalar dependências:
```bash
pip install -r requirements.txt
```

3. Configurar variáveis de ambiente:
```bash
cp .env.example .env
# Editar .env com suas configurações
```

4. Configurar banco de dados (MySQL ou PostgreSQL)

5. Aplicar as migrations já versionadas (não executar `db init` novamente):
```bash
python -m flask --app run db upgrade
```

6. Criar a empresa e o primeiro administrador (a senha é solicitada sem exibição):
```powershell
.\.venv\Scripts\python.exe -m flask --app run criar-admin
```

7. Executar aplicação:
```bash
python run.py
```

## Estrutura do Projeto

```
livesun-propostas/
├── config/           # Configurações
├── src/
│   ├── core/        # Utilitários de banco
│   ├── models/      # Models SQLAlchemy
│   ├── routes/      # Rotas Flask
│   ├── services/    # Serviços (Brevo, PDF)
│   ├── static/      # CSS, JS, imagens
│   ├── templates/   # Templates Jinja2
│   ├── app.py       # Flask app factory
│   ├── extensions.py # Extensions (db, login, csrf)
│   └── utils.py     # Utilitários
├── migrations/       # Migrations Alembic
├── tests/           # Testes
└── uploads/         # Arquivos enviados
```

## Funcionalidades

- Multiempresa (isolamento por empresa_id)
- Autenticação com perfis (admin, operador, visualizador)
- Limite de 3 usuários por empresa
- Cadastro de clientes
- Cadastro de produtos/serviços
- Criação e edição de propostas
- Aprovação e rejeição de propostas
- Replicação de propostas
- Geração de PDF
- Envio por e-mail (Brevo)
- Dashboard com indicadores
- Temas BlueMetal e Moonlight

## Suporte

Para suporte, contate a equipe LiveSun.

## Retomada do desenvolvimento — 30/10/2026

O sistema permanece completamente independente do LiveSun Comercial. Nenhum banco,
login, API ou credencial é compartilhado. O arquivo `.env` local contém os parâmetros
do MySQL e não deve ser versionado. Não utilize o usuário root em produção.

### Execução no Windows

Diretório do projeto: `D:\App_LiveSun\LiveSun_Propostas`.

```powershell
Set-Location 'D:\App_LiveSun\LiveSun_Propostas'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Em uma instalação nova: Copy-Item .env.example .env e ajustar as variáveis.
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe -m flask --app run criar-admin
.\.venv\Scripts\python.exe run.py
```

Endereço local: `http://127.0.0.1:5000`. Não existe senha administrativa padrão.
Para iniciar com duplo clique, utilize
`D:\App_LiveSun\LiveSun_Propostas\Iniciar_LiveSun_Propostas.bat`.
O iniciador verifica o ambiente virtual, o `.env` e a conexão com o banco antes
de iniciar. Ele informa o endereço configurado; abra esse endereço no navegador
e mantenha a janela do servidor aberta. Para encerrar, pressione `Ctrl+C`.
O MySQL precisa estar iniciado. O arquivo não instala dependências, não altera
o banco e não cria usuários automaticamente. Para apenas verificar a configuração,
execute o `.bat` com o argumento `/verificar`.
As credenciais do MySQL não são credenciais de acesso à aplicação.
O desenvolvimento respeita `DB_ENGINE=mysql`; SQLite em memória fica restrito aos testes.

### Fluxo implementado

- Cadastro/edição e inativação de clientes e produtos/serviços.
- Cadastro da emitente e upload de logo convertido para PNG.
- Administrador adiciona usuários até o limite de 3 por empresa.
- Login por usuário único ou e-mail; e-mail é único dentro de cada empresa.
  Se houver mais de uma conta compatível com e-mail e senha, utilizar o nome de usuário.
- Propostas com dados do cliente independentes do cadastro e itens livres ou do catálogo.
- Cálculos definitivos no servidor com Decimal, quantidades de 3 casas e valores de 2 casas.
- Aprovação registra usuário/data UTC e cria ou atualiza o cliente na mesma transação.
- Propostas aceitas/rejeitadas não podem ser editadas: utilizar replicação.
- Replicação preserva valores e itens; limpa o cliente para informar o destino e cria rascunho.
- Número único por empresa, composto pelo ano e um identificador aleatório.
- PDF, impressão, dashboard com filtros e trilha de auditoria.
- Envio e reenvio com PDF, mensagem configurável e histórico de sucesso/falha.
- Recuperação por token aleatório de uso único, hash no banco e validade de 30 minutos.
- Proteção CSRF e perfis aplicados no servidor, incluindo restrições ao visualizador.

### Brevo

A chave também pode ser armazenada no arquivo local
`D:\App_LiveSun\LiveSun_Propostas\Key_Brevo.txt`, ignorado pelo Git.
`BREVO_API_KEY` no ambiente tem prioridade. Configure `BREVO_SENDER_EMAIL`
com um remetente autorizado no Brevo e reinicie o programa após mudar a configuração.

### PDF igual à impressão

Download e anexo de e-mail são gerados a partir do mesmo template HTML da impressão,
usando Chrome/Edge em modo headless. Não existe mais um desenho separado em FPDF.
Bootstrap 5.3.0 é servido localmente e os estilos e o logo da emitente são embutidos
na geração: o navegador não acessa URLs externas nem depende de uma sessão HTTP.
O computador que executa o backend deve ter Chrome/Edge instalado; opcionalmente,
configure o caminho completo em `PDF_BROWSER_PATH`. Em outro servidor, instale um
navegador Chromium compatível e configure esse caminho. Não há fallback para o
modelo antigo: falhas de geração são informadas, sem enviar um anexo diferente.

### Condição de pagamento da proposta

O formulário de proposta possui o campo Condição de pagamento (até 500 caracteres),
preservado na replicação e exibido no documento, impressão e PDF anexado ao e-mail.
O valor por extenso é apresentado como `Valor Total da proposta de: (valor por extenso)`.
Instalações existentes devem aplicar `python -m flask --app run db upgrade`.

### Configuração dos envios

Configurar `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME` e
`PUBLIC_BASE_URL` com credenciais e domínio exclusivos do Propostas. O remetente
precisa estar autorizado no Brevo. O fluxo atual envia HTML diretamente e não exige
template remoto. Sem configuração, o envio falha explicitamente e o histórico da
proposta registra a tentativa; não há simulação de sucesso.

O logo no e-mail utiliza uma URL assinada que dá acesso somente à imagem da marca.
Para visualização fora da rede local, `PUBLIC_BASE_URL` precisa ser um endereço público.
Tokens e senhas não são escritos nos logs da integração.

### Validação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m flask --app run db check
.\.venv\Scripts\python.exe -m compileall -q src config tests
```

Os testes automatizados usam SQLite em memória, nunca o banco de trabalho. Cobrem
permissões, isolamento, aprovação, snapshots do cliente, replicação, cálculo,
PDF, logo, filtros, recuperação de senha, CSRF e integração Brevo simulada.

### Pendências para homologação / produção

- Disponibilizar o modelo visual de impressão citado na definição; o PDF contém os
  campos especificados, sem promessa de fidelidade a um anexo ausente. A marca oficial
  do desenvolvedor está em `D:\App_LiveSun\LiveSun_Propostas\src\static\images\logo.png`
  e é exibida no cabeçalho, login e rodapé. O logo da emitente permanece separado.
- Configurar e homologar envios reais no Brevo, HTTPS e domínio público.
- Validar em um servidor PostgreSQL real; o driver e a configuração estão disponíveis,
  mas a validação local foi feita em MySQL e SQLite.
- Homologar visualmente em navegador e nos dispositivos de destino.
- Antes de exposição pública, adicionar limitação de tentativas de autenticação e
  recuperação, monitoramento, backups e revisão de segurança.
- Bootstrap/ícones usam CDN e exigem conectividade; podem ser hospedados localmente.
- Este servidor de desenvolvimento não deve ser utilizado como servidor de produção.
