-- SOMENTE LEITURA. Resultado esperado: revisao e20261118a; divergencias=0.
SELECT DATABASE() AS banco_conferido, version_num AS revisao_final FROM alembic_version;
SELECT table_name, engine FROM information_schema.tables WHERE table_schema=DATABASE()
 AND table_name IN ('central_tenants','central_eventos_recebidos','cadastros_publicos',
 'tentativas_confirmacao_email','solicitacoes_central') ORDER BY table_name;
SELECT table_name, column_name, column_type, is_nullable, column_default
 FROM information_schema.columns WHERE table_schema=DATABASE()
 AND ((table_name='empresas' AND column_name IN ('documento_normalizado','razao_social_pendente'))
 OR (table_name='usuarios' AND column_name='email_normalizado'));
SELECT table_name, index_name, non_unique FROM information_schema.statistics
 WHERE table_schema=DATABASE() AND index_name IN
 ('uq_usuarios_email_normalizado','uq_empresas_documento_normalizado');
SELECT COUNT(*) AS divergencias_email FROM usuarios
 WHERE NOT (BINARY email_normalizado <=> BINARY LOWER(TRIM(email)));
SELECT COUNT(*) AS divergencias_documento FROM empresas
 WHERE NOT (BINARY documento_normalizado <=> BINARY NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf,''),'[^0-9]',''),''));
SELECT COUNT(*) AS empresas FROM empresas;
SELECT COUNT(*) AS usuarios FROM usuarios;
-- As contagens de empresas/usuarios devem ser iguais as do diagnostico inicial.
