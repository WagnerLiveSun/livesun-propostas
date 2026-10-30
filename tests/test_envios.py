from unittest.mock import patch
from sqlalchemy.exc import OperationalError
import unittest
import test_app
from src.extensions import db
from src.models import EnvioEmail, Auditoria, Empresa
from src.services.envios import finish_delivery


class DeliveryTests(unittest.TestCase):
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    login = test_app.AppTests.login
    payload = test_app.AppTests.payload
    create_proposal = test_app.AppTests.create_proposal

    def test_missing_logo_does_not_block_email_or_embed_broken_image(self):
        from src.services.pdf import render_pdf_html
        p = self.create_proposal()
        company = db.session.get(Empresa, self.company)
        company.logo = 'missing-logo.png'
        db.session.commit()
        with self.app.test_request_context('/'):
            html = render_pdf_html(p)
        self.assertNotIn('class="company-logo"', html)
        self.assertIn('<table class="table">', html)
        with patch('src.routes.propostas.generate_pdf', return_value=b'%PDF-test'):
            with patch('src.services.brevo.brevo_service.send_transactional_email', return_value=True) as send:
                response = self.client.post(f'/propostas/{p.id}/enviar', data={'destinatario':'test@example.com','assunto':'Teste'})
                self.assertEqual(response.status_code, 302)
                send.assert_called_once()
                self.assertNotIn('/marca/', send.call_args.args[3])
        self.assertEqual(EnvioEmail.query.one().status, 'enviado')
        self.assertEqual(company.logo, 'missing-logo.png')
        with self.client.session_transaction() as session:
            self.assertTrue(any('sem logo' in message for category, message in session['_flashes']))

    def test_logo_path_does_not_allow_parent_directory(self):
        from src.services.pdf import company_logo_path
        company = db.session.get(Empresa, self.company)
        company.logo = '../private.png'
        self.assertIsNone(company_logo_path(company))
        company.logo = '..\\private.png'
        self.assertIsNone(company_logo_path(company))

    def test_network_calls_without_active_transaction(self):
        p = self.create_proposal()
        identifier = p.id

        def generate(html):
            self.assertIsInstance(html, str)
            self.assertFalse(db.session().in_transaction())
            return b'%PDF-test'

        def send(*args, **kwargs):
            self.assertFalse(db.session().in_transaction())
            return True

        with patch('src.routes.propostas.generate_pdf', side_effect=generate):
            with patch('src.services.brevo.brevo_service.send_transactional_email', side_effect=send) as api:
                result = self.client.post(f'/propostas/{identifier}/enviar', data={'destinatario':'test@example.com','assunto':'Teste'})
                self.assertEqual(result.status_code, 302)
                api.assert_called_once()
        self.assertEqual(EnvioEmail.query.one().status, 'enviado')

    def test_reconnect_does_not_duplicate_audit(self):
        p = self.create_proposal()
        delivery = EnvioEmail(empresa_id=self.company, proposta_id=p.id, destinatario='test@example.com', status='processando')
        db.session.add(delivery)
        db.session.commit()
        identifier = delivery.id
        commit = db.session.commit
        calls = []

        def fail_once():
            calls.append(1)
            if len(calls) == 1:
                raise OperationalError('INSERT', {}, Exception('connection lost'), connection_invalidated=True)
            return commit()

        with patch.object(db.session, 'commit', side_effect=fail_once):
            self.assertTrue(finish_delivery(identifier, self.company, self.users['admin'], True))
        self.assertTrue(finish_delivery(identifier, self.company, self.users['admin'], True))
        self.assertEqual(Auditoria.query.filter_by(acao='enviar_proposta').count(), 1)
        self.assertEqual(EnvioEmail.query.one().status, 'enviado')

    def test_saved_result_failure_warns_without_resending(self):
        p = self.create_proposal()
        with patch('src.routes.propostas.generate_pdf', return_value=b'%PDF-test'):
            with patch('src.services.brevo.brevo_service.send_transactional_email', return_value=True) as api:
                with patch('src.routes.propostas.finish_delivery', return_value=False):
                    result = self.client.post(f'/propostas/{p.id}/enviar', data={'destinatario':'test@example.com','assunto':'Teste'})
                    self.assertEqual(result.status_code, 302)
                    api.assert_called_once()
        with self.client.session_transaction() as session:
            self.assertTrue(any('Não reenvie' in message for category, message in session['_flashes']))

    def test_persistent_disconnect_retains_processing_record(self):
        p = self.create_proposal()
        delivery = EnvioEmail(empresa_id=self.company, proposta_id=p.id, destinatario='test@example.com', status='processando')
        db.session.add(delivery)
        db.session.commit()
        identifier = delivery.id
        with patch.object(db.session, 'commit', side_effect=OperationalError('INSERT', {}, Exception('disconnect'))):
            self.assertFalse(finish_delivery(identifier, self.company, self.users['admin'], True))
        self.assertEqual(EnvioEmail.query.one().status, 'processando')