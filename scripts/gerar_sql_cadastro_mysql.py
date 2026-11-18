"""Exporta atualizações para phpMyAdmin; não abre conexão com banco."""
import importlib.util
from io import StringIO
from pathlib import Path
import re
import sys
import argparse
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TARGET = ROOT / 'deploy/mysql/cadastro_entregas_1_2'


def migration_sql(filename):
    output = StringIO()
    context = MigrationContext.configure(dialect_name='mysql', opts={'as_sql': True, 'output_buffer': output})
    spec = importlib.util.spec_from_file_location('export_migration', ROOT / 'migrations/versions' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    return re.sub(r'(CREATE TABLE\b.*?\n\))\s*;',
                  r'\1 ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;', sql, flags=re.S)


def wrapped(number, previous, revision, body, preconditions='', approval=False):
    name = f'lsprop_cadastro_{number}'
    return f"""-- LiveSun Propostas | MySQL 8.0.4+ | atualizar {previous} -> {revision}
-- BACKUP OBRIGATORIO. Manutencao SEM ESCRITAS. Importar arquivo completo.
-- Edite SOMENTE os valores abaixo antes de executar no banco correto.
-- Nunca use no Central/Comercial. Em qualquer erro, PARE; DDL nao tem rollback completo.
SET NAMES utf8mb4;
SET @ls_banco_esperado = 'PREENCHA_O_NOME_EXATO_DO_BANCO';
SET @ls_backup_confirmado = 0; -- troque por 1 SOMENTE apos conferir seu backup
{"SET @ls_unicidade_aprovada = 0; -- troque por 1 SOMENTE apos diagnostico sem conflitos" if approval else ''}

DELIMITER $$
DROP PROCEDURE IF EXISTS {name}$$
CREATE PROCEDURE {name}()
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
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE BINARY version_num = BINARY '{previous}') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: revisao incorreta; este arquivo exige {previous}.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE()
               AND table_name IN ('empresas', 'usuarios') AND engine <> 'InnoDB') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: empresas/usuarios precisam usar InnoDB.';
    END IF;
{preconditions}
{body}
    UPDATE alembic_version SET version_num = '{revision}' WHERE version_num = '{previous}';
    COMMIT;
    SELECT RELEASE_LOCK(v_lock_name) INTO v_release;
    SET v_lock = 0;
END$$
CALL {name}()$$
DROP PROCEDURE {name}$$
DELIMITER ;
SELECT DATABASE() AS banco_conferido, version_num AS revisao_apos_execucao FROM alembic_version;
"""


EMAIL = "LOWER(TRIM(email))"
DOC = "NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '')"


def generate(mariadb=False):
    global TARGET
    original_target = TARGET
    if mariadb:
        TARGET = ROOT / 'deploy/mariadb/cadastro_entregas_1_2'
    TARGET.mkdir(parents=True, exist_ok=True)
    diagnostic = f"""-- SOMENTE LEITURA. Selecione o banco PROPOSTAS; exporte backup antes de atualizar.
-- Exige MySQL 8.0.4+ (REGEXP_REPLACE). Nenhum dado pessoal e listado.
SELECT DATABASE() AS banco_atual, VERSION() AS versao_mysql;
SELECT version_num AS revisao_atual FROM alembic_version;
SELECT COUNT(*) AS empresas, SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) AS empresas_ativas FROM empresas;
SELECT COUNT(*) AS usuarios, SUM(CASE WHEN ativo = 1 THEN 1 ELSE 0 END) AS usuarios_ativos FROM usuarios;
SELECT COUNT(*) AS emails_ausentes FROM usuarios WHERE email IS NULL OR TRIM(email) = '';
-- ASCII visivel: casos Unicode/controles precisam de revisao especifica, sem normalizar as cegas.
SELECT COUNT(*) AS emails_para_revisao_especifica FROM usuarios
WHERE email IS NOT NULL AND REGEXP_LIKE(email, '[^ -~]', 'c');
SELECT COUNT(*) AS grupos_email_duplicado FROM (
 SELECT CONVERT({EMAIL} USING utf8mb4) COLLATE utf8mb4_unicode_ci AS identidade
 FROM usuarios GROUP BY identidade HAVING COUNT(*) > 1
) AS conflitos_email;
SELECT COUNT(*) AS grupos_documento_duplicado FROM (
 SELECT {DOC} AS identidade FROM empresas
 WHERE {DOC} IS NOT NULL GROUP BY identidade HAVING COUNT(*) > 1
) AS conflitos_documento;
SELECT COUNT(*) AS documentos_maiores_que_14 FROM empresas WHERE CHAR_LENGTH({DOC}) > 14;
SELECT COUNT(*) AS empresas_sem_documento FROM empresas WHERE {DOC} IS NULL;
SELECT COUNT(*) AS usuario_demonstrativo_ativo FROM usuarios WHERE usuario = 'livesun' AND ativo = 1;
SHOW GRANTS FOR CURRENT_USER;
"""
    (TARGET / '00_DIAGNOSTICO_SOMENTE_LEITURA.sql').write_text(diagnostic, encoding='utf-8')
    steps = [
        ('01', 'b8215bc35a91', 'c20261112', 'c20261112_central_integracao.py',
         """    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name IN ('central_tenants','central_eventos_recebidos')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estrutura Central parcial/existente; revise antes de executar.';
    END IF;""", '01_OPCIONAL_INTEGRACAO_c20261112.sql'),
        ('02', 'c20261112', 'd20261118a', 'd20261118a_cadastro_pendente.py',
         """    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE()
        AND ((table_name='empresas' AND column_name='documento_normalizado')
          OR (table_name='usuarios' AND column_name='email_normalizado')))
       OR EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name IN ('cadastros_publicos','tentativas_confirmacao_email')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estrutura de cadastro parcial/existente; nao reaplicar.';
    END IF;""", '02_CADASTRO_d20261118a.sql'),
        ('04', 'd20261118b', 'e20261118a', 'e20261118a_solicitacao_central.py',
         """    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE()
        AND table_name='empresas' AND column_name='razao_social_pendente')
       OR EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name='solicitacoes_central') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: estrutura Entrega 2 parcial/existente; nao reaplicar.';
    END IF;""", '04_SOLICITACAO_CENTRAL_e20261118a.sql')]
    for number, previous, revision, filename, check, output in steps:
        (TARGET / output).write_text(wrapped(number, previous, revision, migration_sql(filename), check), encoding='utf-8')
    preconditions = f"""    IF COALESCE(@ls_unicidade_aprovada, 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: confirme diagnostico e aprove unicidade no inicio do arquivo.';
    END IF;
    IF EXISTS (SELECT 1 FROM usuarios WHERE email IS NULL OR TRIM(email) = ''
               OR REGEXP_LIKE(email, '[^ -~]', 'c')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: email ausente/Unicode/controle exige revisao especifica.';
    END IF;
    IF EXISTS (SELECT 1 FROM (
        SELECT CONVERT({EMAIL} USING utf8mb4) COLLATE utf8mb4_unicode_ci AS identidade
        FROM usuarios GROUP BY identidade HAVING COUNT(*) > 1
    ) AS duplicados) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: emails duplicados; nenhum cadastro sera unido ou apagado.';
    END IF;
    IF EXISTS (SELECT 1 FROM (
        SELECT {DOC} AS identidade FROM empresas
        WHERE {DOC} IS NOT NULL GROUP BY identidade HAVING COUNT(*) > 1
    ) AS duplicados) OR EXISTS (SELECT 1 FROM empresas WHERE CHAR_LENGTH({DOC}) > 14) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: documentos duplicados/longos; corrija somente com autorizacao.';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
        AND ((table_name='usuarios' AND index_name='uq_usuarios_email_normalizado')
         OR (table_name='empresas' AND index_name='uq_empresas_documento_normalizado'))) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PARE: indice novo ja existe; revisar possivel execucao parcial.';
    END IF;"""
    body = f"""    UPDATE usuarios SET email_normalizado = {EMAIL};
    UPDATE empresas SET documento_normalizado = {DOC};
    ALTER TABLE usuarios ADD CONSTRAINT uq_usuarios_email_normalizado UNIQUE (email_normalizado);
    ALTER TABLE empresas ADD CONSTRAINT uq_empresas_documento_normalizado UNIQUE (documento_normalizado);"""
    (TARGET / '03_UNICIDADE_d20261118b.sql').write_text(wrapped('03', 'd20261118a', 'd20261118b', body, preconditions, True), encoding='utf-8')
    verification = """-- SOMENTE LEITURA. Resultado esperado: revisao e20261118a; divergencias=0.
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
"""
    (TARGET / '05_VERIFICACAO_FINAL.sql').write_text(verification, encoding='utf-8')
    if mariadb:
        for path in TARGET.glob('*.sql'):
            content = path.read_text(encoding='utf-8')
            content = content.replace("REGEXP_LIKE(email, '[^ -~]', 'c')", "(email REGEXP '[^ -~]')")
            content = content.replace("IF VERSION() LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED) < 8 THEN",
                "IF VERSION() NOT LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED) < 11 THEN")
            content = content.replace('PARE: scripts homologados para MySQL 8; nao usar em MariaDB/MySQL 5.',
                'PARE: estes scripts exigem MariaDB 11 ou superior.')
            content = content.replace('MySQL 8.0.4+', 'MariaDB 11+')
            content = content.replace('PREENCHA_O_NOME_EXATO_DO_BANCO', 'u951548013_propostas')
            path.write_text(content, encoding='utf-8')
    print('Scripts gerados offline:', TARGET)
    TARGET = original_target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mariadb', action='store_true', help='Gera variante MariaDB 11+ em pasta separada.')
    generate(mariadb=parser.parse_args().mariadb)