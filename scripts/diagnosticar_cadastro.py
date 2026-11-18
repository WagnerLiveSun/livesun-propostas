"""Executar somente após autorizar uma base; não carrega .env ou aplicação Flask."""
import argparse
import json
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.cadastro_diagnostico import diagnose


def main():
    parser = argparse.ArgumentParser(description='Diagnóstico SELECT-only e agregado, sem limpeza.')
    parser.add_argument('--banco-autorizado', required=True, help='Nome exato do banco autorizado.')
    args = parser.parse_args()
    uri = os.getenv('REGISTRATION_DIAGNOSTIC_DATABASE_URL', '')
    if not uri:
        parser.error('Configure REGISTRATION_DIAGNOSTIC_DATABASE_URL com credencial somente leitura.')
    engine = None
    try:
        engine = create_engine(uri, hide_parameters=True, echo=False)
        if engine.url.database != args.banco_autorizado or engine.dialect.name not in ('mysql', 'postgresql', 'sqlite'):
            raise ValueError()
        with engine.connect() as connection:
            if engine.dialect.name == 'postgresql':
                connection.execute(text('SET TRANSACTION READ ONLY'))
            elif engine.dialect.name == 'mysql':
                connection.execute(text('START TRANSACTION READ ONLY'))
            else:
                connection.execute(text('PRAGMA query_only = ON'))
            result = diagnose(connection)
            connection.rollback()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception:
        print('Diagnóstico não concluído. Confira autorização, destino e permissões, sem expor credenciais.', file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())