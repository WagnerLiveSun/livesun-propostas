# Atualizacao da landing

**Entrega 2:** após definir senha, contas ficam ativas LOCALMENTE e seguem para
acompanhamento/análise, sem acesso comercial antes do vínculo e entitlements.
Consulte `deploy/ENTREGA_2_CADASTRO.md` (migration manual `e20261118a`). Os trechos
históricos abaixo sobre DADOS_COMPLETOS/contas inativas descrevem a Entrega 1.

- URL publica: `/lp/propostas`; `/propostas` permanece reservado ao aplicativo.
- Menu sem precos. Suporte direciona ao formulario Pipefy oficial informado.
- Depois da confirmacao: somente senha e confirmacao de senha, inclusive para PJ.
- Dados empresariais adicionais ficam para uma entrega futura; nao sao inventados.
- Login com links discretos e acao de cadastro separada, mantendo os temas existentes.

# Landing pública — LiveSun Propostas

## Acesso local

Inicie `D:\App_LiveSun\LiveSun_Propostas\Iniciar_LiveSun_Propostas.bat` e abra
`http://127.0.0.1:5000/lp/propostas` (ou a porta local configurada).
Cadastro direto: `/cadastro`. A rota `/` continua sendo o dashboard autenticado.
Se o servidor antigo não recarregar, pare com Ctrl+C e abra o inicializador novamente.

## Design e conteúdo

Layout público independente, BlueMetal com destaques Moonlight, logo LiveSun,
ícones SVG inline, CSS/JS locais e fonte do sistema. Sem frameworks adicionais,
trackers, fontes ou scripts externos. FAQ nativo e menu progressivamente aprimorado.
Preços não são publicados nem exibidos na navegação.
O suporte usa o e-mail oficial existente; não presume WhatsApp oficial.
Valores exibidos nos mockups são de propostas fictícias, não preços do sistema.

O PDF de referência não é publicado. Apenas seu logo incorporado foi extraído
para `src/static/images/demo-proposta-logo.png`, conforme autorização do usuário.
Cliente, contato, itens, totais e número foram reconstruídos com dados fictícios.
O exemplo é HTML/CSS, não documento real nem imagem com dados recuperáveis sob blur.
A revisão do logo/marca do emissor para publicação pública permanece responsabilidade
do proprietário. Ferramentas pypdf/Playwright foram usadas só localmente para
inspeção e validação; não são dependências do runtime.

## Cadastro progressivo sem migration nova

As migrations existentes até `d20261118b` continuam sendo pré-requisito.
1. Cinco campos: e-mail, nome, WhatsApp, empresa/atividade e CPF/CNPJ. Mais aceite,
   CSRF e honeypot. Tipo PF/PJ é inferido pelo documento validado no servidor.
2. Empresa e administrador continuam inativos. E-mail inicial é contato e login.
   Razão social não é inventada. Senha inicial é segredo aleatório descartado,
   armazenado apenas como hash e não utilizável pelo cliente.
3. E-mail síncrono Brevo mantém o mesmo endpoint de confirmação. GET não consome.
4. POST de confirmação consome o token original e gera grant aleatório de 15 minutos.
   Apenas seu hash fica no banco. Segredo fica na sessão Flask assinada/HTTPOnly,
   com Secure em produção. Não é sessão de login, não contém acesso comercial.
5. GET/POST `/cadastro/completar` exige grant válido e CSRF. Coleta somente senha e confirmação de senha. Nome do responsável já foi coletado no primeiro passo.
6. Operação atômica consome grant, salva dados e marca `DADOS_COMPLETOS`.
   Nenhum ativo, vínculo, assinatura ou pagamento é criado/alterado.
7. Grant vencido: novo link limitado pode ser solicitado. Reenvio revoga grant anterior.
   Link/grant consumidos não podem concluir novamente. Cadastros antigos pendentes
   também podem confirmar e definir senha; registros não são migrados automaticamente.

Há reutilização sequencial de token_hash/expira_em: primeiro confirmação, depois
grant de conclusão. Estados PENDENTE_EMAIL → EMAIL_CONFIRMADO → DADOS_COMPLETOS
distinguem as etapas. Nenhum token é colocado em metadata SEO ou logs novos.
O endpoint antigo de cadastro passa a esperar o novo formulário; não é API externa
nem contrato Central. Contratos Central e seus arquivos não foram modificados.

## Segurança e SEO

Unicidade global, validação de documento/e-mail/telefone, limites por IP/identidade,
cooldown, CSRF, respostas genéricas e falha segura permanecem. Sem consentimento
de marketing ou integração WhatsApp. Landing é indexável; todas as etapas do cadastro
continuam noindex e no-store. Landing também é no-store por conter CSRF.
Canonical usa a origem de PUBLIC_BASE_URL; configure origem pública correta antes
de publicar. Não adicionar tokens ou dados pessoais ao canonical.
Não foram criadas novas variáveis de ambiente nem alteradas as existentes.

## Testes e revisão

Na raiz: `.\.venv\Scripts\python.exe -m pytest tests -q`.
Novos testes cobrem estrutura/SEO, formulário, grant, expiração/reenvio, uso único,
CSRF, isolamento e ausência de PDF original nos assets. Brevo e rede são simulados.
Chrome local validado em desktop/tablet/mobile; sem rolagem horizontal,
menu por teclado/Escape, navegação sem JS e logo da proposta verificados.
Não executar formulário com Brevo real sem autorização: enviar gera e-mail síncrono.

## Manual seguro

1. Abrir landing e testar navegação, FAQ, demo e links legais.
2. Redimensionar para celular, teclado Tab/Enter/Escape e zoom.
3. Em ambiente com Brevo mockado, cadastrar PF/PJ com e-mail/documento de teste.
4. Capturar link no mock; abrir e confirmar; definir senha após confirmação.
5. Conferir dados e que usuário/empresa seguem inativos; login não é liberado.
6. Repetir link, grant e envio de dados: nenhuma duplicação ou ativação.
7. Expirar grant, solicitar novo link e verificar revogação da autorização anterior.

Nenhum deploy, migration ou alteração de produção foi executado nesta entrega.