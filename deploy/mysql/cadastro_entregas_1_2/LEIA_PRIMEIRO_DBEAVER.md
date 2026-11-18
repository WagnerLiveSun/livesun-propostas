# Aplicação no DBeaver — SOMENTE banco do Propostas

Scripts validados em MySQL 8.0.31, com dados de exemplo preservados e estrutura
final sem diferenças com os modelos. Requer MySQL 8.0.4+; não usar em MariaDB/MySQL 5.

1. Exporte backup completo antes. Faça a atualização sem usuários gravando dados.
2. Selecione a conexão e o banco de PRODUÇÃO DO PROPOSTAS no DBeaver.
3. Execute `00_DIAGNOSTICO_SOMENTE_LEITURA.sql`.
4. Siga a tabela abaixo conforme `revisao_atual`.

| Revisão atual | Arquivos a executar, nesta ordem |
|---|---|
| b8215bc35a91 | 01 → 02 → 03 → 04 → 05 |
| c20261112 | 02 → 03 → 04 → 05 |
| d20261118a | 03 → 04 → 05 |
| d20261118b | 04 → 05 |
| e20261118a | Somente 05; já atualizado |
| Outra/ausente | Pare; não execute instalação inicial nem altere Alembic manualmente |

## Antes de cada arquivo de atualização (01, 02, 03 e 04)

Edite estas linhas NO ARQUIVO:

```sql
SET @ls_banco_esperado = 'NOME_EXATO_DO_SEU_BANCO_PROPOSTAS';
SET @ls_backup_confirmado = 1;
```

No arquivo 03, somente após diagnóstico sem conflitos, também altere:

```sql
SET @ls_unicidade_aprovada = 1;
```

No diagnóstico: emails_ausentes, emails_para_revisao_especifica,
grupos_email_duplicado, grupos_documento_duplicado e documentos_maiores_que_14
devem ser ZERO. Empresas sem documento podem permanecer com NULL; nenhum valor
é inventado. Não apagar/unir cadastros para contornar erros sem revisão.

## Execução

Abra um arquivo de cada vez e use **Executar script SQL** (Alt+X no atalho padrão),
não executar somente uma instrução. O arquivo usa `DELIMITER $$` para a procedure;
o cliente deve reconhecer essa diretiva. Não remova delimitadores nem separe o corpo.
Se a instalação não interpretar delimitadores, ajuste o modo MySQL do editor antes
de continuar; não execute trechos avulsos. Configure parar no primeiro erro.
Verifique o sucesso e a revisão exibida antes do próximo arquivo.

É necessário permissão para CREATE ROUTINE, ALTER e demais DDL. As procedures são
temporárias de implantação (criadas e removidas no mesmo script). Se faltar permissão,
pare e solicite ao administrador; não retire as proteções. GET_LOCK coordena apenas
estes scripts; NÃO bloqueia escritas do aplicativo. Mantenha a janela sem escritas.

**Em qualquer erro: PARE. Não prossiga para o próximo arquivo nem ignore o erro.**
MySQL DDL não tem rollback completo; uma falha pode deixar estrutura parcial.
Não repita cegamente, não use DROP TABLE, não altere `alembic_version` manualmente.
O DROP PROCEDURE dos arquivos remove apenas o auxiliar de implantação, nunca dados.

Resultado final esperado no 05: revisão `e20261118a`, divergências ZERO,
índices com non_unique=0 e contagens de empresas/usuários iguais ao diagnóstico.
Não cria contas, não ativa cadastros antigos, não envia e-mails e não acessa Central.

Os SQLs substituem a execução Python das mesmas revisões: **não aplique ambos**.
Não use arquivos 01/02 antigos da pasta pai: são de instalação/versões antigas.
Depois da conferência final, o push/deploy é uma operação separada. O hook antigo
pode recusar revisão nova em reinício antes do novo código; coordene a janela.