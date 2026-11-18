"""Envio síncrono idempotente e barreira de provisionamento; sem worker."""
import hashlib
import hmac
import secrets
import time
from datetime import timedelta
import requests
from flask import current_app, session, request, redirect, url_for, abort
from flask_login import current_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from src.extensions import db
from src.models import CadastroPublico, SolicitacaoCentral, Usuario, Auditoria
from src.models.central import CentralTenant
from src.models.cadastro_publico import utcnow
from src.services.central_client import validate_base_url


def audit(row, action):
    db.session.add(Auditoria(empresa_id=row.empresa_id, usuario_id=row.usuario_id,
        acao=action, entidade='cadastro_publico', entidade_id=row.id))


def prepare(row):
    company, user = row.usuario.empresa, row.usuario
    event = 'cad_' + hashlib.sha256(f'PROPOSTAS:empresa:{company.id}'.encode()).hexdigest()[:32]
    obj = SolicitacaoCentral(cadastro_id=row.id, empresa_id=company.id, evento_id=event, payload={
        'evento_id': event, 'empresa_id': company.id,
        'razao_social': company.razao_social or company.nome, 'nome_fantasia': company.nome,
        'cnpj_cpf': company.documento_normalizado, 'email': company.email or user.email,
        'telefone': company.telefone, 'responsavel': user.nome})
    db.session.add(obj)
    audit(row, 'preparar_solicitacao_central')
    return obj


