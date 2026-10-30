from functools import wraps
from flask import abort
from flask_login import current_user, login_required
from src.extensions import db
from src.models import Auditoria


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.perfil not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def owned(model, identifier):
    return model.query.filter_by(id=identifier, empresa_id=current_user.empresa_id).first_or_404()


def audit(action, entity, identifier):
    db.session.add(Auditoria(empresa_id=current_user.empresa_id, usuario_id=current_user.id,
                             acao=action, entidade=entity, entidade_id=identifier))