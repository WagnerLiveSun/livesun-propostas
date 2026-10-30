-- Executar depois da instalação das tabelas, no banco selecionado no phpMyAdmin.
-- Empresa: Demonstração | Usuário: livesun | Senha: livesun | Perfil: Administrador.
-- ATENÇÃO: acesso temporário de demonstração. Troque a senha antes do uso público.
-- Não redefine senha/perfil nem move um usuário que já exista.
-- Execute sem outros cadastros simultâneos durante esta configuração inicial.

SET NAMES utf8mb4;
START TRANSACTION;

INSERT INTO empresas (nome, usuarios_maximos, ativo, data_criacao)
SELECT 'Demonstração', 3, 1, UTC_TIMESTAMP()
WHERE NOT EXISTS (SELECT 1 FROM empresas WHERE nome = 'Demonstração')
  AND NOT EXISTS (SELECT 1 FROM usuarios WHERE usuario = 'livesun');

SET @empresa_demo_id = (
    SELECT id FROM empresas WHERE nome = 'Demonstração' AND ativo = 1 ORDER BY id LIMIT 1
);

INSERT INTO usuarios
    (empresa_id, nome, email, usuario, senha_hash, perfil, ativo, tema_preferido, data_criacao)
SELECT @empresa_demo_id, 'LiveSun', 'livesun@example.invalid', 'livesun',
    'scrypt:32768:8:1$XWNYZs711R6NEV7L$3a438649a55724eb8a96d3f66b0d38bed27021520ab0eb4921921ed10d77a5deda63cbaf44b5ebc5108c986bf2e593735e45ada464634e46c06dffef8f34b823',
    'admin', 1, 'moonlight', UTC_TIMESTAMP()
WHERE @empresa_demo_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM usuarios WHERE usuario = 'livesun')
  AND NOT EXISTS (SELECT 1 FROM usuarios WHERE empresa_id = @empresa_demo_id AND email = 'livesun@example.invalid')
  AND (SELECT COUNT(*) FROM usuarios WHERE empresa_id = @empresa_demo_id)
      < (SELECT usuarios_maximos FROM empresas WHERE id = @empresa_demo_id);

COMMIT;

-- Confira: a empresa deve ser Demonstração, perfil admin e ambos ativos.
-- Se já existir outro cadastro livesun, ele será mostrado SEM ser alterado.
SELECT e.nome AS empresa, u.usuario, u.perfil, u.ativo AS usuario_ativo,
       e.ativo AS empresa_ativa, u.email
FROM usuarios u JOIN empresas e ON e.id = u.empresa_id
WHERE u.usuario = 'livesun';