def send(registration_id, manual=False):
    """Claim atômico antes da rede; resultado só pode ser gravado pelo mesmo lease."""
    row = db.session.get(CadastroPublico, registration_id)
    if row is None or row.status != 'PRONTO_ANALISE':
        db.session.rollback()
        return False
    company_id = row.empresa_id
    if db.session.get(CentralTenant, company_id) is not None:
        db.session.rollback()
        return False
    now, lease = utcnow(), secrets.token_hex(16)
    retry = max(30, min(86400, current_app.config['CENTRAL_REGISTRATION_RETRY_SECONDS']))
    conditions = [SolicitacaoCentral.cadastro_id == registration_id,
        SolicitacaoCentral.empresa_id == company_id, SolicitacaoCentral.status == 'PENDENTE',
        or_(SolicitacaoCentral.proxima_tentativa_em.is_(None), SolicitacaoCentral.proxima_tentativa_em <= now),
        or_(SolicitacaoCentral.lease_ate.is_(None), SolicitacaoCentral.lease_ate <= now)]
    if manual:
        conditions.append(SolicitacaoCentral.erro_categoria.is_not(None))
    changed = db.session.execute(db.update(SolicitacaoCentral).where(*conditions).values(
        lease_id=lease, lease_ate=now + timedelta(seconds=60),
        tentativas=SolicitacaoCentral.tentativas + 1, ultima_tentativa_em=now,
        proxima_tentativa_em=now + timedelta(seconds=retry), erro_categoria='ENVIO_NAO_CONFIRMADO'),
        execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        db.session.rollback()
        return False
    db.session.expire_all()
    obj = db.session.scalar(db.select(SolicitacaoCentral).where(SolicitacaoCentral.cadastro_id == registration_id))
    payload, identifier = dict(obj.payload), obj.id
    audit(row, 'tentar_envio_central')
    db.session.commit()
    category, received_id = None, None
    try:
        base = validate_base_url(current_app.config['CENTRAL_BASE_URL'])
        token = current_app.config.get('CENTRAL_API_TOKEN', '')
        if not token or len(current_app.config.get('CENTRAL_WEBHOOK_SECRET', '')) < 32:
            raise ValueError()
        # Sem transação SQL aberta durante chamada externa; não herdar proxies/netrc.
        with requests.Session() as http:
            http.trust_env = False
            response = http.post(base + '/api/v1/cadastros', json=payload,
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                timeout=(3, 8), allow_redirects=False)
        if response.status_code not in (200, 202):
            category = 'HTTP'
        else:
            data = response.json()
            if (not isinstance(data, dict) or data.get('produto') != 'PROPOSTAS'
                    or type(data.get('empresa_id')) is not int or data['empresa_id'] != company_id
                    or data.get('evento_id') != payload['evento_id']
                    or data.get('status') not in ('PENDENTE', 'VINCULO_PENDENTE', 'VINCULADA')
                    or type(data.get('solicitacao_id')) is not int or not 1 <= data['solicitacao_id'] <= 2147483647):
                category = 'RESPOSTA_INVALIDA'
            else:
                received_id = data['solicitacao_id']
    except requests.Timeout:
        category = 'TIMEOUT'
    except requests.ConnectionError:
        category = 'CONEXAO'
    except requests.RequestException:
        category = 'COMUNICACAO'
    except (ValueError, KeyError, TypeError):
        category = 'CONFIGURACAO_OU_RESPOSTA'
    except Exception:
        category = 'ENVIO_NAO_CONFIRMADO'
    if category:
        current_app.logger.warning('{"event":"central_registration_pending","category":"%s"}', category)
    try:
        values = {'lease_id': None, 'lease_ate': None, 'erro_categoria': category}
        if received_id:
            values.update(status='RECEBIDA_CENTRAL', central_solicitacao_id=received_id, recebida_em=utcnow())
        changed = db.session.execute(db.update(SolicitacaoCentral).where(SolicitacaoCentral.id == identifier,
            SolicitacaoCentral.empresa_id == company_id, SolicitacaoCentral.lease_id == lease).values(**values),
            execution_options={'synchronize_session': False})
        if changed.rowcount == 1:
            audit(db.session.get(CadastroPublico, registration_id),
                  'solicitacao_recebida_central' if received_id else 'falha_envio_central')
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('{"event":"central_registration_result_not_persisted"}')
    return received_id is not None


def registration_for_company(company_id):
    return db.session.scalar(db.select(CadastroPublico).where(CadastroPublico.empresa_id == company_id))


def pending_provisioning(company_id):
    return (not current_app.config.get('CENTRAL_ENABLED')
            or db.session.get(CentralTenant, company_id) is None)


def authorize_tracking(row, user):
    # Cookie Flask assinado/HTTPOnly: escopo limitado, expira em 1h, revogado por troca de senha.
    session['cadastro_tracking'] = {'cadastro_id': row.id, 'empresa_id': row.empresa_id,
        'usuario_id': user.id, 'expires': int(time.time()) + 3600,
        'password_version': hmac.new(current_app.secret_key.encode(), user.senha_hash.encode(), hashlib.sha256).hexdigest()}


def tracking_registration():
    data = session.get('cadastro_tracking')
    if not isinstance(data, dict) or any(type(data.get(k)) is not int for k in
            ('cadastro_id', 'empresa_id', 'usuario_id', 'expires')) or not int(time.time()) < data['expires'] <= int(time.time()) + 3600:
        return None
    user = db.session.get(Usuario, data['usuario_id'])
    row = db.session.get(CadastroPublico, data['cadastro_id'])
    if (user is None or row is None or not user.is_active or row.status != 'PRONTO_ANALISE'
            or row.empresa_id != data['empresa_id'] or user.empresa_id != row.empresa_id
            or not secrets.compare_digest(str(data.get('password_version', '')),
                hmac.new(current_app.secret_key.encode(), user.senha_hash.encode(), hashlib.sha256).hexdigest())):
        return None
    return row


def install_provisioning_guard(app):
    @app.before_request
    def provisioning_guard():
        exempt = {'static', 'healthz', 'publico.landing', 'suporte', 'central.webhook',
                  'central.state', 'central.companies', 'central.company_detail', 'central.link_company'}
        if not current_user.is_authenticated or request.endpoint in exempt or request.endpoint == 'auth.logout':
            return
        row = registration_for_company(current_user.empresa_id)
        if row is None or not pending_provisioning(row.empresa_id):
            return
        if row.status != 'PRONTO_ANALISE':
            logout_user()
            return redirect(url_for('auth.login'))
        authorize_tracking(row, current_user)
        logout_user()
        if request.endpoint in ('cadastro.recebido', 'cadastro.tentar_novamente'):
            return
        if request.method != 'GET' or request.accept_mimetypes.best == 'application/json':
            abort(403)
        return redirect(url_for('cadastro.recebido'))