# Correção de persistência do logo

1. Faça backup do MySQL da Hostinger.
2. Se a revisão atual for `73bd0d15d1db`, execute uma única vez
   `D:\App_LiveSun\LiveSun_Propostas\deploy\mysql\05_persistir_logo_empresa.sql`
   no banco selecionado no phpMyAdmin.
3. Só depois publique este código e faça o deploy no Render.
4. Entre em Empresa, selecione novamente o logo e salve uma vez.

Novos uploads são convertidos para PNG e armazenados no MySQL, limite 2 MB.
O arquivo local não é mais necessário para novos logos. Os antigos ainda podem
ser lidos da pasta configurada; salvar Empresa preserva no banco um arquivo legado
que ainda estiver disponível. Arquivos já perdidos não são recuperáveis pelo código.
O PDF, a impressão e a URL assinada do e-mail utilizam o logo armazenado no banco.
Não reaplique os scripts 01/02 sobre a instalação existente.

A alternativa ao SQL é executar `python -m flask --app wsgi db upgrade` com o
código atualizado e antes de atender requisições. Escolha apenas uma opção.