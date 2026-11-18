-- SOMENTE LEITURA. Selecione o banco PROPOSTAS; exporte backup antes de atualizar.
-- Exige MySQL 8.0.4+ (REGEXP_REPLACE). Nenhum dado pessoal e listado.
SELECT DATABASE() AS banco_atual, VERSION() AS versao_mysql;
SELECT version_num AS revisao_atual FROM alembic_version;
SELECT COUNT(*) AS empresas, SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) AS empresas_ativas FROM empresas;
SELECT COUNT(*) AS usuarios, SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) AS usuarios_ativos FROM usuarios;
SELECT COUNT(*) AS emails_ausentes FROM usuarios WHERE email IS NULL OR TRIM(email) = '';
-- ASCII visivel: casos Unicode/controles precisam de revisao especifica, sem normalizar as cegas.
SELECT COUNT(*) AS emails_para_revisao_especifica FROM usuarios
WHERE email IS NOT NULL AND REGEXP_LIKE(email, '[^ -~]', 'c');
SELECT COUNT(*) AS grupos_email_duplicado FROM (
 SELECT CONVERT(LOWER(TRIM(email)) USING utf8mb4) COLLATE utf8mb4_unicode_ci AS identidade
 FROM usuarios GROUP BY identidade HAVING COUNT(*) > 1
) AS conflitos_email;
SELECT COUNT(*) AS grupos_documento_duplicado FROM (
 SELECT NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '') AS identidade FROM empresas
 WHERE NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '') IS NOT NULL GROUP BY identidade HAVING COUNT(*) > 1
) AS conflitos_documento;
SELECT COUNT(*) AS documentos_maiores_que_14 FROM empresas WHERE CHAR_LENGTH(NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '')) > 14;
SELECT COUNT(*) AS empresas_sem_documento FROM empresas WHERE NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '') IS NULL;
SELECT COUNT(*) AS usuario_demonstrativo_ativo FROM usuarios WHERE usuario = 'livesun' AND ativo = 1;
SHOW GRANTS FOR CURRENT_USER;
