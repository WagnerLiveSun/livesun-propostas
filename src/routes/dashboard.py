from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from src.models import Proposta, Cliente
from src.services.propostas import STATUSES

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    from src.routes.propostas import filtered_query
    query = filtered_query()
    counts = dict(query.with_entities(Proposta.status, func.count(Proposta.id)).group_by(Proposta.status).all())
    total = query.with_entities(func.coalesce(func.sum(Proposta.total), 0)).scalar()
    accepted = query.filter_by(status='aceita').with_entities(func.coalesce(func.sum(Proposta.total), 0)).scalar()
    customers = Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.nome).all()
    return render_template('dashboard.html', counts=counts, total=total, accepted=accepted,
                           total_propostas=sum(counts.values()), clientes=customers, statuses=STATUSES)