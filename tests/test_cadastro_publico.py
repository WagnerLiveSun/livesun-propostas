import hashlib
import re
from datetime import timedelta
from unittest.mock import patch
import pytest
from sqlalchemy.exc import IntegrityError
from src.app import create_app
from src.extensions import db
from src.models import Empresa, Usuario, Auditoria
from src.models.cadastro_publico import CadastroPublico, TentativaConfirmacaoEmail, utcnow
from src.services.cadastro_diagnostico import diagnose


@pytest.fixture
def app(tmp_path):
    app = create_app('testing', {'UPLOAD_FOLDER': str(tmp_path), 'CENTRAL_ENABLED': False,
        'CENTRAL_ALLOW_LOCAL_HTTP': False, 'PUBLIC_REGISTRATION_ENABLED': True,
        'PUBLIC_REGISTRATION_DATA_REVIEWED': True, 'PUBLIC_BASE_URL': 'https://propostas.example.com',
        'TERMS_URL': 'https://propostas.example.com/termos', 'PRIVACY_URL': 'https://propostas.example.com/privacidade',
        'TERMS_VERSION': '2026-11', 'PRIVACY_VERSION': '2026-11',
        'PUBLIC_REGISTRATION_RATE_LIMIT': '1000 per hour', 'REGISTRATION_IDENTITY_RATE_LIMIT': '1000 per hour',
        'CONFIRMATION_RESEND_RATE_LIMIT': '1000 per hour', 'CONFIRMATION_RESEND_COOLDOWN_SECONDS': 1,
        'RATELIMIT_STORAGE_URI': 'memory://'})
    with app.app_context():
        assert db.engine.dialect.name == 'sqlite' and db.engine.url.database == ':memory:'
        db.create_all()
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Rede proibida nos testes')):
            yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def mail():
    with patch('src.services.cadastro.brevo_service.send_transactional_email', return_value=True) as mock:
        yield mock


def payload(**changes):
    data = {'nome': 'Pessoa Teste', 'empresa': 'Atividade Teste', 'documento': '529.982.247-25',
        'telefone': '11999999999', 'email': 'admin@example.com', 'aceite': 'on'}
    data.update(changes)
    return data


def token_from(mail):
    return re.search(r'/cadastro/confirmar/([A-Za-z0-9_-]+)', mail.call_args.args[3]).group(1)


def test_valid_pending_registration_and_confirmation(app, mail):
    client = app.test_client()
    response = client.post('/cadastro', data=payload())
    assert response.status_code == 200
    row = CadastroPublico.query.one()
    token = token_from(mail)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in repr(row.__dict__)
    assert row.termos_versao == '2026-11' and row.aceite_em
    assert not Empresa.query.one().ativo and not Usuario.query.one().ativo
    assert not Usuario.query.one().check_password('senha-forte-123')
    assert TentativaConfirmacaoEmail.query.one().status == 'ACEITA_BREVO'
    path = '/cadastro/confirmar/' + token
    assert client.get(path).status_code == 200
    assert CadastroPublico.query.one().token_hash
    assert client.post(path, data={'confirmar': 'sim'}).location.endswith('/cadastro/completar')
    db.session.expire_all()
    row = CadastroPublico.query.one()
    assert row.token_hash != hashlib.sha256(token.encode()).hexdigest() and row.confirmado_em and row.status == 'EMAIL_CONFIRMADO'
    assert 'já utilizado' in client.post(path, data={'confirmar': 'sim'}).text
    assert not Usuario.query.one().is_active
    assert client.post('/cadastro/completar', data={'senha': 'senha-forte-123', 'confirmar_senha': 'senha-forte-123'}).location.endswith('/cadastro/recebido')
    db.session.expire_all()
    assert Usuario.query.one().is_active
    assert CadastroPublico.query.one().status == 'PRONTO_ANALISE'
    assert CadastroPublico.query.one().token_hash is None
    assert client.post('/auth/login', data={'usuario': 'admin@example.com', 'senha': 'senha-forte-123'}).location.endswith('/cadastro/recebido')
    assert Auditoria.query.filter_by(acao='confirmar_email').count() == 1
    assert response.headers['Referrer-Policy'] == 'origin'


