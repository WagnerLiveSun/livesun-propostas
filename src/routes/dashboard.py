from flask import Blueprint, render_template, redirect, url_for, abort, g
from flask_login import login_required, current_user
from sqlalchemy import func
from src.models import Proposta, Cliente
from src.services.propostas import STATUSES
from src.extensions import db
from src.models.commercial_usage import WelcomePreference

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
    from src.services.commercial_usage import bypass, details, authorize
    from src.services.central_client import CommercialAccessError
    if not bypass():
        from src.models.central import CentralTenant
        commercial = g.commercial_state
        if commercial['usage'] is None:
            try:
                subscription_details = details(current_user.empresa_id, db.session.get(CentralTenant, current_user.empresa_id).payload)
                # A consulta pode ter recebido estado mais novo que o guard.
                authorize(current_user.empresa_id, 'dashboard.index', 'GET')
                commercial = g.commercial_state
                if commercial['usage'] is None:
                    commercial['usage'] = subscription_details
            except CommercialAccessError:
                # ATIVA é autorizada pelos entitlements; data ausente não é inventada.
                from src.models.central import CentralTenant
                current = db.session.get(CentralTenant, current_user.empresa_id)
                if not current or current.payload.get('status') != 'ATIVA' or not current.payload.get('acesso_produto'):
                    raise
                commercial['usage'] = None
        commercial['total_created'] = Proposta.query.filter_by(empresa_id=current_user.empresa_id).count()
        commercial['start'] = commercial['usage'].data_inicio if commercial['usage'] else None
    pref = db.session.get(WelcomePreference, current_user.id)
    return render_template('dashboard.html', welcome_visible=not pref or not pref.oculto, counts=counts, total=total, accepted=accepted,
                           total_propostas=sum(counts.values()), clientes=customers, statuses=STATUSES)


@dashboard_bp.post('/boas-vindas/ocultar')
@login_required
def hide_welcome():
    pref = db.session.get(WelcomePreference, current_user.id)
    if pref is None:
        pref = WelcomePreference(usuario_id=current_user.id, empresa_id=current_user.empresa_id)
        db.session.add(pref)
    if pref.empresa_id != current_user.empresa_id:
        abort(403)
    pref.oculto = True
    from src.core.security import audit
    audit('ocultar_boas_vindas', 'usuario', current_user.id)
    db.session.commit()
    return redirect(url_for('dashboard.index'))