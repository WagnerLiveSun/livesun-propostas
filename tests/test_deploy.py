"""Regressões de inicialização em container não-root."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_wsgi_import_without_file_logging(self):
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ.copy()
            env.update(PYTHONPATH=str(ROOT), FLASK_ENV='production',
                       SECRET_KEY='testing-production-only-key', DB_ENGINE='mysql',
                       MYSQL_HOST='127.0.0.1', MYSQL_DATABASE='testing_only',
                       MYSQL_USER='testing_only', MYSQL_PASSWORD='testing_only',
                       UPLOAD_FOLDER=folder)
            code = (
                'from unittest.mock import patch; '
                'import logging; '
                'guard = patch("logging.FileHandler", side_effect=PermissionError("read-only code directory")); '
                'guard.start(); '
                'from wsgi import app; '
                'assert not app.debug; '
                'assert app.config["SESSION_COOKIE_SECURE"]; '
                'assert app.test_client().get("/auth/login").status_code == 200; '
                'print("WSGI production boot OK")'
            )
            result = subprocess.run([sys.executable, '-c', code], cwd=folder,
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('WSGI production boot OK', result.stdout)
            self.assertFalse((Path(folder) / 'app_errors.log').exists())

    def test_docker_home_permissions_before_non_root_user(self):
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('chown -R livesun:livesun /app/storage /home/livesun', dockerfile)
        self.assertLess(dockerfile.index('chown -R livesun:livesun /app/storage /home/livesun'),
                        dockerfile.index('USER livesun'))