def test_https_confirmation_csrf_origin_without_token_leak(app, mail):
    client = app.test_client()
    client.post('/cadastro', data=payload())
    token = token_from(mail)
    path = '/cadastro/confirmar/' + token
    app.config.update(WTF_CSRF_ENABLED=True, WTF_CSRF_SSL_STRICT=True, SESSION_COOKIE_SECURE=True)
    origin = 'https://localhost'
    page = client.get(path, base_url=origin)
    assert page.status_code == 200 and page.headers['Referrer-Policy'] == 'origin'
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    data = {'csrf_token': csrf, 'confirmar': 'sim'}
    assert client.post(path, data=data, base_url=origin).status_code == 400
    assert client.post(path, data=data, base_url=origin, headers={'Referer': 'https://outro.example/'}).status_code == 400
    assert client.post(path, data={'confirmar': 'sim'}, base_url=origin, headers={'Referer': origin + '/'}).status_code == 400
    result = client.post(path, data=data, base_url=origin, headers={'Referer': origin + '/'})
    assert result.status_code == 302 and result.location.endswith('/cadastro/completar')
    assert token not in (origin + '/')
    completion = client.get(result.location, base_url=origin)
    assert completion.status_code == 200 and completion.headers['Referrer-Policy'] == 'origin'


def test_valid_pj(app, mail):
    assert app.test_client().post('/cadastro', data=payload(tipo_pessoa='PJ', documento='04.252.011/0001-10',
        razao_social='Empresa Teste', nome_fantasia='Teste', responsavel='Responsável')).status_code == 200
    assert CadastroPublico.query.one().tipo_pessoa == 'PJ'


@pytest.mark.parametrize('changes', [{'documento': '11111111111'}, {'documento': 'abc52998224725'},
    {'empresa': ''}, {'email': 'errado'},
    {'aceite': ''}, {'telefone': ''}, {'nome': ''}, {'email': 'x'*121}])
def test_invalid_registration(app, mail, changes):
    assert app.test_client().post('/cadastro', data=payload(**changes)).status_code == 422
    assert Empresa.query.count() == Usuario.query.count() == 0
    mail.assert_not_called()


@pytest.mark.parametrize('changes', [{}, {'documento': '11144477735'}, {'email': 'outro@example.com'}])
def test_duplicates_generic_and_no_new_records(app, mail, changes):
    client = app.test_client()
    first = client.post('/cadastro', data=payload())
    second = client.post('/cadastro', data=payload(**changes))
    assert first.data == second.data
    assert Usuario.query.count() == Empresa.query.count() == 1
    assert mail.call_count == 1


def test_expired_token_and_resend_invalidates_old(app, mail):
    client = app.test_client()
    client.post('/cadastro', data=payload())
    token = token_from(mail)
    row = CadastroPublico.query.one()
    row.expira_em = row.proximo_envio_em = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert 'Link inválido' in client.post('/cadastro/confirmar/' + token, data={'confirmar': 'sim'}).text
    expected = client.post('/cadastro/reenviar-confirmacao', data={'email': 'ADMIN@example.com'})
    new_token = token_from(mail)
    assert token != new_token and mail.call_count == 2
    assert 'Link inválido' in client.post('/cadastro/confirmar/' + token, data={'confirmar': 'sim'}).text
    assert expected.data == client.post('/cadastro/reenviar-confirmacao', data={'email': 'ausente@example.com'}).data
    assert client.post('/cadastro/confirmar/' + new_token, data={'confirmar': 'sim'}).location.endswith('/cadastro/completar')


def test_resend_cooldown_and_honeypot(app, mail):
    client = app.test_client()
    client.post('/cadastro', data=payload(website='bot'))
    assert Empresa.query.count() == 0
    client.post('/cadastro', data=payload())
    client.post('/cadastro/reenviar-confirmacao', data={'email': 'admin@example.com'})
    assert mail.call_count == 1


@pytest.mark.parametrize('failure', [False, RuntimeError('segredo-nao-pode-vazar')])
def test_mail_failure_keeps_pending_and_safe(app, mail, failure, caplog):
    if isinstance(failure, Exception):
        mail.side_effect = failure
    else:
        mail.return_value = False
    response = app.test_client().post('/cadastro', data=payload())
    assert response.status_code == 200
    assert CadastroPublico.query.one().status == 'PENDENTE_EMAIL'
    assert TentativaConfirmacaoEmail.query.one().status in ('NAO_CONFIRMADA', 'INDETERMINADA')
    assert 'segredo-nao-pode-vazar' not in response.text + caplog.text


def test_csrf_payload_and_content_type(app, mail):
    client = app.test_client()
    assert client.post('/cadastro', json=payload()).status_code == 415
    assert client.post('/cadastro', data=payload(nome='x'*17000)).status_code == 413
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/cadastro', data=payload()).status_code == 400
    page = client.get('/cadastro')
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    assert client.post('/cadastro', data=payload(csrf_token=csrf)).status_code == 200


def test_disabled_registration(app, mail):
    app.config['PUBLIC_REGISTRATION_ENABLED'] = False
    assert app.test_client().get('/cadastro').status_code == 404


