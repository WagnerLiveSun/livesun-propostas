"""Política única para todas as empresas; sem rede, Brevo ou banco de uso."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch
import pytest
import requests
from flask import g
from src.app import create_app
from src.extensions import db
from src.models import Empresa, Usuario, Proposta, Auditoria
from src.models.central import CentralTenant
from src.models.commercial_usage import CommercialUsage, TrialProposal, WelcomePreference
from src.services import commercial_usage as service


@pytest.fixture
def commercial_app(tmp_path):
    app = create_app('testing', {'UPLOAD_FOLDER': str(tmp_path), 'CENTRAL_ENABLED': True,
        'CENTRAL_API_TOKEN': 'test-only', 'CENTRAL_WEBHOOK_SECRET': 'h' * 40,
        'CENTRAL_BASE_URL': 'https://central.example.com', 'CENTRAL_ALLOW_LOCAL_HTTP': False,
        'PUBLIC_REGISTRATION_ENABLED': False, 'CENTRAL_CHECKOUT_URL': 'https://central.example.com/contratar'})
    with app.app_context():
        assert db.engine.dialect.name == 'sqlite'
        db.create_all()
        company = Empresa(nome='Empresa Trial')
        other = Empresa(nome='Outra Empresa')
        db.session.add_all([company, other]); db.session.flush()
        user = Usuario(empresa_id=company.id, nome='Admin', email='admin@example.com', usuario='trial', perfil='admin')
        user.set_password('senha1234'); db.session.add(user)
        instant = datetime.now(timezone.utc)
        data = {'cliente_id': '10', 'produto': 'PROPOSTAS', 'assinatura_id': 20, 'versao': 1,
            'plano': 'PROPOSTAS', 'status': 'TRIAL', 'acesso_produto': True, 'modulos': [], 'limites': {},
            'gerado_em': instant.isoformat(), 'valido_ate': (instant + timedelta(minutes=15)).isoformat()}
        db.session.add(CentralTenant(empresa_id=company.id, central_cliente_id=10, assinatura_id=20, versao=1,
            payload=data, valido_ate=(instant + timedelta(minutes=15)).replace(tzinfo=None)))
        db.session.add(CommercialUsage(empresa_id=company.id, assinatura_id=20, versao=1,
            data_inicio=date.today() - timedelta(days=1), trial_ate=date.today() + timedelta(days=6),
            valido_ate=(instant + timedelta(minutes=15)).replace(tzinfo=None), inicializado=True, criadas=0))
        db.session.commit()
        app.company_id, app.other_id = company.id, other.id
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Rede externa proibida')):
            yield app
        db.session.remove(); db.drop_all()


def login(app):
    g.pop('_login_user', None)
    client = app.test_client()
    assert client.post('/auth/login', data={'usuario': 'trial', 'senha': 'senha1234'}).status_code == 302
    return client


def form():
    return {'cliente_nome': 'Cliente', 'cliente_telefone': '11999999999',
        'data_emissao': date.today().isoformat(), 'codigo[]': ['A'], 'descricao[]': ['Serviço'],
        'quantidade[]': ['1'], 'unidade[]': ['UN'], 'valor_unitario[]': ['100']}


def set_status(status, allowed=False):
    tenant = CentralTenant.query.one()
    tenant.payload = {**tenant.payload, 'status': status, 'acesso_produto': allowed}
    db.session.commit()


def test_ten_creations_eleventh_and_replication_blocked(commercial_app):
    client = login(commercial_app)
    for _ in range(10):
        assert client.post('/propostas/nova', data=form()).status_code == 302
    assert CommercialUsage.query.one().criadas == 10
    assert TrialProposal.query.count() == 10
    assert client.post('/propostas/nova', data=form()).status_code == 403
    proposal = Proposta.query.first()
    assert client.post(f'/propostas/{proposal.id}/replicar', data={'retry': 'yes'}).status_code == 403
    assert Proposta.query.count() == 10
    assert 'Contratar agora' in client.get('/').text
    assert Auditoria.query.filter_by(acao='consumir_quota_trial').count() == 10


def test_replication_consumes_and_invalid_creation_rolls_back(commercial_app):
    client = login(commercial_app)
    client.post('/propostas/nova', data=form())
    proposal = Proposta.query.one()
    assert client.post(f'/propostas/{proposal.id}/replicar', data={'copy': 'yes'}).status_code == 302
    assert CommercialUsage.query.one().criadas == 2
    client.post('/propostas/nova', data={**form(), 'cliente_nome': ''})
    assert CommercialUsage.query.one().criadas == 2
    assert Proposta.query.count() == 2


def test_sending_and_resending_do_not_consume(commercial_app):
    client = login(commercial_app)
    client.post('/propostas/nova', data=form())
    proposal = Proposta.query.one()
    with patch('src.routes.propostas.generate_pdf', return_value=b'%PDF-test'), \
            patch('src.routes.propostas.brevo_service.send_transactional_email', return_value=True) as mail:
        for _ in range(2):
            assert client.post(f'/propostas/{proposal.id}/enviar', data={
                'destinatario': 'cliente@example.com', 'assunto': 'Proposta', 'mensagem': 'Olá'}).status_code == 302
        assert mail.call_count == 2
    assert CommercialUsage.query.one().criadas == 1


@pytest.mark.parametrize('status', ['SUSPENSA', 'BLOQUEADA', 'CANCELADA', 'EXPIRADA', 'TRIAL_VENCIDO'])
def test_restricted_only_list_detail_pdf(commercial_app, status):
    client = login(commercial_app)
    client.post('/propostas/nova', data=form())
    proposal = Proposta.query.one()
    usage = CommercialUsage.query.one()
    if status == 'TRIAL_VENCIDO':
        usage.trial_ate = date.today()
        set_status('TRIAL', False)
    else:
        set_status(status)
        if status == 'SUSPENSA':
            usage.suspensa_inadimplencia = True
            db.session.commit()
    reader = login(commercial_app)
    assert reader.get('/propostas/').status_code == 200
    assert reader.get(f'/propostas/{proposal.id}').status_code == 200
    with patch('src.routes.propostas.generate_pdf', return_value=b'%PDF-test'):
        assert reader.get(f'/propostas/{proposal.id}/pdf').status_code == 200
    for path in ('/', '/empresa', '/clientes', '/itens', '/usuarios', '/auth/perfil',
                 '/propostas/nova', f'/propostas/{proposal.id}/editar', f'/propostas/{proposal.id}/imprimir'):
        assert reader.get(path).status_code == 403
    for path in (f'/propostas/{proposal.id}/replicar', f'/propostas/{proposal.id}/enviar', f'/propostas/{proposal.id}/status'):
        assert reader.post(path, data={'status': 'aceita'}).status_code == 403


def test_excluded_disabled_and_expired_cache_fail_closed(commercial_app):
    set_status('EXCLUIDA')
    client = commercial_app.test_client()
    assert client.post('/auth/login', data={'usuario': 'trial', 'senha': 'senha1234'}).status_code == 403
    commercial_app.config['CENTRAL_ENABLED'] = False
    assert client.post('/auth/login', data={'usuario': 'trial', 'senha': 'senha1234'}).status_code == 503
    commercial_app.config['CENTRAL_ENABLED'] = True
    set_status('SUSPENSA')
    tenant = CentralTenant.query.one(); tenant.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db.session.commit()
    with patch('requests.get', side_effect=requests.ConnectionError()):
        assert client.post('/auth/login', data={'usuario': 'trial', 'senha': 'senha1234'}).status_code == 503


def test_active_removes_trial_limit_welcome_dismissal_and_near_banner(commercial_app):
    client = login(commercial_app)
    usage = CommercialUsage.query.one(); usage.criadas = 10; usage.trial_ate = date.today() + timedelta(days=3)
    db.session.commit()
    assert 'Contratar agora' in client.get('/').text
    assert 'Bem-vindo' in client.get('/').text
    assert client.post('/boas-vindas/ocultar', data={'hide': 'yes'}).status_code == 302
    assert WelcomePreference.query.one().oculto
    assert 'id="welcome-title"' not in client.get('/').text
    set_status('ATIVA', True)
    assert client.post('/propostas/nova', data=form()).status_code == 302
    assert CommercialUsage.query.one().criadas == 10


def test_initial_count_uses_creation_period_and_other_tenant_excluded(commercial_app):
    client = login(commercial_app)
    client.post('/propostas/nova', data=form())
    row = CommercialUsage.query.one(); row.inicializado = False
    db.session.add(Proposta(empresa_id=commercial_app.other_id, numero='OTHER', cliente_nome='Outra',
        cliente_telefone='123', data_emissao=date.today(), data_criacao=datetime.now(timezone.utc)))
    db.session.commit()
    client.get('/')
    assert CommercialUsage.query.one().criadas == 1


def test_invalid_checkout_omitted_and_foreign_proposal_denied(commercial_app):
    commercial_app.config['CENTRAL_CHECKOUT_URL'] = 'javascript:alert(1)'
    assert service.checkout_url() is None
    client = login(commercial_app)
    other = Proposta(empresa_id=commercial_app.other_id, numero='OTHER', cliente_nome='Outra',
        cliente_telefone='123', data_emissao=date.today())
    db.session.add(other); db.session.commit()
    assert client.get(f'/propostas/{other.id}').status_code == 404


def test_detail_contract_and_cache_refresh(commercial_app):
    tenant = CentralTenant.query.one(); usage = CommercialUsage.query.one()
    usage.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db.session.commit()
    body = {'id': 20, 'cliente_id': 10, 'versao': 1, 'status': 'TRIAL', 'data_inicio': usage.data_inicio.isoformat(),
        'trial_ate': usage.trial_ate.isoformat(), 'data_fim': None, 'entitlements': dict(tenant.payload)}
    with patch('src.services.commercial_usage.requests.Session') as factory:
        http = factory.return_value.__enter__.return_value
        http.get.return_value = Mock(status_code=200, json=Mock(return_value=body))
        result = service.details(commercial_app.company_id, tenant.payload)
        assert result.trial_ate == usage.trial_ate
        assert http.get.call_args.args[0].endswith('/api/v1/assinaturas/20')
        assert http.trust_env is False


def test_reservation_rollback_and_no_overflow_on_repeated_requests(commercial_app):
    login(commercial_app)
    with commercial_app.test_request_context('/'):
        service.authorize(commercial_app.company_id, 'propostas.nova', 'POST')
        p = Proposta(empresa_id=commercial_app.company_id, numero='ROLLBACK', cliente_nome='Teste',
            cliente_telefone='123', data_emissao=date.today())
        service.reserve_creation(p)
        db.session.rollback()
    assert CommercialUsage.query.one().criadas == 0
    assert Proposta.query.count() == 0


def test_concurrent_quota_reservations_on_isolated_database(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import OperationalError
    from src.services.central_client import CommercialAccessError
    import time as clock
    app = create_app('testing', {'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'concurrency.sqlite'),
        'CENTRAL_ENABLED': False, 'PUBLIC_REGISTRATION_ENABLED': False})
    with app.app_context():
        db.create_all()
        company = Empresa(nome='Concorrencia')
        db.session.add(company); db.session.flush()
        company_id = company.id
        instant = datetime.now(timezone.utc)
        db.session.add(CentralTenant(empresa_id=company_id, central_cliente_id=10, assinatura_id=20, versao=1,
            payload={'status': 'TRIAL', 'acesso_produto': True},
            valido_ate=(instant+timedelta(minutes=15)).replace(tzinfo=None)))
        db.session.add(CommercialUsage(empresa_id=company_id, assinatura_id=20, versao=1,
            data_inicio=date.today(), trial_ate=date.today()+timedelta(days=7),
            valido_ate=(instant+timedelta(minutes=15)).replace(tzinfo=None), inicializado=True, criadas=0))
        db.session.commit()
    def attempt(index):
        with app.test_request_context('/'):
            for _ in range(15):
                try:
                    # O guard foi validado antes; reserva relê autorização sob lock.
                    g.commercial_state = {'status': 'TRIAL'}
                    proposal = Proposta(empresa_id=company_id, numero=f'C-{index}',
                        cliente_nome='Teste', cliente_telefone='123', data_emissao=date.today())
                    service.reserve_creation(proposal)
                    db.session.commit()
                    return True
                except CommercialAccessError:
                    db.session.rollback(); return False
                except OperationalError:
                    db.session.rollback(); clock.sleep(.02)
            raise AssertionError('Contencao nao resolvida')
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(15)))
    with app.app_context():
        assert sum(results) == 10
        assert CommercialUsage.query.one().criadas == 10
        assert Proposta.query.count() == TrialProposal.query.count() == 10
        db.session.remove(); db.engine.dispose()


def test_expired_dates_and_invalid_details_deny_writes(commercial_app):
    tenant = CentralTenant.query.one(); usage = CommercialUsage.query.one()
    usage.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db.session.commit()
    with patch('src.services.commercial_usage.requests.Session') as factory:
        factory.return_value.__enter__.return_value.get.return_value = Mock(
            status_code=200, json=Mock(return_value={'id': 999, 'entitlements': tenant.payload}))
        response = commercial_app.test_client().post('/auth/login', data={'usuario': 'trial', 'senha': 'senha1234'})
        assert response.status_code == 503


def test_trial_extension_never_resets_consumed_usage(commercial_app):
    client = login(commercial_app)
    client.post('/propostas/nova', data=form())
    row = CommercialUsage.query.one(); row.inicializado = False
    row.trial_ate += timedelta(days=3)
    db.session.commit()
    client.get('/')
    assert CommercialUsage.query.one().criadas == 1


def test_details_expired_or_older_snapshot_cannot_authorize(commercial_app):
    from src.services.central_client import CommercialAccessError
    tenant = CentralTenant.query.one()
    usage = CommercialUsage.query.one()
    usage.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db.session.commit()
    expired = datetime.now(timezone.utc) - timedelta(minutes=20)
    body = {'id': 20, 'cliente_id': 10, 'versao': 1, 'status': 'TRIAL',
        'data_inicio': usage.data_inicio.isoformat(), 'trial_ate': usage.trial_ate.isoformat(),
        'data_fim': None, 'entitlements': {**tenant.payload,
        'gerado_em': expired.isoformat(), 'valido_ate': (expired + timedelta(minutes=1)).isoformat()}}
    with patch('src.services.commercial_usage.requests.Session') as factory:
        factory.return_value.__enter__.return_value.get.return_value = Mock(status_code=200, json=Mock(return_value=body))
        with pytest.raises(CommercialAccessError):
            service.details(commercial_app.company_id, tenant.payload)


def test_send_is_revalidated_after_pdf_and_never_calls_brevo_on_revocation(commercial_app):
    client = login(commercial_app)
    client.post('/propostas/nova', data=form())
    proposal = Proposta.query.one()
    def revoke_during_pdf(html):
        tenant = CentralTenant.query.one()
        tenant.payload = {**tenant.payload, 'status': 'BLOQUEADA', 'acesso_produto': False}
        db.session.commit()
        return b'%PDF-test'
    with patch('src.routes.propostas.generate_pdf', side_effect=revoke_during_pdf), \
            patch('src.routes.propostas.brevo_service.send_transactional_email') as mail:
        response = client.post(f'/propostas/{proposal.id}/enviar', data={
            'destinatario': 'cliente@example.com', 'assunto': 'Proposta', 'mensagem': 'Teste'})
        assert response.status_code == 403
        mail.assert_not_called()
    from src.models import EnvioEmail
    assert EnvioEmail.query.one().status == 'falha'


def test_suspended_inadimplencia_shows_safe_checkout(commercial_app):
    client = login(commercial_app)
    set_status('SUSPENSA')
    usage = CommercialUsage.query.one()
    usage.suspensa_inadimplencia = True
    db.session.commit()
    html = client.get('/propostas/').text
    assert 'Contratar agora' in html
    assert '/central/contratar' in html
    assert '?cliente=' not in html