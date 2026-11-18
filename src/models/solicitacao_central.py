"""Solicitação persistente; não representa vínculo ou assinatura local."""
from src.extensions import db
from src.models.cadastro_publico import utcnow


class SolicitacaoCentral(db.Model):
    __tablename__ = 'solicitacoes_central'
    id = db.Column(db.Integer, primary_key=True)
    cadastro_id = db.Column(db.Integer, db.ForeignKey('cadastros_publicos.id'), nullable=False, unique=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, unique=True)
    evento_id = db.Column(db.String(36), nullable=False, unique=True)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='PENDENTE')
    tentativas = db.Column(db.Integer, nullable=False, default=0)
    ultima_tentativa_em = db.Column(db.DateTime)
    proxima_tentativa_em = db.Column(db.DateTime)
    lease_id = db.Column(db.String(32))
    lease_ate = db.Column(db.DateTime)
    erro_categoria = db.Column(db.String(40))
    central_solicitacao_id = db.Column(db.Integer)
    criada_em = db.Column(db.DateTime, nullable=False, default=utcnow)
    recebida_em = db.Column(db.DateTime)