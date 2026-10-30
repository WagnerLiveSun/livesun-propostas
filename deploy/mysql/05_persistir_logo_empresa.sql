-- Fazer backup e executar UMA VEZ antes de implantar o código com logo no banco.
-- Não reaplicar o script 01 em bancos existentes.
ALTER TABLE empresas ADD COLUMN logo_dados MEDIUMBLOB NULL;
UPDATE alembic_version SET version_num = 'b8215bc35a91'
WHERE version_num = '73bd0d15d1db';
-- Depois do deploy: Empresa -> selecionar logo -> Salvar (uma única vez).