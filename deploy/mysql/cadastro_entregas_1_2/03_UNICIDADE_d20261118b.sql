-- LiveSun Propostas | MySQL 8.0.4+ | atualizar d20261118a -> d20261118b
-- BACKUP OBRIGATORIO. Manutencao SEM ESCRITAS. Importar arquivo completo.
-- Edite SOMENTE os valores abaixo antes de executar no banco correto.
-- Nunca use no Central/Comercial. Em qualquer erro, PARE; DDL nao tem rollback completo.
SET NAMES utf8mb4;
SET @ls_banco_esperado = 'PREENCHA_O_NOME_EXATO_DO_BANCO';
SET @ls_backup_confirmado = 0; -- troque por 1 SOMENTE apos conferir seu backup
SET @ls_unicidade_aprovada = 0; -- troque por 1 SOMENTE apos diagnostico sem conflitos

DELIMITER $$
DROP PROCEDURE IF EXISTS lsprop_cadastro_03$$
CREATE PROCEDURE lsprop_cadastro_03()
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
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE BINARY version_num = BINARY 'd20261118a') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: revisao incorreta; este arquivo exige d20261118a.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE()
               AND table_name IN ('empresas', 'usuarios') AND engine <> 'InnoDB') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: empresas/usuarios precisam usar InnoDB.';
    END IF;
    IF COALESCE(@ls_unicidade_aprovada, 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: confirme diagnostico e aprove unicidade no inicio do arquivo.';
    END IF;
    IF EXISTS (SELECT 1 FROM usuarios WHERE email IS NULL OR TRIM(email) = ''
               OR REGEXP_LIKE(email, '[^ -~]', 'c')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: email ausente/Unicode/controle exige revisao especifica.';
    END IF;
    IF EXISTS (SELECT 1 FROM (
        SELECT CONVERT(LOWER(TRIM(email)) USING utf8mb4) COLLATE utf8mb4_unicode_ci AS identidade
        FROM usuarios GROUP BY identidade HAVING COUNT(*) > 1
    ) AS duplicados) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: emails duplicados; nenhum cadastro sera unido ou apagado.';
    END IF;
    IF EXISTS (SELECT 1 FROM (
        SELECT NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '') AS identidade FROM empresas
        WHERE NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '') IS NOT NULL GROUP BY identidade HAVING COUNT(*) > 1
    ) AS duplicados) OR EXISTS (SELECT 1 FROM empresas WHERE CHAR_LENGTH(NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '')) > 14) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: documentos duplicados/longos; corrija somente com autorizacao.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
        AND ((table_name='usuarios' AND index_name='uq_usuarios_email_normalizado')
         OR (table_name='empresas' AND index_name='uq_empresas_documento_normalizado'))) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: indice novo ja existe; revisar possivel execucao parcial.';
    END IF;
    UPDATE usuarios SET email_normalizado = LOWER(TRIM(email));
    UPDATE empresas SET documento_normalizado = NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '');
    ALTER TABLE usuarios ADD CONSTRAINT uq_usuarios_email_normalizado UNIQUE (email_normalizado);
    ALTER TABLE empresas ADD CONSTRAINT uq_empresas_documento_normalizado UNIQUE (documento_normalizado);
    UPDATE alembic_version SET version_num = 'd20261118b' WHERE version_num = 'd20261118a';
    COMMIT;
    SELECT RELEASE_LOCK(v_lock_name) INTO v_release;
    SET v_lock = 0;
END$$
CALL lsprop_cadastro_03()$$
DROP PROCEDURE lsprop_cadastro_03$$
DELIMITER ;
SELECT DATABASE() AS banco_conferido, version_num AS revisao_apos_execucao FROM alembic_version;
