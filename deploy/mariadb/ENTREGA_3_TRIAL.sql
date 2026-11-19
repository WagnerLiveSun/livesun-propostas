-- Entrega 3 | Propostas | MariaDB 11.8.9 | aplicar UMA VEZ apos e20261118a
-- Backup antes; executar sem gravacoes simultaneas. Parar no primeiro erro.
SET NAMES utf8mb4;

CREATE TABLE commercial_usage (
    id INTEGER NOT NULL AUTO_INCREMENT,
    empresa_id INTEGER NOT NULL,
    assinatura_id INTEGER NOT NULL,
    versao INTEGER NOT NULL,
    data_inicio DATE NOT NULL,
    trial_ate DATE,
    data_fim DATE,
    suspensa_inadimplencia BOOL NOT NULL,
    valido_ate DATETIME NOT NULL,
    criadas INTEGER NOT NULL,
    inicializado BOOL NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_usage_empresa_assinatura UNIQUE (empresa_id, assinatura_id),
    FOREIGN KEY(empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE trial_proposals (
    proposta_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    usage_id INTEGER NOT NULL,
    PRIMARY KEY (proposta_id, usage_id),
    FOREIGN KEY(proposta_id) REFERENCES propostas (id),
    FOREIGN KEY(empresa_id) REFERENCES empresas (id),
    FOREIGN KEY(usage_id) REFERENCES commercial_usage (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_trial_proposals_empresa_id ON trial_proposals (empresa_id);

CREATE TABLE welcome_preferences (
    usuario_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    oculto BOOL NOT NULL,
    PRIMARY KEY (usuario_id),
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id),
    FOREIGN KEY(empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


UPDATE alembic_version SET version_num='f20261118a' WHERE version_num='e20261118a';
COMMIT;
SELECT version_num AS revisao FROM alembic_version;
