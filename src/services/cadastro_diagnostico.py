"""Diagnóstico agregado SELECT-only; não classifica contas automaticamente."""
from collections import Counter
from sqlalchemy import text
from src.services.identidades import email_key, document_key


def diagnose(connection):
    companies = list(connection.execute(text('SELECT id, cnpj_cpf, ativo FROM empresas')))
    users = list(connection.execute(text('SELECT id, email, ativo, usuario FROM usuarios')))
    emails = Counter(email_key(row.email) for row in users)
    documents = Counter(document_key(row.cnpj_cpf) for row in companies if document_key(row.cnpj_cpf))
    from src.services.cadastro import valid_document
    return {'empresas': len(companies), 'empresas_ativas': sum(bool(row.ativo) for row in companies),
        'usuarios': len(users), 'usuarios_ativos': sum(bool(row.ativo) for row in users),
        'grupos_email_duplicado': sum(n > 1 for n in emails.values()),
        'emails_ausentes': emails.get('', 0),
        'grupos_documento_duplicado': sum(n > 1 for n in documents.values()),
        'empresas_sem_documento': sum(not document_key(row.cnpj_cpf) for row in companies),
        'documentos_invalidos': sum(bool(document_key(row.cnpj_cpf)) and not valid_document(
            row.cnpj_cpf, 'PF' if len(document_key(row.cnpj_cpf)) == 11 else 'PJ') for row in companies),
        'possivel_usuario_demo_ativo': any(row.usuario == 'livesun' and row.ativo for row in users),
        'classificacao': 'REVISAO_HUMANA_OBRIGATORIA'}