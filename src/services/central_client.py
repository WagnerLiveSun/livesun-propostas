"""Cliente do Central com cache persistente, tenant explícito e falha segura."""
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit
import requests
from flask import current_app, abort
from flask_login import current_user
from src.extensions import db
from src.models.central import CentralTenant
from werkzeug.exceptions import HTTPException


class CommercialAccessError(HTTPException):
    """Bloqueio comercial tratado na página de atendimento do produto."""
    code = 403

    def __init__(self, description, code=403):
        super().__init__(description=description)
        self.code = code

logger = logging.getLogger(__name__)
STATUSES = {'TRIAL', 'ATIVA', 'PAGO_AGUARDANDO_LIBERACAO', 'SUSPENSA', 'BLOQUEADA', 'CANCELADA', 'EXPIRADA', 'EXCLUIDA'}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_base_url(base):
    parsed = urlsplit(base)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('CENTRAL_BASE_URL inválida: use somente a origem do serviço.')
    # HTTP nunca é permitido em produção nem para endereços da LAN/públicos.
    local_http = (
        current_app.config.get('CENTRAL_ALLOW_LOCAL_HTTP') is True
        and current_app.config.get('CENTRAL_RUNTIME_ENV') in ('development', 'testing')
        and parsed.scheme == 'http'
        and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    )
    if parsed.scheme != 'https' and not local_http:
        raise ValueError('HTTPS obrigatório; HTTP loopback exige opt-in em desenvolvimento.')
    return base.rstrip('/')


def validate_payload(data, customer):
    if not isinstance(data, dict) or data.get('cliente_id') != str(customer) or data.get('produto') != 'PROPOSTAS':
        raise ValueError('Tenant/produto incompatível.')
    if (data.get('status') not in STATUSES or type(data.get('acesso_produto')) is not bool
            or type(data.get('assinatura_id')) is not int or data['assinatura_id'] <= 0
            or type(data.get('versao')) is not int or data['versao'] <= 0
            or not isinstance(data.get('limites'), dict) or data.get('modulos') != []):
        raise ValueError('Entitlements inválidos.')
    validity = datetime.fromisoformat(data['valido_ate'])
    generated = datetime.fromisoformat(data['gerado_em'])
    if validity.tzinfo is None:
        raise ValueError('Validade deve conter timezone.')
    if generated.tzinfo is None or validity < generated or generated > datetime.now(timezone.utc) + timedelta(seconds=300):
        raise ValueError('Datas de autorização inválidas.')
    if any(type(value) is not int or value < 0 for value in data['limites'].values()):
        raise ValueError('Limites inválidos.')
    if data['acesso_produto'] and data['status'] not in ('ATIVA', 'TRIAL'):
        raise ValueError('Acesso incompatível com o status.')
    return validity.astimezone(timezone.utc).replace(tzinfo=None)


def store(tenant, data):
    validity = validate_payload(data, tenant.central_cliente_id)
    incoming = (data['assinatura_id'], data['versao'])
    if incoming < (tenant.assinatura_id, tenant.versao):
        return False
    tenant.payload = data
    tenant.assinatura_id, tenant.versao = incoming
    tenant.valido_ate = min(validity, utcnow() + timedelta(seconds=current_app.config['CENTRAL_CACHE_TTL_SECONDS']))
    tenant.atualizado_em = utcnow()
    return True


def get_entitlements(empresa_id, sensitive=True):
    if not current_app.config.get('CENTRAL_ENABLED'):
        raise CommercialAccessError('Integração comercial não configurada.', 503)
    tenant = db.session.get(CentralTenant, empresa_id)
    if tenant is None:
        raise CommercialAccessError('O vínculo comercial da sua empresa ainda não foi concluído. Entre em contato com o suporte.')
    if tenant.payload and tenant.valido_ate and tenant.valido_ate > utcnow():
        return tenant.payload
    customer = tenant.central_cliente_id
    try:
        base = validate_base_url(current_app.config['CENTRAL_BASE_URL'])
        response = requests.get(f'{base}/api/v1/entitlements/{customer}/PROPOSTAS',
            headers={'Authorization': 'Bearer ' + current_app.config['CENTRAL_API_TOKEN']},
            timeout=(3, 5), allow_redirects=False)
        if response.status_code in (401, 403, 404):
            raise CommercialAccessError('Não foi possível autorizar o acesso da sua empresa. Entre em contato com o suporte.')
        response.raise_for_status()
        data = response.json()
        validate_payload(data, customer)
        tenant = db.session.scalar(db.select(CentralTenant).where(CentralTenant.empresa_id == empresa_id)
            .with_for_update().execution_options(populate_existing=True))
        store(tenant, data)
        db.session.commit()
        if not tenant.valido_ate or tenant.valido_ate <= utcnow():
            raise CommercialAccessError('Não foi possível atualizar a autorização de acesso. Tente novamente em instantes.', 503)
        return tenant.payload
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        db.session.rollback()
        if isinstance(error, requests.exceptions.SSLError):
            category = 'TLS'
        elif isinstance(error, requests.Timeout):
            category = 'TIMEOUT'
        elif isinstance(error, requests.ConnectionError):
            category = 'CONEXAO'
        elif isinstance(error, requests.HTTPError):
            category = 'HTTP'
        else:
            category = 'CONFIGURACAO_OU_RESPOSTA'
        logger.warning('Falha de comunicação com o Central. Categoria: %s', category)
        # Cache expirado não autoriza nem leitura restrita na política comercial.
        raise CommercialAccessError('Não foi possível consultar sua assinatura neste momento. Tente novamente em instantes ou fale com o suporte.', 503)


def check_subscription(empresa_id, sensitive=True):
    data = get_entitlements(empresa_id, sensitive=sensitive)
    if data.get('status') not in ('ATIVA', 'TRIAL') or data.get('acesso_produto') is not True:
        raise CommercialAccessError('O acesso ao LiveSun Propostas está indisponível para sua assinatura. Fale com nossa equipe para verificar a situação e regularizar o acesso.')
    return data


def require_active_subscription(view=None, *, sensitive=True):
    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            check_subscription(current_user.empresa_id, sensitive=sensitive)
            return func(*args, **kwargs)
        return wrapped
    return decorate(view) if view else decorate