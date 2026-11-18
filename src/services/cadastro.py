"""Cadastro pendente e confirmação síncrona; nunca concede acesso comercial."""
import hashlib
import re
import secrets
from datetime import timedelta
from flask import current_app, render_template, url_for
from email_validator import validate_email, EmailNotValidError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.extensions import db
from src.models import Empresa, Usuario, Auditoria
from src.models.cadastro_publico import CadastroPublico, TentativaConfirmacaoEmail, utcnow
from src.services.identidades import email_key, document_key
from src.services.brevo import brevo_service


GENERIC_RESPONSE = ('Se os dados puderem ser utilizados, você receberá um e-mail com instruções. '
                    'Confira sua caixa de entrada e spam. Se necessário, solicite um novo link.')


def valid_document(value, person_type):
    if re.search(r'[^0-9./\-\s]', value or ''):
        return False
    digits = document_key(value) or ''
    size = 11 if person_type == 'PF' else 14
    if len(digits) != size or len(set(digits)) == 1:
        return False
    weights = ([list(range(10, 1, -1)), list(range(11, 1, -1))] if size == 11 else
               [[5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]])
    for offset, weight in enumerate(weights):
        remainder = sum(int(n) * w for n, w in zip(digits[:size-2+offset], weight)) % 11
        if int(digits[size-2+offset]) != (0 if remainder < 2 else 11-remainder):
            return False
    return True


def validate_form(form):
    limits = {'nome': 150, 'empresa': 150, 'email': 120, 'telefone': 20, 'documento': 18}
    data = {name: form.get(name, '').strip() for name in limits}
    if any(len(data[name]) > size for name, size in limits.items()):
        raise ValueError('Um dos campos excede o tamanho permitido.')
    data['tipo_pessoa'] = 'PF' if len(document_key(data['documento']) or '') == 11 else 'PJ'
    if not valid_document(data['documento'], data['tipo_pessoa']):
        raise ValueError('Informe um CPF ou CNPJ válido.')
    if not data['nome'] or not data['empresa']:
        raise ValueError('Informe seu nome completo e o nome da empresa ou atividade.')
    if not re.fullmatch(r'[+()0-9\s-]+', data['telefone']) or not 10 <= len(document_key(data['telefone']) or '') <= 15:
        raise ValueError('Informe telefone com DDD válido.')
    for field in ('email',):
        try:
            data[field] = email_key(validate_email(data[field], check_deliverability=False).normalized)
        except EmailNotValidError:
            raise ValueError('Informe um e-mail válido.') from None
        if len(data[field]) > 120:
            raise ValueError('O e-mail excede o tamanho permitido.')
    if form.get('aceite') != 'on':
        raise ValueError('É necessário aceitar os Termos de Uso e a Política de Privacidade.')
    data['documento'] = document_key(data['documento'])
    return data


def audit_registration(row, action):
    db.session.add(Auditoria(empresa_id=row.empresa_id, usuario_id=row.usuario_id,
        acao=action, entidade='cadastro_publico', entidade_id=row.id))


def issue_token(row):
    token = secrets.token_urlsafe(32)
    row.token_hash = hashlib.sha256(token.encode()).hexdigest()
    row.expira_em = utcnow() + timedelta(minutes=current_app.config['EMAIL_CONFIRMATION_TTL_MINUTES'])
    row.proximo_envio_em = utcnow() + timedelta(seconds=current_app.config['CONFIRMATION_RESEND_COOLDOWN_SECONDS'])
    attempt = TentativaConfirmacaoEmail(cadastro_id=row.id, status='INICIADA')
    db.session.add(attempt)
    audit_registration(row, 'solicitar_confirmacao_email')
    db.session.flush()
    return token, attempt.id


def send_confirmation(row_id, token, attempt_id):
    # Transação de criação já confirmada antes da chamada externa.
    row = db.session.get(CadastroPublico, row_id)
    user = row.usuario
    recipient, name = user.email, user.nome
    confirmation_url = current_app.config['PUBLIC_BASE_URL'].rstrip('/') + url_for('cadastro.confirmar', token=token)
    html = render_template('email/confirmacao_cadastro.html', nome=name, confirmation_url=confirmation_url,
        ttl=current_app.config['EMAIL_CONFIRMATION_TTL_MINUTES'])
    db.session.rollback()
    status = 'INDETERMINADA'
    try:
        accepted = brevo_service.send_transactional_email(recipient, name,
            'Confirme seu e-mail — LiveSun Propostas', html)
        # False inclui falha de comunicação: não presumir que é seguro repetir.
        status = 'ACEITA_BREVO' if accepted else 'NAO_CONFIRMADA'
    except Exception:
        current_app.logger.warning('{"event":"confirmation_email_uncertain"}')
    try:
        attempt = db.session.get(TentativaConfirmacaoEmail, attempt_id)
        attempt.status, attempt.concluida_em = status, utcnow()
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('{"event":"confirmation_result_not_persisted"}')


