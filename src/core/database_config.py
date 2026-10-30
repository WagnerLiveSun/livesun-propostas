"""Fabrica central de URI de banco para LiveSun - Propostas."""

from __future__ import annotations

import os
from urllib.parse import quote_plus, urlparse


def _env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != '':
            return value
    return default


def _require(name: str, value: str | None) -> str:
    if value is None or str(value).strip() == '':
        raise RuntimeError(f'Variavel obrigatoria nao configurada: {name}')
    return value


def get_db_engine() -> str:
    raw = (_env_first('DB_ENGINE', 'DB_TYPE', default='mysql') or 'mysql').strip().lower()
    if raw == 'mysql':
        return 'mysql'
    if raw in {'postgres', 'postgresql'}:
        return 'postgresql'
    if raw == 'sqlite':
        return 'sqlite'
    raise RuntimeError('DB_ENGINE invalido. Use mysql, postgres, postgresql ou sqlite.')


def is_postgresql_configured() -> bool:
    return get_db_engine() == 'postgresql'


def _mysql_parts() -> dict[str, str]:
    user = _env_first('MYSQL_USER', 'DB_USER', default='root')
    password = _env_first('MYSQL_PASSWORD', 'DB_PASSWORD', default='')
    host = _env_first('MYSQL_HOST', 'DB_HOST', default='localhost')
    port = _env_first('MYSQL_PORT', 'DB_PORT', default='3306')
    database = _env_first('MYSQL_DATABASE', 'DB_NAME', default='livesun_propostas')
    return {
        'user': _require('MYSQL_USER/DB_USER', user),
        'password': password if password is not None else '',
        'host': _require('MYSQL_HOST/DB_HOST', host),
        'port': str(port),
        'database': _require('MYSQL_DATABASE/DB_NAME', database),
    }


def _postgres_parts() -> dict[str, str]:
    user = _env_first('POSTGRES_USER', 'DB_USER', default='livesun_propostas')
    password = _env_first('POSTGRES_PASSWORD', 'DB_PASSWORD')
    host = _env_first('POSTGRES_HOST', 'DB_HOST', default='127.0.0.1')
    database = _env_first('POSTGRES_DATABASE', 'DB_NAME', default='livesun_propostas')

    if os.getenv('POSTGRES_PORT'):
        port = os.getenv('POSTGRES_PORT')
    elif os.getenv('DB_PORT'):
        port = os.getenv('DB_PORT')
        if str(port) == '3306':
            port = '5432'
    else:
        port = '5432'

    return {
        'user': _require('POSTGRES_USER', user),
        'password': _require('POSTGRES_PASSWORD', password),
        'host': _require('POSTGRES_HOST/DB_HOST', host),
        'port': str(port),
        'database': _require('POSTGRES_DATABASE/DB_NAME', database),
    }


def build_database_uri() -> str:
    engine = get_db_engine()

    if engine == 'sqlite':
        return 'sqlite:///:memory:'

    if engine == 'mysql':
        parts = _mysql_parts()
        user = quote_plus(parts['user'])
        password = quote_plus(parts['password'])
        return (
            f"mysql+pymysql://{user}:{password}@{parts['host']}:{parts['port']}"
            f"/{parts['database']}?charset=utf8mb4"
        )

    parts = _postgres_parts()
    user = quote_plus(parts['user'])
    password = quote_plus(parts['password'])
    return (
        f"postgresql+psycopg2://{user}:{password}@{parts['host']}:{parts['port']}"
        f"/{parts['database']}?application_name=livesun_propostas"
    )


def is_postgresql_uri(uri: str | None) -> bool:
    if not uri:
        return False
    return str(uri).lower().startswith('postgresql')


def sqlalchemy_engine_options(database_uri: str) -> dict:
    options = {
        'pool_pre_ping': True,
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '1800')),
    }
    if is_postgresql_uri(database_uri):
        options.update(
            {
                'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
                'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '10')),
                'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '30')),
            }
        )
    return options


def missing_production_env() -> list[str]:
    missing = []
    if not os.getenv('SECRET_KEY'):
        missing.append('SECRET_KEY')
    if get_db_engine() == 'postgresql':
        checks = [
            ('POSTGRES_HOST', 'POSTGRES_HOST', 'DB_HOST'),
            ('POSTGRES_USER', 'POSTGRES_USER', 'DB_USER'),
            ('POSTGRES_PASSWORD', 'POSTGRES_PASSWORD', 'DB_PASSWORD'),
            ('POSTGRES_DATABASE', 'POSTGRES_DATABASE', 'DB_NAME'),
        ]
        for label, primary, fallback in checks:
            if not _env_first(primary, fallback):
                missing.append(label)
    else:
        checks = [
            ('DB_HOST', 'MYSQL_HOST', 'DB_HOST'),
            ('DB_USER', 'MYSQL_USER', 'DB_USER'),
            ('DB_PASSWORD', 'MYSQL_PASSWORD', 'DB_PASSWORD'),
            ('DB_NAME', 'MYSQL_DATABASE', 'DB_NAME'),
        ]
        for label, primary, fallback in checks:
            if not _env_first(primary, fallback):
                missing.append(label)
    return missing
