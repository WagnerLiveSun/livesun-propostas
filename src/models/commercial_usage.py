"""Cache de datas do Central e consumo local; não é assinatura local."""
from src.extensions import db


class CommercialUsage(db.Model):
    __tablename__ = 'commercial_usage'
    __table_args__ = (db.UniqueConstraint('empresa_id', 'assinatura_id', name='uq_usage_empresa_assinatura'),)
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    assinatura_id = db.Column(db.Integer, nullable=False)
    versao = db.Column(db.Integer, nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    trial_ate = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    suspensa_inadimplencia = db.Column(db.Boolean, nullable=False, default=False)
    valido_ate = db.Column(db.DateTime, nullable=False)
    criadas = db.Column(db.Integer, nullable=False, default=0)
    inicializado = db.Column(db.Boolean, nullable=False, default=False)


class TrialProposal(db.Model):
    __tablename__ = 'trial_proposals'
    proposta_id = db.Column(db.Integer, db.ForeignKey('propostas.id'), primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    usage_id = db.Column(db.Integer, db.ForeignKey('commercial_usage.id'), primary_key=True)


class WelcomePreference(db.Model):
    __tablename__ = 'welcome_preferences'
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    oculto = db.Column(db.Boolean, nullable=False, default=False)