from datetime import datetime, timezone
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class EnvioEmail(db.Model):
    __tablename__ = 'envios_email'

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    proposta_id = db.Column(db.Integer, db.ForeignKey('propostas.id'), index=True)
    destinatario = db.Column(db.String(120), nullable=False)
    assunto = db.Column(db.String(255))
    mensagem = db.Column(db.Text)
    status = db.Column(db.String(20), default='enviado')  # 'processando', 'enviado', 'falha'
    data_envio = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f'<EnvioEmail {self.destinatario} - {self.status}>'
