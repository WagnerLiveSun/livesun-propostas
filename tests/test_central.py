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


class CentralIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app('testing', {'UPLOAD_FOLDER': self.folder.name,
            'CENTRAL_ENABLED': True, 'CENTRAL_API_TOKEN': 'test-only', 'CENTRAL_WEBHOOK_SECRET': 'h' * 40,
            'CENTRAL_BASE_URL': 'https://central.example.com', 'CENTRAL_ALLOW_LOCAL_HTTP': False})
        self.context = self.app.app_context()
        self.context.push()
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
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.folder.cleanup()

    def login(self):
        return self.client.post('/auth/login', data={'usuario': 'test', 'senha': 'password123'})

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

    def send(self, payload=None, event='evt_test', stamp=None, signature=None):
        entitlement = payload or self.payload
        data = {'evento': 'ASSINATURA_SUSPENSA', 'evento_id': event, 'cliente_id': '123',
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
        self.assertEqual(self.login().status_code, 403)
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

    def test_all_blocked_states_prevent_login(self):
        for version, status in enumerate(['SUSPENSA', 'BLOQUEADA', 'CANCELADA', 'EXPIRADA', 'EXCLUIDA'], start=2):
            with self.subTest(status=status):
                blocked = {**self.payload, 'status': status, 'acesso_produto': False, 'limites': {}, 'versao': version}
                self.assertEqual(self.send(blocked, event='evt_'+status).status_code, 200)
                self.assertEqual(self.login().status_code, 403)

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
            self.assertEqual(self.login().status_code, 403)
            self.assertTrue(get.call_args.args[0].startswith('http://127.0.0.1:5001/'))
        self.assertEqual(tenant.payload['status'], 'SUSPENSA')