def register(data):
    # Constraints normalizadas também protegem contra concorrência e outras rotas ORM.
    if db.session.scalar(db.select(Usuario.id).where(or_(Usuario.email_normalizado == data['email'],
            db.func.lower(db.func.trim(Usuario.email)) == data['email']))):
        return
    if db.session.scalar(db.select(Empresa.id).where(Empresa.documento_normalizado == data['documento'])):
        return
    try:
        company = Empresa(nome=data['empresa'], cnpj_cpf=data['documento'],
            email=data['email'], telefone=data['telefone'], ativo=False)
        db.session.add(company)
        db.session.flush()
        user = Usuario(empresa_id=company.id, nome=data['nome'], email=data['email'],
            usuario='cad_' + secrets.token_hex(16), perfil='admin', ativo=False)
        # Não é senha padrão nem credencial utilizável: segredo descartado, conta inativa.
        user.set_password(secrets.token_urlsafe(48))
        db.session.add(user)
        db.session.flush()
        row = CadastroPublico(empresa_id=company.id, usuario_id=user.id, tipo_pessoa=data['tipo_pessoa'],
            termos_versao=current_app.config['TERMS_VERSION'], privacidade_versao=current_app.config['PRIVACY_VERSION'])
        db.session.add(row)
        db.session.flush()
        audit_registration(row, 'criar_conta_pendente')
        token, attempt_id = issue_token(row)
        row_id = row.id
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return
    send_confirmation(row_id, token, attempt_id)


def resend(email):
    row = db.session.scalar(db.select(CadastroPublico).join(Usuario, CadastroPublico.usuario_id == Usuario.id)
        .where(Usuario.email_normalizado == email_key(email),
               CadastroPublico.status.in_(['PENDENTE_EMAIL', 'EMAIL_CONFIRMADO']))
        .with_for_update())
    if row is None or (row.proximo_envio_em and row.proximo_envio_em > utcnow()):
        db.session.rollback()
        return
    token, attempt_id = issue_token(row)
    row_id = row.id
    db.session.commit()
    send_confirmation(row_id, token, attempt_id)


def confirm(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    # UPDATE condicional atômico garante uso único também em bancos sem row locks.
    row = db.session.scalar(db.select(CadastroPublico).where(CadastroPublico.token_hash == digest))
    if row is None or row.status not in ('PENDENTE_EMAIL', 'EMAIL_CONFIRMADO'):
        return False
    previous_status = row.status
    grant = secrets.token_urlsafe(32)
    changed = db.session.execute(db.update(CadastroPublico).where(CadastroPublico.id == row.id,
        CadastroPublico.token_hash == digest, CadastroPublico.status == previous_status,
        CadastroPublico.expira_em > utcnow()).values(
            token_hash=hashlib.sha256(grant.encode()).hexdigest(), expira_em=utcnow() + timedelta(minutes=15),
            confirmado_em=row.confirmado_em or utcnow(), status='EMAIL_CONFIRMADO'),
        execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        db.session.rollback()
        return False
    audit_registration(row, 'confirmar_email' if previous_status == 'PENDENTE_EMAIL' else 'renovar_conclusao_cadastro')
    db.session.commit()
    return {'id': row.id, 'secret': grant}


def completion_registration(grant):
    """Grant de escopo único, mantido no cookie HTTPOnly e verificado no banco."""
    if not isinstance(grant, dict) or type(grant.get('id')) is not int or not isinstance(grant.get('secret'), str):
        return None
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', grant['secret']):
        return None
    return db.session.scalar(db.select(CadastroPublico).where(CadastroPublico.id == grant['id'],
        CadastroPublico.token_hash == hashlib.sha256(grant['secret'].encode()).hexdigest(),
        CadastroPublico.status == 'EMAIL_CONFIRMADO', CadastroPublico.expira_em > utcnow()))


def complete(grant, form):
    row = completion_registration(grant)
    if row is None:
        raise ValueError('A autorização expirou. Solicite um novo link de confirmação.')
    password = form.get('senha', '')
    if not 8 <= len(password) <= 128 or not password.strip():
        raise ValueError('A senha deve ter de 8 a 128 caracteres.')
    if password != form.get('confirmar_senha', ''):
        raise ValueError('As senhas não coincidem.')
    changed = db.session.execute(db.update(CadastroPublico).where(CadastroPublico.id == row.id,
        CadastroPublico.status == 'EMAIL_CONFIRMADO', CadastroPublico.token_hash == row.token_hash,
        CadastroPublico.expira_em > utcnow()).values(status='PRONTO_ANALISE', token_hash=None, expira_em=None),
        execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        db.session.rollback()
        raise ValueError('A autorização expirou. Solicite um novo link de confirmação.')
    user = row.usuario
    user.set_password(password)
    user.ativo = True
    user.empresa.ativo = True
    user.empresa.razao_social_pendente = row.tipo_pessoa == 'PJ' and not (user.empresa.razao_social or '').strip()
    # Ativo local não representa acesso comercial; guard independente impede bypass.
    from src.services.cadastro_central import prepare
    prepare(row)
    audit_registration(row, 'completar_cadastro')
    identifier = row.id
    db.session.commit()
    return identifier