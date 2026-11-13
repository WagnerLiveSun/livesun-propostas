import hashlib
import hmac
import json
import os
import time
import click
from flask import Blueprint, request, abort, current_app
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from src.extensions import db, csrf
from src.models.central import CentralTenant, CentralEventoRecebido
from src.services.central_client import store, validate_payload, check_subscription

central_bp = Blueprint('central', __name__)
EVENTS = {'ASSINATURA_CRIADA', 'ASSINATURA_ATIVADA', 'ASSINATURA_SUSPENSA',
          'ASSINATURA_BLOQUEADA', 'ASSINATURA_REATIVADA', 'ASSINATURA_CANCELADA',
          'ASSINATURA_EXPIRADA', 'ASSINATURA_EXCLUIDA', 'LIMITE_ALTERADO',
          'COBRANCA_CRIADA', 'COBRANCA_PAGA', 'COBRANCA_ATRASADA',
          'TRIAL_ALTERADO', 'CORTESIA_ALTERADA', 'CORTESIA_ENCERRADA'}


def authenticate(raw, enrollment=False):
    secret = current_app.config.get('CENTRAL_WEBHOOK_SECRET', '')
    if len(secret) < 32 or (not enrollment and not current_app.config.get('CENTRAL_ENABLED')):
        abort(503)
    stamp = request.headers.get('X-LiveSun-Timestamp', '')
    try:
        if abs(time.time() - int(stamp)) > 300:
            abort(401)
    except ValueError:
        abort(401)
    expected = 'sha256=' + hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get('X-LiveSun-Signature', '')):
        abort(401)


def company_registration(company):
    from src.models.usuario import Usuario
    owner = db.session.scalar(db.select(Usuario).where(Usuario.empresa_id == company.id,
        Usuario.perfil == 'admin', Usuario.ativo.is_(True)).order_by(Usuario.id))
    tenant = db.session.get(CentralTenant, company.id)
    return {'dados': {
        'evento_id': 'cad_' + hashlib.sha256(f'PROPOSTAS:empresa:{company.id}'.encode()).hexdigest()[:32],
        'empresa_id': company.id, 'razao_social': company.razao_social or company.nome,
        'nome_fantasia': company.nome, 'cnpj_cpf': ''.join(c for c in (company.cnpj_cpf or '') if c.isdigit()),
        'email': company.email or (owner.email if owner else ''), 'telefone': company.telefone,
        'responsavel': owner.nome if owner else company.nome},
        'ativo': bool(company.ativo), 'cliente_id': tenant.central_cliente_id if tenant else None}


@central_bp.get('/central/empresas')
def companies():
    # Permite preparar vínculos sem ligar o guard comercial e bloquear clientes.
    authenticate(request.full_path.rstrip('?').encode(), enrollment=True)
    from src.models.empresa import Empresa
    try:
        cursor = int(request.args.get('apos', '0'))
        if cursor < 0 or cursor > 2147483647:
            raise ValueError()
    except ValueError:
        abort(422)
    rows = db.session.scalars(db.select(Empresa).where(Empresa.id > cursor)
        .order_by(Empresa.id).limit(51)).all()
    return {'produto': 'PROPOSTAS', 'empresas': [company_registration(row) for row in rows[:50]],
            'proximo': rows[49].id if len(rows) > 50 else None}


@central_bp.get('/central/empresas/<int:empresa_id>')
def company_detail(empresa_id):
    authenticate(request.path.encode(), enrollment=True)
    from src.models.empresa import Empresa
    company = db.get_or_404(Empresa, empresa_id)
    return {'produto': 'PROPOSTAS', 'empresa': company_registration(company)}


