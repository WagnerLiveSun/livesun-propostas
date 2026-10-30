from datetime import datetime, timezone
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Empresa(db.Model):
    __tablename__ = 'empresas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    razao_social = db.Column(db.String(150))
    cnpj_cpf = db.Column(db.String(18))
    endereco = db.Column(db.String(255))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    logo = db.Column(db.String(255))
    usuarios_maximos = db.Column(db.Integer, default=3)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=_utcnow)

    # Relationships
    usuarios = db.relationship('Usuario', backref='empresa', lazy='dynamic')
    clientes = db.relationship('Cliente', backref='empresa', lazy='dynamic')
    produtos_servicos = db.relationship('ProdutoServico', backref='empresa', lazy='dynamic')
    propostas = db.relationship('Proposta', backref='empresa', lazy='dynamic')

    def __repr__(self):
        return f'<Empresa {self.nome}>'
