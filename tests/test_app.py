import hashlib
import io
import tempfile
import unittest
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from PIL import Image
from src.app import create_app
from src.extensions import db
from src.models import Empresa, Usuario, Cliente, Proposta, Auditoria, EnvioEmail
from src.services.money import numero_por_extenso, decimal_value


class AppTests(unittest.TestCase):
    def setUp(self):
        self.uploads = tempfile.TemporaryDirectory()
        self.app = create_app('testing', {'UPLOAD_FOLDER': self.uploads.name})
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        first, second = Empresa(nome='Empresa A'), Empresa(nome='Empresa B')
        db.session.add_all([first, second])
        db.session.flush()
        self.company = first.id
        self.other = second.id
        self.users = {}
        for name, role, company in [('admin','admin',first.id),('viewer','visualizador',first.id),('other','admin',second.id)]:
            user = Usuario(nome=name, usuario=name, email=name+'@example.com', empresa_id=company, perfil=role)
            user.set_password('senha1234')
            db.session.add(user)
            db.session.flush()
            self.users[name] = user.id
        customer = Cliente(empresa_id=second.id, nome='SEGREDO OUTRA EMPRESA', telefone='11999999999')
        db.session.add(customer)
        db.session.commit()
        self.foreign_customer = customer.id
        self.client = self.app.test_client()
        self.login()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        self.uploads.cleanup()

    def login(self, name='admin'):
        return self.client.post('/auth/login', data={'usuario': name, 'senha': 'senha1234'})

    def payload(self, **changes):
        data = {'cliente_nome':'Cliente livre', 'cliente_telefone':'11912345678', 'cliente_email':'cliente@example.com',
                'data_emissao':'2026-10-30', 'validade':'2026-11-30', 'codigo[]':['A'], 'descricao[]':['Serviço de instalação'],
                'quantidade[]':['2.500'], 'unidade[]':['UN'], 'valor_unitario[]':['10.01'],
                'desconto':'1.00', 'impostos':'2', 'outros_acrescimos':'3', 'observacoes':'Condição especial'}
        data.update(changes)
        return data

    def create_proposal(self):
        response = self.client.post('/propostas/nova', data=self.payload())
        self.assertEqual(response.status_code, 302)
        return Proposta.query.order_by(Proposta.id.desc()).first()

    def test_authenticated_pages_and_templates(self):
        for path in ['/', '/clientes', '/clientes/novo', '/itens', '/itens/novo', '/empresa', '/usuarios', '/auth/perfil', '/propostas/', '/propostas/nova', '/suporte']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(b'SEGREDO OUTRA EMPRESA', response.data)

    def test_health_check(self):
        from sqlalchemy.exc import OperationalError
        self.client.post('/auth/logout')
        response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'ok'})
        with patch.object(db.session, 'execute', side_effect=OperationalError('SELECT 1', {}, Exception('private'))):
            response = self.client.get('/healthz')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json, {'status': 'unavailable'})
            self.assertNotIn(b'private', response.data)

    def test_official_developer_logo(self):
        response = self.client.get('/static/images/logo.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        self.assertTrue(response.data.startswith(b'\x89PNG'))
        response.close()
        self.assertIn(b'/static/images/logo.png', self.client.get('/').data)
        self.client.post('/auth/logout')
        login = self.client.get('/auth/login')
        self.assertIn(b'class="login-logo"', login.data)
        self.assertIn(b'alt="LiveSun Tecnologia"', login.data)
        self.assertIn(b'<h2 class="mb-2">Propostas Comerciais</h2>', login.data)
        self.assertNotIn(b'<h2 class="mb-2">LiveSun - Propostas</h2>', login.data)

    def test_footer_copyright_and_support(self):
        for path in ['/', '/auth/login']:
            if path == '/auth/login':
                self.client.post('/auth/logout')
            html = self.client.get(path).get_data(as_text=True)
            footer = re.search(r'<footer.*?</footer>', html, re.S).group()
            self.assertIn('© 2026 LiveSun', footer)
            self.assertIn('href="mailto:suporte@livesun.com.br"', footer)
            self.assertIn('>suporte@livesun.com.br</a>', footer)
            self.assertNotIn('Sistema independente', footer)

    def test_left_sidebar_and_role_navigation(self):
        html = self.client.get('/clientes/novo').get_data(as_text=True)
        sidebar = re.search(r'<aside.*?</aside>', html, re.S).group()
        self.assertIn('id="sidebar"', sidebar)
        self.assertIn('href="/clientes" class="sidebar-link active" aria-current="page"', sidebar)
        self.assertIn('href="/usuarios"', sidebar)
        self.assertIn('href="/empresa"', sidebar)
        self.assertNotIn('action="/auth/logout"', sidebar)
        header = re.search(r'<header.*?</header>', html, re.S).group()
        self.assertNotIn('href="/clientes"', header)
        self.assertIn('action="/auth/logout"', header)
        self.assertIn('id="theme-toggle"', header)
        self.assertNotIn('id="sidebar-toggle"', header)
        self.assertEqual(len(re.findall(r'<button\b', header)), 2)
        self.assertIn('aria-controls="sidebar"', html)
        self.assertIn('<div class="app-content">', html)
        self.client.post('/auth/logout')
        login = self.client.get('/auth/login').get_data(as_text=True)
        self.assertNotIn('<aside', login)
        self.assertNotIn('id="sidebar-toggle"', login)
        self.login('viewer')
        html = self.client.get('/').get_data(as_text=True)
        sidebar = re.search(r'<aside.*?</aside>', html, re.S).group()
        self.assertNotIn('href="/usuarios"', sidebar)
        self.assertNotIn('href="/empresa"', sidebar)
        self.assertIn('href="/propostas/"', sidebar)

    def test_logo_url_changes_when_file_is_replaced(self):
        original_folder = self.app.static_folder
        with tempfile.TemporaryDirectory() as folder:
            images = Path(folder) / 'images'
            images.mkdir()
            css = Path(folder) / 'css'
            css.mkdir()
            (css / 'style.css').write_text('', encoding='utf-8')
            logo = images / 'logo.png'
            try:
                self.app.static_folder = folder
                logo.write_bytes(b'first-logo')
                first = self.client.get('/auth/perfil').get_data(as_text=True)
                first_url = re.search(r'/static/images/logo\.png\?v=[a-f0-9]+', first).group()
                self.assertEqual(first.count(first_url), 2)
                logo.write_bytes(b'updated-logo')
                updated = self.client.get('/auth/perfil').get_data(as_text=True)
                updated_url = re.search(r'/static/images/logo\.png\?v=[a-f0-9]+', updated).group()
                self.assertNotEqual(first_url, updated_url)
                response = self.client.get(updated_url)
                self.assertEqual(response.data, b'updated-logo')
                response.close()
            finally:
                self.app.static_folder = original_folder

    def test_logo_background_is_transparent_and_css_is_versioned(self):
        response = self.client.get('/auth/perfil')
        html = response.get_data(as_text=True)
        css_url = re.search(r'/static/css/style\.css\?v=[a-f0-9]+', html).group()
        stylesheet = self.client.get(css_url)
        self.assertEqual(stylesheet.status_code, 200)
        rule = re.search(r'\.developer-logo,\.login-logo,\.footer-logo\{([^}]+)\}',
                         stylesheet.get_data(as_text=True)).group(1)
        self.assertIn('background:transparent', rule)
        self.assertNotIn('background:#000', rule)
        stylesheet.close()

    def test_print_pdf_pagination(self):
        from src.services.pdf import generate_pdf
        from src.models import PropostaItem
        p = self.create_proposal()
        p.itens.append(PropostaItem(sequencial=2, codigo='B', descricao='Segundo item', quantidade=1,
                                   unidade='UN', valor_unitario=10, valor_total=10))
        p.observacoes = 'Uma linha de observações.'
        db.session.commit()
        response = self.client.get(f'/propostas/{p.id}/imprimir')
        self.assertEqual(response.mimetype, 'text/html')
        html = response.get_data(as_text=True)
        document = re.search(r'<article class="document">.*?</article>', html, re.S).group()
        self.assertIn('<table class="table">', document)
        self.assertIn('<th>Descrição</th>', document)
        self.assertIn('Segundo item', document)
        self.assertIn('Uma linha de observações.', document)
        self.assertNotIn('admin', document)
        self.assertIn('counter(page)', html)
        self.assertIn('counter(pages)', html)
        self.assertIn('min-height: 0 !important', html)
        self.assertIn('overflow: visible !important', html)
        self.assertIn('window.print()', html)
        self.assertIn(p.numero, html)
        short_pdf = self.client.get(f'/propostas/{p.id}/pdf')
        self.assertEqual(short_pdf.status_code, 200)
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', short_pdf.data)), 1)
        for i in range(3, 83):
            p.itens.append(PropostaItem(sequencial=i, descricao=f'Item adicional {i}', quantidade=1,
                                       valor_unitario=1, valor_total=1))
        db.session.commit()
        html = self.client.get(f'/propostas/{p.id}/imprimir').get_data(as_text=True)
        self.assertIn('Item adicional 82', html)
        self.assertIn('display: table-header-group', html)
        pdf = generate_pdf(p)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(re.findall(rb'/Type\s*/Page\b', pdf)), 1)

    def test_payment_terms_saved_printed_and_replicated(self):
        response = self.client.post('/propostas/nova', data=self.payload(condicao_pagamento='50% na aprovação e 50% na entrega'))
        self.assertEqual(response.status_code, 302)
        p = Proposta.query.order_by(Proposta.id.desc()).first()
        self.assertEqual(p.condicao_pagamento, '50% na aprovação e 50% na entrega')
        for suffix in ['', '/imprimir', '/editar']:
            html = self.client.get(f'/propostas/{p.id}{suffix}').get_data(as_text=True)
            self.assertIn(p.condicao_pagamento, html)
            if suffix != '/editar':
                self.assertIn(f'Valor Total da proposta de: ({p.total_extenso})', html)
        from src.services.pdf import render_pdf_html
        with self.app.test_request_context('/'):
            pdf_html = render_pdf_html(p)
        self.assertIn(p.condicao_pagamento, pdf_html)
        self.assertIn(f'Valor Total da proposta de: ({p.total_extenso})', pdf_html)
        self.assertIn('<table class="table">', pdf_html)
        self.assertNotIn('<script', pdf_html)
        self.assertNotIn('<link', pdf_html)
        pdf = self.client.get(f'/propostas/{p.id}/pdf').data
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.client.post(f'/propostas/{p.id}/replicar')
        copy = Proposta.query.order_by(Proposta.id.desc()).first()
        self.assertEqual(copy.condicao_pagamento, p.condicao_pagamento)
        response = self.client.post('/propostas/nova', data=self.payload(condicao_pagamento='X'*501))
        self.assertEqual(response.status_code, 400)

    def test_proposal_full_lifecycle(self):
        p = self.create_proposal()
        self.assertEqual(p.total, Decimal('29.03'))
        self.assertEqual(Cliente.query.filter_by(empresa_id=self.company).count(), 0)
        for suffix in ['', '/editar', '/imprimir']:
            self.assertEqual(self.client.get(f'/propostas/{p.id}{suffix}').status_code, 200)
        pdf = self.client.get(f'/propostas/{p.id}/pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b'%PDF'))
        response = self.client.post(f'/propostas/{p.id}/status', data={'status':'aceita'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(p.status, 'aceita')
        self.assertIsNotNone(p.aprovado_em)
        self.assertEqual(p.aprovado_por, self.users['admin'])
        self.assertEqual(p.cliente.nome, 'Cliente livre')
        self.assertEqual(self.client.post(f'/propostas/{p.id}/editar', data=self.payload()).status_code, 409)
        self.assertEqual(self.client.post(f'/propostas/{p.id}/status', data={'status':'rejeitada'}).status_code, 409)
        original_id, number = p.id, p.numero
        self.assertEqual(self.client.post(f'/propostas/{p.id}/replicar').status_code, 302)
        copy = Proposta.query.order_by(Proposta.id.desc()).first()
        self.assertNotEqual(copy.numero, number)
        self.assertEqual(copy.status, 'rascunho')
        self.assertEqual(copy.total, p.total)
        self.assertEqual(copy.itens.first().descricao, p.itens.first().descricao)
        self.assertFalse(copy.cliente_nome)
        self.assertIsNone(copy.cliente_id)
        self.assertEqual(db.session.get(Proposta, original_id).status, 'aceita')
        self.assertGreaterEqual(Auditoria.query.filter_by(empresa_id=self.company).count(), 3)

    def test_tenant_boundaries_and_viewer(self):
        p = self.create_proposal()
        self.client.post('/auth/logout')
        self.login('other')
        for suffix in ['', '/editar', '/pdf', '/imprimir']:
            self.assertEqual(self.client.get(f'/propostas/{p.id}{suffix}').status_code, 404)
        for suffix in ['/replicar', '/status', '/enviar']:
            self.assertEqual(self.client.post(f'/propostas/{p.id}{suffix}').status_code, 404)
        self.client.post('/auth/logout')
        self.login('viewer')
        for path in ['/propostas/nova', '/clientes/novo', '/itens/novo', '/empresa', '/usuarios']:
            self.assertEqual(self.client.post(path, data=self.payload()).status_code, 403)
        self.assertEqual(self.client.get(f'/propostas/{p.id}').status_code, 200)
        self.assertEqual(self.client.post(f'/propostas/{p.id}/status', data={'status':'aceita'}).status_code, 403)

    def test_validation_does_not_persist(self):
        for changes in [{'cliente_nome':''}, {'quantidade[]':['0']}, {'valor_unitario[]':['NaN']},
                        {'desconto':'100000'}, {'cliente_id':str(self.foreign_customer)},
                        {'validade':'2020-01-01'}, {'descricao[]':['']}]:
            with self.subTest(changes=changes):
                response = self.client.post('/propostas/nova', data=self.payload(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Proposta.query.count(), 0)

    def test_edit_replaces_items_and_approval_updates_customer(self):
        p = self.create_proposal()
        self.assertEqual(self.client.post(f'/propostas/{p.id}/editar', data=self.payload(**{'descricao[]':['Novo serviço']})).status_code, 302)
        self.assertEqual(p.itens.count(), 1)
        self.assertEqual(p.itens.first().descricao, 'Novo serviço')
        self.client.post(f'/propostas/{p.id}/status', data={'status':'aceita'})
        customer_id = p.cliente_id
        other = self.client.post('/propostas/nova', data=self.payload(cliente_id=str(customer_id), cliente_nome='Nome atualizado'))
        self.assertEqual(other.status_code, 302)
        new = Proposta.query.order_by(Proposta.id.desc()).first()
        self.client.post(f'/propostas/{new.id}/status', data={'status':'aceita'})
        self.assertEqual(Cliente.query.filter_by(empresa_id=self.company).count(), 1)
        self.assertEqual(db.session.get(Cliente, customer_id).nome, 'Nome atualizado')
        self.assertEqual(p.cliente_nome, 'Cliente livre')

    def test_email_history_and_final_status(self):
        p = self.create_proposal()
        data = {'destinatario':'cliente@example.com', 'assunto':'Proposta', 'mensagem':'<script>teste</script>'}
        with patch('src.services.brevo.brevo_service.send_transactional_email', return_value=True) as send:
            self.assertEqual(self.client.post(f'/propostas/{p.id}/enviar', data=data).status_code, 302)
            self.assertTrue(send.call_args.kwargs['attachment']['content'].startswith(b'%PDF'))
            self.assertIn('&lt;script&gt;', send.call_args.args[3])
        self.assertEqual(p.status, 'enviada')
        self.client.post(f'/propostas/{p.id}/status', data={'status':'aceita'})
        with patch('src.services.brevo.brevo_service.send_transactional_email', return_value=False):
            self.client.post(f'/propostas/{p.id}/enviar', data=data)
        self.assertEqual(p.status, 'aceita')
        self.assertEqual([e.status for e in EnvioEmail.query.order_by(EnvioEmail.id)], ['enviado','falha'])

    def test_pdf_download_and_email_use_same_generator(self):
        p = self.create_proposal()
        pdf = b'%PDF-shared-print-layout'
        with patch('src.routes.propostas.generate_pdf', return_value=pdf) as generator:
            response = self.client.get(f'/propostas/{p.id}/pdf')
            self.assertEqual(response.data, pdf)
            with patch('src.services.brevo.brevo_service.send_transactional_email', return_value=True) as send:
                self.client.post(f'/propostas/{p.id}/enviar', data={'destinatario':'client@example.com', 'assunto':'Proposta'})
                self.assertEqual(send.call_args.kwargs['attachment']['content'], response.data)
            self.assertEqual(generator.call_count, 2)

    def test_missing_pdf_browser_does_not_send_email(self):
        from src.services.pdf import PDFGenerationError
        p = self.create_proposal()
        with patch('src.routes.propostas.generate_pdf', side_effect=PDFGenerationError('Navegador indisponível')):
            with patch('src.services.brevo.brevo_service.send_transactional_email') as send:
                response = self.client.post(f'/propostas/{p.id}/enviar', data={'destinatario':'client@example.com','assunto':'Proposta'})
                self.assertEqual(response.status_code, 302)
                send.assert_not_called()

    def test_password_reset_single_use_and_expiry(self):
        self.client.post('/auth/logout')
        with patch('src.services.brevo.brevo_service.send_reset_password_email', return_value=True) as send:
            self.client.post('/auth/forgot_password', data={'email':'admin@example.com'})
            link = send.call_args.args[2]
        token = link.rsplit('/',1)[1]
        user = db.session.get(Usuario, self.users['admin'])
        self.assertNotEqual(user.reset_token_hash, token)
        self.assertEqual(self.client.get('/auth/reset_password/'+token).status_code, 200)
        self.client.post('/auth/reset_password/'+token, data={'nova_senha':'novasenha123','confirmar_senha':'novasenha123'})
        self.assertTrue(user.check_password('novasenha123'))
        self.assertIsNone(user.reset_token_hash)
        self.assertEqual(self.client.get('/auth/reset_password/'+token).status_code, 302)
        user.reset_token_hash = hashlib.sha256(b'expired').hexdigest()
        user.reset_expira_em = datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)
        db.session.commit()
        self.assertEqual(self.client.get('/auth/reset_password/expired').status_code, 302)
        self.assertEqual(self.client.get('/auth/reset_password/arbitrary').status_code, 302)

    def test_email_login_and_disabled_user(self):
        self.client.post('/auth/logout')
        self.assertEqual(self.login('admin@example.com').status_code, 302)
        user = db.session.get(Usuario, self.users['admin'])
        user.ativo = False
        db.session.commit()
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_catalog_and_logo(self):
        self.assertEqual(self.client.post('/clientes/novo', data={'nome':'Cliente','telefone':'123','ativo':'on'}).status_code, 302)
        self.assertEqual(self.client.post('/itens/novo', data={'descricao':'Produto','tipo':'P','valor_unitario':'19.90','ativo':'on'}).status_code, 302)
        image = io.BytesIO()
        Image.new('RGB',(100,100),'blue').save(image,format='PNG')
        image.seek(0)
        response = self.client.post('/empresa', data={'nome':'Empresa A','logo':(image,'logo.png')}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        response = self.client.get('/empresa/logo')
        self.assertEqual(response.status_code, 200)
        response.close()
        p = self.create_proposal()
        self.assertTrue(self.client.get(f'/propostas/{p.id}/pdf').data.startswith(b'%PDF'))

    def test_user_limit_and_email_scope(self):
        data = {'nome':'Novo','usuario':'novo','email':'other@example.com','senha':'senha1234','perfil':'operador'}
        self.client.post('/usuarios',data=data)
        self.assertEqual(Usuario.query.filter_by(empresa_id=self.company).count(), 3)
        data['usuario']='quarto'
        data['email']='quarto@example.com'
        self.client.post('/usuarios',data=data)
        self.assertEqual(Usuario.query.filter_by(empresa_id=self.company).count(), 3)

    def test_dashboard_filters(self):
        p = self.create_proposal()
        response = self.client.get('/?inicio=2026-10-01&fim=2026-10-31&status=rascunho')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'29,03',response.data)
        self.assertNotIn(b'29,03',self.client.get('/?inicio=2027-01-01').data)
        self.assertEqual(self.client.get('/?inicio=invalid').status_code,400)

    def test_csrf_protection(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/clientes/novo',data={'nome':'Teste','telefone':'1'}).status_code,400)
        self.assertEqual(self.client.get('/auth/logout').status_code,405)

    def test_money(self):
        self.assertEqual(numero_por_extenso('101'),'cento e um reais')
        self.assertEqual(numero_por_extenso('1000000'),'um milhão de reais')
        self.assertEqual(numero_por_extenso('1.999'),'dois reais')
        self.assertEqual(numero_por_extenso('0.01'),'um centavo')
        self.assertEqual(decimal_value('1.234,56'),Decimal('1234.56'))
        for value in ['NaN','Infinity','-1','999999999999999']:
            with self.assertRaises(ValueError):
                decimal_value(value)

    def test_brevo_key_file_and_environment_priority(self):
        from config.config import brevo_api_key
        with tempfile.TemporaryDirectory() as folder:
            with patch('config.config.BASE_DIR', Path(folder)), patch.dict('os.environ', {'BREVO_API_KEY': ''}):
                self.assertEqual(brevo_api_key(), '')
                (Path(folder) / 'Key_Brevo.txt').write_text('Chave: xkeysib-test-local', encoding='utf-8-sig')
                self.assertEqual(brevo_api_key(), 'xkeysib-test-local')
                with patch.dict('os.environ', {'BREVO_API_KEY': 'environment-key'}):
                    self.assertEqual(brevo_api_key(), 'environment-key')

    def test_brevo_request_and_no_configuration(self):
        from src.services.brevo import brevo_service
        self.app.config.update(BREVO_API_KEY='', BREVO_SENDER_EMAIL='')
        with patch('src.services.brevo.requests.post') as post:
            self.assertFalse(brevo_service.send_transactional_email('a@example.com','A','Assunto','Texto'))
            post.assert_not_called()
        self.app.config.update(BREVO_API_KEY='test-key', BREVO_SENDER_EMAIL='sender@example.com')
        with patch('src.services.brevo.requests.post') as post:
            post.return_value.status_code = 201
            self.assertTrue(brevo_service.send_transactional_email('a@example.com','A','Assunto','Texto',attachment={'name':'p.pdf','content':b'%PDF'}))
            self.assertEqual(post.call_args.kwargs['json']['attachment'][0]['content'],'JVBERg==')
            self.assertEqual(post.call_args.kwargs['timeout'],30)

    def test_cli_admin(self):
        result = self.app.test_cli_runner().invoke(args=['criar-admin','--empresa','Conta CLI','--nome','Administrador',
            '--email','cli@example.com','--usuario','cli','--senha','senha1234'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertTrue(Usuario.query.filter_by(usuario='cli').one().check_password('senha1234'))


if __name__ == '__main__':
    unittest.main()