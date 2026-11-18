"""Normalização compartilhada, sem consultas nem acesso à configuração privada."""
import re
from sqlalchemy import event


def email_key(value):
    return (value or '').strip().lower()


def document_key(value):
    return re.sub(r'[^0-9]', '', value or '') or None


def register_identity_events(company_model, user_model):
    def company_identity(mapper, connection, target):
        target.documento_normalizado = document_key(target.cnpj_cpf)

    def user_identity(mapper, connection, target):
        target.email_normalizado = email_key(target.email) or None

    for model, listener in ((company_model, company_identity), (user_model, user_identity)):
        event.listen(model, 'before_insert', listener)
        event.listen(model, 'before_update', listener)