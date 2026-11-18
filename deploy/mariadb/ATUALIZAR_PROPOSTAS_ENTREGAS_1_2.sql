-- LiveSun Propostas | MariaDB 11.8.9
-- Aplicar UMA VEZ no banco u951548013_propostas, partindo de c20261112.
-- Fazer backup antes e executar sem gravacoes simultaneas no aplicativo.
-- DBeaver: executar script completo (Alt+X), parando no primeiro erro.
-- Nao executar junto dos arquivos incrementais anteriores.
-- DDL MariaDB nao possui rollback completo; nao ignorar erros.

USE u951548013_propostas;
SET NAMES utf8mb4;

-- Entrega 1: cadastro e confirmacao de e-mail.
ALTER TABLE empresas ADD COLUMN documento_normalizado VARCHAR(14);
ALTER TABLE usuarios ADD COLUMN email_normalizado VARCHAR(120);

CREATE TABLE cadastros_publicos (
    id INT NOT NULL AUTO_INCREMENT,
    empresa_id INT NOT NULL,
    usuario_id INT NOT NULL,
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
    UNIQUE (usuario_id),
    UNIQUE (token_hash),
    FOREIGN KEY (empresa_id) REFERENCES empresas (id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE tentativas_confirmacao_email (
    id INT NOT NULL AUTO_INCREMENT,
    cadastro_id INT NOT NULL,
    status VARCHAR(30) NOT NULL,
    criada_em DATETIME NOT NULL,
    concluida_em DATETIME,
    PRIMARY KEY (id),
    INDEX ix_tentativas_confirmacao_email_cadastro_id (cadastro_id),
    FOREIGN KEY (cadastro_id) REFERENCES cadastros_publicos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE alembic_version SET version_num = 'd20261118a'
WHERE version_num = 'c20261112';
COMMIT;

-- Identidades normalizadas: indices recusam duplicidades, sem excluir registros.
UPDATE usuarios SET email_normalizado = LOWER(TRIM(email));
UPDATE empresas SET documento_normalizado =
    NULLIF(REGEXP_REPLACE(COALESCE(cnpj_cpf, ''), '[^0-9]', ''), '');

ALTER TABLE usuarios
    ADD CONSTRAINT uq_usuarios_email_normalizado UNIQUE (email_normalizado);
ALTER TABLE empresas
    ADD CONSTRAINT uq_empresas_documento_normalizado UNIQUE (documento_normalizado);

UPDATE alembic_version SET version_num = 'd20261118b'
WHERE version_num = 'd20261118a';
COMMIT;

-- Entrega 2: solicita novos vinculos por API; nao acessa banco do Central.
ALTER TABLE empresas
    ADD COLUMN razao_social_pendente BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE solicitacoes_central (
    id INT NOT NULL AUTO_INCREMENT,
    cadastro_id INT NOT NULL,
    empresa_id INT NOT NULL,
    evento_id VARCHAR(36) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(30) NOT NULL,
    tentativas INT NOT NULL,
    ultima_tentativa_em DATETIME,
    proxima_tentativa_em DATETIME,
    lease_id VARCHAR(32),
    lease_ate DATETIME,
    erro_categoria VARCHAR(40),
    central_solicitacao_id INT,
    criada_em DATETIME NOT NULL,
    recebida_em DATETIME,
    PRIMARY KEY (id),
    UNIQUE (cadastro_id),
    UNIQUE (empresa_id),
    UNIQUE (evento_id),
    FOREIGN KEY (cadastro_id) REFERENCES cadastros_publicos (id),
    FOREIGN KEY (empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE alembic_version SET version_num = 'e20261118a'
WHERE version_num = 'd20261118b';
COMMIT;

-- Resultado esperado: u951548013_propostas | e20261118a.
SELECT DATABASE() AS banco, version_num AS revisao_final FROM alembic_version;
