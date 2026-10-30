-- LiveSun - Propostas | SQL gerado das migrations, sem dados locais.
-- SOMENTE BANCO VAZIO: cria o esquema completo, incluindo condição de pagamento e Alembic.
-- Selecione o banco correto ANTES de importar. Faça backup antes de atualizar.
-- Não inclui CREATE DATABASE, USE, usuários MySQL ou credenciais.
-- Executar uma única vez. Não ignorar erros. DDL MySQL não é transacional.

SET NAMES utf8mb4;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Running upgrade  -> 9eb8e86ea7b2

CREATE TABLE empresas (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    nome VARCHAR(150) NOT NULL, 
    razao_social VARCHAR(150), 
    cnpj_cpf VARCHAR(18), 
    endereco VARCHAR(255), 
    telefone VARCHAR(20), 
    email VARCHAR(120), 
    logo VARCHAR(255), 
    usuarios_maximos INTEGER, 
    ativo BOOL, 
    data_criacao DATETIME, 
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE clientes (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    empresa_id INTEGER NOT NULL, 
    nome VARCHAR(150) NOT NULL, 
    telefone VARCHAR(20) NOT NULL, 
    cnpj_cpf VARCHAR(18), 
    email VARCHAR(120), 
    contato VARCHAR(150), 
    endereco VARCHAR(255), 
    ativo BOOL, 
    data_criacao DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_clientes_empresa_id ON clientes (empresa_id);

CREATE TABLE produtos_servicos (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    empresa_id INTEGER NOT NULL, 
    codigo VARCHAR(50), 
    descricao VARCHAR(255) NOT NULL, 
    tipo VARCHAR(1), 
    unidade VARCHAR(20), 
    valor_unitario NUMERIC(15, 2), 
    ativo BOOL, 
    data_criacao DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_produtos_servicos_empresa_id ON produtos_servicos (empresa_id);

CREATE TABLE usuarios (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    empresa_id INTEGER NOT NULL, 
    nome VARCHAR(150) NOT NULL, 
    email VARCHAR(120) NOT NULL, 
    usuario VARCHAR(80) NOT NULL, 
    senha_hash VARCHAR(255) NOT NULL, 
    perfil VARCHAR(20), 
    ativo BOOL, 
    tema_preferido VARCHAR(20), 
    data_criacao DATETIME, 
    reset_token_hash VARCHAR(64), 
    reset_expira_em DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(empresa_id) REFERENCES empresas (id), 
    CONSTRAINT uq_usuario_empresa_email UNIQUE (empresa_id, email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_usuarios_email ON usuarios (email);

CREATE INDEX ix_usuarios_empresa_id ON usuarios (empresa_id);

CREATE INDEX ix_usuarios_reset_token_hash ON usuarios (reset_token_hash);

CREATE UNIQUE INDEX ix_usuarios_usuario ON usuarios (usuario);

CREATE TABLE auditoria (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    empresa_id INTEGER NOT NULL, 
    usuario_id INTEGER, 
    acao VARCHAR(100) NOT NULL, 
    entidade VARCHAR(50) NOT NULL, 
    entidade_id INTEGER, 
    detalhes TEXT, 
    data_hora DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(empresa_id) REFERENCES empresas (id), 
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_auditoria_empresa_id ON auditoria (empresa_id);

CREATE INDEX ix_auditoria_usuario_id ON auditoria (usuario_id);

CREATE TABLE propostas (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    empresa_id INTEGER NOT NULL, 
    usuario_id INTEGER, 
    cliente_id INTEGER, 
    cliente_nome VARCHAR(150) NOT NULL, 
    cliente_telefone VARCHAR(20) NOT NULL, 
    cliente_cnpj_cpf VARCHAR(18), 
    cliente_email VARCHAR(120), 
    cliente_contato VARCHAR(150), 
    cliente_endereco VARCHAR(255), 
    aprovado_por INTEGER, 
    aprovado_em DATETIME, 
    numero VARCHAR(50) NOT NULL, 
    data_emissao DATE NOT NULL, 
    validade DATE, 
    status VARCHAR(20), 
    subtotal NUMERIC(15, 2), 
    desconto NUMERIC(15, 2), 
    impostos NUMERIC(15, 2), 
    outros_acrescimos NUMERIC(15, 2), 
    total NUMERIC(15, 2), 
    total_extenso VARCHAR(500), 
    observacoes TEXT, 
    data_criacao DATETIME, 
    data_atualizacao DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(aprovado_por) REFERENCES usuarios (id), 
    FOREIGN KEY(cliente_id) REFERENCES clientes (id), 
    FOREIGN KEY(empresa_id) REFERENCES empresas (id), 
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
    CONSTRAINT uq_proposta_empresa_numero UNIQUE (empresa_id, numero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_propostas_cliente_id ON propostas (cliente_id);

CREATE INDEX ix_propostas_empresa_id ON propostas (empresa_id);

CREATE INDEX ix_propostas_usuario_id ON propostas (usuario_id);

CREATE TABLE envios_email (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    empresa_id INTEGER NOT NULL, 
    proposta_id INTEGER, 
    destinatario VARCHAR(120) NOT NULL, 
    assunto VARCHAR(255), 
    mensagem TEXT, 
    status VARCHAR(20), 
    data_envio DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(empresa_id) REFERENCES empresas (id), 
    FOREIGN KEY(proposta_id) REFERENCES propostas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_envios_email_empresa_id ON envios_email (empresa_id);

CREATE INDEX ix_envios_email_proposta_id ON envios_email (proposta_id);

CREATE TABLE proposta_itens (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    proposta_id INTEGER NOT NULL, 
    sequencial INTEGER, 
    codigo VARCHAR(50), 
    descricao VARCHAR(255) NOT NULL, 
    quantidade NUMERIC(10, 3) NOT NULL, 
    unidade VARCHAR(20), 
    valor_unitario NUMERIC(15, 2) NOT NULL, 
    valor_total NUMERIC(15, 2), 
    PRIMARY KEY (id), 
    FOREIGN KEY(proposta_id) REFERENCES propostas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_proposta_itens_proposta_id ON proposta_itens (proposta_id);

INSERT INTO alembic_version (version_num) VALUES ('9eb8e86ea7b2');

-- Running upgrade 9eb8e86ea7b2 -> 73bd0d15d1db

ALTER TABLE propostas ADD COLUMN condicao_pagamento VARCHAR(500);

UPDATE alembic_version SET version_num='73bd0d15d1db' WHERE alembic_version.version_num = '9eb8e86ea7b2';

-- Running upgrade 73bd0d15d1db -> b8215bc35a91

ALTER TABLE empresas ADD COLUMN logo_dados MEDIUMBLOB;

UPDATE alembic_version SET version_num='b8215bc35a91' WHERE alembic_version.version_num = '73bd0d15d1db';