@central_bp.post('/central/cadastros/vincular')
@csrf.exempt
def link_company():
    raw = request.get_data(cache=True)
    if len(raw) > 131072:
        abort(413)
    authenticate(raw, enrollment=True)
    from src.models.empresa import Empresa
    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or data['produto'] != 'PROPOSTAS' or data['status'] not in ('VINCULO_PENDENTE', 'VINCULADA'):
            raise ValueError()
        if any(type(data[field]) is not int or not 1 <= data[field] <= 2147483647
               for field in ('empresa_id', 'cliente_id', 'assinatura_id', 'solicitacao_id')):
            raise ValueError()
        company = db.session.scalar(db.select(Empresa).where(Empresa.id == data['empresa_id']).with_for_update())
        if company is None or not company.ativo:
            abort(409)
        if data['evento_id'] != company_registration(company)['dados']['evento_id']:
            raise ValueError()
        document = ''.join(c for c in (company.cnpj_cpf or '') if c.isdigit())
        if len(document) not in (11, 14) or data.get('cnpj_cpf') != document:
            abort(409)
        entitlement = data['entitlements']
        validate_payload(entitlement, data['cliente_id'])
        if entitlement['assinatura_id'] != data['assinatura_id'] or not entitlement['acesso_produto']:
            raise ValueError()
        tenant = db.session.get(CentralTenant, company.id)
        if tenant and tenant.central_cliente_id != data['cliente_id']:
            abort(409)
        existing = db.session.scalar(db.select(CentralTenant).where(
            CentralTenant.central_cliente_id == data['cliente_id']))
        if existing and existing.empresa_id != company.id:
            abort(409)
        if tenant is None:
            tenant = CentralTenant(empresa_id=company.id, central_cliente_id=data['cliente_id'],
                assinatura_id=0, versao=0)
            db.session.add(tenant)
            from src.models.auditoria import Auditoria
            db.session.add(Auditoria(empresa_id=company.id, acao='central_vinculo_criado',
                entidade='central_tenants', entidade_id=company.id,
                detalhes=json.dumps({'cliente_id': data['cliente_id'], 'solicitacao_id': data['solicitacao_id']})))
        store(tenant, entitlement)
        db.session.commit()
        return {'evento_id': data['evento_id'], 'empresa_id': company.id,
                'cliente_id': tenant.central_cliente_id, 'status': 'VINCULADA'}
    except IntegrityError:
        db.session.rollback()
        abort(409)
    except (ValueError, TypeError, KeyError):
        db.session.rollback()
        abort(422)


@central_bp.post('/webhooks/assinatura')
@csrf.exempt
def webhook():
    if request.content_length is None or request.content_length > 131072:
        abort(413)
    raw = request.get_data()
    authenticate(raw)
    if request.headers.get('X-LiveSun-Event') == 'INTEGRACAO_TESTE':
        data=request.get_json()
        if not isinstance(data,dict) or data.get('produto') != 'PROPOSTAS' or not isinstance(data.get('nonce'),str) or len(data['nonce']) != 64:
            abort(422)
        proof=hmac.new(current_app.config['CENTRAL_WEBHOOK_SECRET'].encode(),
            ('PROPOSTAS:'+data['nonce']).encode(),hashlib.sha256).hexdigest()
        return {'produto':'PROPOSTAS','nonce':data['nonce'],'prova':proof,'status':'receptor_pronto'},200
    try:
        data = json.loads(raw)
        event = data['evento_id']
        if not isinstance(event, str) or not event.startswith('evt_') or len(event) > 50:
            raise ValueError('Evento inválido.')
        if data['produto'] != 'PROPOSTAS' or data['evento'] not in EVENTS or request.headers.get('X-LiveSun-Event') != data['evento']:
            raise ValueError('Evento incompatível.')
        customer = int(data['cliente_id'])
        entitlement = data['entitlements']
        validate_payload(entitlement, customer)
        if (entitlement['assinatura_id'] != data['assinatura_id'] or entitlement['versao'] != data['versao']
                or entitlement['status'] != data['status_novo']):
            raise ValueError('Estado incompatível.')
        tenant = db.session.scalar(db.select(CentralTenant).where(CentralTenant.central_cliente_id == customer)
                                   .with_for_update())
        if tenant is None:
            abort(422)
        if db.session.get(CentralEventoRecebido, event):
            db.session.rollback()
            return {'status': 'duplicado'}, 200
        db.session.add(CentralEventoRecebido(evento_id=event, cliente_id=customer,
                                             assinatura_id=data['assinatura_id'], versao=data['versao']))
        applied = store(tenant, entitlement)
        db.session.commit()
        return {'status': 'aplicado' if applied else 'obsoleto'}, 200
    except IntegrityError:
        db.session.rollback()
        if db.session.get(CentralEventoRecebido, event):
            return {'status': 'duplicado'}, 200
        abort(409)
    except (ValueError, TypeError, KeyError):
        db.session.rollback()
        abort(422)


