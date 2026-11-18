-- LiveSun Propostas | MariaDB 11+ | atualizar c20261112 -> d20261118a
-- BACKUP OBRIGATORIO. Manutencao SEM ESCRITAS. Importar arquivo completo.
-- Edite SOMENTE os valores abaixo antes de executar no banco correto.
-- Nunca use no Central/Comercial. Em qualquer erro, PARE; DDL nao tem rollback completo.
SET NAMES utf8mb4;
SET @ls_banco_esperado = 'u951548013_propostas';
SET @ls_backup_confirmado = 0; -- troque por 1 SOMENTE apos conferir seu backup


DELIMITER $$
DROP PROCEDURE IF EXISTS lsprop_cadastro_02$$
CREATE PROCEDURE lsprop_cadastro_02()
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
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE BINARY version_num = BINARY 'c20261112') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: revisao incorreta; este arquivo exige c20261112.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE()
               AND table_name IN ('empresas', 'usuarios') AND engine <> 'InnoDB') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: empresas/usuarios precisam usar InnoDB.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE()
        AND ((table_name='empresas' AND column_name='documento_normalizado')
          OR (table_name='usuarios' AND column_name='email_normalizado')))
       OR EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name IN ('cadastros_publicos','tentativas_confirmacao_email')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estrutura de cadastro parcial/existente; nao reaplicar.';
    END IF;
ALTER TABLE empresas ADD COLUMN documento_normalizado VARCHAR(14);

ALTER TABLE usuarios ADD COLUMN email_normalizado VARCHAR(120);

CREATE TABLE cadastros_publicos (
    id INTEGER NOT NULL AUTO_INCREMENT,
    empresa_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    tipo_pessoa VARCHAR(2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    token_hash VARCHAR(64),
    expira_em DATETIME,
    confirmado_em DATETIME,
    proximo_envio_em DATETIME,
    termos_versao VARCHAR(100) NOT NULL,
    privacidade_versao VARCHAR(100) NOT NULL,
    aceite_em DATETIME NOT NULL,
    criado_em DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (empresa_id),
    FOREIGN KEY(empresa_id) REFERENCES empresas (id),
    UNIQUE (usuario_id),
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id),
    UNIQUE (token_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE tentativas_confirmacao_email (
    id INTEGER NOT NULL AUTO_INCREMENT,
    cadastro_id INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    criada_em DATETIME NOT NULL,
    concluida_em DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(cadastro_id) REFERENCES cadastros_publicos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_tentativas_confirmacao_email_cadastro_id ON tentativas_confirmacao_email (cadastro_id);


    UPDATE alembic_version SET version_num = 'd20261118a' WHERE version_num = 'c20261112';
    COMMIT;
    SELECT RELEASE_LOCK(v_lock_name) INTO v_release;
    SET v_lock = 0;
END$$
CALL lsprop_cadastro_02()$$
DROP PROCEDURE lsprop_cadastro_02$$
DELIMITER ;
SELECT DATABASE() AS banco_conferido, version_num AS revisao_apos_execucao FROM alembic_version;
