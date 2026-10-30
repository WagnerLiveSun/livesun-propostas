"""Persistência idempotente do resultado, sem repetir chamadas ao Brevo."""
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from flask import current_app
from src.extensions import db
from src.models import Proposta, EnvioEmail, Auditoria


def finish_delivery(delivery_id, company_id, user_id, successful):
    for attempt in range(2):
        try:
            delivery = EnvioEmail.query.filter_by(id=delivery_id, empresa_id=company_id).with_for_update().one()
            if delivery.status != 'processando':
                db.session.rollback()
                return True
            proposal = Proposta.query.filter_by(id=delivery.proposta_id, empresa_id=company_id).with_for_update().one()
            delivery.status = 'enviado' if successful else 'falha'
            if successful and proposal.status in ('rascunho', 'pendente'):
                proposal.status = 'enviada'
            db.session.add(Auditoria(empresa_id=company_id, usuario_id=user_id,
                acao='enviar_proposta' if successful else 'falha_envio_proposta',
                entidade='proposta', entidade_id=proposal.id))
            db.session.commit()
            return True
        except OperationalError:
            db.session.rollback()
            if attempt == 0:
                continue
        except SQLAlchemyError:
            db.session.rollback()
        break
    current_app.logger.error('Resultado do envio %s não persistido; aceito pelo Brevo=%s. Não reenviar automaticamente.',
                             delivery_id, successful)
    return False