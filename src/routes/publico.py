"""Página institucional pública, sem consulta a dados comerciais ou de tenants."""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import Blueprint, current_app, render_template

publico_bp = Blueprint('publico', __name__)


@publico_bp.get('/lp/propostas')
def landing():
    base = urlsplit(current_app.config.get('PUBLIC_BASE_URL', ''))
    canonical = None
    if base.scheme in ('http', 'https') and base.hostname and not base.username and not base.password:
        canonical = f'{base.scheme}://{base.netloc}/lp/propostas'
    response = current_app.make_response(render_template('publico/landing.html',
        canonical=canonical, public_year=datetime.now(timezone.utc).year))
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Formulário contém CSRF: não permitir cache compartilhado de tokens.
    response.headers['Cache-Control'] = 'no-store'
    return response