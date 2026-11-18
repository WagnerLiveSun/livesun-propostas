"""Rotas públicas isoladas dos contratos comerciais existentes."""
import hashlib
import hmac
from urllib.parse import urlsplit
from flask import Blueprint, abort, current_app, request, render_template, session, redirect, url_for
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from src.extensions import limiter, db
from src.services import cadastro as service
from src.services.identidades import email_key, document_key


cadastro_bp = Blueprint('cadastro', __name__, url_prefix='/cadastro')


@cadastro_bp.errorhandler(Exception)
def safe_error(error):
    if isinstance(error, HTTPException):
        return error
    db.session.rollback()
    current_app.logger.error('{"event":"registration_request_failed"}')
    return render_template('auth/confirmacao.html', message='Não foi possível concluir agora. Tente novamente mais tarde.'), 503


def validate_registration_config(app):
    if app.config.get('PUBLIC_REGISTRATION_PREVIEW') and app.config['CENTRAL_RUNTIME_ENV'] != 'development':
        raise RuntimeError('Visualização de cadastro é exclusiva de desenvolvimento.')
    if not app.config['PUBLIC_REGISTRATION_ENABLED']:
        return
    if not app.config['PUBLIC_REGISTRATION_DATA_REVIEWED']:
        raise RuntimeError('Cadastro requer diagnóstico e aprovação dos dados antes da ativação.')
    for key in ('TERMS_VERSION', 'PRIVACY_VERSION'):
        if not app.config[key] or len(app.config[key]) > 100:
            raise RuntimeError('Configure as versões dos documentos de aceite.')
    for key in ('PUBLIC_BASE_URL', 'TERMS_URL', 'PRIVACY_URL'):
        value = urlsplit(app.config[key])
        local = app.config['CENTRAL_RUNTIME_ENV'] in ('testing', 'development') and value.hostname in ('localhost', '127.0.0.1', '::1')
        if (not value.hostname or value.username or value.password or value.fragment or value.query
                or (value.scheme != 'https' and not (local and value.scheme == 'http'))
                or (key == 'PUBLIC_BASE_URL' and value.path not in ('', '/'))):
            raise RuntimeError('Configure URLs públicas seguras para cadastro e documentos de aceite.')
    if not 1 <= app.config['EMAIL_CONFIRMATION_TTL_MINUTES'] <= 10080:
        raise RuntimeError('Validade de confirmação fora do intervalo permitido.')
    if not 1 <= app.config['CONFIRMATION_RESEND_COOLDOWN_SECONDS'] <= 86400:
        raise RuntimeError('Intervalo de reenvio fora do intervalo permitido.')


def identity_key(field):
    raw = request.form.get(field, '')[:256]
    value = document_key(raw) if field == 'documento' else email_key(raw)
    return hmac.new(current_app.secret_key.encode(), (field + ':' + (value or '')).encode(), hashlib.sha256).hexdigest()


@cadastro_bp.before_request
def require_available():
    if current_app.config.get('PUBLIC_REGISTRATION_PREVIEW'):
        if current_app.config['CENTRAL_RUNTIME_ENV'] != 'development':
            abort(404)
        if request.method != 'GET' or request.endpoint != 'cadastro.index':
            abort(403)
        return
    tracking = request.endpoint in ('cadastro.recebido', 'cadastro.tentar_novamente')
    if tracking:
        return
    if not current_app.config['PUBLIC_REGISTRATION_ENABLED']:
        abort(404)
    # Não abre cadastro só porque uma variável foi ligada antes da migration B.
    schema = inspect(db.engine)
    for table, column in (('usuarios', 'email_normalizado'), ('empresas', 'documento_normalizado')):
        if not any(item['column_names'] == [column] for item in schema.get_unique_constraints(table)):
            abort(503)
    if request.method == 'POST':
        if request.mimetype != 'application/x-www-form-urlencoded':
            abort(415)
        if request.content_length is None or request.content_length > 16384:
            abort(413)
        if len(request.get_data(cache=True)) > 16384:
            abort(413)


@cadastro_bp.after_request
def secure_response(response):
    response.headers['Cache-Control'] = 'no-store'
    # HTTPS/CSRF exige Referer da mesma origem. Enviar apenas a origem evita
    # vazar o token presente no caminho da confirmação (inclusive no POST).
    response.headers['Referrer-Policy'] = 'origin'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@cadastro_bp.errorhandler(429)
def rate_limited(error):
    return render_template('auth/confirmacao.html', message='Muitas tentativas. Aguarde antes de tentar novamente.'), 429


