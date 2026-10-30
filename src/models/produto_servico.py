from datetime import datetime, timezone
from src.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class ProdutoServico(db.Model):
    __tablename__ = 'produtos_servicos'

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    codigo = db.Column(db.String(50))
    descricao = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(1))  # 'P' = Produto, 'S' = Serviço
    unidade = db.Column(db.String(20))
    valor_unitario = db.Column(db.Numeric(15, 2))
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f'<ProdutoServico {self.descricao}>'
