"""Valida scripts em dois bancos temporários, sem tocar no banco da aplicação."""
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv(ROOT / '.env')
from src.app import create_app
from src.extensions import db


def statements(text):
    return [part.strip() for part in '\n'.join(line for line in text.splitlines()
            if not line.lstrip().startswith('--')).split(';') if part.strip()]


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        admin = create_engine(db.engine.url.set(database=None))
        for scenario in ('fresh', 'upgrade'):
            name = 'livesun_sql_test_' + uuid4().hex[:12]
            engine = None
            try:
                with admin.connect() as connection:
                    connection.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
                engine = create_engine(db.engine.url.set(database=name))
                install = (ROOT / 'deploy/mysql/01_instalacao_banco_vazio.sql').read_text(encoding='utf-8')
                with engine.begin() as connection:
                    for statement in statements(install):
                        connection.exec_driver_sql(statement)
                    if scenario == 'upgrade':
                        connection.exec_driver_sql('ALTER TABLE propostas DROP COLUMN condicao_pagamento')
                        connection.exec_driver_sql('ALTER TABLE empresas DROP COLUMN logo_dados')
                        connection.exec_driver_sql("UPDATE alembic_version SET version_num='9eb8e86ea7b2'")
                        upgrade = (ROOT / 'deploy/mysql/02_atualizar_estrutura_inicial.sql').read_text(encoding='utf-8')
                        for statement in statements(upgrade):
                            connection.exec_driver_sql(statement)
                    assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == 'b8215bc35a91'
                    differences = compare_metadata(MigrationContext.configure(connection), db.metadata)
                    assert not differences, differences
                    assert connection.exec_driver_sql('SELECT COUNT(*) FROM usuarios').scalar() == 0
                    print(scenario, ': SQL válido, sem diferenças com os modelos e sem usuários padrão.')
                    seed = (ROOT / 'deploy/mysql/04_criar_demonstracao.sql').read_text(encoding='utf-8')
                    from werkzeug.security import check_password_hash
                    for attempt in range(2):
                        for statement in statements(seed):
                            connection.exec_driver_sql(statement)
                        user = connection.exec_driver_sql("SELECT u.senha_hash, u.perfil, e.nome FROM usuarios u JOIN empresas e ON e.id=u.empresa_id WHERE u.usuario='livesun'").one()
                        assert check_password_hash(user[0], 'livesun')
                        assert user[1] == 'admin' and user[2] == 'Demonstração'
                        assert connection.exec_driver_sql('SELECT COUNT(*) FROM usuarios').scalar() == 1
                        assert connection.exec_driver_sql('SELECT COUNT(*) FROM empresas').scalar() == 1
                    connection.exec_driver_sql("UPDATE usuarios SET senha_hash='senha_alterada_pelo_usuario'")
                    for statement in statements(seed):
                        connection.exec_driver_sql(statement)
                    assert connection.exec_driver_sql('SELECT senha_hash FROM usuarios').scalar() == 'senha_alterada_pelo_usuario'
                    print('Seed validado: administrador, hash, repetição sem duplicação e senha existente preservada.')
            finally:
                if engine:
                    engine.dispose()
                # O único alvo é o nome aleatório gerado acima para este teste.
                with admin.connect() as connection:
                    connection.exec_driver_sql(f'DROP DATABASE IF EXISTS `{name}`')
                print('Banco temporário removido:', name)
        admin.dispose()