"""Gera pacote local revisável. Não conecta a provedores, banco ou e-mail."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT = {'.dockerignore', '.gitignore', '.env.example', 'Dockerfile', 'README.md',
                'render.yaml', 'requirements.txt', 'requirements-test.txt', 'run.py', 'wsgi.py',
                'Iniciar_LiveSun_Propostas.bat', 'Definicao_LiveSunPropostas.txt'}
ALLOWED_DIRS = {'src', 'config', 'migrations', 'deploy', 'scripts', 'tests'}
SECRET_PATTERNS = [re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(rb'xkeysib-[A-Za-z0-9_-]{25,}'),
    re.compile(rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}'),
    re.compile(rb'(?:mysql(?:\+pymysql)?|postgresql(?:\+psycopg2?)?)://[^\s:/{}]+:[^\s@{}]+@')]


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        return False
    if any(p in {'.git', '.venv', '__pycache__', '.pytest_cache', 'backups',
                 'storage', 'uploads', 'instance', 'migration-snapshots'} for p in path.parts):
        return False
    if any(p.startswith('.env') for p in path.parts) and name != '.env.example':
        return False
    if path.suffix.lower() in {'.log', '.pdf', '.db', '.sqlite', '.sqlite3', '.pyc', '.pem', '.key', '.pfx', '.zip'}:
        return False
    # Script histórico contém credencial de demonstração conhecida; não distribuir.
    if path.name in {'Key_Brevo.txt', 'sk_render.txt', '04_criar_demonstracao.sql'}:
        return False
    return name in ALLOWED_ROOT or (len(path.parts) > 1 and path.parts[0] in ALLOWED_DIRS)


def ensure_safe(name, data):
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        raise ValueError('Possível segredo detectado no arquivo: ' + name)


def build(root, destination):
    root, destination = root.resolve(), destination.resolve()
    if destination == root or root in destination.parents:
        raise ValueError('Destino deve ficar fora do repositório.')
    names = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--cached', '--others',
                                     '--exclude-standard', '-z']).decode('utf-8').split('\0')
    selected = sorted({name for name in names if name and allowed(name)})
    entries = []
    for name in selected:
        source = root / name
        if source.is_symlink() or not source.is_file() or root not in source.resolve().parents:
            raise ValueError('Arquivo ausente ou caminho não permitido: ' + name)
        data = source.read_bytes()
        # Exemplos e código de detecção contêm padrões ilustrativos, não credenciais.
        if name != 'scripts/preparar_publicacao.py':
            ensure_safe(name, data)
        entries.append((name, data))
    required = {'src/services/cadastro_central.py', 'src/routes/cadastro.py',
                'migrations/versions/e20261118a_solicitacao_central.py', 'deploy/PUBLICACAO_ENTREGAS_1_2.md'}
    if not required <= {name for name, _ in entries}:
        raise ValueError('Pacote incompleto: faltam arquivos necessários.')
    if destination.exists():
        raise ValueError('Destino já existe; não será sobrescrito.')
    base = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'base_commit': base,
        'source': 'working_tree_not_committed', 'deploy_executed': False,
        'files': [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in entries]}
    destination.mkdir(parents=True)
    archive = destination / 'livesun-propostas-entregas-1-2.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
        for name, data in entries:
            output.writestr(name, data)
    (destination / 'manifesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (destination / 'SHA256.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='ascii')
    with ZipFile(archive) as check:
        if check.testzip() is not None or len(check.namelist()) != len(entries):
            raise ValueError('Falha na integridade do pacote.')
        for entry in manifest['files']:
            if hashlib.sha256(check.read(entry['path'])).hexdigest() != entry['sha256']:
                raise ValueError('Hash divergente no pacote.')
    return archive, len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, required=True)
    args = parser.parse_args()
    try:
        archive, count = build(ROOT, args.destino)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Pacote não concluído. Revise a seleção e os pré-requisitos; não publique sem conferência.\n')
    print(f'Pacote local validado: {archive}\nArquivos: {count}\nSem commit, push, deploy ou migration.')


if __name__ == '__main__':
    main()