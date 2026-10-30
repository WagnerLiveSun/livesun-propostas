import os
import logging
import sys
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables
load_dotenv()

# Import configuration
from config.config import config

# Import extensions
from src.extensions import db, login_manager, csrf, migrate

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    # Containers coletam stdout; não exigir escrita no diretório do código.
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def _validate_production_settings(config_name: str):
    if config_name != 'production':
        return

    from src.core.database_config import missing_production_env

    missing = missing_production_env()
    if missing:
        raise RuntimeError(
            'Configuracao insegura para producao. Variaveis ausentes: '
            + ', '.join(missing)
        )


def create_app(config_name=None, overrides=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    _validate_production_settings(config_name)

    app = Flask(__name__)
    app.config.from_object(config[config_name])
    if overrides:
        app.config.update(overrides)
    if os.getenv('TRUST_PROXY') == 'true':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    if config_name == 'production':
        app.config['PREFERRED_URL_SCHEME'] = 'https'

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    from src.core.database_config import sqlalchemy_engine_options

    app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
    app.config['SQLALCHEMY_ENGINE_OPTIONS'].update(
        sqlalchemy_engine_options(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    )

    db.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    # Import models to register with SQLAlchemy
    from src.models import Empresa, Usuario, Cliente, ProdutoServico, Proposta, PropostaItem, EnvioEmail, Auditoria

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = None

    @login_manager.user_loader
    def load_user(user_id):
        from src.models.usuario import Usuario
        try:
            user = db.session.get(Usuario, int(user_id))
        except (ValueError, TypeError):
            return None
        return user if user and user.is_active else None

    # Not creating tables automatically - will use Flask-Migrate
    # with app.app_context():
    #     db.create_all()

    # Register blueprints
    from src.routes.auth import auth_bp
    from src.routes.dashboard import dashboard_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    from src.routes.gestao import gestao_bp
    from src.routes.propostas import propostas_bp
    app.register_blueprint(gestao_bp)
    app.register_blueprint(propostas_bp)
    from src.cli import register_commands
    register_commands(app)

    @app.route('/healthz')
    def healthz():
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError
        try:
            db.session.execute(text('SELECT 1'))
            return {'status': 'ok'}, 200
        except SQLAlchemyError:
            db.session.rollback()
            return {'status': 'unavailable'}, 503

    @app.context_processor
    def developer_brand():
        # A URL muda com o conteúdo, mesmo se a cópia preservar a data do arquivo.
        logo = Path(app.static_folder) / 'images' / 'logo.png'
        version = hashlib.sha256(logo.read_bytes()).hexdigest()[:16]
        stylesheet = Path(app.static_folder) / 'css' / 'style.css'
        css_version = hashlib.sha256(stylesheet.read_bytes()).hexdigest()[:16]
        return {'developer_logo_url': url_for('static', filename='images/logo.png', v=version),
                'stylesheet_url': url_for('static', filename='css/style.css', v=css_version)}

    @app.route('/suporte')
    def suporte():
        return render_template('suporte.html')

    @app.template_filter('brl')
    def format_brl(value):
        """Format numeric values using pt-BR currency style."""
        from decimal import Decimal, InvalidOperation
        if value is None:
            value = 0
        try:
            num = Decimal(str(value)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError, TypeError):
            num = Decimal('0.00')
        formatted = f"{num:,.2f}"
        return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')

    @app.template_filter('documento')
    def format_documento(value):
        digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
        if len(digits) == 11:
            return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
        if len(digits) == 14:
            return f'{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}'
        return str(value or '-')

    return app
