from datetime import datetime, timezone
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    nome = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    cnpj_cpf = db.Column(db.String(18))
    email = db.Column(db.String(120))
    contato = db.Column(db.String(150))
    endereco = db.Column(db.String(255))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=_utcnow)

    # Relationships
    propostas = db.relationship('Proposta', backref='cliente', lazy='dynamic')

    def __repr__(self):
        return f'<Cliente {self.nome}>'
