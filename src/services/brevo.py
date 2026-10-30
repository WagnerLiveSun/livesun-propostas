import base64
import logging
import requests
from flask import current_app
from markupsafe import escape

logger = logging.getLogger(__name__)


class BrevoService:
    def send_reset_password_email(self, to_email, username, reset_url):
        return self.send_transactional_email(to_email, username, 'Recuperação de senha - LiveSun Propostas',
            f'<p>Olá, {escape(username)}.</p><p><a href="{escape(reset_url)}">Redefinir senha</a></p>'
            '<p>O link é válido por 30 minutos e pode ser usado uma única vez.</p>')

    def send_transactional_email(self, to_email, to_name, subject, html_content, attachment=None, cc=None):
        key = current_app.config.get('BREVO_API_KEY')
        sender = current_app.config.get('BREVO_SENDER_EMAIL')
        if not key or not sender:
            logger.warning('Brevo exclusivo do Propostas não configurado: chave e remetente são obrigatórios.')
            return False
        payload = {'sender': {'name': current_app.config['BREVO_SENDER_NAME'], 'email': sender},
                   'to': [{'email': to_email, 'name': to_name or to_email}],
                   'subject': subject, 'htmlContent': html_content}
        if cc:
            payload['cc'] = [{'email': cc}]
        if attachment:
            payload['attachment'] = [{'name': attachment['name'],
                                     'content': base64.b64encode(attachment['content']).decode('ascii')}]
        try:
            response = requests.post('https://api.brevo.com/v3/smtp/email',
                headers={'api-key': key, 'accept': 'application/json'}, json=payload, timeout=30)
            if response.status_code != 201:
                logger.warning('Brevo recusou o envio (HTTP %s).', response.status_code)
            return response.status_code == 201
        except requests.RequestException:
            logger.warning('Falha de comunicação com o Brevo.')
            return False


brevo_service = BrevoService()