-- LiveSun - Propostas | SQL gerado das migrations, sem dados locais.
-- SOMENTE revisão 9eb8e86ea7b2: adiciona condição de pagamento e atualiza Alembic.
-- Selecione o banco correto ANTES de importar. Faça backup antes de atualizar.
-- Não inclui CREATE DATABASE, USE, usuários MySQL ou credenciais.
-- Executar uma única vez. Não ignorar erros. DDL MySQL não é transacional.

SET NAMES utf8mb4;

-- Running upgrade 9eb8e86ea7b2 -> 73bd0d15d1db

ALTER TABLE propostas ADD COLUMN condicao_pagamento VARCHAR(500);

UPDATE alembic_version SET version_num='73bd0d15d1db' WHERE alembic_version.version_num = '9eb8e86ea7b2';

