"""Uma política para todas as empresas; Central autoriza, Propostas conta uso."""
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlsplit
import requests
from flask import current_app, g
from src.extensions import db
from src.models import Empresa, Proposta, Auditoria
from src.models.central import CentralTenant
from src.models.commercial_usage import CommercialUsage, TrialProposal
from src.services.central_client import (CommercialAccessError, get_entitlements, validate_base_url,
                                         validate_payload, store, utcnow)

LIMIT = 10
READ_ONLY = {'SUSPENSA', 'BLOQUEADA', 'CANCELADA', 'EXPIRADA'}
READ_ENDPOINTS = {'propostas.index', 'propostas.detalhe', 'propostas.pdf'}
TRIAL_EXPIRED = 'Seu período de teste expirou. Contrate o LiveSun Propostas para continuar criando e enviando propostas.'
QUOTA_REACHED = 'Você atingiu o limite de 10 propostas do período de teste. Contrate o LiveSun Propostas para continuar criando propostas.'


def bypass():
    # Somente fixtures antigas de testes funcionais; impossível habilitar em runtime.
    return current_app.testing and current_app.config.get('TEST_BYPASS_COMMERCIAL_POLICY', False)


def checkout_url():
    value = current_app.config.get('CENTRAL_CHECKOUT_URL', '').strip()
    parsed = urlsplit(value)
    if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.fragment:
        return value
    return None


