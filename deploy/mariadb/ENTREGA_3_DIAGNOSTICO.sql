-- SOMENTE LEITURA | MariaDB 11.8.9 | banco Propostas.
-- Executar ANTES de ativar a politica comercial unica; nao lista dados pessoais.
SELECT DATABASE() AS banco, VERSION() AS servidor;
SELECT version_num AS revisao FROM alembic_version;
SELECT COUNT(*) AS empresas,
       SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) AS empresas_ativas
FROM empresas;
SELECT COUNT(*) AS usuarios,
       SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) AS usuarios_ativos
FROM usuarios;
SELECT COUNT(*) AS empresas_sem_vinculo FROM empresas e
LEFT JOIN central_tenants t ON t.empresa_id=e.id WHERE t.empresa_id IS NULL;
SELECT COUNT(*) AS vinculos_sem_snapshot FROM central_tenants
WHERE assinatura_id < 1 OR versao < 1 OR payload IS NULL;
SELECT JSON_UNQUOTE(JSON_EXTRACT(payload,'$.status')) AS status_central,
       COUNT(*) AS empresas FROM central_tenants GROUP BY status_central;
SELECT COUNT(*) AS caches_vencidos FROM central_tenants
WHERE valido_ate IS NULL OR valido_ate <= UTC_TIMESTAMP();
SELECT COUNT(*) AS propostas,
       SUM(CASE WHEN data_criacao IS NULL THEN 1 ELSE 0 END) AS sem_data_criacao
FROM propostas;
SELECT empresa_id, COUNT(*) AS propostas, MIN(data_criacao) AS primeira_criacao,
       MAX(data_criacao) AS ultima_criacao FROM propostas GROUP BY empresa_id;
SELECT COUNT(*) AS propostas_sem_empresa FROM propostas p
LEFT JOIN empresas e ON e.id=p.empresa_id WHERE e.id IS NULL;
SELECT COUNT(*) AS possivel_conta_demo_ativa FROM usuarios
WHERE usuario='livesun' AND ativo=1;
-- Nao apagar, anonimizar ou ativar vinculos automaticamente com base neste resultado.
-- Contagens/IDs devem ser revisados pelo responsavel, pois ativo nao comprova cliente real.