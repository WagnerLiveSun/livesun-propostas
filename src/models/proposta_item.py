from src.extensions import db


class PropostaItem(db.Model):
    __tablename__ = 'proposta_itens'

    id = db.Column(db.Integer, primary_key=True)
    proposta_id = db.Column(db.Integer, db.ForeignKey('propostas.id'), nullable=False, index=True)
    sequencial = db.Column(db.Integer)
    codigo = db.Column(db.String(50))
    descricao = db.Column(db.String(255), nullable=False)
    quantidade = db.Column(db.Numeric(10, 3), nullable=False)
    unidade = db.Column(db.String(20))
    valor_unitario = db.Column(db.Numeric(15, 2), nullable=False)
    valor_total = db.Column(db.Numeric(15, 2))

    def __repr__(self):
        return f'<PropostaItem {self.sequencial} - {self.descricao}>'
