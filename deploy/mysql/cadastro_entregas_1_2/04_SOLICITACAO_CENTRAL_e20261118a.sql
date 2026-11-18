-- LiveSun Propostas | MySQL 8.0.4+ | atualizar d20261118b -> e20261118a
-- BACKUP OBRIGATORIO. Manutencao SEM ESCRITAS. Importar arquivo completo.
-- Edite SOMENTE os valores abaixo antes de executar no banco correto.
-- Nunca use no Central/Comercial. Em qualquer erro, PARE; DDL nao tem rollback completo.
SET NAMES utf8mb4;
SET @ls_banco_esperado = 'PREENCHA_O_NOME_EXATO_DO_BANCO';
SET @ls_backup_confirmado = 0; -- troque por 1 SOMENTE apos conferir seu backup


DELIMITER $$
DROP PROCEDURE IF EXISTS lsprop_cadastro_04$$
CREATE PROCEDURE lsprop_cadastro_04()
SQL SECURITY INVOKER
BEGIN
    DECLARE v_lock INT DEFAULT 0;
    DECLARE v_release INT DEFAULT 0;
    DECLARE v_lock_name VARCHAR(64);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        IF v_lock = 1 THEN
            SELECT RELEASE_LOCK(v_lock_name) INTO v_release;
        END IF;
        RESIGNAL;
    END;
    IF DATABASE() IS NULL OR NOT (BINARY DATABASE() = BINARY @ls_banco_esperado)
       OR COALESCE(@ls_backup_confirmado, 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: confirme banco esperado e backup no inicio do arquivo.';
    END IF;
    IF VERSION() LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED) < 8 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: scripts homologados para MySQL 8; nao usar em MariaDB/MySQL 5.';
    END IF;
    SET v_lock_name = CONCAT('lsprop_sql_', LEFT(SHA2(DATABASE(), 256), 32));
    SELECT GET_LOCK(v_lock_name, 0) INTO v_lock;
    IF COALESCE(v_lock, 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: outra atualizacao SQL em andamento.';
    END IF;
    IF (SELECT COUNT(*) FROM alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE BINARY version_num = BINARY 'd20261118b') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: revisao incorreta; este arquivo exige d20261118b.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE()
               AND table_name IN ('empresas', 'usuarios') AND engine <> 'InnoDB') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: empresas/usuarios precisam usar InnoDB.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE()
        AND table_name='empresas' AND column_name='razao_social_pendente')
       OR EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name='solicitacoes_central') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estrutura Entrega 2 parcial/existente; nao reaplicar.';
    END IF;
ALTER TABLE empresas ADD COLUMN razao_social_pendente BOOL NOT NULL DEFAULT false;

CREATE TABLE solicitacoes_central (
    id INTEGER NOT NULL AUTO_INCREMENT,
    cadastro_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    evento_id VARCHAR(36) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(30) NOT NULL,
    tentativas INTEGER NOT NULL,
    ultima_tentativa_em DATETIME,
    proxima_tentativa_em DATETIME,
    lease_id VARCHAR(32),
    lease_ate DATETIME,
    erro_categoria VARCHAR(40),
    central_solicitacao_id INTEGER,
    criada_em DATETIME NOT NULL,
    recebida_em DATETIME,
    PRIMARY KEY (id),
    UNIQUE (cadastro_id),
    FOREIGN KEY(cadastro_id) REFERENCES cadastros_publicos (id),
    UNIQUE (empresa_id),
    FOREIGN KEY(empresa_id) REFERENCES empresas (id),
    UNIQUE (evento_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


    UPDATE alembic_version SET version_num = 'e20261118a' WHERE version_num = 'd20261118b';
    COMMIT;
    SELECT RELEASE_LOCK(v_lock_name) INTO v_release;
    SET v_lock = 0;
END$$
CALL lsprop_cadastro_04()$$
DROP PROCEDURE lsprop_cadastro_04$$
DELIMITER ;
SELECT DATABASE() AS banco_conferido, version_num AS revisao_apos_execucao FROM alembic_version;
