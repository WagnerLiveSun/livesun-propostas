-- LiveSun Propostas | MariaDB 11+ | atualizar b8215bc35a91 -> c20261112
-- BACKUP OBRIGATORIO. Manutencao SEM ESCRITAS. Importar arquivo completo.
-- Edite SOMENTE os valores abaixo antes de executar no banco correto.
-- Nunca use no Central/Comercial. Em qualquer erro, PARE; DDL nao tem rollback completo.
SET NAMES utf8mb4;
SET @ls_banco_esperado = 'u951548013_propostas';
SET @ls_backup_confirmado = 0; -- troque por 1 SOMENTE apos conferir seu backup


DELIMITER $$
DROP PROCEDURE IF EXISTS lsprop_cadastro_01$$
CREATE PROCEDURE lsprop_cadastro_01()
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
    IF VERSION() NOT LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED) < 11 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estes scripts exigem MariaDB 11 ou superior.';
    END IF;
    SET v_lock_name = CONCAT('lsprop_sql_', LEFT(SHA2(DATABASE(), 256), 32));
    SELECT GET_LOCK(v_lock_name, 0) INTO v_lock;
    IF COALESCE(v_lock, 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: outra atualizacao SQL em andamento.';
    END IF;
    IF (SELECT COUNT(*) FROM alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE BINARY version_num = BINARY 'b8215bc35a91') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: revisao incorreta; este arquivo exige b8215bc35a91.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE()
               AND table_name IN ('empresas', 'usuarios') AND engine <> 'InnoDB') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: empresas/usuarios precisam usar InnoDB.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name IN ('central_tenants','central_eventos_recebidos')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estrutura Central parcial/existente; revise antes de executar.';
    END IF;
CREATE TABLE central_tenants (
    empresa_id INTEGER NOT NULL,
    central_cliente_id INTEGER NOT NULL,
    payload JSON NOT NULL,
    assinatura_id INTEGER NOT NULL,
    versao INTEGER NOT NULL,
    valido_ate DATETIME,
    atualizado_em DATETIME NOT NULL,
    PRIMARY KEY (empresa_id),
    FOREIGN KEY(empresa_id) REFERENCES empresas (id),
    UNIQUE (central_cliente_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE central_eventos_recebidos (
    evento_id VARCHAR(50) NOT NULL,
    cliente_id INTEGER NOT NULL,
    assinatura_id INTEGER NOT NULL,
    versao INTEGER NOT NULL,
    recebido_em DATETIME NOT NULL,
    PRIMARY KEY (evento_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


    UPDATE alembic_version SET version_num = 'c20261112' WHERE version_num = 'b8215bc35a91';
    COMMIT;
    SELECT RELEASE_LOCK(v_lock_name) INTO v_release;
    SET v_lock = 0;
END$$
CALL lsprop_cadastro_01()$$
DROP PROCEDURE lsprop_cadastro_01$$
DELIMITER ;
SELECT DATABASE() AS banco_conferido, version_num AS revisao_apos_execucao FROM alembic_version;