def details(company_id, payload):
    cached = db.session.scalar(db.select(CommercialUsage).where(
        CommercialUsage.empresa_id == company_id, CommercialUsage.assinatura_id == payload['assinatura_id']))
    if cached and cached.versao == payload['versao'] and cached.valido_ate > utcnow():
        return cached
    tenant = db.session.get(CentralTenant, company_id)
    customer, subscription_id = tenant.central_cliente_id, payload['assinatura_id']
    try:
        base = validate_base_url(current_app.config['CENTRAL_BASE_URL'])
        with requests.Session() as http:
            http.trust_env = False
            response = http.get(f'{base}/api/v1/assinaturas/{subscription_id}',
                headers={'Authorization': 'Bearer ' + current_app.config['CENTRAL_API_TOKEN']},
                timeout=(3, 5), allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        effective = data['entitlements']
        validate_payload(effective, customer)
        if (type(data['id']) is not int or data['id'] != subscription_id
                or type(data['cliente_id']) is not int or data['cliente_id'] != customer
                or effective.get('plano') != 'PROPOSTAS' or effective['assinatura_id'] != subscription_id
                or data['versao'] != effective['versao'] or data['status'] != effective['status']
                or data['versao'] < payload['versao']):
            raise ValueError()
        start = date.fromisoformat(data['data_inicio'])
        end = date.fromisoformat(data['trial_ate']) if data.get('trial_ate') else None
        contract_end = date.fromisoformat(data['data_fim']) if data.get('data_fim') else None
        if effective['status'] == 'TRIAL' and (not end or end < start):
            raise ValueError()
        # Serializa atualização do cache com criação/replicação da mesma empresa.
        db.session.scalar(db.select(Empresa).where(Empresa.id == company_id).with_for_update())
        tenant = db.session.scalar(db.select(CentralTenant).where(CentralTenant.empresa_id == company_id)
            .with_for_update().execution_options(populate_existing=True))
        if (effective['assinatura_id'], effective['versao']) < (tenant.assinatura_id, tenant.versao):
            raise ValueError()
        store(tenant, effective)
        if not tenant.valido_ate or tenant.valido_ate <= utcnow():
            raise ValueError('Snapshot de autorizacao vencido.')
        cached = db.session.scalar(db.select(CommercialUsage).where(
            CommercialUsage.empresa_id == company_id, CommercialUsage.assinatura_id == subscription_id)
            .with_for_update().execution_options(populate_existing=True))
        if cached is None:
            cached = CommercialUsage(empresa_id=company_id, assinatura_id=subscription_id, criadas=0, inicializado=False)
            db.session.add(cached)
        elif start != cached.data_inicio:
            raise ValueError('Inicio alterado: requer revisao para nao reiniciar quota.')
        elif end != cached.trial_ate:
            cached.inicializado = False
        cached.versao, cached.data_inicio, cached.trial_ate = data['versao'], start, end
        cached.data_fim = contract_end
        cached.suspensa_inadimplencia = data.get('suspensa_por_inadimplencia') is True
        cached.valido_ate = min(tenant.valido_ate, utcnow() + timedelta(minutes=15))
        db.session.commit()
        return cached
    except (requests.RequestException, ValueError, KeyError, TypeError):
        db.session.rollback()
        raise CommercialAccessError('Não foi possível validar o período da assinatura. Tente novamente em instantes.', 503) from None


def state(company_id):
    if bypass():
        return {'status': 'ATIVA', 'restricted': False, 'can_create': True, 'usage': None, 'checkout': None}
    if not current_app.config.get('CENTRAL_ENABLED'):
        raise CommercialAccessError('A autorização comercial está temporariamente indisponível.', 503)
    payload = get_entitlements(company_id)
    if payload['status'] == 'EXCLUIDA':
        raise CommercialAccessError('O acesso comercial desta empresa foi encerrado.')
    usage = None
    if payload['status'] == 'TRIAL':
        usage = details(company_id, payload)
        payload = dict(db.session.get(CentralTenant, company_id).payload)
    elif payload['status'] in READ_ONLY:
        usage = db.session.scalar(db.select(CommercialUsage).where(CommercialUsage.empresa_id == company_id,
            CommercialUsage.assinatura_id == payload['assinatura_id'], CommercialUsage.versao == payload['versao'],
            CommercialUsage.valido_ate > utcnow()))
        if usage is None and payload['status'] == 'SUSPENSA':
            try:
                usage = details(company_id, payload)
                payload = dict(db.session.get(CentralTenant, company_id).payload)
            except CommercialAccessError:
                # Não presumir inadimplência quando detalhes não estão disponíveis.
                usage = None
    if payload['status'] == 'EXCLUIDA':
        raise CommercialAccessError('O acesso comercial desta empresa foi encerrado.')
    expired = bool(payload['status'] == 'TRIAL' and usage and usage.trial_ate <= date.today())
    expired = expired or bool(payload['status'] == 'TRIAL' and usage and usage.data_fim and usage.data_fim < date.today())
    restricted = payload['status'] in READ_ONLY or expired
    if payload['status'] in ('TRIAL', 'ATIVA') and not payload['acesso_produto'] and not expired:
        raise CommercialAccessError('O acesso ao produto não foi autorizado pelo Central.')
    if payload['status'] == 'TRIAL':
        initialize_usage(company_id, usage)
    used = usage.criadas if usage and usage.inicializado else 0
    near = bool(payload['status'] == 'TRIAL' and usage and 0 < (usage.trial_ate - date.today()).days <= 3)
    return {'status': payload['status'], 'restricted': restricted, 'expired': expired,
        'can_create': not restricted and (payload['status'] != 'TRIAL' or used < LIMIT),
        'usage': usage, 'used': used, 'limit': LIMIT, 'near': near,
        'checkout': checkout_url() if (expired or near or (payload['status'] == 'TRIAL' and used >= LIMIT)
            or (payload['status'] == 'SUSPENSA' and usage and usage.suspensa_inadimplencia)
            or payload['status'] == 'EXPIRADA') else None,
        'message': TRIAL_EXPIRED if expired else QUOTA_REACHED if payload['status'] == 'TRIAL' and used >= LIMIT
            else 'Sua assinatura está indisponível para alterações. Você pode consultar suas propostas e baixar os PDFs.' if restricted else None}


def initialize_usage(company_id, usage):
    if usage.inicializado:
        return
    db.session.scalar(db.select(Empresa).where(Empresa.id == company_id).with_for_update())
    row = db.session.scalar(db.select(CommercialUsage).where(CommercialUsage.id == usage.id)
        .with_for_update().execution_options(populate_existing=True))
    if not row.inicializado:
        if db.session.scalar(db.select(Proposta.id).where(Proposta.empresa_id == company_id,
                Proposta.data_criacao.is_(None)).limit(1)):
            db.session.rollback()
            raise CommercialAccessError('Há propostas sem data de criação. Solicite a revisão da LiveSun antes de continuar.', 503)
        proposals = db.session.scalars(db.select(Proposta).where(Proposta.empresa_id == company_id,
            Proposta.data_criacao >= datetime.combine(row.data_inicio, time.min),
            Proposta.data_criacao < datetime.combine(row.trial_ate, time.min))).all()
        added = 0
        for proposal in proposals:
            if db.session.get(TrialProposal, (proposal.id, row.id)) is None:
                db.session.add(TrialProposal(proposta_id=proposal.id, empresa_id=company_id, usage_id=row.id))
                added += 1
        row.criadas += added
        row.inicializado = True
    db.session.commit()


def authorize(company_id, endpoint=None, method='GET', login=False):
    result = state(company_id)
    g.commercial_state = result
    if result['restricted'] and not login and (method != 'GET' or endpoint not in READ_ENDPOINTS):
        raise CommercialAccessError(result['message'])
    if not login and endpoint in ('propostas.nova', 'propostas.replicar') and not result['can_create']:
        raise CommercialAccessError(QUOTA_REACHED)
    return result


def assert_send_authorized(company_id):
    """Revalida após PDF/antes do envio, que pode levar vários segundos."""
    if bypass():
        return
    result = authorize(company_id, 'propostas.enviar', 'POST')
    if result['restricted']:
        raise CommercialAccessError(TRIAL_EXPIRED)
    db.session.rollback()


def reserve_creation(proposal):
    """Não faz commit. Lock empresa -> cache -> contador; rollback desfaz reserva."""
    if bypass():
        return
    company_id = proposal.empresa_id
    if not getattr(g, 'commercial_state', None):
        authorize(company_id, 'propostas.nova', 'POST')
    db.session.scalar(db.select(Empresa).where(Empresa.id == company_id).with_for_update())
    tenant = db.session.scalar(db.select(CentralTenant).where(CentralTenant.empresa_id == company_id)
        .with_for_update().execution_options(populate_existing=True))
    if not tenant or not tenant.valido_ate or tenant.valido_ate <= utcnow():
        raise CommercialAccessError('Autorização expirada. Atualize a página antes de continuar.', 503)
    payload = tenant.payload
    if payload.get('status') == 'ATIVA' and payload.get('acesso_produto'):
        return
    if payload.get('status') != 'TRIAL' or not payload.get('acesso_produto'):
        raise CommercialAccessError(TRIAL_EXPIRED)
    usage = db.session.scalar(db.select(CommercialUsage).where(CommercialUsage.empresa_id == company_id,
        CommercialUsage.assinatura_id == tenant.assinatura_id).with_for_update().execution_options(populate_existing=True))
    if not usage or usage.versao != tenant.versao or usage.valido_ate <= utcnow():
        raise CommercialAccessError('Atualize a autorização do período de teste.', 503)
    if not usage.trial_ate or usage.trial_ate <= date.today() or (usage.data_fim and usage.data_fim < date.today()):
        raise CommercialAccessError(TRIAL_EXPIRED)
    changed = db.session.execute(db.update(CommercialUsage).where(CommercialUsage.id == usage.id,
        CommercialUsage.criadas < LIMIT, CommercialUsage.inicializado.is_(True))
        .values(criadas=CommercialUsage.criadas + 1), execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        raise CommercialAccessError(QUOTA_REACHED)
    db.session.add(proposal)
    db.session.flush()
    db.session.add(TrialProposal(proposta_id=proposal.id, empresa_id=company_id, usage_id=usage.id))
    db.session.add(Auditoria(empresa_id=company_id, usuario_id=proposal.usuario_id,
        acao='consumir_quota_trial', entidade='proposta', entidade_id=proposal.id))