@central_bp.get('/central/estado/<int:cliente_id>')
def state(cliente_id):
    authenticate(request.path.encode())
    tenant = db.session.scalar(db.select(CentralTenant).filter_by(central_cliente_id=cliente_id))
    if tenant is None:
        abort(404)
    return {'cliente_id': str(cliente_id), 'produto': 'PROPOSTAS', 'assinatura_id': tenant.assinatura_id,
            'versao': tenant.versao, 'entitlements': tenant.payload}


def register_central(app):
    app.config.setdefault('CENTRAL_ENABLED', os.getenv('CENTRAL_ENABLED', 'false').lower() == 'true')
    for key, default in [('CENTRAL_BASE_URL', 'https://central.livesun.com.br'), ('CENTRAL_API_TOKEN', ''),
                         ('CENTRAL_WEBHOOK_SECRET', '')]:
        app.config.setdefault(key, os.getenv(key, default))
    app.config.setdefault('CENTRAL_CACHE_TTL_SECONDS', int(os.getenv('CENTRAL_CACHE_TTL_SECONDS', '900')))
    app.config.setdefault('CENTRAL_FAILSAFE_MINUTES', int(os.getenv('CENTRAL_FAILSAFE_MINUTES', '15')))
    app.config.setdefault('CENTRAL_ALLOW_FAIL_OPEN_NON_SENSITIVE', os.getenv('CENTRAL_ALLOW_FAIL_OPEN_NON_SENSITIVE') == 'true')
    app.config.setdefault('CENTRAL_ALLOW_LOCAL_HTTP', os.getenv('CENTRAL_ALLOW_LOCAL_HTTP', 'false').lower() == 'true')
    if app.config['CENTRAL_ALLOW_LOCAL_HTTP'] and app.config.get('CENTRAL_RUNTIME_ENV') not in ('development', 'testing'):
        raise RuntimeError('CENTRAL_ALLOW_LOCAL_HTTP é exclusivo de desenvolvimento/testes. Produção exige HTTPS.')
    if app.config['CENTRAL_ENABLED']:
        if not app.config['CENTRAL_API_TOKEN'] or len(app.config['CENTRAL_WEBHOOK_SECRET']) < 32:
            raise RuntimeError('Configure token de API e segredo HMAC do Central.')
        if not 1 <= app.config['CENTRAL_CACHE_TTL_SECONDS'] <= 900 or not 0 <= app.config['CENTRAL_FAILSAFE_MINUTES'] <= 60:
            raise RuntimeError('TTL/cache de contingência fora dos limites permitidos.')
    app.register_blueprint(central_bp)

    @app.before_request
    def central_guard():
        if (app.config['CENTRAL_ENABLED'] and current_user.is_authenticated
                and request.endpoint not in ('static', 'healthz', 'central.webhook', 'central.state',
                    'central.companies', 'central.company_detail', 'central.link_company')
                and not (request.endpoint or '').endswith('.logout')):
            check_subscription(current_user.empresa_id)

    @app.cli.command('central-vincular')
    @click.argument('empresa_id', type=int)
    @click.argument('cliente_id', type=int)
    def bind(empresa_id, cliente_id):
        from src.models.empresa import Empresa
        if empresa_id < 1 or cliente_id < 1 or db.session.get(Empresa, empresa_id) is None:
            raise click.ClickException('Empresa ou cliente inválido.')
        if db.session.get(CentralTenant, empresa_id):
            raise click.ClickException('Empresa já vinculada. Alteração exige migração administrativa auditada.')
        db.session.add(CentralTenant(empresa_id=empresa_id, central_cliente_id=cliente_id))
        db.session.commit()
        click.echo('Vínculo comercial criado.')