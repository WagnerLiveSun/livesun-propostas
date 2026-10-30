from datetime import datetime, timezone
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Proposta(db.Model):
    __tablename__ = 'propostas'
    __table_args__ = (db.UniqueConstraint('empresa_id', 'numero', name='uq_proposta_empresa_numero'),)

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), index=True)
    cliente_nome = db.Column(db.String(150), nullable=False)
    cliente_telefone = db.Column(db.String(20), nullable=False)
    cliente_cnpj_cpf = db.Column(db.String(18))
    cliente_email = db.Column(db.String(120))
    cliente_contato = db.Column(db.String(150))
    cliente_endereco = db.Column(db.String(255))
    aprovado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    aprovado_em = db.Column(db.DateTime)
    numero = db.Column(db.String(50), nullable=False)
    data_emissao = db.Column(db.Date, nullable=False)
    validade = db.Column(db.Date)
    status = db.Column(db.String(20), default='rascunho')  # 'rascunho', 'enviada', 'pendente', 'aceita', 'rejeitada'
    subtotal = db.Column(db.Numeric(15, 2), default=0)
    desconto = db.Column(db.Numeric(15, 2), default=0)
    impostos = db.Column(db.Numeric(15, 2), default=0)
    outros_acrescimos = db.Column(db.Numeric(15, 2), default=0)
    total = db.Column(db.Numeric(15, 2), default=0)
    total_extenso = db.Column(db.String(500))
    observacoes = db.Column(db.Text)
    condicao_pagamento = db.Column(db.String(500))
    data_criacao = db.Column(db.DateTime, default=_utcnow)
    data_atualizacao = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    itens = db.relationship('PropostaItem', backref='proposta', lazy='dynamic', cascade='all, delete-orphan')
    envios = db.relationship('EnvioEmail', backref='proposta', lazy='dynamic')

    def __repr__(self):
        return f'<Proposta {self.numero}>'
