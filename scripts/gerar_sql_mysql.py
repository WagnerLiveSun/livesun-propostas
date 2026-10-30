r"""Gera SQL a partir das migrations reais, sem consultar ou modificar bancos.

Executar na raiz: .venv\Scripts\python.exe scripts\gerar_sql_mysql.py
"""
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'deploy' / 'mysql'


def export_sql(filename, revision, description):
    environment = os.environ.copy()
    environment.update(FLASK_ENV='development', DB_ENGINE='mysql', MYSQL_HOST='127.0.0.1',
                       MYSQL_DATABASE='sql_generation_only', MYSQL_USER='sql_generation_only', MYSQL_PASSWORD='')
    result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'run', 'db', 'upgrade',
                             '--sql', revision], cwd=ROOT, env=environment, capture_output=True, check=True)
    sql = result.stdout.decode('utf-8').replace('\r\n', '\n')
    # Collation compatível com MySQL/MariaDB; não depender do padrão do servidor.
    if filename.startswith('01_'):
        sql = re.sub(r'(CREATE TABLE\b.*?\n\));',
                     r'\1 ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
                     sql, flags=re.S)
    header = ('-- LiveSun - Propostas | SQL gerado das migrations, sem dados locais.\n'
              f'-- {description}\n'
              '-- Selecione o banco correto ANTES de importar. Faça backup antes de atualizar.\n'
              '-- Não inclui CREATE DATABASE, USE, usuários MySQL ou credenciais.\n'
              '-- Executar uma única vez. Não ignorar erros. DDL MySQL não é transacional.\n\n'
              'SET NAMES utf8mb4;\n\n')
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / filename).write_text(header + sql, encoding='utf-8')
    print('Gerado:', TARGET / filename)


if __name__ == '__main__':
    export_sql('01_instalacao_banco_vazio.sql', 'base:head',
               'SOMENTE BANCO VAZIO: cria o esquema completo, incluindo condição de pagamento e Alembic.')
    export_sql('02_atualizar_estrutura_inicial.sql', '9eb8e86ea7b2:head',
               'SOMENTE revisão 9eb8e86ea7b2: adiciona condição de pagamento e atualiza Alembic.')