def test_development_preview_read_only_without_legal_documents(tmp_path):
    preview = create_app('development', {'UPLOAD_FOLDER': str(tmp_path),
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'PUBLIC_REGISTRATION_ENABLED': False,
        'PUBLIC_REGISTRATION_PREVIEW': True, 'TERMS_URL': '', 'PRIVACY_URL': '',
        'CENTRAL_ENABLED': False, 'CENTRAL_ALLOW_LOCAL_HTTP': False, 'WTF_CSRF_ENABLED': False})
    with patch('src.services.cadastro.brevo_service.send_transactional_email') as mail:
        client = preview.test_client()
        response = client.get('/cadastro')
        assert response.status_code == 200 and 'Visualização local' in response.text
        assert 'disabled' in response.text and 'href=""' not in response.text
        assert client.post('/cadastro', data=payload()).status_code == 403
        assert client.get('/cadastro/reenviar-confirmacao').status_code == 403
        assert client.post('/cadastro/reenviar-confirmacao', data={'email': 'test@example.com'}).status_code == 403
        assert client.get('/cadastro/confirmar/qualquer').status_code == 403
        assert 'Visualizar cadastro' in client.get('/auth/login').text
        mail.assert_not_called()


def test_preview_refused_outside_development(tmp_path):
    with pytest.raises(RuntimeError, match='exclusiva de desenvolvimento'):
        create_app('testing', {'UPLOAD_FOLDER': str(tmp_path), 'PUBLIC_REGISTRATION_PREVIEW': True})


def test_missing_review_refuses_startup(tmp_path):
    with pytest.raises(RuntimeError, match='diagnóstico'):
        create_app('testing', {'UPLOAD_FOLDER': str(tmp_path), 'PUBLIC_REGISTRATION_ENABLED': True,
            'PUBLIC_REGISTRATION_DATA_REVIEWED': False})


def test_global_normalized_identity_enforced_by_database(app, mail):
    app.test_client().post('/cadastro', data=payload())
    company = Empresa(nome='Outra')
    db.session.add(company)
    db.session.flush()
    user = Usuario(empresa_id=company.id, nome='Outro', usuario='outro', email=' ADMIN@EXAMPLE.COM ')
    user.set_password('senha1234')
    db.session.add(user)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    db.session.add(Empresa(nome='Outra', cnpj_cpf='52998224725'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_diagnostic_is_aggregate(app, mail):
    app.test_client().post('/cadastro', data=payload())
    with db.engine.connect() as connection:
        result = diagnose(connection)
    assert result['empresas'] == 1 and result['usuarios_ativos'] == 0
    assert result['grupos_email_duplicado'] == 0
    assert 'admin@example.com' not in repr(result) and '52998224725' not in repr(result)


def test_rate_limit_per_ip(app, mail):
    app.config['PUBLIC_REGISTRATION_RATE_LIMIT'] = '1 per hour'
    client = app.test_client()
    assert client.post('/cadastro', data=payload()).status_code == 200
    assert client.post('/cadastro', data=payload()).status_code == 429


def test_rate_limit_identity_across_ips(app, mail):
    app.config['REGISTRATION_IDENTITY_RATE_LIMIT'] = '1 per hour'
    client = app.test_client()
    assert client.post('/cadastro', data=payload(), environ_base={'REMOTE_ADDR': '192.0.2.1'}).status_code == 200
    assert client.post('/cadastro', data=payload(), environ_base={'REMOTE_ADDR': '192.0.2.2'}).status_code == 429


def test_access_and_rate_logs_redact_secrets(app):
    import logging
    # Alembic pode desabilitar loggers na suíte; exercitar os filtros registrados.
    access = logging.LogRecord('werkzeug', logging.INFO, '', 0,
        'GET /cadastro/confirmar/%s HTTP/1.1', ('TOKEN-SECRETO',), None)
    rate = logging.LogRecord('flask-limiter', logging.INFO, '', 0,
        'limite excedido para %s', ('IDENTIDADE-SECRETA',), None)
    assert logging.getLogger('werkzeug').filter(access)
    assert logging.getLogger('flask-limiter').filter(rate)
    assert 'TOKEN-SECRETO' not in access.getMessage() and 'IDENTIDADE-SECRETA' not in rate.getMessage()
    assert 'confirmation_http_request' in access.getMessage() and 'rate_limit_event' in rate.getMessage()


def test_email_escaping_and_pending_routes(app, mail):
    client = app.test_client()
    client.post('/cadastro', data=payload(nome='<script>alert(1)</script>'))
    assert '<script>' not in mail.call_args.args[3]
    assert '&lt;script&gt;' in mail.call_args.args[3]
    assert client.get('/cadastro/reenviar-confirmacao').status_code == 200
    assert client.post('/cadastro/confirmar/invalido', data={'confirmar': 'sim'}).status_code == 200
    for path in ('/', '/empresa', '/usuarios', '/clientes', '/itens', '/propostas/'):
        assert client.get(path).status_code == 302