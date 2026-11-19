-- SOMENTE LEITURA | apos ENTREGA_3_TRIAL.sql | esperado f20261118a.
SELECT version_num AS revisao FROM alembic_version;
SHOW CREATE TABLE commercial_usage;
SHOW CREATE TABLE trial_proposals;
SHOW CREATE TABLE welcome_preferences;
SELECT COUNT(*) AS empresas FROM empresas;
SELECT COUNT(*) AS usuarios FROM usuarios;
SELECT COUNT(*) AS propostas FROM propostas;
SELECT COUNT(*) AS contadores_invalidos FROM commercial_usage WHERE criadas < 0;
SELECT COUNT(*) AS registros_empresa_divergente FROM trial_proposals t
JOIN commercial_usage u ON u.id=t.usage_id
JOIN propostas p ON p.id=t.proposta_id
WHERE t.empresa_id <> u.empresa_id OR t.empresa_id <> p.empresa_id;
-- Contagens originais devem ser preservadas. Inicializacao do trial ocorre somente
-- quando o estado e periodo reais sao consultados no Central durante uso autorizado.