@cadastro_bp.route('', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['PUBLIC_REGISTRATION_RATE_LIMIT'], methods=['POST'])
@limiter.limit(lambda: current_app.config['REGISTRATION_IDENTITY_RATE_LIMIT'], key_func=lambda: identity_key('email'), methods=['POST'])
@limiter.limit(lambda: current_app.config['REGISTRATION_IDENTITY_RATE_LIMIT'], key_func=lambda: identity_key('documento'), methods=['POST'])
def index():
    error = None
    if request.method == 'POST':
        if request.form.get('website', ''):
            return render_template('auth/confirmacao.html', message=service.GENERIC_RESPONSE)
        try:
            data = service.validate_form(request.form)
            service.register(data)
            return render_template('auth/confirmacao.html', message=service.GENERIC_RESPONSE)
        except ValueError as exc:
            error = str(exc)
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error('{"event":"public_registration_failed"}')
            return render_template('auth/confirmacao.html', message='Não foi possível concluir agora. Tente novamente mais tarde.'), 503
    # Não devolver senhas, tokens ou valores pessoais em mensagens/sessão.
    return render_template('auth/cadastro.html', error=error), 422 if error else 200


@cadastro_bp.route('/confirmar/<token>', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def confirmar(token):
    if request.method == 'GET':
        return render_template('auth/confirmacao.html', confirmar=True)
    confirmed = service.confirm(token)
    if confirmed:
        session['cadastro_completion'] = confirmed
        return redirect(url_for('cadastro.completar'))
    message = 'Link inválido, expirado ou já utilizado. Se necessário, solicite um novo link.'
    return render_template('auth/confirmacao.html', message=message)


@cadastro_bp.route('/completar', methods=['GET', 'POST'])
@limiter.limit('20 per minute')
def completar():
    grant = session.get('cadastro_completion')
    row = service.completion_registration(grant)
    if row is None:
        session.pop('cadastro_completion', None)
        return render_template('auth/confirmacao.html', message='A autorização expirou ou já foi utilizada. Solicite um novo link para completar seu cadastro.'), 403
    error = None
    if request.method == 'POST':
        try:
            identifier = service.complete(grant, request.form)
            session.pop('cadastro_completion', None)
            from src.models import CadastroPublico
            from src.services.cadastro_central import authorize_tracking, send
            row = db.session.get(CadastroPublico, identifier)
            authorize_tracking(row, row.usuario)
            # Primeiro commit garante que falha de rede não perde senha/cadastro.
            db.session.rollback()
            try:
                send(identifier)
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.error('{"event":"central_registration_attempt_not_persisted"}')
            return redirect(url_for('cadastro.recebido'))
        except ValueError as exc:
            error = str(exc)
    return render_template('auth/completar_cadastro.html', cadastro=row, error=error), 422 if error else 200


def require_tracking():
    from src.services.cadastro_central import tracking_registration
    row = tracking_registration()
    if row is None:
        session.pop('cadastro_tracking', None)
        abort(403)
    return row


@cadastro_bp.get('/recebido')
@limiter.limit('30 per minute')
def recebido():
    from src.models import SolicitacaoCentral
    from src.models.central import CentralTenant
    from src.models.cadastro_publico import utcnow
    row = require_tracking()
    obj = db.session.scalar(db.select(SolicitacaoCentral).where(
        SolicitacaoCentral.cadastro_id == row.id, SolicitacaoCentral.empresa_id == row.empresa_id))
    linked = db.session.get(CentralTenant, row.empresa_id) is not None
    retry_visible = bool(obj and obj.status == 'PENDENTE' and obj.erro_categoria and not linked)
    retry_ready = bool(retry_visible and (not obj.proxima_tentativa_em or obj.proxima_tentativa_em <= utcnow())
                       and (not obj.lease_ate or obj.lease_ate <= utcnow()))
    return render_template('auth/cadastro_recebido.html', retry_visible=retry_visible,
        retry_ready=retry_ready, linked=linked)


@cadastro_bp.post('/tentar-novamente')
@limiter.limit('3 per hour')
def tentar_novamente():
    from src.services.cadastro_central import send
    row = require_tracking()
    identifier = row.id
    db.session.rollback()
    try:
        send(identifier, manual=True)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('{"event":"central_registration_retry_not_persisted"}')
    return redirect(url_for('cadastro.recebido'))


@cadastro_bp.route('/reenviar-confirmacao', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['CONFIRMATION_RESEND_RATE_LIMIT'], methods=['POST'])
@limiter.limit(lambda: current_app.config['REGISTRATION_IDENTITY_RATE_LIMIT'], key_func=lambda: identity_key('email'), methods=['POST'])
def reenviar():
    if request.method == 'POST':
        if not request.form.get('website', ''):
            try:
                service.resend(request.form.get('email', '')[:120])
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.warning('{"event":"confirmation_resend_failed"}')
        return render_template('auth/confirmacao.html', message=service.GENERIC_RESPONSE)
    return render_template('auth/reenviar_confirmacao.html')