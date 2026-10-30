import os
import re
from datetime import timedelta
from pathlib import Path

from src.core.database_config import (
    build_database_uri,
    get_db_engine,
    sqlalchemy_engine_options,
)

BASE_DIR = Path(__file__).parent.parent


def brevo_api_key():
    key = os.environ.get('BREVO_API_KEY', '').strip()
    if key:
        return key
    path = BASE_DIR / 'Key_Brevo.txt'
    if not path.is_file():
        return ''
    text = path.read_text(encoding='utf-8-sig').strip()
    match = re.search(r'xkeysib-[A-Za-z0-9_-]+', text)
    return match.group() if match else text


class Config:
    """Base configuration"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.environ.get('SQLALCHEMY_ECHO', 'False').lower() == 'true'

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Upload files
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Database (URI centralizada; DB_ENGINE ou DB_TYPE. Alias MYSQL_*/POSTGRES_*/DB_*)
    DB_TYPE = os.environ.get('DB_ENGINE', os.environ.get('DB_TYPE', 'mysql'))
    DB_HOST = os.environ.get('DB_HOST', os.environ.get('MYSQL_HOST', os.environ.get('POSTGRES_HOST', 'localhost')))
    DB_PORT = int(os.environ.get('DB_PORT', os.environ.get('MYSQL_PORT', os.environ.get('POSTGRES_PORT', '3306'))))
    DB_USER = os.environ.get('DB_USER', os.environ.get('MYSQL_USER', os.environ.get('POSTGRES_USER', 'root')))
    DB_PASSWORD = os.environ.get('DB_PASSWORD', os.environ.get('MYSQL_PASSWORD', os.environ.get('POSTGRES_PASSWORD', '')))
    DB_NAME = os.environ.get('DB_NAME', os.environ.get('MYSQL_DATABASE', os.environ.get('POSTGRES_DATABASE', 'livesun_propostas')))
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = sqlalchemy_engine_options(SQLALCHEMY_DATABASE_URI)
    DB_ENGINE = get_db_engine()

    # Server
    SERVER_HOST = os.environ.get('SERVER_HOST', '0.0.0.0')
    SERVER_PORT = int(os.environ.get('SERVER_PORT', 5000))

    # Security
    SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))

    # Brevo
    BREVO_API_KEY = brevo_api_key()
    BREVO_RESET_PASSWORD_TEMPLATE_ID = os.environ.get('BREVO_RESET_PASSWORD_TEMPLATE_ID', '1')
    BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', '')
    BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'LiveSun - Propostas')
    PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    PDF_BROWSER_PATH = os.environ.get('PDF_BROWSER_PATH', '')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-change-me')


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SECRET_KEY = 'testing-only-key'
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    DB_ENGINE = 'sqlite'  # Override for testing


# Config dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
