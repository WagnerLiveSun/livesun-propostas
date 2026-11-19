import hashlib
import hmac
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock
import requests
from src.app import create_app
from src.extensions import db
from src.models import Empresa, Usuario
from src.models.central import CentralTenant, CentralEventoRecebido
from src.services.central_client import CommercialAccessError


class CentralIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app('testing', {'UPLOAD_FOLDER': self.folder.name,
            'CENTRAL_ENABLED': True, 'CENTRAL_API_TOKEN': 'test-only', 'CENTRAL_WEBHOOK_SECRET': 'h' * 40,
            'CENTRAL_BASE_URL': 'https://central.example.com', 'CENTRAL_ALLOW_LOCAL_HTTP': False})
        self.context = self.app.app_context()
        self.context.push()
        self.details_patch = patch('src.services.commercial_usage.details',
            side_effect=CommercialAccessError('Detalhes indisponíveis no teste', 503))
        self.details_patch.start()
        db.create_all()
        company = Empresa(nome='Teste')
        db.session.add(company)
        db.session.flush()
        self.company_id = company.id
        user = Usuario(nome='Teste', usuario='test', email='test@example.com', empresa_id=company.id, perfil='admin')
        user.set_password('password123')
        db.session.add(user)
        self.payload = {'cliente_id': '123', 'produto': 'PROPOSTAS', 'assinatura_id': 10,
            'status': 'ATIVA', 'plano': 'PROPOSTAS', 'acesso_produto': True, 'modulos': [],
            'limites': {'usuarios': 3}, 'versao': 1,
            'gerado_em': datetime.now(timezone.utc).isoformat(),
            'valido_ate': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
        db.session.add(CentralTenant(empresa_id=company.id, central_cliente_id=123,
            payload=self.payload, assinatura_id=10, versao=1,
            valido_ate=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=15)))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.details_patch.stop()
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.folder.cleanup()

    def login(self):
        return self.client.post('/auth/login', data={'usuario': 'test', 'senha': 'password123'})

    def test_checkout_uses_authenticated_tenant_not_query_id(self):
        import base64
        from urllib.parse import urlsplit, parse_qs
        self.assertEqual(self.login().status_code, 302)
        response = self.client.get('/central/contratar?cliente_id=999')
        self.assertEqual(response.status_code, 302)
        target = urlsplit(response.location)
        self.assertEqual(target.hostname, 'central.example.com')
        self.assertEqual(target.path, '/contratar/propostas')
        encoded, signature = parse_qs(target.query)['token'][0].split('.')
        data = json.loads(base64.urlsafe_b64decode(encoded + '='*(-len(encoded)%4)))
        self.assertEqual(data['cliente_id'], 123)
        expected = hmac.new(('h'*40).encode(), ('checkout-propostas:'+encoded).encode(), hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(signature, expected))

    def test_checkout_anonymous_denied(self):
        response = self.client.get('/central/contratar')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.location)

    def test_paid_pending_webhook_does_not_activate_access(self):
        pending = {**self.payload, 'status': 'PAGO_AGUARDANDO_LIBERACAO', 'acesso_produto': False, 'versao': 2}
        self.assertEqual(self.send(pending, event='evt_paid', event_type='ASSINATURA_PAGO_AGUARDANDO_LIBERACAO').status_code, 200)
        self.assertFalse(db.session.get(CentralTenant, self.company_id).payload['acesso_produto'])

    def signed_request(self, method, path, data=None):
        raw = json.dumps(data).encode() if data is not None else path.encode()
        stamp = str(int(time.time()))
        digest = hmac.new(('h'*40).encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return self.client.open(path, method=method, data=raw if data is not None else None,
            content_type='application/json', headers={'X-LiveSun-Timestamp':stamp,
            'X-LiveSun-Signature':'sha256='+digest})

    def test_company_listing_signed_without_enabling_commercial_guard(self):
        self.app.config['CENTRAL_ENABLED'] = False
        company = db.session.get(Empresa, self.company_id)
        company.cnpj_cpf = '12.345.678/0001-90'
        db.session.commit()
        response = self.signed_request('GET', '/central/empresas?apos=0')
        self.assertEqual(response.status_code, 200)
        item = response.json['empresas'][0]
        self.assertEqual(item['dados']['cnpj_cpf'], '12345678000190')
        self.assertEqual(item['cliente_id'], 123)
        self.assertNotIn('senha_hash', response.get_data(as_text=True))
        self.assertEqual(self.client.get('/central/empresas').status_code, 401)
        self.assertEqual(self.signed_request('GET', '/central/empresas?apos=-1').status_code, 422)

    def test_company_binding_is_idempotent_and_cannot_reassign(self):
        self.app.config['CENTRAL_ENABLED'] = False
        db.session.get(Empresa, self.company_id).cnpj_cpf = '12345678000190'
        db.session.delete(db.session.get(CentralTenant, self.company_id))
        db.session.commit()
        detail = self.signed_request('GET', f'/central/empresas/{self.company_id}').json
        data = {'empresa_id':self.company_id, 'cliente_id':123, 'assinatura_id':10,
            'solicitacao_id':1, 'evento_id':detail['empresa']['dados']['evento_id'],
            'produto':'PROPOSTAS', 'status':'VINCULO_PENDENTE', 'entitlements':self.payload,
            'cnpj_cpf':'12345678000190'}
        self.assertEqual(self.signed_request('POST', '/central/cadastros/vincular', data).status_code, 200)
        self.assertEqual(self.signed_request('POST', '/central/cadastros/vincular', data).status_code, 200)
        self.assertEqual(CentralTenant.query.count(), 1)
        reassigned = {**data, 'cliente_id':999, 'entitlements':{**self.payload, 'cliente_id':'999'}}
        self.assertEqual(self.signed_request('POST', '/central/cadastros/vincular', reassigned).status_code, 409)
        self.assertEqual(db.session.get(CentralTenant, self.company_id).central_cliente_id, 123)
        wrong_document = {**data, 'cnpj_cpf':'99999999000199'}
        self.assertEqual(self.signed_request('POST', '/central/cadastros/vincular', wrong_document).status_code, 409)

    def test_company_binding_rejects_unsigned_and_other_product(self):
        self.assertEqual(self.client.post('/central/cadastros/vincular', json={}).status_code, 401)
        self.assertEqual(self.signed_request('POST', '/central/cadastros/vincular', {'produto':'COMERCIAL'}).status_code, 422)

    def test_company_listing_signature_covers_cursor(self):
        path = '/central/empresas?apos=0'
        stamp = str(int(time.time()))
        signature = hmac.new(('h'*40).encode(), stamp.encode()+b'.'+path.encode(), hashlib.sha256).hexdigest()
        response = self.client.get('/central/empresas?apos=1', headers={
            'X-LiveSun-Timestamp':stamp, 'X-LiveSun-Signature':'sha256='+signature})
        self.assertEqual(response.status_code, 401)

    def send(self, payload=None, event='evt_test', stamp=None, signature=None, event_type='ASSINATURA_SUSPENSA'):
        entitlement = payload or self.payload
        data = {'evento': event_type, 'evento_id': event, 'cliente_id': '123',
            'produto': 'PROPOSTAS', 'assinatura_id': entitlement['assinatura_id'],
            'versao': entitlement['versao'], 'status_novo': entitlement['status'], 'entitlements': entitlement}
        raw = json.dumps(data).encode()
        stamp = str(stamp or int(time.time()))
        digest = hmac.new(('h'*40).encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/assinatura', data=raw, content_type='application/json', headers={
            'X-LiveSun-Timestamp': stamp, 'X-LiveSun-Signature': signature or 'sha256='+digest,
            'X-LiveSun-Event': data['evento']})

    def test_login_suspension_and_reactivation(self):
        self.assertEqual(self.login().status_code, 302)
        blocked = {**self.payload, 'status': 'SUSPENSA', 'acesso_produto': False, 'limites': {}, 'versao': 2}
        self.assertEqual(self.send(blocked).status_code, 200)
        self.assertEqual(self.client.get('/').status_code, 403)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.send({**self.payload, 'versao': 3}, event='evt_active').status_code, 200)
        self.assertEqual(self.client.get('/auth/perfil').status_code, 200)

    def test_receiver_preflight_has_no_commercial_side_effect(self):
        data={'produto':'PROPOSTAS','nonce':'a'*64}
        raw=json.dumps(data).encode();stamp=str(int(time.time()))
        signature='sha256='+hmac.new(('h'*40).encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        response=self.client.post('/webhooks/assinatura',data=raw,content_type='application/json',headers={
            'X-LiveSun-Timestamp':stamp,'X-LiveSun-Signature':signature,'X-LiveSun-Event':'INTEGRACAO_TESTE'})
        self.assertEqual(response.status_code,200)
        proof=hmac.new(('h'*40).encode(),('PROPOSTAS:'+data['nonce']).encode(),hashlib.sha256).hexdigest()
        self.assertEqual(response.json['prova'],proof)
        self.assertEqual(CentralEventoRecebido.query.count(),0)

    def test_health_check_remains_available_for_blocked_session(self):
        self.assertEqual(self.login().status_code, 302)
        blocked = {**self.payload, 'status': 'SUSPENSA', 'acesso_produto': False, 'limites': {}, 'versao': 2}
        self.assertEqual(self.send(blocked).status_code, 200)
        self.assertEqual(self.client.get('/auth/perfil').status_code, 403)
        response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'ok'})

    def test_signature_replay_idempotency_and_order(self):
        self.assertEqual(self.send(signature='invalid').status_code, 401)
        self.assertEqual(self.send(stamp=int(time.time())-600).status_code, 401)
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(self.send().json['status'], 'duplicado')
        self.assertEqual(CentralEventoRecebido.query.count(), 1)
        self.assertEqual(self.send({**self.payload, 'versao': 5}, event='evt_new').status_code, 200)
        self.assertEqual(self.send({**self.payload, 'versao': 2}, event='evt_old').json['status'], 'obsoleto')
        self.assertEqual(db.session.get(CentralTenant, self.company_id).versao, 5)

    def test_offline_sensitive_fails_closed(self):
        tenant = db.session.get(CentralTenant, self.company_id)
        tenant.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)
        db.session.commit()
        with patch('requests.get', side_effect=requests.ConnectionError('secret-not-logged')):
            self.assertEqual(self.login().status_code, 503)

    def test_cache_refresh(self):
        tenant = db.session.get(CentralTenant, self.company_id)
        tenant.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)
        db.session.commit()
        response = Mock(status_code=200)
        response.json.return_value = {**self.payload, 'versao': 2}
        with patch('requests.get', return_value=response):
            self.assertEqual(self.login().status_code, 302)
        self.assertEqual(tenant.versao, 2)

    def test_unmapped_tenant(self):
        db.session.delete(db.session.get(CentralTenant, self.company_id))
        db.session.commit()
        self.assertEqual(self.login().status_code, 403)

    def test_restricted_states_allow_read_login_excluded_denies(self):
        for version, status in enumerate(['SUSPENSA', 'BLOQUEADA', 'CANCELADA', 'EXPIRADA', 'EXCLUIDA'], start=2):
            with self.subTest(status=status):
                blocked = {**self.payload, 'status': status, 'acesso_produto': False, 'limites': {}, 'versao': version}
                self.assertEqual(self.send(blocked, event='evt_'+status).status_code, 200)
                self.client.post('/auth/logout')
                response = self.login()
                self.assertEqual(response.status_code, 403 if status == 'EXCLUIDA' else 302)

    def test_blocked_access_uses_product_theme_and_support_contacts(self):
        self.assertEqual(self.login().status_code, 302)
        blocked = {**self.payload, 'status':'SUSPENSA', 'acesso_produto':False,
                   'limites':{}, 'versao':2}
        self.assertEqual(self.send(blocked).status_code, 200)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 403)
        html = response.get_data(as_text=True)
        self.assertIn('Vamos ajudar você a retomar o acesso', html)
        self.assertIn('mailto:suporte@livesun.com.br', html)
        self.assertIn('tel:+5571999990204', html)
        self.assertIn('71 99999-0204', html)
        self.assertIn('href="https://app.pipefy.com/public/form/ETeM9Gbz" target="_blank" rel="noopener noreferrer"', html)
        self.assertIn('Entrar em contato com o suporte', html)
        self.assertIn('ls-theme', html)
        self.assertNotIn('<aside', html)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/suporte').status_code, 200)
        self.assertEqual(self.client.post('/auth/logout').status_code, 302)

    def test_temporary_failure_shows_support_and_preserves_503(self):
        tenant = db.session.get(CentralTenant, self.company_id)
        tenant.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)
        db.session.commit()
        with patch('requests.get', side_effect=requests.Timeout):
            response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertIn('Estamos verificando seu acesso', response.get_data(as_text=True))
        self.assertEqual(response.headers['Retry-After'], '60')

    def test_blocked_json_request_is_not_replaced_by_html(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.send({**self.payload, 'status':'SUSPENSA',
            'acesso_produto':False, 'limites':{}, 'versao':2}).status_code, 200)
        response = self.client.get('/', headers={'Accept':'application/json'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['error'], 'acesso_comercial_indisponivel')

    def test_different_tenant_webhook_is_rejected(self):
        data = {**self.payload, 'cliente_id': '999'}
        self.assertEqual(self.send(data).status_code, 422)
        self.assertEqual(CentralEventoRecebido.query.count(), 0)

    def test_signed_reconciliation_state(self):
        path = '/central/estado/123'
        stamp = str(int(time.time()))
        digest = hmac.new(('h'*40).encode(), stamp.encode()+b'.'+path.encode(), hashlib.sha256).hexdigest()
        response = self.client.get(path, headers={'X-LiveSun-Timestamp': stamp, 'X-LiveSun-Signature': 'sha256='+digest})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['versao'], 1)
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_local_http_requires_explicit_opt_in(self):
        from src.services.central_client import validate_base_url
        with self.assertRaises(ValueError):
            validate_base_url('http://127.0.0.1:5001')
        self.app.config['CENTRAL_ALLOW_LOCAL_HTTP'] = True
        self.assertEqual(validate_base_url('http://127.0.0.1:5001'), 'http://127.0.0.1:5001')
        for url in ['http://192.168.1.1:5001', 'http://central.example.com',
                    'http://127.0.0.1.evil.example', 'http://user:secret@localhost:5001',
                    'http://localhost:5001?token=secret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_base_url(url)
        self.app.config['CENTRAL_RUNTIME_ENV'] = 'production'
        with self.assertRaises(ValueError):
            validate_base_url('http://127.0.0.1:5001')

    def test_refresh_over_local_http_and_enforce_block(self):
        self.app.config.update(CENTRAL_BASE_URL='http://127.0.0.1:5001', CENTRAL_ALLOW_LOCAL_HTTP=True)
        tenant = db.session.get(CentralTenant, self.company_id)
        tenant.valido_ate = datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)
        db.session.commit()
        response = Mock(status_code=200)
        response.json.return_value = {**self.payload, 'versao': 2, 'status': 'SUSPENSA',
                                      'acesso_produto': False, 'limites': {}}
        with patch('requests.get', return_value=response) as get:
            self.assertEqual(self.login().status_code, 302)
            self.assertTrue(get.call_args.args[0].startswith('http://127.0.0.1:5001/'))
        self.assertEqual(tenant.payload['status'], 'SUSPENSA')