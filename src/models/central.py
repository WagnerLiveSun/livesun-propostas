"""Dados exclusivos da integração; não modifica permissões do produto."""
from datetime import datetime, timezone
from src.extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CentralTenant(db.Model):
    __tablename__ = 'central_tenants'
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), primary_key=True)
    central_cliente_id = db.Column(db.Integer, nullable=False, unique=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    assinatura_id = db.Column(db.Integer, nullable=False, default=0)
    versao = db.Column(db.Integer, nullable=False, default=0)
    valido_ate = db.Column(db.DateTime)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=utcnow)


class CentralEventoRecebido(db.Model):
    __tablename__ = 'central_eventos_recebidos'
    evento_id = db.Column(db.String(50), primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=False)
    assinatura_id = db.Column(db.Integer, nullable=False)
    versao = db.Column(db.Integer, nullable=False)
    recebido_em = db.Column(db.DateTime, nullable=False, default=utcnow)