import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preparar_publicacao_test', ROOT / 'scripts/preparar_publicacao.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('name', ['.env', '.env.render', 'deploy/.env.production.example',
    'Key_Brevo.txt', 'sk_render.txt', 'backups/propostas.sql', 'uploads/logo.png',
    'src/__pycache__/app.pyc', '../segredo.py', '/segredo.py', 'src/arquivo.pdf',
    'deploy/mysql/04_criar_demonstracao.sql'])
def test_private_files_excluded(name):
    assert not module.allowed(name)


@pytest.mark.parametrize('name', ['.env.example', 'src/app.py', 'Dockerfile',
    'migrations/versions/e20261118a_solicitacao_central.py', 'deploy/PUBLICACAO_ENTREGAS_1_2.md'])
def test_required_files_allowed(name):
    assert module.allowed(name)


def test_secret_scan_redacts_content():
    with pytest.raises(ValueError) as result:
        module.ensure_safe('src/example.py', b'-----BEGIN ' + b'PRIVATE KEY-----')
    assert 'BEGIN' not in str(result.value)


def test_output_must_be_outside_repo(tmp_path):
    with pytest.raises(ValueError):
        module.build(tmp_path, tmp_path / 'release')