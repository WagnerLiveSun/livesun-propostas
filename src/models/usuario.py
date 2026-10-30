from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    __table_args__ = (db.UniqueConstraint('empresa_id', 'email', name='uq_usuario_empresa_email'),)

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    nome = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    usuario = db.Column(db.String(80), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), default='visualizador')  # 'admin', 'operador', 'visualizador'
    ativo = db.Column(db.Boolean, default=True)
    tema_preferido = db.Column(db.String(20), default='moonlight')  # 'bluemetal', 'moonlight'
    data_criacao = db.Column(db.DateTime, default=_utcnow)
    reset_token_hash = db.Column(db.String(64), index=True)
    reset_expira_em = db.Column(db.DateTime)

    @property
    def is_active(self):
        return self.ativo and self.empresa.ativo

    def set_password(self, password):
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.senha_hash, password)

    def __repr__(self):
        return f'<Usuario {self.usuario}>'
