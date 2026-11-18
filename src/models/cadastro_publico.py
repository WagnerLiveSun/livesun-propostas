"""Estado local de confirmação; não representa autorização comercial."""
from datetime import datetime, timezone
from src.extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CadastroPublico(db.Model):
    __tablename__ = 'cadastros_publicos'
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, unique=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, unique=True)
    tipo_pessoa = db.Column(db.String(2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='PENDENTE_EMAIL')
    token_hash = db.Column(db.String(64), unique=True)
    expira_em = db.Column(db.DateTime)
    confirmado_em = db.Column(db.DateTime)
    proximo_envio_em = db.Column(db.DateTime)
    termos_versao = db.Column(db.String(100), nullable=False)
    privacidade_versao = db.Column(db.String(100), nullable=False)
    aceite_em = db.Column(db.DateTime, nullable=False, default=utcnow)
    criado_em = db.Column(db.DateTime, nullable=False, default=utcnow)
    usuario = db.relationship('Usuario')


class TentativaConfirmacaoEmail(db.Model):
    __tablename__ = 'tentativas_confirmacao_email'
    id = db.Column(db.Integer, primary_key=True)
    cadastro_id = db.Column(db.Integer, db.ForeignKey('cadastros_publicos.id'), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default='INICIADA')
    criada_em = db.Column(db.DateTime, nullable=False, default=utcnow)
    concluida_em = db.Column(db.DateTime)