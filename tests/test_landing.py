"""Landing e cadastro progressivo: dados temporários e nenhuma rede externa."""
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
import pytest
from src.extensions import db
from src.models import Empresa, Usuario, Auditoria
from src.models.cadastro_publico import CadastroPublico, utcnow
from test_cadastro_publico import app, mail, payload, token_from


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.h1_count = 0
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input':
            self.inputs.append(attrs)
        if tag == 'h1':
            self.h1_count += 1
        if 'id' in attrs:
            self.ids.append(attrs['id'])


def test_public_landing_structure_and_five_fields(app):
    response = app.test_client().get('/lp/propostas')
    assert response.status_code == 200
    html = response.text
    tags = Tags()
    tags.feed(html)
    assert tags.h1_count == 1
    assert len(tags.ids) == len(set(tags.ids))
    assert {i['name'] for i in tags.inputs if i.get('type') != 'hidden'} == {
        'email', 'nome', 'telefone', 'empresa', 'documento', 'aceite', 'website'}
    assert not any(i.get('type') == 'password' for i in tags.inputs)
    assert 'name="description"' in html and 'property="og:title"' in html
    assert 'content="index, follow"' in html and 'rel="canonical"' in html
    assert 'https://propostas.example.com/lp/propostas' in html
    for section in ('recursos', 'como-funciona', 'demonstracao', 'para-quem', 'faq', 'cadastro'):
        assert section in tags.ids
    assert 'Demonstração ilustrativa' in html and 'demo-proposta-logo.png' in html
    assert 'cdnjs.cloudflare.com' not in html and 'fonts.googleapis.com' not in html
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'Preços' not in html and '#precos' not in html
    assert 'https://app.pipefy.com/public/form/ETeM9Gbz' in html
    assert app.test_client().get('/propostas-comerciais').status_code == 404
    assert app.test_client().get('/propostas/').status_code == 302


def test_login_secondary_links_are_compact_and_use_new_route(app):
    html = app.test_client().get('/auth/login').text
    assert 'class="login-discover"' in html and 'class="login-signup"' in html
    assert 'href="/lp/propostas"' in html
    assert 'Criar minha conta' in html
    assert 'Criar conta no LiveSun Propostas' not in html


def test_landing_available_when_registration_disabled(app):
    app.config['PUBLIC_REGISTRATION_ENABLED'] = False
    html = app.test_client().get('/lp/propostas').text
    assert 'temporariamente indisponível' in html and 'name="email"' not in html
    assert app.test_client().get('/').status_code == 302


def start_confirmation(app, mail, **changes):
    client = app.test_client()
    client.post('/cadastro', data=payload(**changes))
    token = token_from(mail)
    result = client.post('/cadastro/confirmar/' + token, data={'confirmar': 'sim'})
    assert result.status_code == 302
    return client


def test_completion_requires_confirmed_grant_and_password(app, mail):
    assert app.test_client().get('/cadastro/completar').status_code == 403
    client = start_confirmation(app, mail)
    assert 'senha' in client.get('/cadastro/completar').text
    for data in ({'senha': 'curta', 'confirmar_senha': 'curta'},
                 {'senha': 'senha-valida', 'confirmar_senha': 'diferente'}):
        assert client.post('/cadastro/completar', data=data).status_code == 422
    assert client.post('/cadastro/completar', data={'senha': 'senha-valida', 'confirmar_senha': 'senha-valida'}).status_code == 302
    assert Usuario.query.one().ativo and Empresa.query.one().ativo
    assert Auditoria.query.filter_by(acao='completar_cadastro').count() == 1
    assert client.get('/cadastro/completar').status_code == 403


def test_completion_stores_only_hash_and_does_not_login(app, mail):
    import hashlib
    client = start_confirmation(app, mail)
    with client.session_transaction() as session:
        grant = dict(session['cadastro_completion'])
        assert '_user_id' not in session
    assert CadastroPublico.query.one().token_hash == hashlib.sha256(grant['secret'].encode()).hexdigest()
    assert grant['secret'] not in client.get('/cadastro/completar').text
    assert 'admin@example.com' not in client.get('/cadastro/completar').text


def test_completion_pj_only_password_preserves_company(app, mail):
    client = start_confirmation(app, mail, documento='04.252.011/0001-10')
    assert Empresa.query.one().razao_social is None
    tags = Tags()
    tags.feed(client.get('/cadastro/completar').text)
    assert {i['name'] for i in tags.inputs if i.get('type') != 'hidden'} == {'senha', 'confirmar_senha'}
    data = {'senha': 'senha-valida', 'confirmar_senha': 'senha-valida',
            'razao_social': 'NAO ALTERAR', 'nome_fantasia': 'NAO ALTERAR'}
    assert client.post('/cadastro/completar', data=data).status_code == 302
    assert Empresa.query.one().razao_social is None
    assert Empresa.query.one().nome == 'Atividade Teste'
    assert Usuario.query.one().ativo and Empresa.query.one().ativo


def test_expired_completion_and_new_link(app, mail):
    client = start_confirmation(app, mail)
    row = CadastroPublico.query.one()
    row.expira_em = row.proximo_envio_em = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert client.get('/cadastro/completar').status_code == 403
    client.post('/cadastro/reenviar-confirmacao', data={'email': 'admin@example.com'})
    assert mail.call_count == 2
    assert client.post('/cadastro/confirmar/' + token_from(mail), data={'confirmar': 'sim'}).status_code == 302
    assert client.get('/cadastro/completar').status_code == 200


def test_grant_cannot_change_tenant_and_resend_revokes_grant(app, mail):
    client = start_confirmation(app, mail)
    other = app.test_client()
    with client.session_transaction() as session:
        grant = dict(session['cadastro_completion'])
    with other.session_transaction() as session:
        session['cadastro_completion'] = {**grant, 'id': grant['id'] + 1}
    assert other.get('/cadastro/completar').status_code == 403
    row = CadastroPublico.query.one()
    row.proximo_envio_em = utcnow() - timedelta(minutes=1)
    db.session.commit()
    client.post('/cadastro/reenviar-confirmacao', data={'email': 'admin@example.com'})
    assert client.get('/cadastro/completar').status_code == 403


def test_completion_csrf(app, mail):
    client = start_confirmation(app, mail)
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/cadastro/completar', data={'senha': 'senha-valida', 'confirmar_senha': 'senha-valida'}).status_code == 400


def test_document_reference_no_original_pdf_published(app):
    root = Path(__file__).resolve().parents[1]
    assert (root / 'src/static/images/demo-proposta-logo.png').is_file()
    assert not list((root / 'src/static').rglob('proposta-2026-06D6CEE15C224544*'))
    assert app.test_client().get('/static/images/demo-proposta-logo.png').status_code == 200