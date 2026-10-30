from datetime import datetime, timezone
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Auditoria(db.Model):
    __tablename__ = 'auditoria'

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), index=True)
    acao = db.Column(db.String(100), nullable=False)  # ex: 'criar_proposta', 'aprovar_proposta'
    entidade = db.Column(db.String(50), nullable=False)  # ex: 'proposta'
    entidade_id = db.Column(db.Integer)
    detalhes = db.Column(db.Text)
    data_hora = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f'<Auditoria {self.acao} - {self.entidade}>'
