"""Entrega 2: banco temporário, Central/Brevo simulados, sem rede real."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import pytest
import requests
from sqlalchemy.exc import OperationalError
from src.extensions import db
from src.models import Empresa, Usuario, CadastroPublico, SolicitacaoCentral, Auditoria
from src.models.central import CentralTenant
from src.models.cadastro_publico import utcnow
from src.services import cadastro_central as service
from test_cadastro_publico import app, mail, payload, token_from


PASSWORD = {'senha': 'senha-forte-123', 'confirmar_senha': 'senha-forte-123'}


def configure(app):
    app.config.update(CENTRAL_BASE_URL='https://central.example.com', CENTRAL_API_TOKEN='credencial-teste',
        CENTRAL_WEBHOOK_SECRET='h' * 40, CENTRAL_REGISTRATION_RETRY_SECONDS=120)


def pending_password(app, mail, **changes):
    client = app.test_client()
    client.post('/cadastro', data=payload(**changes))
    client.post('/cadastro/confirmar/' + token_from(mail), data={'confirmar': 'sim'})
    return client


def received_response(payload, status_code=202, **changes):
    return Mock(status_code=status_code, json=Mock(return_value={
        'solicitacao_id': 91, 'empresa_id': payload['empresa_id'], 'evento_id': payload['evento_id'],
        'produto': 'PROPOSTAS', 'status': 'PENDENTE', 'cliente_id': None, 'assinatura_id': None, **changes}))


def finish(app, mail, success=False, **changes):
    configure(app)
    client = pending_password(app, mail, **changes)
    with patch('src.services.cadastro_central.requests.Session') as factory:
        post = factory.return_value.__enter__.return_value.post
        if success:
            post.side_effect = lambda url, **kw: received_response(kw['json'])
        else:
            post.side_effect = requests.Timeout('TOKEN-OU-DADOS-NAO-LOGAR')
        response = client.post('/cadastro/completar', data=PASSWORD)
        assert response.status_code == 302 and response.location.endswith('/cadastro/recebido')
    return client


def allow_retry():
    obj = SolicitacaoCentral.query.one()
    obj.proxima_tentativa_em = utcnow() - timedelta(seconds=1)
    obj.lease_ate = None
    db.session.commit()


def entitlement():
    return {'cliente_id': '123', 'produto': 'PROPOSTAS', 'assinatura_id': 10, 'status': 'ATIVA',
        'plano': 'PROPOSTAS', 'acesso_produto': True, 'modulos': [], 'limites': {}, 'versao': 1,
        'gerado_em': datetime.now(timezone.utc).isoformat(),
        'valido_ate': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}


def callback(client, obj, invalid=False):
    data = {'empresa_id': obj.empresa_id, 'cliente_id': 123, 'assinatura_id': 10, 'solicitacao_id': 91,
        'evento_id': obj.evento_id, 'produto': 'PROPOSTAS', 'status': 'VINCULO_PENDENTE',
        'cnpj_cpf': obj.payload['cnpj_cpf'], 'entitlements': entitlement()}
    raw = json.dumps(data).encode()
    stamp = str(int(time.time()))
    digest = hmac.new(('h' * 40).encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    return client.post('/central/cadastros/vincular', data=raw, content_type='application/json',
        headers={'X-LiveSun-Timestamp': stamp, 'X-LiveSun-Signature': 'sha256=' + ('invalid' if invalid else digest)})


@pytest.mark.parametrize('code', [200, 202])
def test_complete_sends_exact_contract_after_commit(app, mail, code):
    configure(app)
    client = pending_password(app, mail, documento='04.252.011/0001-10')
    with patch('src.services.cadastro_central.requests.Session') as factory:
        http = factory.return_value.__enter__.return_value
        def respond(url, **kwargs):
            assert not db.session().in_transaction()
            assert url == 'https://central.example.com/api/v1/cadastros'
            assert kwargs['allow_redirects'] is False and kwargs['timeout'] == (3, 8)
            assert kwargs['headers']['Authorization'] == 'Bearer credencial-teste'
            body = kwargs['json']
            assert set(body) == {'evento_id', 'empresa_id', 'razao_social', 'nome_fantasia',
                                 'cnpj_cpf', 'email', 'telefone', 'responsavel'}
            assert body['evento_id'] == 'cad_' + hashlib.sha256(f"PROPOSTAS:empresa:{body['empresa_id']}".encode()).hexdigest()[:32]
            assert body['razao_social'] == 'Atividade Teste'
            return received_response(body, code)
        http.post.side_effect = respond
        assert client.post('/cadastro/completar', data=PASSWORD).status_code == 302
        http.post.assert_called_once()
        assert http.trust_env is False
    db.session.expire_all()
    obj = SolicitacaoCentral.query.one()
    assert obj.status == 'RECEBIDA_CENTRAL' and obj.central_solicitacao_id == 91
    assert obj.recebida_em and obj.tentativas == 1 and obj.lease_id is None
    assert Empresa.query.one().razao_social is None and Empresa.query.one().razao_social_pendente
    assert Empresa.query.one().ativo and Usuario.query.one().ativo
    assert CadastroPublico.query.one().status == 'PRONTO_ANALISE'
    assert CentralTenant.query.count() == 0
    for action in ('completar_cadastro', 'preparar_solicitacao_central', 'tentar_envio_central', 'solicitacao_recebida_central'):
        assert Auditoria.query.filter_by(acao=action).count() == 1
    html = client.get('/cadastro/recebido').text
    assert 'Seus dados foram recebidos e estão em análise pela equipe LiveSun.' in html
    assert 'Após a análise, você receberá um e-mail com a liberação do acesso ao LiveSun Propostas.' in html
    assert 'Tentar novamente' not in html and 'credencial-teste' not in html
    assert client.post('/cadastro/completar', data=PASSWORD).status_code == 403
    assert SolicitacaoCentral.query.count() == 1


def test_failure_pending_safe_status_get_and_retry(app, mail, caplog):
    client = finish(app, mail)
    obj = SolicitacaoCentral.query.one()
    assert obj.status == 'PENDENTE' and obj.erro_categoria == 'TIMEOUT'
    assert 'TOKEN-OU-DADOS-NAO-LOGAR' not in caplog.text
    original = dict(obj.payload)
    with patch('src.services.cadastro_central.requests.Session') as factory:
        for _ in range(2):
            response = client.get('/cadastro/recebido')
            assert response.status_code == 200 and 'Tentar novamente' in response.text
        assert client.post('/cadastro/tentar-novamente', data={'retry': 'sim'}).status_code == 302
        factory.assert_not_called()
        allow_retry()
        post = factory.return_value.__enter__.return_value.post
        post.side_effect = lambda url, **kw: received_response(kw['json'], 200)
        assert client.post('/cadastro/tentar-novamente', data={'retry': 'sim'}).status_code == 302
        assert post.call_args.kwargs['json'] == original
        post.assert_called_once()
        assert 'Tentar novamente' not in client.get('/cadastro/recebido').text
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
        assert post.call_count == 1
    db.session.expire_all()
    assert SolicitacaoCentral.query.one().tentativas == 2
    assert SolicitacaoCentral.query.count() == 1


@pytest.mark.parametrize('status,changes', [(401, {}), (500, {}), (302, {}),
    (202, {'produto': 'COMERCIAL'}), (200, {'empresa_id': 999}), (202, {'evento_id': 'cad_outro'}),
    (202, {'solicitacao_id': True}), (202, {'status': 'ATIVA'})])
def test_http_and_invalid_responses_keep_pending(app, mail, status, changes):
    client = finish(app, mail)
    allow_retry()
    with patch('src.services.cadastro_central.requests.Session') as factory:
        factory.return_value.__enter__.return_value.post.side_effect = lambda url, **kw: received_response(kw['json'], status, **changes)
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
    db.session.expire_all()
    obj = SolicitacaoCentral.query.one()
    assert obj.status == 'PENDENTE' and obj.erro_categoria
    assert CentralTenant.query.count() == 0


def test_credentials_missing_and_invalid_url_no_network(app, mail):
    configure(app)
    client = pending_password(app, mail)
    app.config['CENTRAL_API_TOKEN'] = ''
    with patch('src.services.cadastro_central.requests.Session') as factory:
        client.post('/cadastro/completar', data=PASSWORD)
        factory.assert_not_called()
    assert SolicitacaoCentral.query.one().status == 'PENDENTE'
    allow_retry()
    app.config.update(CENTRAL_API_TOKEN='test', CENTRAL_BASE_URL='http://nao-autorizado.example.com')
    with patch('src.services.cadastro_central.requests.Session') as factory:
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
        factory.assert_not_called()


def test_retry_restricted_csrf_rate_limit_and_lease(app, mail):
    client = finish(app, mail)
    assert app.test_client().get('/cadastro/recebido').status_code == 403
    assert app.test_client().post('/cadastro/tentar-novamente', data={'retry': 'sim'}).status_code == 403
    allow_retry()
    obj = SolicitacaoCentral.query.one()
    obj.lease_ate = utcnow() + timedelta(seconds=60)
    db.session.commit()
    with patch('src.services.cadastro_central.requests.Session') as factory:
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
        factory.assert_not_called()
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/cadastro/tentar-novamente', data={'retry': 'sim'}).status_code == 400
    app.config['WTF_CSRF_ENABLED'] = False
    for _ in range(3):
        result = client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
    assert result.status_code == 429


def test_tracking_expiry_tenant_isolation_and_password_rotation(app, mail):
    client = finish(app, mail)
    with client.session_transaction() as state:
        grant = dict(state['cadastro_tracking'])
    stranger = app.test_client()
    with stranger.session_transaction() as state:
        state['cadastro_tracking'] = {**grant, 'empresa_id': grant['empresa_id'] + 1}
    assert stranger.get('/cadastro/recebido').status_code == 403
    with stranger.session_transaction() as state:
        state['cadastro_tracking'] = {**grant, 'expires': int(time.time()) - 1}
    assert stranger.get('/cadastro/recebido').status_code == 403
    user = Usuario.query.one()
    user.set_password('senha-alterada')
    db.session.commit()
    assert client.get('/cadastro/recebido').status_code == 403


def test_login_pending_and_guard_even_when_disabled(app, mail):
    finish(app, mail)
    client = app.test_client()
    assert client.post('/auth/login', data={'usuario': 'admin@example.com', 'senha': 'senha-forte-123'}).location.endswith('/cadastro/recebido')
    with client.session_transaction() as state:
        assert '_user_id' not in state
        assert 'cadastro_tracking' in state
    for path in ('/', '/clientes', '/itens', '/usuarios', '/empresa', '/propostas/'):
        assert client.get(path).status_code == 302
    assert client.get('/cadastro/recebido').status_code == 200
    # Mesmo uma sessão de login prévia/forçada não contorna a barreira.
    user = Usuario.query.one()
    with client.session_transaction() as state:
        state['_user_id'] = str(user.id)
        state['_fresh'] = True
    from flask import g
    g.pop('_login_user', None)  # fixture mantém app_context entre requisições
    assert client.get('/empresa').location.endswith('/cadastro/recebido')
    with client.session_transaction() as state:
        state['_user_id'] = str(user.id)
    g.pop('_login_user', None)
    assert client.post('/propostas/nova', data={'teste': 'sim'}).status_code == 403


def test_callback_unchanged_idempotent_and_existing_entitlements(app, mail):
    client = finish(app, mail, success=True, documento='04.252.011/0001-10')
    obj = SolicitacaoCentral.query.one()
    assert callback(client, obj, invalid=True).status_code == 401
    assert CentralTenant.query.count() == 0
    assert callback(client, obj).status_code == 200
    assert callback(client, obj).status_code == 200
    assert CentralTenant.query.count() == 1
    assert Auditoria.query.filter_by(acao='central_vinculo_criado').count() == 1
    login_data = {'usuario': 'admin@example.com', 'senha': 'senha-forte-123'}
    assert client.post('/auth/login', data=login_data).location.endswith('/cadastro/recebido')
    app.config['CENTRAL_ENABLED'] = True
    result = client.post('/auth/login', data=login_data)
    assert result.status_code == 302 and result.location.endswith('/')
    response = client.get('/')
    assert response.status_code == 200 and 'Complete a razão social' in response.text
    assert client.post('/empresa', data={'nome': 'Atividade Teste', 'razao_social': 'Empresa Real Ltda',
        'cnpj_cpf': '04252011000110', 'email': 'admin@example.com'}).status_code == 302
    assert not Empresa.query.one().razao_social_pendente
    tenant = CentralTenant.query.one()
    tenant.payload = {**tenant.payload, 'status': 'SUSPENSA', 'acesso_produto': False}
    db.session.commit()
    assert client.get('/').status_code == 403


def test_callback_before_post_result_does_not_repeat_request(app, mail):
    client = finish(app, mail)
    obj = SolicitacaoCentral.query.one()
    assert callback(client, obj).status_code == 200
    assert 'Tentar novamente' not in client.get('/cadastro/recebido').text
    allow_retry()
    with patch('src.services.cadastro_central.requests.Session') as factory:
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
        factory.assert_not_called()


def test_tracking_works_with_public_registration_closed(app, mail):
    client = finish(app, mail)
    app.config['PUBLIC_REGISTRATION_ENABLED'] = False
    assert client.get('/cadastro/recebido').status_code == 200
    assert client.get('/cadastro').status_code == 404


def test_transaction_failure_does_not_send_or_activate(app, mail):
    configure(app)
    client = pending_password(app, mail)
    with patch.object(db.session, 'commit', side_effect=OperationalError('private', {}, Exception('secret'))), \
            patch('src.services.cadastro_central.requests.Session') as factory:
        assert client.post('/cadastro/completar', data=PASSWORD).status_code == 503
        factory.assert_not_called()
    db.session.rollback()
    db.session.expire_all()
    assert not Usuario.query.one().ativo and not Empresa.query.one().ativo
    assert CadastroPublico.query.one().status == 'EMAIL_CONFIRMADO'
    assert SolicitacaoCentral.query.count() == 0


def test_legacy_company_login_unaffected(app):
    company = Empresa(nome='Legado')
    db.session.add(company)
    db.session.flush()
    user = Usuario(empresa_id=company.id, nome='Legado', email='legado@example.com', usuario='legado', perfil='admin')
    user.set_password('senha-legada')
    db.session.add(user)
    db.session.commit()
    client = app.test_client()
    assert client.post('/auth/login', data={'usuario': 'legado', 'senha': 'senha-legada'}).status_code == 302
    assert client.get('/empresa').status_code == 200


def test_no_retry_button_without_failure_and_no_get_side_effect(app, mail):
    client = finish(app, mail)
    obj = SolicitacaoCentral.query.one()
    obj.erro_categoria = None
    obj.proxima_tentativa_em = None
    db.session.commit()
    with patch('src.services.cadastro_central.requests.Session') as factory:
        assert 'Tentar novamente' not in client.get('/cadastro/recebido').text
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
        factory.assert_not_called()
    assert SolicitacaoCentral.query.one().tentativas == 1


@pytest.mark.parametrize('error', [requests.ConnectionError('DADO_PRIVADO'), ValueError('TOKEN_PRIVADO')])
def test_connection_and_json_error_are_safe(app, mail, error, caplog):
    client = finish(app, mail)
    allow_retry()
    with patch('src.services.cadastro_central.requests.Session') as factory:
        post = factory.return_value.__enter__.return_value.post
        if isinstance(error, requests.ConnectionError):
            post.side_effect = error
        else:
            post.return_value = Mock(status_code=202, json=Mock(side_effect=error))
        client.post('/cadastro/tentar-novamente', data={'retry': 'sim'})
    assert SolicitacaoCentral.query.one().status == 'PENDENTE'
    assert 'DADO_PRIVADO' not in caplog.text and 'TOKEN_PRIVADO' not in caplog.text


def test_reentrant_send_cannot_claim_same_request(app, mail):
    client = finish(app, mail)
    allow_retry()
    obj = SolicitacaoCentral.query.one()
    identifier = obj.cadastro_id
    original_payload = dict(obj.payload)
    db.session.rollback()
    with patch('src.services.cadastro_central.requests.Session') as factory:
        post = factory.return_value.__enter__.return_value.post
        def reentrant(url, **kwargs):
            assert service.send(identifier, manual=True) is False
            return received_response(original_payload)
        post.side_effect = reentrant
        assert service.send(identifier, manual=True)
        post.assert_called_once()


def test_result_persistence_failure_does_not_repeat_post(app, mail):
    finish(app, mail)
    allow_retry()
    obj = SolicitacaoCentral.query.one()
    identifier, body = obj.cadastro_id, dict(obj.payload)
    db.session.rollback()
    real_commit = db.session.commit
    count = 0
    def commit():
        nonlocal count
        count += 1
        if count == 2:
            raise OperationalError('private', {}, Exception('nao-logar'))
        return real_commit()
    with patch.object(db.session, 'commit', side_effect=commit), patch('src.services.cadastro_central.requests.Session') as factory:
        factory.return_value.__enter__.return_value.post.return_value = received_response(body)
        service.send(identifier, manual=True)
        factory.return_value.__enter__.return_value.post.assert_called_once()
    db.session.expire_all()
    obj = SolicitacaoCentral.query.one()
    assert obj.status == 'PENDENTE' and obj.erro_categoria == 'ENVIO_NAO_CONFIRMADO'
    assert obj.lease_ate is not None