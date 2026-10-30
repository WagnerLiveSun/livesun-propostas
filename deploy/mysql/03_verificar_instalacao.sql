-- Somente leitura. Executar no banco selecionado depois da importação.
SELECT DATABASE() AS banco_selecionado, VERSION() AS versao_servidor;
SELECT version_num AS revisao_esperada_73bd0d15d1db FROM alembic_version;
SELECT table_name, engine, table_collation
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;
SELECT column_name, column_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'propostas'
  AND column_name = 'condicao_pagamento';
SELECT COUNT(*) AS empresas FROM empresas;
SELECT COUNT(*) AS usuarios FROM usuarios;